"""Claude Agent coding-router provider (Mission 2 wiring).

The readiness builder (:func:`build_claude_agent_readiness`) remains the
disabled-by-default scaffold introduced in Mission 1.

:func:`launch_claude_agent_coding` is the **in-process synchronous facade**
for the Mission 1 invariant "provider has a launch shim". It runs the same
:func:`run_claude_agent_mission` the route uses, emits a
``managed_workspace`` snapshot, and persists one ``ControlPlaneRun``. It
**never raises** — every error path collapses into a
:class:`ClaudeAgentLaunchResult`.

External callers should prefer ``POST /api/claude-agent/build/launch``
(:mod:`src.api.claude_agent_build`); that route runs the full gate stack.
This facade exists so the conductor / router invariant continues to hold
and so non-HTTP call sites (operator CLI, future scripted invocations)
have a single, well-tested entry point.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from src.ham.coding_router.types import ProviderReadiness
from src.ham.worker_adapters.claude_agent_adapter import (
    _redact_diagnostic_text,
    check_claude_agent_readiness,
    claude_agent_coarse_provider,
    claude_agent_mission_auth_configured,
)

_LOG = logging.getLogger(__name__)

CLAUDE_AGENT_ENABLED_ENV_NAME = "CLAUDE_AGENT_ENABLED"
CLAUDE_AGENT_REGISTRY_REVISION = "claude-agent-v1"

_BLOCKER_DISABLED = "Claude Agent provider is disabled on this host."
_BLOCKER_SDK_MISSING = "Claude Agent SDK is not installed on this host."
_BLOCKER_NOT_CONFIGURED = "Claude Agent has no Anthropic credentials configured."
_BLOCKER_RUNNER_UNAVAILABLE = "Claude Agent runner is not available yet."


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class ClaudeAgentLaunchResult:
    status: Literal["disabled", "not_implemented", "success", "failure"]
    reason: str
    ham_run_id: str | None = None


def _status_reason_from_run(run_status: str, snapshot_outcome: str | None) -> tuple[str, str]:
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


def _run_mission_sync(
    coro_factory: Any,
) -> Any:
    """Run ``coro_factory()`` to completion regardless of loop state."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        return asyncio.run(coro_factory())
    new_loop = asyncio.new_event_loop()
    try:
        return new_loop.run_until_complete(coro_factory())
    finally:
        new_loop.close()


