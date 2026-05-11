"""
Gated Factory Droid Build router — POST /api/droid/build/preview + /launch.

This router is the **mutating** counterpart to ``src/api/droid_audit.py``. The
audit router exposes only the read-only ``readonly_repo_audit`` workflow and
must remain untouched. This router exposes only the ``safe_edit_low`` workflow
and is hardcoded server-side; the workflow id is **never** read from the
client request and is **never** echoed in user-facing response fields. The
internal workflow id, ``--auto low`` flag, argv, and the
``HAM_DROID_EXEC_TOKEN`` env name are deliberately kept out of the response
shape.

Fail-closed gates (in the order checked):

1. Clerk session required (router-level dep).
2. Caller must be a workspace operator (``actor_is_workspace_operator``).
3. Project must exist.
4. Project must have ``build_lane_enabled=True``.
5. Project must have ``github_repo`` configured.
6. Launch must include ``confirmed=True`` and ``accept_pr=True``.
7. Proposal digest + base revision must match the prior preview.
8. ``HAM_DROID_EXEC_TOKEN`` must be configured on the API host.

If any gate fails, the route returns a structured error and **never** touches
the runner, never spawns ``droid``, never opens a PR, and never writes to the
project store.

The launch executor (``execute_droid_build_workflow``) is a thin seam so
tests can mock the post-Droid commit/push/PR step without invoking real
``git`` / ``gh`` / network calls. The production wiring of that executor
lives in ``src/ham/droid_runner/build_lane.py`` and is intentionally inert
in P3 — it cannot be reached today because ``HAM_DROID_EXEC_TOKEN`` is not
set on any deployed host.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor
from src.ham.clerk_operator import actor_is_workspace_operator
from src.ham.droid_workflows.preview_launch import (
    build_droid_preview,
    execute_droid_build_workflow_remote,
    verify_launch_against_preview,
)
from src.ham.droid_workflows.registry import REGISTRY_REVISION, get_workflow
from src.persistence.control_plane_run import DroidBuildOutcome
from src.persistence.project_store import get_project_store

# Hardcoded server-side. NEVER read from the client. NEVER echoed in a response field.
_BUILD_WORKFLOW_ID = "safe_edit_low"

# Token gate — must be configured on the API host before any launch executes.
# This is the *name* of an env var, not a secret value (S105 false positive).
_DROID_EXEC_TOKEN_ENV = "HAM_DROID_EXEC_TOKEN"  # noqa: S105


router = APIRouter(
    prefix="/api/droid/build",
    tags=["control-plane"],
    dependencies=[Depends(get_ham_clerk_actor)],
)


# ---------------------------------------------------------------------------
# Internal helpers (all gates fail closed before any executor call).
# ---------------------------------------------------------------------------


def _build_workflow_or_500() -> Any:
    wf = get_workflow(_BUILD_WORKFLOW_ID)
    if wf is None:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "DROID_BUILD_WORKFLOW_MISSING",
                    "message": "The build workflow is not registered on this API host.",
                }
            },
        )
    if not wf.mutates or not wf.requires_launch_token:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "DROID_BUILD_WORKFLOW_MISCONFIGURED",
                    "message": "The build workflow has been misconfigured (mutation/token flags).",
                }
            },
        )
    return wf


def _require_workspace_operator(actor: HamActor | None) -> None:
    if not actor_is_workspace_operator(actor):
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "WORKSPACE_OPERATOR_REQUIRED",
                    "message": "This action requires a workspace operator.",
                }
            },
        )


def _require_build_lane_project(project_id: str) -> Any:
    pid = (project_id or "").strip()
    rec = get_project_store().get_project(pid)
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PROJECT_NOT_FOUND",
                    "message": f"Unknown project_id {pid!r}.",
                }
            },
        )
    if not getattr(rec, "build_lane_enabled", False):
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "BUILD_LANE_NOT_ENABLED_FOR_PROJECT",
                    "message": "Build lane is not enabled for this project.",
                }
            },
        )
    repo = (getattr(rec, "github_repo", None) or "").strip()
    if not repo:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "BUILD_LANE_PROJECT_MISSING_GITHUB_REPO",
                    "message": "Project has no github_repo configured for build lane.",
                }
            },
        )
    return rec


def _require_droid_exec_token() -> None:
    if not (os.environ.get(_DROID_EXEC_TOKEN_ENV) or "").strip():
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "BUILD_LANE_UNCONFIGURED",
                    "message": (
                        "The Factory Droid build lane is not configured on this host yet. "
                        "Try the read-only audit lane or contact your workspace operator."
                    ),
                }
            },
        )


def _created_by(actor: HamActor | None) -> dict[str, Any] | None:
    if actor is None:
        return None
    d: dict[str, Any] = {"user_id": actor.user_id}
    if actor.org_id:
        d["org_id"] = actor.org_id
    if actor.email:
        d["email"] = actor.email
    if actor.session_id:
        d["session_id"] = actor.session_id
    return d


# ---------------------------------------------------------------------------
# Launch executor seam (mocked in tests; inert in P3 production).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DroidBuildLaunchOutcome:
    """In-router shape returned by :func:`execute_droid_build_workflow`."""

    ok: bool
    ham_run_id: str | None
    control_plane_status: str | None
    pr_url: str | None
    pr_branch: str | None
    pr_commit_sha: str | None
    build_outcome: DroidBuildOutcome | None
    summary: str | None
    error_summary: str | None


def execute_droid_build_workflow(
    *,
    project_id: str,
    project_root: Path,
    user_prompt: str,
    proposal_digest: str,
    created_by: dict[str, Any] | None,
) -> DroidBuildLaunchOutcome:
    """
    Drive the safe_edit_low workflow plus the runner-side Build Lane post-exec.

    This function is a deliberate seam: tests patch it directly and assert that
    the gate stack runs *before* it is reached. Production cannot reach it
    today because :func:`_require_droid_exec_token` fails closed unless an
    operator sets ``HAM_DROID_EXEC_TOKEN`` on the API host AND the deployed
    runner exposes the Build Lane post-exec step.

    The runner is the authority on branch/commit/PR text. This API hands the
    runner the workflow id, project id, project root, sanitized prompt, and
    proposal digest; the runner sanitizes its own output, runs ``git`` and
    ``gh pr create`` under ``shell=False``, refuses sensitive-path changes,
    refuses to push the base branch, and returns the PR coordinates.
    """
    launch = execute_droid_build_workflow_remote(
        workflow_id=_BUILD_WORKFLOW_ID,
        project_root=project_root,
        user_prompt=user_prompt,
        project_id=project_id,
        proposal_digest=proposal_digest,
        created_by=created_by,
    )
    return DroidBuildLaunchOutcome(
        ok=launch.ok,
        ham_run_id=launch.ham_run_id,
        control_plane_status=launch.control_plane_status,
        pr_url=launch.pr_url,
        pr_branch=launch.pr_branch,
        pr_commit_sha=launch.pr_commit_sha,
        build_outcome=launch.build_outcome,
        summary=launch.summary,
        error_summary=launch.build_error_summary or launch.blocking_reason,
    )


# ---------------------------------------------------------------------------
# Pydantic bodies — both reject extra fields. ``workflow_id`` is never accepted.
# ---------------------------------------------------------------------------


class DroidBuildPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=180)
    user_prompt: str = Field(min_length=1, max_length=12_000)


class DroidBuildLaunchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=180)
    user_prompt: str = Field(min_length=1, max_length=12_000)
    proposal_digest: str = Field(min_length=64, max_length=64)
    base_revision: str = Field(min_length=1, max_length=64)
    confirmed: bool = False
    accept_pr: bool = False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _user_facing_summary() -> str:
    """Sanitized preview summary — never exposes workflow id, argv, or token env."""
    return (
        "This action proposes a low-risk pull request: documentation, comments, "
        "and non-behavioral edits only. You will review and approve the PR on "
        "GitHub before anything merges. No CI configuration or business logic "
        "will be modified."
    )


@router.post("/preview")
async def preview_droid_build(
    body: DroidBuildPreviewBody,
    ham_actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    """Preview a build (low-risk PR-opening) workflow. No execution; returns a digest."""
    _build_workflow_or_500()
    _require_workspace_operator(ham_actor)
    rec = _require_build_lane_project(body.project_id)
    prev = build_droid_preview(
        workflow_id=_BUILD_WORKFLOW_ID,
        project_id=rec.id,
        project_root=Path(rec.root),
        user_prompt=body.user_prompt,
    )
    if not prev.ok:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "DROID_BUILD_PREVIEW_BLOCKED",
                    "message": prev.blocking_reason or "Preview blocked.",
                }
            },
        )
    return {
        "kind": "droid_build_preview",
        "project_id": rec.id,
        "project_name": rec.name,
        "user_prompt": prev.user_prompt,
        "summary": _user_facing_summary(),
        "proposal_digest": prev.proposal_digest,
        "base_revision": prev.base_revision,
        "is_readonly": False,
        "will_open_pull_request": True,
        "requires_approval": True,
    }


@router.post("/launch")
async def launch_droid_build(
    body: DroidBuildLaunchBody,
    ham_actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    """Launch the previewed build. Digest-verified; gated by token + accept_pr + confirmed."""
    if not body.confirmed:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "DROID_BUILD_LAUNCH_REQUIRES_CONFIRMATION",
                    "message": "Approve the launch before sending.",
                }
            },
        )
    if not body.accept_pr:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "DROID_BUILD_LAUNCH_REQUIRES_ACCEPT_PR",
                    "message": "Acknowledge that this opens a pull request before sending.",
                }
            },
        )
    _build_workflow_or_500()
    _require_workspace_operator(ham_actor)
    rec = _require_build_lane_project(body.project_id)
    root = Path(rec.root)
    v_err = verify_launch_against_preview(
        workflow_id=_BUILD_WORKFLOW_ID,
        project_id=rec.id,
        project_root=root,
        user_prompt=body.user_prompt,
        proposal_digest=body.proposal_digest,
        base_revision=body.base_revision,
    )
    if v_err:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "DROID_BUILD_LAUNCH_PREVIEW_STALE",
                    "message": v_err,
                }
            },
        )
    # Token gate is the LAST check: only after every other gate passes do we even
    # consider whether the runner is reachable. This keeps the failure mode honest
    # for non-operators / disabled projects (403 / 422) instead of leaking the
    # token-configured / not-configured signal to unauthorized callers.
    _require_droid_exec_token()

    out = execute_droid_build_workflow(
        project_id=rec.id,
        project_root=root,
        user_prompt=body.user_prompt,
        proposal_digest=body.proposal_digest,
        created_by=_created_by(ham_actor),
    )
    return {
        "kind": "droid_build_launch",
        "project_id": rec.id,
        "ok": out.ok,
        "ham_run_id": out.ham_run_id,
        "control_plane_status": out.control_plane_status,
        "pr_url": out.pr_url,
        "pr_branch": out.pr_branch,
        "pr_commit_sha": out.pr_commit_sha,
        "build_outcome": out.build_outcome,
        "summary": out.summary,
        "error_summary": out.error_summary if not out.ok else None,
        "is_readonly": False,
        "will_open_pull_request": True,
        "requires_approval": True,
    }


__all__ = [
    "DroidBuildLaunchOutcome",
    "REGISTRY_REVISION",
    "execute_droid_build_workflow",
    "router",
]
