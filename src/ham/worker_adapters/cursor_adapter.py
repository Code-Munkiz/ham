"""Cursor worker adapter — readiness shell only (MVP).

Exposes capabilities and auth-readiness for the Cursor worker entry
in tool discovery. Does NOT launch real coding work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.persistence.cursor_credentials import get_effective_cursor_api_key


@dataclass(frozen=True)
class CursorWorkerCapabilities:
    """Capabilities the Cursor worker can provide when ready."""

    can_plan: bool = True
    can_edit_code: bool = True
    can_run_tests: bool = True
    can_open_pr: bool = True
    requires_project_root: bool = True
    requires_auth: bool = True
    launch_mode: Literal["cloud_agent"] = "cloud_agent"


@dataclass
class CursorWorkerReadiness:
    """Current readiness state of the Cursor worker."""

    authenticated: bool = False
    status: Literal["ready", "needs_sign_in", "unavailable"] = "needs_sign_in"
    capabilities: CursorWorkerCapabilities = field(default_factory=CursorWorkerCapabilities)
    reason: str | None = None


def check_cursor_readiness() -> CursorWorkerReadiness:
    """Check if Cursor worker is ready (has valid credentials).

    This does NOT launch a real agent or make external API calls.
    It only checks local credential availability.
    """
    caps = CursorWorkerCapabilities()

    try:
        key = get_effective_cursor_api_key()
    except Exception:
        key = None

    if key:
        return CursorWorkerReadiness(
            authenticated=True,
            status="ready",
            capabilities=caps,
            reason=None,
        )

    return CursorWorkerReadiness(
        authenticated=False,
        status="needs_sign_in",
        capabilities=caps,
        reason="Cursor API key not configured. Add it in Settings.",
    )


def is_cursor_launchable(readiness: CursorWorkerReadiness | None = None) -> bool:
    """Check if the Cursor worker would be launchable.

    In this MVP, even a 'ready' worker does NOT actually launch.
    This is a policy gate for future use.
    """
    if readiness is None:
        readiness = check_cursor_readiness()
    return readiness.authenticated and readiness.status == "ready"
