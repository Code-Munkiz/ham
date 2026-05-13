"""Claude Agent coding-router provider scaffold (Mission 1).

Disabled-by-default adapter for the ``claude_agent`` coding-router provider.
This module intentionally does **not** import the Claude Agent SDK at module
level, does not run a subprocess, and does not require Anthropic credentials.

All blocker / reason strings exposed here are normie-safe: they never name
env vars, secret values, URLs, internal workflow ids, or argv flags.

Mission 2 will wire a HAM-controlled backend runner that emits
``managed_workspace`` snapshots via the existing GCS + Firestore path; that
work lives behind this same gate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from src.ham.coding_router.types import ProviderReadiness
from src.ham.worker_adapters.claude_agent_adapter import (
    check_claude_agent_readiness,
    claude_agent_coarse_provider,
)

CLAUDE_AGENT_ENABLED_ENV_NAME = "CLAUDE_AGENT_ENABLED"

_BLOCKER_DISABLED = "Claude Agent provider is disabled on this host."
_BLOCKER_SDK_MISSING = "Claude Agent SDK is not installed on this host."
_BLOCKER_NOT_CONFIGURED = "Claude Agent has no Anthropic credentials configured."
_BLOCKER_RUNNER_UNAVAILABLE = "Claude Agent runner is not available yet."


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class ClaudeAgentLaunchResult:
    status: Literal["disabled", "not_implemented"]
    reason: str


def launch_claude_agent_coding(
    *, project_id: str, user_prompt: str
) -> ClaudeAgentLaunchResult:
    """Mission 1 scaffold: Claude Agent provider is disabled. Returns immediately.

    Mission 2 will wire a backend-controlled runner that emits managed_workspace
    snapshots via the existing GCS + Firestore path. This function intentionally
    does NOT import the Claude Agent SDK or run a subprocess.
    """
    return ClaudeAgentLaunchResult(
        status="not_implemented",
        reason="Claude Agent live execution is not implemented yet.",
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
    "ClaudeAgentLaunchResult",
    "build_claude_agent_readiness",
    "launch_claude_agent_coding",
]
