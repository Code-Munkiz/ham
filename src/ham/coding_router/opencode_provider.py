"""OpenCode coding-router provider — Mission 1 disabled launch shim.

This module is the sibling of :mod:`src.ham.coding_router.claude_agent_provider`
but is intentionally a no-op facade:

- :func:`launch_opencode_coding` returns an :class:`OpenCodeLaunchResult`
  with ``status="disabled"`` (or ``"not_implemented"`` once the env gate
  is on but no live executor is wired) and ``ham_run_id=None``. It never
  invokes the OpenCode CLI, never opens a socket, never writes to
  Firestore / GCS / audit JSONL, never mints a ``ControlPlaneRun`` row,
  and never raises.
- :func:`build_opencode_readiness` reduces the Mission 1 readiness adapter
  to the conductor's ``ProviderReadiness`` shape with normie-safe blocker
  copy.

Live execution lands in Mission 2; see ``docs/OPENCODE_PROVIDER.md``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from src.ham.coding_router.types import ProviderReadiness
from src.ham.worker_adapters.opencode_adapter import (
    OPENCODE_ENABLED_ENV_NAME,
    OpenCodeStatus,
    check_opencode_readiness,
)

_BLOCKER_DISABLED = "OpenCode provider is disabled on this host."
_BLOCKER_CLI_MISSING = "OpenCode CLI is not installed on this host."
_BLOCKER_AUTH_MISSING = "OpenCode has no model-provider credentials configured."
_BLOCKER_NOT_IMPLEMENTED = "OpenCode live execution is not yet implemented on this host."


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class OpenCodeLaunchResult:
    """In-process facade outcome for the OpenCode launch shim.

    Mission 1 only ever emits ``status="disabled"`` or
    ``status="not_implemented"``; the ``success`` / ``failure`` slots are
    reserved for Mission 2 once a real runner exists. ``ham_run_id`` is
    always ``None`` in Mission 1 — no ``ControlPlaneRun`` row is minted
    for a non-executing shim.
    """

    status: Literal["disabled", "not_implemented", "success", "failure"]
    reason: str
    summary: str | None = None
    ham_run_id: None = None


def launch_opencode_coding(
    *,
    project_id: str | None = None,
    user_prompt: str | None = None,
    actor: object | None = None,
) -> OpenCodeLaunchResult:
    """Return the OpenCode disabled-shim outcome.

    Behavior (Mission 1):

    - When ``HAM_OPENCODE_ENABLED`` is not truthy, returns
      ``status="disabled"``.
    - Otherwise, returns ``status="not_implemented"``.

    Never invokes the OpenCode CLI, never makes a network call, never
    writes any audit / control-plane artefact, and never raises.
    """
    del project_id, user_prompt, actor

    if not _truthy_env(OPENCODE_ENABLED_ENV_NAME):
        return OpenCodeLaunchResult(
            status="disabled",
            reason="opencode:not_implemented",
            summary="OpenCode is not yet enabled in this build.",
        )
    return OpenCodeLaunchResult(
        status="not_implemented",
        reason="opencode:not_implemented",
        summary="OpenCode live execution has not landed on this host yet.",
    )


def build_opencode_readiness(
    actor: object | None = None,
    *,
    include_operator_details: bool = False,
) -> ProviderReadiness:
    """Return ProviderReadiness for the opencode_cli coding-router provider.

    Mission 1: presence-only signals delegated to the worker adapter. The
    provider is treated as unavailable until the env gate is on AND
    readiness reports ``configured``; the recommender layer enforces the
    same invariant as a defence-in-depth check.
    """
    if not _truthy_env(OPENCODE_ENABLED_ENV_NAME):
        return ProviderReadiness(
            provider="opencode_cli",
            available=False,
            blockers=(_BLOCKER_DISABLED,),
            operator_signals=(("enabled=false",) if include_operator_details else ()),
        )
    readiness = check_opencode_readiness(actor)
    blockers: list[str] = []
    if readiness.status == OpenCodeStatus.CLI_MISSING:
        blockers.append(_BLOCKER_CLI_MISSING)
    elif readiness.status == OpenCodeStatus.PROVIDER_AUTH_MISSING:
        blockers.append(_BLOCKER_AUTH_MISSING)
    elif readiness.status != OpenCodeStatus.CONFIGURED:
        blockers.append(_BLOCKER_NOT_IMPLEMENTED)
    # Mission 1 invariant: even a fully "configured" host has no live
    # executor wired yet, so the provider is intentionally not
    # approve-able from the conductor.
    if not blockers:
        blockers.append(_BLOCKER_NOT_IMPLEMENTED)

    operator_signals: tuple[str, ...] = ()
    if include_operator_details:
        operator_signals = (
            "enabled=true",
            f"cli_present={'true' if readiness.cli_present else 'false'}",
            f"status={readiness.status.value}",
        )
    return ProviderReadiness(
        provider="opencode_cli",
        available=False,
        blockers=tuple(blockers),
        operator_signals=operator_signals,
    )


__all__ = [
    "OPENCODE_ENABLED_ENV_NAME",
    "OpenCodeLaunchResult",
    "build_opencode_readiness",
    "launch_opencode_coding",
]
