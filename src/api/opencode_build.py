"""Gated HAM OpenCode build router — POST /api/opencode/build/(preview|launch).

Sibling of :mod:`src.api.claude_agent_build`. The Claude Agent build route is
the canonical template for the Mission 2 OpenCode build lane; this module
mirrors the same gate-stack shape, digest-verification pattern, and
ControlPlaneRun persistence with an OpenCode-specific ``base_revision``
(:data:`OPENCODE_REGISTRY_REVISION`) and exec-token env
(:data:`_OPENCODE_EXEC_TOKEN_ENV`).

Fail-closed gates (evaluation order):

1. Clerk session (router-level dep).
2. ``confirmed=True`` body field (launch only).
3. ``HAM_OPENCODE_ENABLED`` env truthy.
4. ``HAM_OPENCODE_EXECUTION_ENABLED`` env truthy.
5. Project exists, ``build_lane_enabled=True``.
6. Project ``output_target == "managed_workspace"``.
7. Target-aware build approver (workspace owner/admin for managed).
8. OpenCode readiness probe reports ``configured``.
9. Workspace ``workspace_id`` populated (also enforced by gate 7).
10. Digest + base_revision verify (launch only).
11. ``HAM_OPENCODE_EXEC_TOKEN`` configured (checked **last**).

The launch route never accepts the OpenCode binary path or env values
from the request. All credential / config bring-up is handled inside
:func:`src.ham.opencode_runner.run_opencode_mission`.
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.dependencies.workspace import get_workspace_store
from src.api.droid_build import _require_build_approver, _require_build_lane_project
from src.ham.clerk_auth import HamActor
from src.ham.coding_router.opencode_provider import (
    OPENCODE_EXECUTION_ENABLED_ENV_NAME,
    launch_opencode_coding,
)
from src.ham.droid_runner.build_lane_output import PostExecCommon
from src.ham.managed_workspace.paths import managed_working_dir
from src.ham.managed_workspace.provisioning import (
    ManagedWorkspaceSetupError,
    ensure_managed_working_tree,
)
from src.ham.managed_workspace.workspace_adapter import (
    compute_deleted_paths_against_parent,
    emit_managed_workspace_snapshot,
)
from src.ham.opencode_runner import run_opencode_mission
from src.ham.worker_adapters.claude_agent_adapter import _redact_diagnostic_text
from src.ham.worker_adapters.opencode_adapter import (
    OPENCODE_ENABLED_ENV_NAME,
    OpenCodeStatus,
    check_opencode_readiness,
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

OPENCODE_REGISTRY_REVISION = "opencode-v1"
_OPENCODE_EXEC_TOKEN_ENV = "HAM_OPENCODE_EXEC_TOKEN"  # noqa: S105
_OPENCODE_ALLOW_DELETIONS_ENV = "HAM_OPENCODE_ALLOW_DELETIONS"
_SUMMARY_FALLBACK = "OpenCode mission finished."


router = APIRouter(
    prefix="/api/opencode",
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


def _require_opencode_enabled() -> None:
    if not _truthy_env(OPENCODE_ENABLED_ENV_NAME):
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "OPENCODE_DISABLED",
                    "message": "OpenCode live execution is disabled on this host.",
                }
            },
        )


def _require_opencode_execution_enabled() -> None:
    if not _truthy_env(OPENCODE_EXECUTION_ENABLED_ENV_NAME):
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "OPENCODE_EXECUTION_DISABLED",
                    "message": "OpenCode live execution is not enabled on this host.",
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
                    "code": "OPENCODE_REQUIRES_MANAGED_WORKSPACE",
                    "message": ("OpenCode live execution requires a managed-workspace project."),
                }
            },
        )


def _require_opencode_configured(actor: HamActor | None) -> None:
    readiness = check_opencode_readiness(actor)
    if readiness.status != OpenCodeStatus.CONFIGURED:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "OPENCODE_PROVIDER_NOT_CONFIGURED",
                    "message": "OpenCode is not configured on this host.",
                }
            },
        )


def _require_opencode_exec_token(header_token: str | None) -> None:
    expected = (os.environ.get(_OPENCODE_EXEC_TOKEN_ENV) or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "OPENCODE_LANE_UNCONFIGURED",
                    "message": (
                        "The OpenCode build lane is not configured on this host yet. "
                        "Contact your workspace operator."
                    ),
                }
            },
        )
    presented = (header_token or "").strip()
    if presented.lower().startswith("bearer "):
        presented = presented[7:].strip()
    if not presented or presented != expected:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "OPENCODE_LANE_UNCONFIGURED",
                    "message": (
                        "The OpenCode build lane is not configured on this host yet. "
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


def compute_opencode_proposal_digest(
    *,
    project_id: str,
    user_prompt: str,
    model: str | None = None,
) -> str:
    """Stable per-(project, prompt, model, registry) digest for preview/launch coupling."""
    raw = "|".join(
        [
            OPENCODE_REGISTRY_REVISION,
            project_id.strip(),
            user_prompt,
            (model or "").strip(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_opencode_launch_against_preview(
    *,
    project_id: str,
    user_prompt: str,
    model: str | None,
    proposal_digest: str,
    base_revision: str,
) -> str | None:
    if base_revision != OPENCODE_REGISTRY_REVISION:
        return (
            f"Stale base_revision: expected {OPENCODE_REGISTRY_REVISION!r}, got {base_revision!r}."
        )
    expected = compute_opencode_proposal_digest(
        project_id=project_id,
        user_prompt=user_prompt,
        model=model,
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


def _persist_opencode_terminal_run(
    *,
    rec: Any,
    ham_actor: HamActor | None,
    project_root: Path,
    proposal_digest: str,
    change_id: str,
    ham_run_id: str,
    status: str,
    status_reason: str,
    summary: str | None,
    error_summary: str | None,
    output_ref: dict[str, Any] | None,
) -> None:
    now = utc_now_iso()
    project_root_str = str(project_root.resolve())
    cp_run = ControlPlaneRun(
        ham_run_id=ham_run_id,
        provider="opencode_cli",
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
        proposal_digest=proposal_digest,
        base_revision=OPENCODE_REGISTRY_REVISION,
        external_id=change_id,
        workflow_id=None,
        summary=cap_summary(summary),
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
    except Exception as exc:  # noqa: BLE001
        _LOG.warning(
            "opencode_build control-plane save failed (%s)",
            type(exc).__name__,
        )


def _persist_workspace_setup_failed_opencode(
    *,
    rec: Any,
    ham_actor: HamActor | None,
    project_root: Path,
    proposal_digest: str,
    setup_error: ManagedWorkspaceSetupError,
    ham_run_id: str,
    change_id: str,
) -> dict[str, Any]:
    error_summary = _redact_diagnostic_text(setup_error.detail, cap=2000)
    _persist_opencode_terminal_run(
        rec=rec,
        ham_actor=ham_actor,
        project_root=project_root,
        proposal_digest=proposal_digest,
        change_id=change_id,
        ham_run_id=ham_run_id,
        status="failed",
        status_reason="opencode:workspace_setup_failed",
        summary=None,
        error_summary=error_summary,
        output_ref=None,
    )
    return {
        "kind": "opencode_build_launch",
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


def _persist_output_requires_review_opencode(
    *,
    rec: Any,
    ham_actor: HamActor | None,
    project_root: Path,
    proposal_digest: str,
    deleted_paths: tuple[str, ...],
    change_id: str,
    ham_run_id: str,
) -> dict[str, Any]:
    preview = ", ".join(deleted_paths[:5])
    suffix = "" if len(deleted_paths) <= 5 else f" (+{len(deleted_paths) - 5} more)"
    plural = "s" if len(deleted_paths) != 1 else ""
    error_summary_raw = (
        f"output_requires_review: {len(deleted_paths)} file{plural} "
        f"would be deleted: {preview}{suffix}"
    )
    error_summary = _redact_diagnostic_text(error_summary_raw, cap=2000)
    summary_text = "OpenCode proposed deleting files, so HAM stopped before saving this version."
    _persist_opencode_terminal_run(
        rec=rec,
        ham_actor=ham_actor,
        project_root=project_root,
        proposal_digest=proposal_digest,
        change_id=change_id,
        ham_run_id=ham_run_id,
        status="failed",
        status_reason="opencode:output_requires_review",
        summary=summary_text,
        error_summary=error_summary,
        output_ref=None,
    )
    return {
        "kind": "opencode_build_launch",
        "project_id": rec.id,
        "ok": False,
        "ham_run_id": ham_run_id,
        "control_plane_status": "failed",
        "summary": summary_text,
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
            return "succeeded", "opencode:snapshot_emitted"
        if snapshot_outcome == "nothing_to_change":
            return "succeeded", "opencode:nothing_to_change"
        return "failed", "opencode:runner_error"
    if run_status == "permission_denied":
        return "failed", "opencode:permission_denied"
    if run_status == "serve_unavailable":
        return "failed", "opencode:serve_unavailable"
    if run_status == "auth_missing":
        return "failed", "opencode:provider_not_configured"
    if run_status == "timeout":
        return "failed", "opencode:runner_error"
    return "failed", "opencode:runner_error"


# ---------------------------------------------------------------------------
# Pydantic bodies
# ---------------------------------------------------------------------------


class OpenCodeBuildPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=180)
    user_prompt: str = Field(min_length=1, max_length=12_000)
    model: str | None = Field(default=None, max_length=180)


class OpenCodeBuildLaunchBody(BaseModel):
    """Launch body. Fields are intentionally optional so the Mission 1
    "disabled shim" 503 envelope keeps firing for callers that have not
    yet been updated to send the digest + base_revision pair (Mission 1
    tests pass ``{project_id, user_prompt}`` only). All required-field
    validation moves into the handler so the disabled-state 503 fires
    before Pydantic's 422.
    """

    model_config = ConfigDict(extra="allow")

    project_id: str | None = Field(default=None, max_length=180)
    user_prompt: str | None = Field(default=None, max_length=12_000)
    model: str | None = Field(default=None, max_length=180)
    proposal_digest: str | None = Field(default=None, max_length=64)
    base_revision: str | None = Field(default=None, max_length=64)
    confirmed: bool = False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _user_facing_summary() -> str:
    return (
        "This action proposes an OpenCode managed workspace edit: HAM brokers "
        "every tool call against a deny-by-default policy, the working tree is "
        "scoped to the project root, and a preview snapshot is captured for you "
        "to review before anything is published."
    )


@router.post("/build/preview")
async def preview_opencode_build(
    body: OpenCodeBuildPreviewBody,
    ham_actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    workspace_store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
) -> dict[str, Any]:
    """Preview an OpenCode managed-workspace edit. No execution; returns a digest."""
    _require_opencode_enabled()
    _require_opencode_execution_enabled()
    rec = _require_build_lane_project(body.project_id)
    _require_managed_workspace_target(rec)
    _require_build_approver(ham_actor, rec, workspace_store)
    _require_opencode_configured(ham_actor)
    digest = compute_opencode_proposal_digest(
        project_id=rec.id,
        user_prompt=body.user_prompt,
        model=body.model,
    )
    return {
        "kind": "opencode_build_preview",
        "project_id": rec.id,
        "project_name": rec.name,
        "user_prompt": body.user_prompt,
        "model": body.model,
        "summary": _user_facing_summary(),
        "proposal_digest": digest,
        "base_revision": OPENCODE_REGISTRY_REVISION,
        "is_readonly": False,
        "will_open_pull_request": False,
        "requires_approval": True,
        "output_target": "managed_workspace",
    }


# Legacy Mission 1 path retained for back-compat: the disabled state is
# detected via :func:`launch_opencode_coding` before either real route is
# reached. Mission 1 tests assert this route returns HTTP 503 with a
# ``detail.reason="opencode:not_implemented"`` envelope whenever execution
# is not fully gated on.
def _build_disabled_legacy_response(actor: HamActor | None, body: Any) -> None:
    result = launch_opencode_coding(
        project_id=getattr(body, "project_id", None),
        user_prompt=getattr(body, "user_prompt", None),
        actor=actor,
    )
    raise HTTPException(
        status_code=503,
        detail={
            "error": {
                "code": "OPENCODE_NOT_IMPLEMENTED",
                "message": "OpenCode live execution is not yet implemented on this host.",
            },
            "status": result.status,
            "reason": result.reason,
            "summary": result.summary,
        },
    )


@router.post("/build/launch")
async def launch_opencode_build(  # noqa: C901
    body: OpenCodeBuildLaunchBody | None = None,
    ham_actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
    workspace_store: Annotated[WorkspaceStore | None, Depends(get_workspace_store)] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> dict[str, Any]:
    """Launch an OpenCode managed-workspace edit. Digest-verified; token-gated."""
    # Mission 1 back-compat: if either feature flag is off, return the
    # 503 disabled-shim envelope without running any gate.
    if not (
        _truthy_env(OPENCODE_ENABLED_ENV_NAME) and _truthy_env(OPENCODE_EXECUTION_ENABLED_ENV_NAME)
    ):
        _build_disabled_legacy_response(ham_actor, body)

    if body is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "OPENCODE_LAUNCH_REQUIRES_BODY",
                    "message": "Approve the launch before sending.",
                }
            },
        )
    if not body.confirmed:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "OPENCODE_LAUNCH_REQUIRES_CONFIRMATION",
                    "message": "Approve the launch before sending.",
                }
            },
        )
    if not (body.project_id and body.user_prompt):
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "OPENCODE_LAUNCH_REQUIRES_BODY",
                    "message": "project_id and user_prompt are required to launch.",
                }
            },
        )
    if not body.proposal_digest or len(body.proposal_digest) != 64:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "OPENCODE_LAUNCH_PREVIEW_STALE",
                    "message": "proposal_digest must be 64-char sha256; re-run preview.",
                }
            },
        )
    if not body.base_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "OPENCODE_LAUNCH_PREVIEW_STALE",
                    "message": "base_revision is required to launch.",
                }
            },
        )

    _require_opencode_enabled()
    _require_opencode_execution_enabled()
    rec = _require_build_lane_project(body.project_id)
    _require_managed_workspace_target(rec)
    assert workspace_store is not None  # noqa: S101 — FastAPI dep always populated.
    _require_build_approver(ham_actor, rec, workspace_store)
    _require_opencode_configured(ham_actor)
    v_err = verify_opencode_launch_against_preview(
        project_id=rec.id,
        user_prompt=body.user_prompt,
        model=body.model,
        proposal_digest=body.proposal_digest,
        base_revision=body.base_revision,
    )
    if v_err:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "OPENCODE_LAUNCH_PREVIEW_STALE",
                    "message": v_err,
                }
            },
        )
    _require_opencode_exec_token(authorization)

    ham_run_id = new_ham_run_id()
    change_id = uuid.uuid4().hex
    project_root = _project_managed_root(rec)

    try:
        ensure_managed_working_tree(
            workspace_id=getattr(rec, "workspace_id", None),
            project_id=rec.id,
        )
    except ManagedWorkspaceSetupError as exc:
        return _persist_workspace_setup_failed_opencode(
            rec=rec,
            ham_actor=ham_actor,
            project_root=project_root,
            proposal_digest=body.proposal_digest,
            setup_error=exc,
            ham_run_id=ham_run_id,
            change_id=change_id,
        )

    run_result = run_opencode_mission(
        project_root=project_root,
        user_prompt=body.user_prompt,
        model=body.model,
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
        would_be_deleted = compute_deleted_paths_against_parent(common)
        if would_be_deleted and not _truthy_env(_OPENCODE_ALLOW_DELETIONS_ENV):
            return _persist_output_requires_review_opencode(
                rec=rec,
                ham_actor=ham_actor,
                project_root=project_root,
                proposal_digest=body.proposal_digest,
                deleted_paths=would_be_deleted,
                change_id=change_id,
                ham_run_id=ham_run_id,
            )
        try:
            snap = emit_managed_workspace_snapshot(common)
        except Exception as exc:  # noqa: BLE001
            _LOG.warning(
                "opencode_build snapshot emit raised %s",
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
                f"opencode run finished with status={run_result.status}",
                cap=2000,
            )
    else:
        error_summary = None

    _persist_opencode_terminal_run(
        rec=rec,
        ham_actor=ham_actor,
        project_root=project_root,
        proposal_digest=body.proposal_digest,
        change_id=change_id,
        ham_run_id=ham_run_id,
        status=status,
        status_reason=status_reason,
        summary=summary_text,
        error_summary=error_summary,
        output_ref=output_ref,
    )

    return {
        "kind": "opencode_build_launch",
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
    "OPENCODE_REGISTRY_REVISION",
    "compute_opencode_proposal_digest",
    "router",
    "verify_opencode_launch_against_preview",
]
