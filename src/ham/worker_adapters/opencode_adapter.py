"""OpenCode CLI worker adapter — Mission 1 readiness scaffold.

Presence-only readiness probe for the OpenCode CLI lane. This module is the
sibling of :mod:`src.ham.worker_adapters.claude_agent_adapter` but is
intentionally narrower: it performs **only** ``shutil.which`` and
``os.environ.get(...)`` boolean checks. It does not import the OpenCode
CLI, does not call ``subprocess.run``, does not open a socket, and does
not invoke a model.

Mission 1 contract:

- Disabled-by-default via ``HAM_OPENCODE_ENABLED``.
- Status is a 5-state enum (``disabled``, ``not_configured``,
  ``cli_missing``, ``provider_auth_missing``, ``configured``).
- ``integration_modes`` advertises which of the three OpenCode integration
  surfaces (``serve``, ``acp``, ``cli``) are locally reachable; today they
  are all gated by the same ``opencode`` binary so they mirror
  ``cli_present`` until Mission 2 introduces more granular probes.
- Provider auth is checked by env-var presence only. Values are never read
  into a returned field; the dataclass surfaces only the boolean of
  ``bool(os.environ.get(...))``.

Live execution (``opencode serve`` adapter with per-run XDG isolation,
SSE permission interception, HAM-enforced deletion guard at the snapshot
boundary, and BYOK injection from Connected Tools) lands in Mission 2 and
is documented in ``docs/OPENCODE_PROVIDER.md``.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

OPENCODE_ENABLED_ENV_NAME = "HAM_OPENCODE_ENABLED"

_AUTH_ENV_NAMES: tuple[str, ...] = (
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GROQ_API_KEY",
)

_INTEGRATION_MODE_KEYS: tuple[str, ...] = ("serve", "acp", "cli")


class OpenCodeStatus(StrEnum):
    """5-state readiness vocabulary for the OpenCode lane."""

    DISABLED = "disabled"
    NOT_CONFIGURED = "not_configured"
    CLI_MISSING = "cli_missing"
    PROVIDER_AUTH_MISSING = "provider_auth_missing"
    CONFIGURED = "configured"


@dataclass(frozen=True)
class OpenCodeReadiness:
    """Presence-only readiness snapshot for the OpenCode lane.

    Every field carries either a boolean, an enum string, or a short
    human-facing reason. No env value ever flows through this dataclass.
    """

    status: OpenCodeStatus
    enabled: bool
    cli_present: bool
    auth_hints: dict[str, bool] = field(default_factory=dict)
    integration_modes: dict[str, bool] = field(default_factory=dict)
    reason: str | None = None


_CACHE: OpenCodeReadiness | None = None


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _env_present(name: str) -> bool:
    """Boolean cast over ``os.environ`` — never returns the actual value."""
    return bool((os.environ.get(name) or "").strip())


def _opencode_cli_on_path() -> bool:
    return bool(shutil.which("opencode"))


def reset_opencode_readiness_cache() -> None:
    """Clear the cached readiness so the next call re-probes.

    Mirror of :func:`reset_claude_agent_readiness_cache`. Wire into
    ``POST /api/workspace/tools/scan`` so a freshly-installed CLI is
    picked up without a server restart.
    """
    global _CACHE
    _CACHE = None


def _build_auth_hints() -> dict[str, bool]:
    hints: dict[str, bool] = {name: _env_present(name) for name in _AUTH_ENV_NAMES}
    # Reserved Mission 2 slot — Connected Tools BYOK injection. Always
    # False in Mission 1 since the readiness adapter does not consult
    # the per-user Connected Tools record yet.
    hints["byok_via_connected_tools"] = False
    return hints


def _build_integration_modes(cli_present: bool) -> dict[str, bool]:
    """All three modes are gated by the same ``opencode`` binary today.

    Mission 2 may differentiate (e.g. once ``opencode serve`` becomes a
    long-lived sidecar with its own readiness signal); the slot stays
    forward-compat regardless.
    """
    return {key: cli_present for key in _INTEGRATION_MODE_KEYS}


def check_opencode_readiness(actor: Any | None = None) -> OpenCodeReadiness:
    """Check OpenCode lane readiness without invoking any subprocess.

    ``actor`` is accepted for parity with the Claude Agent adapter (it
    will be used in Mission 2 to look up Connected Tools BYOK records);
    it is unused in Mission 1.
    """
    del actor

    global _CACHE
    if _CACHE is not None:
        return _CACHE

    enabled = _truthy_env(OPENCODE_ENABLED_ENV_NAME)
    if not enabled:
        readiness = OpenCodeReadiness(
            status=OpenCodeStatus.DISABLED,
            enabled=False,
            cli_present=False,
            auth_hints=_build_auth_hints(),
            integration_modes=_build_integration_modes(False),
            reason="OpenCode lane is disabled on this host.",
        )
        _CACHE = readiness
        return readiness

    cli_present = _opencode_cli_on_path()
    auth_hints = _build_auth_hints()
    any_auth = any(v for k, v in auth_hints.items() if k != "byok_via_connected_tools")

    if not cli_present:
        readiness = OpenCodeReadiness(
            status=OpenCodeStatus.CLI_MISSING,
            enabled=True,
            cli_present=False,
            auth_hints=auth_hints,
            integration_modes=_build_integration_modes(False),
            reason="OpenCode CLI was not found on PATH.",
        )
        _CACHE = readiness
        return readiness

    if not any_auth:
        readiness = OpenCodeReadiness(
            status=OpenCodeStatus.PROVIDER_AUTH_MISSING,
            enabled=True,
            cli_present=True,
            auth_hints=auth_hints,
            integration_modes=_build_integration_modes(True),
            reason="No model-provider credential is configured for the OpenCode lane.",
        )
        _CACHE = readiness
        return readiness

    readiness = OpenCodeReadiness(
        status=OpenCodeStatus.CONFIGURED,
        enabled=True,
        cli_present=True,
        auth_hints=auth_hints,
        integration_modes=_build_integration_modes(True),
        reason=None,
    )
    _CACHE = readiness
    return readiness


__all__ = [
    "OPENCODE_ENABLED_ENV_NAME",
    "OpenCodeReadiness",
    "OpenCodeStatus",
    "check_opencode_readiness",
    "reset_opencode_readiness_cache",
]
