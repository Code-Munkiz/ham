"""
Read-only chat-first conductor preview — POST /api/coding/conductor/preview.

Phase 2A. The conductor classifies the user's prompt, snapshots provider
readiness, and returns a ranked list of provider candidates with a single
``chosen`` recommendation. **It does not launch any provider.** Provider
launches stay with their existing routes (Cursor missions,
``/api/droid/preview`` + ``/launch``, ``/api/droid/build/preview`` +
``/launch``); each provider keeps its own safety contract there.

Hard guarantees (locked by tests):

- The response NEVER contains ``safe_edit_low``, ``readonly_repo_audit``,
  ``low_edit``, ``--auto low``, argv, runner URLs, ``HAM_DROID_EXEC_TOKEN``,
  ``CURSOR_API_KEY``, ``ANTHROPIC_API_KEY``, or any other secret value /
  env-name string.
- Unknown task kinds NEVER pick a mutating provider; ``chosen`` falls back
  to ``no_agent`` or to ``null`` so the chat card asks the user to choose.
- Operator-only readiness signals stay redacted for non-operators.
- Candidates carry a stable ``label`` / ``output_kind`` mapping so the chat
  card can render copy without provider internals.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

_LOG = logging.getLogger(__name__)

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor
from src.ham.clerk_operator import actor_is_workspace_operator
from src.ham.coding_router import (
    Candidate,
    classify_task,
    collate_readiness,
    recommend,
)
from src.ham.coding_router.types import ProviderKind

router = APIRouter(
    prefix="/api/coding/conductor",
    tags=["coding-router"],
    dependencies=[Depends(get_ham_clerk_actor)],
)


# ---------------------------------------------------------------------------
# Public-facing per-provider product copy.
#
# This table is the ONLY place the conductor maps internal provider ids to
# user-facing copy. Internal workflow ids (``safe_edit_low``,
# ``readonly_repo_audit``) and env names (``HAM_DROID_EXEC_TOKEN``,
# ``CURSOR_API_KEY``) are deliberately absent so a future test against the
# rendered response cannot accidentally let them through.
# ---------------------------------------------------------------------------

_LABEL: dict[ProviderKind, str] = {
    "no_agent": "Conversational answer",
    "factory_droid_audit": "Read-only audit",
    "factory_droid_build": "Low-risk pull request",
    "cursor_cloud": "Cursor pull request",
    "claude_code": "Local single-file edit",
}

_OUTPUT_KIND: dict[ProviderKind, str] = {
    "no_agent": "answer",
    "factory_droid_audit": "report",
    "factory_droid_build": "pull_request",
    "cursor_cloud": "pull_request",
    "claude_code": "mission",
}

_WILL_MODIFY_CODE: dict[ProviderKind, bool] = {
    "no_agent": False,
    "factory_droid_audit": False,
    "factory_droid_build": True,
    "cursor_cloud": True,
    "claude_code": True,
}

_APPROVAL_KIND: dict[ProviderKind, str] = {
    "no_agent": "none",
    "factory_droid_audit": "confirm",
    "factory_droid_build": "confirm_and_accept_pr",
    "cursor_cloud": "confirm",
    "claude_code": "confirm",
}


def _candidate_to_public_dict(c: Candidate) -> dict[str, Any]:
    return {
        "provider": c.provider,
        "label": _LABEL[c.provider],
        "available": not c.blockers,
        "reason": c.reason,
        "blockers": list(c.blockers),
        "confidence": round(c.confidence, 4),
        "output_kind": _OUTPUT_KIND[c.provider],
        "requires_operator": c.requires_operator,
        "requires_confirmation": c.requires_confirmation,
        "will_modify_code": _WILL_MODIFY_CODE[c.provider],
        "will_open_pull_request": c.will_open_pull_request,
    }


def _is_approveable(c: Candidate) -> bool:
    return not c.blockers


def _pick_chosen(candidates: list[Candidate], task_kind: str) -> Candidate | None:
    """Return the recommended candidate, or None when no approve-able pick exists.

    Safety: ``unknown`` task kinds never confidently pick a mutating provider.
    The recommender already returns only ``no_agent`` for ``unknown``, but this
    function applies the same guard at the conductor seam as defence in depth.
    """
    for c in candidates:
        if not _is_approveable(c):
            continue
        if task_kind == "unknown" and _WILL_MODIFY_CODE[c.provider]:
            # Belt-and-braces: the recommender table for "unknown" never lists
            # a mutating provider, but the conductor must hold this invariant
            # even if the table is later edited.
            continue
        return c
    return None


def _apply_preferred_override(
    candidates: list[Candidate], preferred: ProviderKind | None
) -> list[Candidate]:
    """If ``preferred`` is approve-able, promote it to position 0; otherwise no-op.

    This NEVER bypasses blockers. A preferred provider that is unavailable,
    blocked by project policy, or missing host configuration stays blocked
    and stays in its ranked position. Phase 2A only re-orders approve-able
    candidates.
    """
    if preferred is None:
        return candidates
    for i, c in enumerate(candidates):
        if c.provider == preferred and _is_approveable(c):
            if i == 0:
                return candidates
            return [candidates[i], *candidates[:i], *candidates[i + 1 :]]
    return candidates


def _recommendation_reason(
    chosen: Candidate | None, task_kind: str, candidates: list[Candidate]
) -> str:
    # Unknown tasks must always surface uncertainty in the copy, even when
    # the conversational fallback is approve-able. The chat card uses this
    # string to render "I'm not sure" + alternatives prominently.
    if task_kind == "unknown":
        if chosen is not None:
            return (
                "I'm not sure which path is best for this request — falling back "
                "to a conversational answer. Pick another option below if you "
                "wanted code work."
            )
        return (
            "I'm not sure which path is best for this request. "
            "Pick an option below or rephrase the task."
        )
    if chosen is not None:
        return chosen.reason
    if not any(_is_approveable(c) for c in candidates):
        return (
            "No coding agent is available for this task on this host yet. "
            "Contact your workspace operator to configure a provider."
        )
    return "Multiple candidates are blocked; pick one to see how to unblock it."


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ConductorPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_prompt: str = Field(min_length=1, max_length=12_000)
    project_id: str | None = Field(default=None, max_length=180)
    # Optional forward-compatibility hook. The conductor only re-orders
    # approve-able candidates; preferred_provider can NEVER bypass blockers
    # or force-enable a disabled provider. Per project policy, Factory Droid
    # Build remains operator-controlled in Settings.
    preferred_provider: ProviderKind | None = None


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/preview")
async def post_coding_conductor_preview(
    body: ConductorPreviewBody,
    ham_actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    """Classify + recommend; returns candidates only. No launch, no execution."""
    if not body.user_prompt.strip():
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "CODING_CONDUCTOR_EMPTY_PROMPT",
                    "message": "Empty user_prompt; please describe the task in chat.",
                }
            },
        )

    is_op = actor_is_workspace_operator(ham_actor)
    task = classify_task(body.user_prompt, project_id=body.project_id)
    snapshot = collate_readiness(
        actor=ham_actor,
        project_id=body.project_id,
        include_operator_details=is_op,
    )

    candidates = recommend(task, snapshot)
    candidates = _apply_preferred_override(candidates, body.preferred_provider)
    chosen = _pick_chosen(candidates, task.kind)

    public_candidates = [_candidate_to_public_dict(c) for c in candidates]
    chosen_public = _candidate_to_public_dict(chosen) if chosen is not None else None

    response_blockers: list[str] = []
    if body.project_id and not snapshot.project.found:
        response_blockers.append(
            f"Unknown project_id {body.project_id!r}. Pick an existing project."
        )

    chosen_provider = chosen.provider if chosen is not None else None
    chosen_blocker_count = len(chosen.blockers) if chosen is not None else 0
    chosen_available = bool(chosen is not None and not chosen.blockers)
    approval_kind_value = _APPROVAL_KIND[chosen.provider] if chosen else "none"
    _LOG.info(
        "coding_conductor_preview decision: task_kind=%s task_confidence=%.2f "
        "project_found=%s project_id_present=%s build_lane_enabled=%s "
        "output_target=%s has_workspace_id=%s "
        "chosen_provider=%s chosen_available=%s chosen_blocker_count=%d "
        "approval_kind=%s requires_approval=%s",
        task.kind,
        task.confidence,
        snapshot.project.found,
        bool(snapshot.project.project_id),
        snapshot.project.build_lane_enabled,
        snapshot.project.output_target or "none",
        snapshot.project.has_workspace_id,
        chosen_provider or "none",
        chosen_available,
        chosen_blocker_count,
        approval_kind_value,
        chosen is not None and chosen.requires_confirmation,
    )

    return {
        "kind": "coding_conductor_preview",
        "preview_id": str(uuid.uuid4()),
        "task_kind": task.kind,
        "task_confidence": round(task.confidence, 4),
        "chosen": chosen_public,
        "candidates": public_candidates,
        "blockers": response_blockers,
        "recommendation_reason": _recommendation_reason(chosen, task.kind, candidates),
        "requires_approval": chosen is not None and chosen.requires_confirmation,
        "approval_kind": _APPROVAL_KIND[chosen.provider] if chosen else "none",
        "project": {
            "found": snapshot.project.found,
            "project_id": snapshot.project.project_id,
            "build_lane_enabled": snapshot.project.build_lane_enabled,
            "has_github_repo": snapshot.project.has_github_repo,
            "output_target": snapshot.project.output_target,
            "has_workspace_id": snapshot.project.has_workspace_id,
        },
        "is_operator": is_op,
    }


__all__ = ["router"]
