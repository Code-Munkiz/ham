"""Readiness collator for the HAM Coding Router (Phase 1).

Reduces every "is provider X usable?" question to a small, redacted bool +
human blocker copy. **Never** returns secret values, internal workflow ids,
runner URLs, env-name strings, or argv. Operator-only signals (``runner_kind``,
``token_configured``, ``auth_kind``) are populated only when the caller
explicitly opts in via ``include_operator_details=True``; non-operator
surfaces in :class:`WorkspaceReadiness.public_dict` strip them again as a
defence-in-depth pass.

This module is allowed to import the various provider clients and inspect
``os.environ`` because that is the entire point — it is the *one place*
that translates messy provider state into clean booleans for the rest of
the Coding Router.
"""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

from src.ham.coding_router.claude_agent_provider import (
    build_claude_agent_readiness as _build_claude_agent_readiness,
)
from src.ham.coding_router.opencode_provider import (
    build_opencode_readiness as _build_opencode_readiness,
)
from src.ham.coding_router.types import (
    ProjectFlags,
    ProviderReadiness,
    WorkspaceAgentPolicy,
    WorkspaceReadiness,
)

if TYPE_CHECKING:
    from src.ham.clerk_auth import HamActor

# Generic, normie-safe blocker copy. None of these strings name an env var,
# secret value, runner URL, internal workflow id, or argv flag.
_BLOCKER_NO_PROJECT = "Pick a project before launching this kind of work."
_BLOCKER_PROJECT_NO_GH = "This project has no GitHub repository configured."
_BLOCKER_PROJECT_BUILD_DISABLED = (
    "Build lane is disabled for this project. A workspace operator must enable it in Settings."
)
_BLOCKER_DROID_RUNNER = (
    "Factory Droid is not configured on this host. Contact your workspace operator."
)
_BLOCKER_BUILD_LANE_HOST = (
    "The Factory Droid build lane is not configured on this host yet. "
    "Contact your workspace operator."
)
_BLOCKER_CURSOR_KEY = "Cursor team key is not configured for this workspace."
_BLOCKER_CLAUDE_SDK = "Claude Code is not available on this host."
_BLOCKER_CLAUDE_AUTH = "Claude Code is installed, but no authentication channel is configured."


# ---------------------------------------------------------------------------
# Per-provider readiness probes (boolean only; never returns values)
# ---------------------------------------------------------------------------


def _droid_runner_kind() -> str:
    """Return ``remote`` | ``local`` | ``none`` — never a URL or token."""
    if (os.environ.get("HAM_DROID_RUNNER_URL") or "").strip() and (
        os.environ.get("HAM_DROID_RUNNER_TOKEN") or ""
    ).strip():
        return "remote"
    if shutil.which("droid"):
        return "local"
    return "none"


def _droid_audit_workflow_registered() -> bool:
    try:
        from src.ham.droid_workflows.registry import get_workflow

        return get_workflow("readonly_repo_audit") is not None
    except Exception:
        return False


def _droid_build_workflow_registered() -> bool:
    try:
        from src.ham.droid_workflows.registry import get_workflow

        wf = get_workflow("safe_edit_low")
        return wf is not None and wf.mutates and wf.requires_launch_token
    except Exception:
        return False


def _droid_build_token_configured() -> bool:
    """Boolean presence check for the build-lane mutation gate. Never returns the value."""
    return bool((os.environ.get("HAM_DROID_EXEC_TOKEN") or "").strip())


def _cursor_team_key_configured() -> bool:
    """Boolean cast over ``cursor_credentials.get_effective_cursor_api_key``."""
    try:
        from src.persistence.cursor_credentials import get_effective_cursor_api_key

        return bool(get_effective_cursor_api_key())
    except Exception:
        return False


def _cursor_key_source() -> str:
    """``ui`` | ``env`` | ``none`` — never the key value."""
    try:
        from src.persistence.cursor_credentials import key_source

        return key_source()
    except Exception:
        return "none"


def _claude_sdk_available() -> bool:
    try:
        from src.ham.worker_adapters.claude_agent_adapter import (
            check_claude_agent_readiness,
        )

        return bool(check_claude_agent_readiness(None).sdk_available)
    except Exception:
        return False


