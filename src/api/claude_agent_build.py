"""Gated HAM Claude Agent build router — POST /api/claude-agent/build/(preview|launch).

Sibling of :mod:`src.api.droid_build`. The Factory Droid build route is the
canonical template; do **not** modify it. This module mirrors the same
gate-stack shape and digest-verification pattern with a Claude-Agent-specific
``base_revision`` (:data:`CLAUDE_AGENT_REGISTRY_REVISION`) and exec-token env
(:data:`_CLAUDE_AGENT_EXEC_TOKEN_ENV`).

Fail-closed gates (evaluation order):

1. Clerk session (router-level dep).
2. ``confirmed=True`` body field (launch only).
3. ``CLAUDE_AGENT_ENABLED`` env truthy.
4. Project exists, ``build_lane_enabled=True``.
5. Project ``output_target == "managed_workspace"``.
6. Target-aware build approver (workspace owner/admin for managed).
7. Claude Agent SDK installed (``check_claude_agent_readiness``).
8. Anthropic auth signal present (``claude_agent_mission_auth_configured``).
9. Workspace ``workspace_id`` populated (also enforced by gate 6).
10. Digest + base_revision verify (launch only).
11. ``HAM_CLAUDE_AGENT_EXEC_TOKEN`` configured (checked **last**).
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.dependencies.workspace import get_workspace_store
from src.api.droid_build import _require_build_approver, _require_build_lane_project
from src.ham.claude_agent_runner import (
    ClaudeAgentPermissionPolicy,
    run_claude_agent_mission,
)
from src.ham.clerk_auth import HamActor
from src.ham.droid_runner.build_lane_output import PostExecCommon
from src.ham.managed_workspace.paths import managed_working_dir
from src.ham.managed_workspace.provisioning import (
    ManagedWorkspaceSetupError,
    ensure_managed_working_tree,
)
from src.ham.managed_workspace.workspace_adapter import emit_managed_workspace_snapshot
from src.ham.worker_adapters.claude_agent_adapter import (
    _redact_diagnostic_text,
    check_claude_agent_readiness,
    claude_agent_mission_auth_configured,
)
from src.persistence.control_plane_run import (
    ControlPlaneRun,
    cap_error_summary,
    cap_summary,
    get_control_plane_run_store,
    new_ham_run_id,
    utc_now_iso,
)
from src.persistence.workspace_store import WorkspaceStore

_LOG = logging.getLogger(__name__)

CLAUDE_AGENT_REGISTRY_REVISION = "claude-agent-v1"
CLAUDE_AGENT_ENABLED_ENV_NAME = "CLAUDE_AGENT_ENABLED"
_CLAUDE_AGENT_EXEC_TOKEN_ENV = "HAM_CLAUDE_AGENT_EXEC_TOKEN"  # noqa: S105
_SUMMARY_FALLBACK = "Claude Agent mission finished."


router = APIRouter(
    prefix="/api/claude-agent/build",
    tags=["control-plane"],
    dependencies=[Depends(get_ham_clerk_actor)],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _require_claude_agent_enabled() -> None:
    if not _truthy_env(CLAUDE_AGENT_ENABLED_ENV_NAME):
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "CLAUDE_AGENT_DISABLED",
                    "message": "Claude Agent live execution is disabled on this host.",
                }
            },
        )


def _require_managed_workspace_target(rec: Any) -> None:
    target = (getattr(rec, "output_target", None) or "managed_workspace").strip()
    if target != "managed_workspace":
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "CLAUDE_AGENT_REQUIRES_MANAGED_WORKSPACE",
                    "message": (
                        "Claude Agent live execution requires a managed-workspace project."
                    ),
                }
            },
        )


def _require_claude_agent_sdk(actor: HamActor | None) -> None:
    readiness = check_claude_agent_readiness(actor)
    if not readiness.sdk_available:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "CLAUDE_AGENT_SDK_UNAVAILABLE",
                    "message": "Claude Agent SDK is not installed on this host.",
                }
            },
        )


def _require_claude_agent_auth(actor: HamActor | None) -> None:
    if not claude_agent_mission_auth_configured(actor):
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "CLAUDE_AGENT_AUTH_UNAVAILABLE",
                    "message": "Claude Agent has no credentials configured on this host.",
                }
            },
        )


def _require_claude_agent_exec_token() -> None:
    if not (os.environ.get(_CLAUDE_AGENT_EXEC_TOKEN_ENV) or "").strip():
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "CLAUDE_AGENT_LANE_UNCONFIGURED",
                    "message": (
                        "The Claude Agent build lane is not configured on this host yet. "
                        "Contact your workspace operator."
                    ),
                }
            },
        )


def _project_managed_root(rec: Any) -> Path:
    wid = (getattr(rec, "workspace_id", None) or "").strip()
    pid = (rec.id or "").strip()
    if not wid:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "BUILD_LANE_PROJECT_MISSING_WORKSPACE_ID",
                    "message": (
                        "This project is configured for managed workspace builds "
                        "but has no workspace assigned yet."
                    ),
                }
            },
        )
    try:
        return managed_working_dir(wid, pid)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "BUILD_LANE_PROJECT_MISSING_WORKSPACE_ID",
                    "message": ("This project has an invalid workspace or project identifier."),
                }
            },
        ) from exc


def compute_claude_agent_proposal_digest(
    *,
    project_id: str,
    user_prompt: str,
) -> str:
    """Stable per-(project, prompt, registry) digest for preview/launch coupling.

    TODO(mission-2.x): align with the canonical-JSON pattern used by Factory
    Droid (``compute_proposal_digest``) once the Claude Agent lane gains
    workflow-level inputs (cwd / argv equivalents). The simplified form is
    sufficient for the Mission 2 "same digest on preview & launch within a
    short window" contract.
    """
    raw = "|".join(
        [
            CLAUDE_AGENT_REGISTRY_REVISION,
            project_id.strip(),
            user_prompt,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_claude_agent_launch_against_preview(
    *,
    project_id: str,
    user_prompt: str,
    proposal_digest: str,
    base_revision: str,
) -> str | None:
    if base_revision != CLAUDE_AGENT_REGISTRY_REVISION:
        return (
            f"Stale base_revision: expected {CLAUDE_AGENT_REGISTRY_REVISION!r}, "
            f"got {base_revision!r}."
        )
    expected = compute_claude_agent_proposal_digest(
        project_id=project_id,
        user_prompt=user_prompt,
    )
    if expected != proposal_digest.strip():
        return "proposal_digest mismatch — re-run preview before launch."
    return None


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


def _persist_workspace_setup_failed(
    *,
    rec: Any,
    ham_actor: HamActor | None,
    project_root: Path,
    proposal_digest: str,
    setup_error: ManagedWorkspaceSetupError,
) -> dict[str, Any]:
    """Persist a single terminal control-plane row for a provisioning failure.

    The runner is **not** invoked, no snapshot is emitted, and no PR is
    opened. The new ``claude_agent:workspace_setup_failed`` status_reason
    is emitted directly here so the runner taxonomy in
    :func:`_status_from_run` stays unchanged.
    """
    error_summary = _redact_diagnostic_text(setup_error.detail, cap=2000)
    now = utc_now_iso()
    ham_run_id = new_ham_run_id()
    project_root_str = str(project_root.resolve())
    change_id = uuid.uuid4().hex
    cp_run = ControlPlaneRun(
        ham_run_id=ham_run_id,
        provider="claude_agent",
        action_kind="launch",
        project_id=rec.id,
        created_by=_created_by(ham_actor),
        created_at=now,
        updated_at=now,
        committed_at=now,
        started_at=now,
        finished_at=now,
        last_observed_at=now,
        status="failed",
        status_reason="claude_agent:workspace_setup_failed",
        proposal_digest=proposal_digest,
        base_revision=CLAUDE_AGENT_REGISTRY_REVISION,
        external_id=change_id,
        workflow_id=None,
        summary=None,
        error_summary=cap_error_summary(error_summary),
        last_provider_status=None,
        audit_ref=None,
        project_root=project_root_str,
        pr_url=None,
        pr_branch=None,
        pr_commit_sha=None,
        build_outcome=None,
        output_target="managed_workspace",
        output_ref=None,
    )
    try:
        get_control_plane_run_store().save(cp_run, project_root_for_mirror=project_root_str)
    except Exception as exc:
        _LOG.warning(
            "claude_agent_build control-plane save failed (%s)",
            type(exc).__name__,
        )
    return {
        "kind": "claude_agent_build_launch",
        "project_id": rec.id,
        "ok": False,
        "ham_run_id": ham_run_id,
        "control_plane_status": "failed",
        "summary": None,
        "error_summary": error_summary,
        "is_readonly": False,
        "will_open_pull_request": False,
        "requires_approval": True,
        "output_target": "managed_workspace",
        "output_ref": None,
    }


def _status_from_run(run_status: str, snapshot_outcome: str | None) -> tuple[str, str]:
    if run_status == "success":
        if snapshot_outcome == "succeeded":
            return "succeeded", "claude_agent:snapshot_emitted"
        if snapshot_outcome == "nothing_to_change":
            return "succeeded", "claude_agent:nothing_to_change"
        return "failed", "claude_agent:snapshot_failed"
    if run_status == "blocked_by_policy":
        return "failed", "claude_agent:blocked_by_policy"
    if run_status == "timeout":
        return "failed", "claude_agent:timeout"
    if run_status == "sdk_missing":
        return "failed", "claude_agent:sdk_missing"
    if run_status == "auth_missing":
        return "failed", "claude_agent:auth_missing"
    if run_status == "disabled":
        return "failed", "claude_agent:disabled"
    return "failed", "claude_agent:sdk_error"


# ---------------------------------------------------------------------------
# Pydantic bodies
# ---------------------------------------------------------------------------


class ClaudeAgentBuildPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=180)
    user_prompt: str = Field(min_length=1, max_length=12_000)


class ClaudeAgentBuildLaunchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=180)
    user_prompt: str = Field(min_length=1, max_length=12_000)
    proposal_digest: str = Field(min_length=64, max_length=64)
    base_revision: str = Field(min_length=1, max_length=64)
    confirmed: bool = False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _user_facing_summary() -> str:
    return (
        "This action proposes a Claude Agent managed workspace edit: "
        "scoped read and write tools only, no shell, no network. "
        "HAM will capture a preview snapshot for you to review before "
        "anything is published."
    )


@router.post("/preview")
async def preview_claude_agent_build(
    body: ClaudeAgentBuildPreviewBody,
    ham_actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    workspace_store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
) -> dict[str, Any]:
    """Preview a Claude Agent managed-workspace edit. No execution; returns a digest."""
    _require_claude_agent_enabled()
    rec = _require_build_lane_project(body.project_id)
    _require_managed_workspace_target(rec)
    _require_build_approver(ham_actor, rec, workspace_store)
    _require_claude_agent_sdk(ham_actor)
    _require_claude_agent_auth(ham_actor)
    digest = compute_claude_agent_proposal_digest(project_id=rec.id, user_prompt=body.user_prompt)
    return {
        "kind": "claude_agent_build_preview",
        "project_id": rec.id,
        "project_name": rec.name,
        "user_prompt": body.user_prompt,
        "summary": _user_facing_summary(),
        "proposal_digest": digest,
        "base_revision": CLAUDE_AGENT_REGISTRY_REVISION,
        "is_readonly": False,
        "will_open_pull_request": False,
        "requires_approval": True,
        "output_target": "managed_workspace",
    }


@router.post("/launch")
async def launch_claude_agent_build(
    body: ClaudeAgentBuildLaunchBody,
    ham_actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    workspace_store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
) -> dict[str, Any]:
    """Launch a Claude Agent managed-workspace edit. Digest-verified; token-gated."""
    if not body.confirmed:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "CLAUDE_AGENT_LAUNCH_REQUIRES_CONFIRMATION",
                    "message": "Approve the launch before sending.",
                }
            },
        )
    _require_claude_agent_enabled()
    rec = _require_build_lane_project(body.project_id)
    _require_managed_workspace_target(rec)
    _require_build_approver(ham_actor, rec, workspace_store)
    _require_claude_agent_sdk(ham_actor)
    _require_claude_agent_auth(ham_actor)
    v_err = verify_claude_agent_launch_against_preview(
        project_id=rec.id,
        user_prompt=body.user_prompt,
        proposal_digest=body.proposal_digest,
        base_revision=body.base_revision,
    )
    if v_err:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "CLAUDE_AGENT_LAUNCH_PREVIEW_STALE",
                    "message": v_err,
                }
            },
        )
    # Token gate last so non-operators cannot probe configured-vs-not.
    _require_claude_agent_exec_token()

    project_root = _project_managed_root(rec)
    try:
        ensure_managed_working_tree(
            workspace_id=getattr(rec, "workspace_id", None),
            project_id=rec.id,
        )
    except ManagedWorkspaceSetupError as exc:
        return _persist_workspace_setup_failed(
            rec=rec,
            ham_actor=ham_actor,
            project_root=project_root,
            proposal_digest=body.proposal_digest,
            setup_error=exc,
        )
    policy = ClaudeAgentPermissionPolicy(project_root=project_root)
    change_id = uuid.uuid4().hex

    run_result = await run_claude_agent_mission(
        project_root=project_root,
        user_prompt=body.user_prompt,
        policy=policy,
        actor=ham_actor,
    )

    snapshot_outcome: str | None = None
    output_ref: dict[str, Any] = {}
    snapshot_error: str | None = None

    if run_result.status == "success":
        common = PostExecCommon(
            project_id=rec.id,
            project_root=project_root,
            summary=run_result.assistant_summary or _SUMMARY_FALLBACK,
            change_id=change_id,
            pr_inputs=None,
            workspace_id=getattr(rec, "workspace_id", None),
        )
        try:
            snap = emit_managed_workspace_snapshot(common)
        except Exception as exc:
            _LOG.warning(
                "claude_agent_build snapshot emit raised %s",
                type(exc).__name__,
            )
            snapshot_outcome = "failed"
            snapshot_error = _redact_diagnostic_text(
                f"managed_workspace snapshot raised {type(exc).__name__}",
                cap=2000,
            )
        else:
            snapshot_outcome = snap.build_outcome
            output_ref = dict(snap.target_ref or {})
            if snap.error_summary:
                snapshot_error = _redact_diagnostic_text(snap.error_summary, cap=2000)

    status, status_reason = _status_from_run(run_result.status, snapshot_outcome)

    summary_text: str | None
    if run_result.assistant_summary:
        summary_text = run_result.assistant_summary
    else:
        summary_text = None

    error_summary: str | None
    if status == "failed":
        if run_result.error_summary:
            error_summary = run_result.error_summary
        elif snapshot_error:
            error_summary = snapshot_error
        else:
            error_summary = _redact_diagnostic_text(
                f"claude_agent run finished with status={run_result.status}",
                cap=2000,
            )
    else:
        error_summary = None

    now = utc_now_iso()
    ham_run_id = new_ham_run_id()
    project_root_str = str(project_root.resolve())
    cp_run = ControlPlaneRun(
        ham_run_id=ham_run_id,
        provider="claude_agent",
        action_kind="launch",
        project_id=rec.id,
        created_by=_created_by(ham_actor),
        created_at=now,
        updated_at=now,
        committed_at=now,
        started_at=now,
        finished_at=now,
        last_observed_at=now,
        status=status,
        status_reason=status_reason,
        proposal_digest=body.proposal_digest,
        base_revision=CLAUDE_AGENT_REGISTRY_REVISION,
        external_id=change_id,
        workflow_id=None,
        summary=cap_summary(summary_text),
        error_summary=cap_error_summary(error_summary),
        last_provider_status=None,
        audit_ref=None,
        project_root=project_root_str,
        pr_url=None,
        pr_branch=None,
        pr_commit_sha=None,
        build_outcome=None,
        output_target="managed_workspace",
        output_ref=output_ref or None,
    )
    try:
        get_control_plane_run_store().save(cp_run, project_root_for_mirror=project_root_str)
    except Exception as exc:
        _LOG.warning(
            "claude_agent_build control-plane save failed (%s)",
            type(exc).__name__,
        )

    return {
        "kind": "claude_agent_build_launch",
        "project_id": rec.id,
        "ok": status == "succeeded",
        "ham_run_id": ham_run_id,
        "control_plane_status": status,
        "summary": summary_text,
        "error_summary": error_summary,
        "is_readonly": False,
        "will_open_pull_request": False,
        "requires_approval": True,
        "output_target": "managed_workspace",
        "output_ref": output_ref or None,
    }


__all__ = [
    "CLAUDE_AGENT_ENABLED_ENV_NAME",
    "CLAUDE_AGENT_REGISTRY_REVISION",
    "compute_claude_agent_proposal_digest",
    "router",
    "verify_claude_agent_launch_against_preview",
]