def launch_claude_agent_coding(  # noqa: C901
    *,
    project_id: str,
    user_prompt: str,
    actor: object | None = None,
) -> ClaudeAgentLaunchResult:
    """Synchronous facade for the Claude Agent coding-router provider.

    Behavior:
    - Returns ``disabled`` when ``CLAUDE_AGENT_ENABLED`` is not truthy.
    - Returns ``not_implemented`` when the project is not a managed-workspace
      project (Claude Agent is managed-workspace-only in Mission 2).
    - When enabled and the project matches: runs the in-process runner and
      emits a snapshot + ``ControlPlaneRun``. Never raises.
    """
    try:
        if not _truthy_env(CLAUDE_AGENT_ENABLED_ENV_NAME):
            return ClaudeAgentLaunchResult(
                status="disabled",
                reason="Claude Agent live execution is disabled on this host.",
            )

        from src.persistence.project_store import get_project_store

        rec = get_project_store().get_project((project_id or "").strip())
        if rec is None:
            return ClaudeAgentLaunchResult(
                status="not_implemented",
                reason="Unknown project for Claude Agent launch.",
            )
        target = (getattr(rec, "output_target", None) or "managed_workspace").strip()
        if target != "managed_workspace":
            return ClaudeAgentLaunchResult(
                status="not_implemented",
                reason="Claude Agent requires a managed_workspace project.",
            )
        wid = (getattr(rec, "workspace_id", None) or "").strip()
        pid = (rec.id or "").strip()
        if not wid or not pid:
            return ClaudeAgentLaunchResult(
                status="not_implemented",
                reason="Managed-workspace project is missing workspace assignment.",
            )

        from src.ham.claude_agent_runner import (
            ClaudeAgentPermissionPolicy,
            run_claude_agent_mission,
        )
        from src.ham.droid_runner.build_lane_output import PostExecCommon
        from src.ham.managed_workspace.paths import managed_working_dir
        from src.ham.managed_workspace.provisioning import (
            ManagedWorkspaceSetupError,
            ensure_managed_working_tree,
        )
        from src.ham.managed_workspace.workspace_adapter import (
            emit_managed_workspace_snapshot,
        )
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
            return ClaudeAgentLaunchResult(
                status="not_implemented",
                reason=_redact_diagnostic_text(
                    f"managed-workspace project misconfigured: {type(exc).__name__}",
                    cap=400,
                ),
            )

        try:
            ensure_managed_working_tree(workspace_id=wid, project_id=pid)
        except ManagedWorkspaceSetupError as exc:
            error_summary = _redact_diagnostic_text(exc.detail, cap=2000)
            now = utc_now_iso()
            ham_run_id = new_ham_run_id()
            project_root_str = str(Path(project_root).resolve())
            change_id = uuid.uuid4().hex
            cp_run = ControlPlaneRun(
                ham_run_id=ham_run_id,
                provider="claude_agent",
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
                status_reason="claude_agent:workspace_setup_failed",
                proposal_digest="",
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
            except Exception as save_exc:
                _LOG.warning(
                    "claude_agent_provider control-plane save failed (%s)",
                    type(save_exc).__name__,
                )
            return ClaudeAgentLaunchResult(
                status="failure",
                reason=error_summary,
                ham_run_id=ham_run_id,
            )

        policy = ClaudeAgentPermissionPolicy(project_root=project_root)
        change_id = uuid.uuid4().hex

        async def _do_run() -> Any:
            return await run_claude_agent_mission(
                project_root=project_root,
                user_prompt=user_prompt,
                policy=policy,
                actor=actor,
            )

        run = _run_mission_sync(_do_run)

        snapshot_outcome: str | None = None
        output_ref: dict[str, Any] = {}
        snapshot_error: str | None = None

        if run.status == "success":
            common = PostExecCommon(
                project_id=rec.id,
                project_root=project_root,
                summary=run.assistant_summary or "Claude Agent mission finished.",
                change_id=change_id,
                pr_inputs=None,
                workspace_id=wid,
            )
            try:
                snap = emit_managed_workspace_snapshot(common)
            except Exception as exc:
                _LOG.warning(
                    "claude_agent_provider snapshot emit raised %s",
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

        status, status_reason = _status_reason_from_run(run.status, snapshot_outcome)

        error_summary: str | None
        if status == "failed":
            if run.error_summary:
                error_summary = run.error_summary
            elif snapshot_error:
                error_summary = snapshot_error
            else:
                error_summary = _redact_diagnostic_text(
                    f"claude_agent run finished with status={run.status}",
                    cap=2000,
                )
        else:
            error_summary = None

        now = utc_now_iso()
        ham_run_id = new_ham_run_id()
        project_root_str = str(Path(project_root).resolve())
        cp_run = ControlPlaneRun(
            ham_run_id=ham_run_id,
            provider="claude_agent",
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
            base_revision=CLAUDE_AGENT_REGISTRY_REVISION,
            external_id=change_id,
            workflow_id=None,
            summary=cap_summary(run.assistant_summary or None),
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
                "claude_agent_provider control-plane save failed (%s)",
                type(exc).__name__,
            )

        if status == "succeeded":
            return ClaudeAgentLaunchResult(
                status="success",
                reason=(
                    "Claude Agent mission finished and a managed workspace "
                    "snapshot was captured for your review."
                ),
                ham_run_id=ham_run_id,
            )
        return ClaudeAgentLaunchResult(
            status="failure",
            reason=error_summary or "Claude Agent mission did not complete successfully.",
            ham_run_id=ham_run_id,
        )
    except Exception as exc:
        _LOG.warning(
            "claude_agent_provider launch raised %s",
            type(exc).__name__,
        )
        return ClaudeAgentLaunchResult(
            status="failure",
            reason=_redact_diagnostic_text(
                f"Claude Agent launch failed: {type(exc).__name__}",
                cap=400,
            ),
        )


def build_claude_agent_readiness(
    actor: object | None = None,
    *,
    include_operator_details: bool = False,
) -> ProviderReadiness:
    """Return ProviderReadiness for the claude_agent coding-router provider.

    Disabled-by-default: if CLAUDE_AGENT_ENABLED is not truthy, returns
    available=False with a normie-safe blocker. Otherwise delegates SDK +
    auth presence detection to claude_agent_adapter (presence-only — no
    secret values returned).
    """
    if not _truthy_env(CLAUDE_AGENT_ENABLED_ENV_NAME):
        return ProviderReadiness(
            provider="claude_agent",
            available=False,
            blockers=(_BLOCKER_DISABLED,),
            operator_signals=(("enabled=false",) if include_operator_details else ()),
        )
    worker = check_claude_agent_readiness(actor)
    blockers: list[str] = []
    if not worker.sdk_available:
        blockers.append(_BLOCKER_SDK_MISSING)
    elif not worker.authenticated:
        blockers.append(_BLOCKER_NOT_CONFIGURED)
    elif not claude_agent_mission_auth_configured(actor):
        blockers.append(_BLOCKER_NOT_CONFIGURED)
    operator_signals: tuple[str, ...] = ()
    if include_operator_details:
        operator_signals = (
            "enabled=true",
            f"sdk_available={'true' if worker.sdk_available else 'false'}",
            f"auth_kind={claude_agent_coarse_provider()}",
        )
    return ProviderReadiness(
        provider="claude_agent",
        available=not blockers,
        blockers=tuple(blockers),
        operator_signals=operator_signals,
    )


__all__ = [
    "CLAUDE_AGENT_ENABLED_ENV_NAME",
    "CLAUDE_AGENT_REGISTRY_REVISION",
    "ClaudeAgentLaunchResult",
    "build_claude_agent_readiness",
    "launch_claude_agent_coding",
]