def _claude_auth_kind(actor: HamActor | None) -> str:
    """``anthropic`` | ``bedrock`` | ``vertex`` | ``none`` — never values."""
    try:
        from src.ham.worker_adapters.claude_agent_adapter import (
            claude_agent_coarse_provider,
            claude_agent_mission_auth_configured,
        )

        if not claude_agent_mission_auth_configured(actor):
            return "none"
        coarse = claude_agent_coarse_provider()
        if coarse == "anthropic_direct":
            return "anthropic"
        if coarse in ("bedrock", "vertex"):
            return coarse
        return "none"
    except Exception:
        return "none"


# ---------------------------------------------------------------------------
# Provider readiness builders
# ---------------------------------------------------------------------------


def _build_no_agent_readiness() -> ProviderReadiness:
    # ``no_agent`` is always available; it just answers via the LLM gateway.
    return ProviderReadiness(
        provider="no_agent",
        available=True,
        blockers=(),
        operator_signals=(),
    )


def _build_audit_readiness(*, include_operator_details: bool) -> ProviderReadiness:
    workflow_ok = _droid_audit_workflow_registered()
    runner_kind = _droid_runner_kind()
    available = workflow_ok and runner_kind != "none"
    blockers: list[str] = []
    if not available:
        blockers.append(_BLOCKER_DROID_RUNNER)
    op_signals: tuple[str, ...] = ()
    if include_operator_details:
        op_signals = (f"runner_kind={runner_kind}", f"workflow_registered={workflow_ok}")
    return ProviderReadiness(
        provider="factory_droid_audit",
        available=available,
        blockers=tuple(blockers),
        operator_signals=op_signals,
    )


def _build_build_readiness(*, include_operator_details: bool) -> ProviderReadiness:
    workflow_ok = _droid_build_workflow_registered()
    runner_kind = _droid_runner_kind()
    token_ok = _droid_build_token_configured()
    available = workflow_ok and runner_kind != "none" and token_ok
    blockers: list[str] = []
    if not available:
        blockers.append(_BLOCKER_BUILD_LANE_HOST)
    op_signals: tuple[str, ...] = ()
    if include_operator_details:
        op_signals = (
            f"runner_kind={runner_kind}",
            f"workflow_registered={workflow_ok}",
            f"token_configured={token_ok}",
        )
    return ProviderReadiness(
        provider="factory_droid_build",
        available=available,
        blockers=tuple(blockers),
        operator_signals=op_signals,
    )


def _build_cursor_readiness(*, include_operator_details: bool) -> ProviderReadiness:
    key_ok = _cursor_team_key_configured()
    blockers = () if key_ok else (_BLOCKER_CURSOR_KEY,)
    op_signals: tuple[str, ...] = ()
    if include_operator_details:
        op_signals = (f"key_source={_cursor_key_source()}",)
    return ProviderReadiness(
        provider="cursor_cloud",
        available=key_ok,
        blockers=blockers,
        operator_signals=op_signals,
    )


def _build_claude_readiness(
    actor: HamActor | None, *, include_operator_details: bool
) -> ProviderReadiness:
    sdk_ok = _claude_sdk_available()
    auth_kind = _claude_auth_kind(actor) if sdk_ok else "none"
    available = sdk_ok and auth_kind != "none"
    blockers: list[str] = []
    if not sdk_ok:
        blockers.append(_BLOCKER_CLAUDE_SDK)
    elif auth_kind == "none":
        blockers.append(_BLOCKER_CLAUDE_AUTH)
    op_signals: tuple[str, ...] = ()
    if include_operator_details:
        op_signals = (f"sdk_available={sdk_ok}", f"auth_kind={auth_kind}")
    return ProviderReadiness(
        provider="claude_code",
        available=available,
        blockers=tuple(blockers),
        operator_signals=op_signals,
    )


# ---------------------------------------------------------------------------
# Project flags lookup
# ---------------------------------------------------------------------------


