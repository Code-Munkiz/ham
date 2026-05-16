"""OpenCode coding-router provider — Mission 2 gated runner.

The readiness builder (:func:`build_opencode_readiness`) remains the
disabled-by-default scaffold introduced in Mission 1 (no live execution
is implied just because the readiness probe is configured).

:func:`launch_opencode_coding` is the **in-process synchronous facade**
that mirrors :func:`src.ham.coding_router.claude_agent_provider.launch_claude_agent_coding`.
It is dormant unless **both** ``HAM_OPENCODE_ENABLED`` and
``HAM_OPENCODE_EXECUTION_ENABLED`` are truthy. When live, it provisions
the managed working tree, drives the bounded
:func:`src.ham.opencode_runner.run_opencode_mission` call, enforces the
Mission 3.1 deletion guard, and writes one terminal ``ControlPlaneRun``.

External callers should prefer ``POST /api/opencode/build/launch``
(:mod:`src.api.opencode_build`); that route runs the full gate stack
including Clerk approval and the ``HAM_OPENCODE_EXEC_TOKEN`` Bearer
header. This facade exists so the conductor / router invariant keeps
holding for non-HTTP callers.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from src.ham.coding_router.types import ProviderReadiness
from src.ham.worker_adapters.claude_agent_adapter import _redact_diagnostic_text
from src.ham.worker_adapters.opencode_adapter import (
    OPENCODE_ENABLED_ENV_NAME,
    OpenCodeStatus,
    check_opencode_readiness,
)

_LOG = logging.getLogger(__name__)

OPENCODE_EXECUTION_ENABLED_ENV_NAME = "HAM_OPENCODE_EXECUTION_ENABLED"
OPENCODE_ALLOW_DELETIONS_ENV_NAME = "HAM_OPENCODE_ALLOW_DELETIONS"
# Presence of this env var is required for the launch proxy to accept build requests.
OPENCODE_EXEC_TOKEN_ENV = "HAM_OPENCODE_EXEC_TOKEN"  # noqa: S105
OPENCODE_REGISTRY_REVISION = "opencode-v1"

_BLOCKER_DISABLED = "OpenCode provider is disabled on this host."
_BLOCKER_CLI_MISSING = "OpenCode CLI is not installed on this host."
_BLOCKER_AUTH_MISSING = "OpenCode has no model-provider credentials configured."
_BLOCKER_NOT_IMPLEMENTED = "OpenCode live execution is not yet enabled on this host."
_BLOCKER_EXECUTION_DISABLED = "OpenCode execution is paused for this host. An admin must enable it."
_BLOCKER_EXEC_TOKEN_MISSING = (
    "OpenCode build lane is not configured on this host. Contact your workspace operator."  # noqa: S105
)


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class OpenCodeLaunchResult:
    """In-process facade outcome for the OpenCode launch shim.

    Mission 1 emitted only ``disabled`` / ``not_implemented``. Mission 2
    extends the status alphabet to mirror Claude Agent's terminal
    branches.
    """

    status: Literal[
        "disabled",
        "not_implemented",
        "provider_not_configured",
        "workspace_setup_failed",
        "output_requires_review",
        "snapshot_emitted",
        "nothing_to_change",
        "permission_denied",
        "serve_unavailable",
        "runner_error",
        "success",
        "failure",
    ]
    reason: str
    summary: str | None = None
    ham_run_id: str | None = None


def _status_reason_from_run(run_status: str, snapshot_outcome: str | None) -> tuple[str, str]:
    if run_status == "success":
        if snapshot_outcome == "succeeded":
            return "succeeded", "opencode:snapshot_emitted"
        if snapshot_outcome == "nothing_to_change":
            return "succeeded", "opencode:nothing_to_change"
        return "failed", "opencode:runner_error"
    if run_status == "permission_denied":
        return "failed", "opencode:permission_denied"
    if run_status == "timeout":
        return "failed", "opencode:runner_error"
    if run_status == "serve_unavailable":
        return "failed", "opencode:serve_unavailable"
    if run_status == "auth_missing":
        return "failed", "opencode:provider_not_configured"
    if run_status == "provider_not_configured":
        return "failed", "opencode:provider_not_configured"
    if run_status == "session_no_completion":
        return "failed", "opencode:session_no_completion"
    if run_status == "disabled":
        return "failed", "opencode:execution_disabled"
    return "failed", "opencode:runner_error"


def launch_opencode_coding(  # noqa: C901
    *,
    project_id: str | None = None,
    user_prompt: str | None = None,
    actor: object | None = None,
) -> OpenCodeLaunchResult:
    """Synchronous facade for the OpenCode coding-router provider.

    Returns ``disabled`` unless both ``HAM_OPENCODE_ENABLED`` and
    ``HAM_OPENCODE_EXECUTION_ENABLED`` are truthy. When live, mirrors the
    Mission 2.x Claude Agent flow: ensure managed working tree, run the
    bounded runner, apply the deletion guard, then snapshot. Never raises.
    """
    try:
        if not _truthy_env(OPENCODE_ENABLED_ENV_NAME):
            return OpenCodeLaunchResult(
                status="disabled",
                reason="opencode:not_implemented",
                summary="OpenCode is not yet enabled in this build.",
            )
        if not _truthy_env(OPENCODE_EXECUTION_ENABLED_ENV_NAME):
            return OpenCodeLaunchResult(
                status="not_implemented",
                reason="opencode:not_implemented",
                summary="OpenCode live execution is not enabled on this host yet.",
            )

        readiness = check_opencode_readiness(actor)
        if readiness.status != OpenCodeStatus.CONFIGURED:
            return OpenCodeLaunchResult(
                status="provider_not_configured",
                reason="opencode:provider_not_configured",
                summary=readiness.reason or _BLOCKER_NOT_IMPLEMENTED,
            )

        from src.persistence.project_store import get_project_store

        rec = get_project_store().get_project((project_id or "").strip())
        if rec is None:
            return OpenCodeLaunchResult(
                status="not_implemented",
                reason="opencode:project_not_found",
                summary="Unknown project for OpenCode launch.",
            )
        target = (getattr(rec, "output_target", None) or "managed_workspace").strip()
        if target != "managed_workspace":
            return OpenCodeLaunchResult(
                status="not_implemented",
                reason="opencode:not_managed_workspace",
                summary="OpenCode requires a managed_workspace project.",
            )
        wid = (getattr(rec, "workspace_id", None) or "").strip()
        pid = (rec.id or "").strip()
        if not wid or not pid:
            return OpenCodeLaunchResult(
                status="not_implemented",
                reason="opencode:missing_workspace_assignment",
                summary="Managed-workspace project is missing workspace assignment.",
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
        from src.persistence.control_plane_run import (
            ControlPlaneRun,
            cap_error_summary,
            cap_summary,
            get_control_plane_run_store,
            new_ham_run_id,
            utc_now_iso,
        )

        try:
            project_root = managed_working_dir(wid, pid)
        except ValueError as exc:
            return OpenCodeLaunchResult(
                status="not_implemented",
                reason="opencode:missing_workspace_assignment",
                summary=_redact_diagnostic_text(
                    f"managed-workspace project misconfigured: {type(exc).__name__}",
                    cap=400,
                ),
            )

        ham_run_id = new_ham_run_id()
        change_id = uuid.uuid4().hex

        try:
            ensure_managed_working_tree(workspace_id=wid, project_id=pid)
        except ManagedWorkspaceSetupError as exc:
            return _persist_workspace_setup_failed_opencode(
                rec=rec,
                project_root=project_root,
                ham_run_id=ham_run_id,
                change_id=change_id,
                setup_error=exc,
                store_factory=get_control_plane_run_store,
                control_plane_run_cls=ControlPlaneRun,
                cap_error_summary=cap_error_summary,
                utc_now_iso=utc_now_iso,
            )

        log_context = {
            "ham_run_id": ham_run_id,
            "provider": "opencode_cli",
            "route": "coding_router.launch_opencode_coding",
            "project_id": rec.id,
            "workspace_id": wid,
        }
        run_result = run_opencode_mission(
            project_root=project_root,
            user_prompt=user_prompt or "",
            actor=actor,
            log_context=log_context,
        )

        snapshot_outcome: str | None = None
        output_ref: dict[str, Any] = {}
        snapshot_error: str | None = None

        if run_result.status == "success":
            common = PostExecCommon(
                project_id=rec.id,
                project_root=project_root,
                summary=run_result.assistant_summary or "OpenCode mission finished.",
                change_id=change_id,
                pr_inputs=None,
                workspace_id=wid,
            )
            would_be_deleted = compute_deleted_paths_against_parent(common)
            if would_be_deleted and not _truthy_env(OPENCODE_ALLOW_DELETIONS_ENV_NAME):
                return _persist_output_requires_review_opencode(
                    rec=rec,
                    project_root=project_root,
                    ham_run_id=ham_run_id,
                    change_id=change_id,
                    deleted_paths=would_be_deleted,
                    store_factory=get_control_plane_run_store,
                    control_plane_run_cls=ControlPlaneRun,
                    cap_summary=cap_summary,
                    cap_error_summary=cap_error_summary,
                    utc_now_iso=utc_now_iso,
                )
            try:
                snap = emit_managed_workspace_snapshot(common)
            except Exception as exc:  # noqa: BLE001
                _LOG.warning(
                    "opencode_provider snapshot emit raised %s",
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

        status, status_reason = _status_reason_from_run(run_result.status, snapshot_outcome)

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

        now = utc_now_iso()
        project_root_str = str(Path(project_root).resolve())
        cp_run = ControlPlaneRun(
            ham_run_id=ham_run_id,
            provider="opencode_cli",
            action_kind="launch",
            project_id=rec.id,
            created_by=None,
            created_at=now,
            updated_at=now,
            committed_at=now,
            started_at=now,
            finished_at=now,
            last_observed_at=now,
            status=status,
            status_reason=status_reason,
            proposal_digest="",
            base_revision=OPENCODE_REGISTRY_REVISION,
            external_id=change_id,
            workflow_id=None,
            summary=cap_summary(run_result.assistant_summary or None),
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
                "opencode_provider control-plane save failed (%s)",
                type(exc).__name__,
            )

        if status == "succeeded":
            if snapshot_outcome == "nothing_to_change":
                return OpenCodeLaunchResult(
                    status="nothing_to_change",
                    reason="opencode:nothing_to_change",
                    summary="OpenCode mission finished without changes.",
                    ham_run_id=ham_run_id,
                )
            return OpenCodeLaunchResult(
                status="snapshot_emitted",
                reason="opencode:snapshot_emitted",
                summary=(
                    "OpenCode mission finished and a managed workspace snapshot "
                    "was captured for your review."
                ),
                ham_run_id=ham_run_id,
            )
        if status_reason == "opencode:permission_denied":
            return OpenCodeLaunchResult(
                status="permission_denied",
                reason="opencode:permission_denied",
                summary=error_summary
                or "OpenCode mission halted because HAM policy denied a tool call.",
                ham_run_id=ham_run_id,
            )
        if status_reason == "opencode:serve_unavailable":
            return OpenCodeLaunchResult(
                status="serve_unavailable",
                reason="opencode:serve_unavailable",
                summary=error_summary or "opencode serve did not become healthy.",
                ham_run_id=ham_run_id,
            )
        if status_reason == "opencode:provider_not_configured":
            return OpenCodeLaunchResult(
                status="provider_not_configured",
                reason="opencode:provider_not_configured",
                summary=error_summary or "OpenCode provider was not configured for this launch.",
                ham_run_id=ham_run_id,
            )
        return OpenCodeLaunchResult(
            status="runner_error",
            reason=status_reason,
            summary=error_summary or "OpenCode mission did not complete successfully.",
            ham_run_id=ham_run_id,
        )
    except Exception as exc:  # noqa: BLE001
        _LOG.warning(
            "opencode_provider launch raised %s",
            type(exc).__name__,
        )
        return OpenCodeLaunchResult(
            status="failure",
            reason="opencode:runner_error",
            summary=_redact_diagnostic_text(
                f"OpenCode launch failed: {type(exc).__name__}",
                cap=400,
            ),
        )


def _persist_workspace_setup_failed_opencode(
    *,
    rec: Any,
    project_root: Path,
    ham_run_id: str,
    change_id: str,
    setup_error: Any,
    store_factory: Any,
    control_plane_run_cls: Any,
    cap_error_summary: Any,
    utc_now_iso: Any,
) -> OpenCodeLaunchResult:
    error_summary = _redact_diagnostic_text(setup_error.detail, cap=2000)
    now = utc_now_iso()
    project_root_str = str(Path(project_root).resolve())
    cp_run = control_plane_run_cls(
        ham_run_id=ham_run_id,
        provider="opencode_cli",
        action_kind="launch",
        project_id=rec.id,
        created_by=None,
        created_at=now,
        updated_at=now,
        committed_at=now,
        started_at=now,
        finished_at=now,
        last_observed_at=now,
        status="failed",
        status_reason="opencode:workspace_setup_failed",
        proposal_digest="",
        base_revision=OPENCODE_REGISTRY_REVISION,
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
        store_factory().save(cp_run, project_root_for_mirror=project_root_str)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning(
            "opencode_provider control-plane save failed (%s)",
            type(exc).__name__,
        )
    return OpenCodeLaunchResult(
        status="workspace_setup_failed",
        reason="opencode:workspace_setup_failed",
        summary=error_summary,
        ham_run_id=ham_run_id,
    )


def _persist_output_requires_review_opencode(
    *,
    rec: Any,
    project_root: Path,
    ham_run_id: str,
    change_id: str,
    deleted_paths: tuple[str, ...],
    store_factory: Any,
    control_plane_run_cls: Any,
    cap_summary: Any,
    cap_error_summary: Any,
    utc_now_iso: Any,
) -> OpenCodeLaunchResult:
    preview = ", ".join(deleted_paths[:5])
    suffix = "" if len(deleted_paths) <= 5 else f" (+{len(deleted_paths) - 5} more)"
    plural = "s" if len(deleted_paths) != 1 else ""
    error_summary_raw = (
        f"output_requires_review: {len(deleted_paths)} file{plural} "
        f"would be deleted: {preview}{suffix}"
    )
    error_summary = _redact_diagnostic_text(error_summary_raw, cap=2000)
    summary_text = "OpenCode proposed deleting files, so HAM stopped before saving this version."
    now = utc_now_iso()
    project_root_str = str(Path(project_root).resolve())
    cp_run = control_plane_run_cls(
        ham_run_id=ham_run_id,
        provider="opencode_cli",
        action_kind="launch",
        project_id=rec.id,
        created_by=None,
        created_at=now,
        updated_at=now,
        committed_at=now,
        started_at=now,
        finished_at=now,
        last_observed_at=now,
        status="failed",
        status_reason="opencode:output_requires_review",
        proposal_digest="",
        base_revision=OPENCODE_REGISTRY_REVISION,
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
        output_ref=None,
    )
    try:
        store_factory().save(cp_run, project_root_for_mirror=project_root_str)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning(
            "opencode_provider control-plane save failed (%s)",
            type(exc).__name__,
        )
    return OpenCodeLaunchResult(
        status="output_requires_review",
        reason="opencode:output_requires_review",
        summary=summary_text,
        ham_run_id=ham_run_id,
    )


def _opencode_exec_token_configured() -> bool:
    """Boolean presence check for the launch-proxy exec token. Never returns the value."""
    return bool((os.environ.get(OPENCODE_EXEC_TOKEN_ENV) or "").strip())


def build_opencode_readiness(
    actor: object | None = None,
    *,
    include_operator_details: bool = False,
) -> ProviderReadiness:
    """Return ProviderReadiness for the opencode_cli coding-router provider.

    Reports ``available=True`` only when all of:
    - ``HAM_OPENCODE_ENABLED`` is truthy
    - ``HAM_OPENCODE_EXECUTION_ENABLED`` is truthy
    - :func:`check_opencode_readiness` returns ``OpenCodeStatus.CONFIGURED``
    - ``HAM_OPENCODE_EXEC_TOKEN`` is present in the process environment
      (required by the launch proxy; absence means launch would fail with 503)
    """
    enabled = _truthy_env(OPENCODE_ENABLED_ENV_NAME)
    execution_enabled = _truthy_env(OPENCODE_EXECUTION_ENABLED_ENV_NAME)
    if not enabled:
        return ProviderReadiness(
            provider="opencode_cli",
            available=False,
            blockers=(_BLOCKER_DISABLED,),
            operator_signals=(
                ("enabled=false", f"execution_enabled={'true' if execution_enabled else 'false'}")
                if include_operator_details
                else ()
            ),
        )
    readiness = check_opencode_readiness(actor)
    exec_token_ok = _opencode_exec_token_configured()
    blockers: list[str] = []
    if readiness.status == OpenCodeStatus.CLI_MISSING:
        blockers.append(_BLOCKER_CLI_MISSING)
    elif readiness.status == OpenCodeStatus.PROVIDER_AUTH_MISSING:
        blockers.append(_BLOCKER_AUTH_MISSING)
    elif readiness.status != OpenCodeStatus.CONFIGURED:
        blockers.append(_BLOCKER_NOT_IMPLEMENTED)
    if not execution_enabled and not blockers:
        blockers.append(_BLOCKER_EXECUTION_DISABLED)
    if not exec_token_ok and not blockers:
        blockers.append(_BLOCKER_EXEC_TOKEN_MISSING)

    available = (
        enabled
        and execution_enabled
        and exec_token_ok
        and readiness.status == OpenCodeStatus.CONFIGURED
    )

    operator_signals: tuple[str, ...] = ()
    if include_operator_details:
        operator_signals = (
            "enabled=true",
            f"execution_enabled={'true' if execution_enabled else 'false'}",
            f"cli_present={'true' if readiness.cli_present else 'false'}",
            f"status={readiness.status.value}",
            f"exec_token_configured={'true' if exec_token_ok else 'false'}",
        )
    return ProviderReadiness(
        provider="opencode_cli",
        available=available,
        blockers=tuple(blockers),
        operator_signals=operator_signals,
    )


__all__ = [
    "OPENCODE_ALLOW_DELETIONS_ENV_NAME",
    "OPENCODE_ENABLED_ENV_NAME",
    "OPENCODE_EXECUTION_ENABLED_ENV_NAME",
    "OPENCODE_EXEC_TOKEN_ENV",
    "OPENCODE_REGISTRY_REVISION",
    "OpenCodeLaunchResult",
    "build_opencode_readiness",
    "launch_opencode_coding",
]
