"""
In-process dispatch helper for approved Browser Operator proposals.

The dispatch helper calls :class:`BrowserSessionManager` action methods *directly*
(via :func:`run_browser_io`), bypassing the HTTP route-layer
``operator_mode_required`` 409 gate. This is the only intended bypass and it
is **not** reachable from the frontend — there is no spoofable header, query
param, or body field that performs the bypass.

Validation is shared with the raw browser API where possible:

* ``browser.navigate``     → re-enforces ``BrowserSessionManager`` domain policy.
* ``browser.click_xy``     → re-enforces viewport bounds inside the manager.
* ``browser.type``         → reuses manager fill/type with same caps.
* ``browser.scroll`` / ``browser.key`` / ``browser.reset`` → manager-side checks.

No proposal data flows back to clients beyond the proposal record itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.ham.browser_runtime.service import get_browser_runtime_manager, run_browser_io
from src.ham.browser_runtime.sessions import (
    BrowserPolicyError,
    BrowserSessionConflictError,
    BrowserSessionError,
    BrowserSessionNotFoundError,
    BrowserSessionOwnerMismatchError,
)
from src.persistence.browser_proposal import BrowserActionProposal


@dataclass
class DispatchResult:
    ok: bool
    state: dict[str, Any] | None
    error_kind: str | None
    error_message: str | None


_NOT_FOUND = "not_found"
_OWNER_MISMATCH = "owner_mismatch"
_POLICY = "policy"
_CONFLICT = "conflict"
_RUNTIME = "runtime"
_UNKNOWN = "unknown"
_UNSUPPORTED = "unsupported_action"


def _classify(exc: Exception) -> str:
    if isinstance(exc, BrowserSessionNotFoundError):
        return _NOT_FOUND
    if isinstance(exc, BrowserSessionOwnerMismatchError):
        return _OWNER_MISMATCH
    if isinstance(exc, BrowserPolicyError):
        return _POLICY
    if isinstance(exc, BrowserSessionConflictError):
        return _CONFLICT
    if isinstance(exc, BrowserSessionError):
        return _RUNTIME
    return _UNKNOWN


def dispatch_approved_proposal(proposal: BrowserActionProposal) -> DispatchResult:
    """
    Execute an already-approved proposal against the Browser runtime manager.

    Caller is responsible for state transitions on the persisted proposal. This
    helper does **not** mutate the proposal record; it only returns a
    :class:`DispatchResult` describing the outcome.
    """
    manager = get_browser_runtime_manager()
    a = proposal.action
    sid = proposal.session_id
    ok = proposal.owner_key

    try:
        if a.action_type == "browser.navigate":
            url = (a.url or "").strip()
            if not url:
                return DispatchResult(False, None, _POLICY, "url is required")
            state = run_browser_io(
                lambda: manager.navigate(session_id=sid, owner_key=ok, url=url)
            )
        elif a.action_type == "browser.click_xy":
            if a.x is None or a.y is None:
                return DispatchResult(False, None, _POLICY, "x and y are required")
            x = float(a.x)
            y = float(a.y)
            state = run_browser_io(
                lambda: manager.click_xy(
                    session_id=sid, owner_key=ok, x=x, y=y, button="left"
                )
            )
        elif a.action_type == "browser.scroll":
            dx = float(a.delta_x or 0.0)
            dy = float(a.delta_y or 0.0)
            state = run_browser_io(
                lambda: manager.scroll(
                    session_id=sid, owner_key=ok, delta_x=dx, delta_y=dy
                )
            )
        elif a.action_type == "browser.key":
            key = (a.key or "").strip()
            if not key:
                return DispatchResult(False, None, _POLICY, "key is required")
            state = run_browser_io(
                lambda: manager.key_press(session_id=sid, owner_key=ok, key=key)
            )
        elif a.action_type == "browser.type":
            sel = (a.selector or "").strip()
            if not sel:
                return DispatchResult(False, None, _POLICY, "selector is required")
            text = a.text or ""
            clear_first = True if a.clear_first is None else bool(a.clear_first)
            state = run_browser_io(
                lambda: manager.type_text(
                    session_id=sid,
                    owner_key=ok,
                    selector=sel,
                    text=text,
                    clear_first=clear_first,
                )
            )
        elif a.action_type == "browser.reset":
            state = run_browser_io(
                lambda: manager.reset(session_id=sid, owner_key=ok)
            )
        else:
            return DispatchResult(False, None, _UNSUPPORTED, f"unsupported action_type: {a.action_type}")
    except Exception as exc:  # noqa: BLE001 — we map all known runtime exceptions
        return DispatchResult(False, None, _classify(exc), str(exc))

    return DispatchResult(True, state, None, None)


__all__ = [
    "DispatchResult",
    "dispatch_approved_proposal",
]