def _project_flags(project_id: str | None) -> ProjectFlags:
    pid = (project_id or "").strip()
    if not pid:
        return ProjectFlags(found=False, project_id=None)
    try:
        from src.persistence.project_store import get_project_store

        rec = get_project_store().get_project(pid)
    except Exception:
        return ProjectFlags(found=False, project_id=pid)
    if rec is None:
        return ProjectFlags(found=False, project_id=pid)
    target = (getattr(rec, "output_target", None) or "managed_workspace").strip()
    return ProjectFlags(
        found=True,
        project_id=rec.id,
        build_lane_enabled=bool(getattr(rec, "build_lane_enabled", False)),
        has_github_repo=bool((getattr(rec, "github_repo", None) or "").strip()),
        output_target=target or None,
        has_workspace_id=bool((getattr(rec, "workspace_id", None) or "").strip()),
    )


# ---------------------------------------------------------------------------
# Public collator
# ---------------------------------------------------------------------------


# Normie-safe blocker for workspace policy gate.
_BLOCKER_POLICY_DISABLED = (
    "This builder is not enabled for this workspace. Update builder settings to turn it on."
)

# Maps provider kind → which WorkspaceAgentPolicy flag gates it.
# factory_droid_audit and factory_droid_build share the allow_factory_droid flag.
_POLICY_ALLOW_FLAG: dict[str, str] = {
    "factory_droid_audit": "allow_factory_droid",
    "factory_droid_build": "allow_factory_droid",
    "claude_agent": "allow_claude_agent",
    "opencode_cli": "allow_opencode",
    "cursor_cloud": "allow_cursor",
}


def _apply_workspace_policy(
    providers: tuple[ProviderReadiness, ...],
    policy: WorkspaceAgentPolicy | None,
) -> tuple[ProviderReadiness, ...]:
    """Demote providers that the workspace policy has disabled.

    When a provider is disabled by policy it stays in the list as a blocked
    candidate (so the chat card can render "blocked because…") but its
    ``available`` flag is set to ``False`` and a normie-safe policy blocker
    is appended. ``no_agent`` is always allowed regardless of policy.
    """
    if policy is None:
        return providers

    result: list[ProviderReadiness] = []
    for p in providers:
        flag_name = _POLICY_ALLOW_FLAG.get(p.provider)
        if flag_name is None:
            result.append(p)
            continue
        allowed = getattr(policy, flag_name, True)
        if allowed:
            result.append(p)
        else:
            result.append(
                ProviderReadiness(
                    provider=p.provider,
                    available=False,
                    blockers=(*p.blockers, _BLOCKER_POLICY_DISABLED),
                    operator_signals=p.operator_signals,
                )
            )
    return tuple(result)


def collate_readiness(
    *,
    actor: HamActor | None = None,
    project_id: str | None = None,
    include_operator_details: bool = False,
    workspace_policy: WorkspaceAgentPolicy | None = None,
) -> WorkspaceReadiness:
    """Build a :class:`WorkspaceReadiness` snapshot for the calling context.

    ``include_operator_details`` should be passed only after the caller has
    confirmed the actor is a workspace operator. The caller is also
    responsible for setting :attr:`WorkspaceReadiness.is_operator` to match —
    this collator does not authenticate; it just refuses to populate
    operator-only signals when ``include_operator_details=False``.

    ``workspace_policy`` carries workspace-level allow/deny flags for each
    provider. When ``None``, no policy is applied and platform readiness alone
    determines availability (preserving pre-settings behavior).
    """
    providers: tuple[ProviderReadiness, ...] = (
        _build_no_agent_readiness(),
        _build_audit_readiness(include_operator_details=include_operator_details),
        _build_build_readiness(include_operator_details=include_operator_details),
        _build_cursor_readiness(include_operator_details=include_operator_details),
        _build_claude_readiness(actor, include_operator_details=include_operator_details),
        _build_claude_agent_readiness(actor, include_operator_details=include_operator_details),
        _build_opencode_readiness(actor, include_operator_details=include_operator_details),
    )
    providers = _apply_workspace_policy(providers, workspace_policy)
    return WorkspaceReadiness(
        is_operator=include_operator_details,
        providers=providers,
        project=_project_flags(project_id),
    )


__all__ = ["collate_readiness"]
