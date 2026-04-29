from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from src.bridge.contracts import BrowserStepSpec
from src.ham.browser_runtime.service import get_browser_runtime_manager, run_browser_io


def resolve_browser_adapter_name(raw: str | None) -> str:
    value = (raw or os.environ.get("HAM_BROWSER_ADAPTER") or "playwright").strip().lower()
    if value in {"playwright", "chromium"}:
        return value
    return "playwright"


def build_browser_executor(adapter_name: str | None = None):
    adapter = resolve_browser_adapter_name(adapter_name)
    if adapter == "chromium":
        return ChromiumBrowserExecutor()
    return PlaywrightBrowserExecutor()


@dataclass
class PlaywrightBrowserExecutor:
    """
    Bridge-facing step executor backed by HAM Browser Runtime (Playwright).
    """

    _owner_key: str = "bridge.browser"
    _session_id: str | None = None

    def execute_step(self, step: BrowserStepSpec, *, timeout_ms: int) -> dict[str, Any]:
        session_id = self._ensure_session()
        action = str(step.action.value)
        args = step.args or {}
        if action == "navigate":
            url = str(args.get("url", "")).strip()
            if not url:
                return {"status": "blocked", "error": "navigate step requires args.url"}
            state = run_browser_io(
                lambda: get_browser_runtime_manager().navigate(
                    session_id=session_id,
                    owner_key=self._owner_key,
                    url=url,
                )
            )
            return _state_payload("executed", state)
        if action == "click":
            selector = str(args.get("selector", "")).strip()
            if not selector:
                return {"status": "blocked", "error": "click step requires args.selector"}
            state = run_browser_io(
                lambda: get_browser_runtime_manager().click(
                    session_id=session_id,
                    owner_key=self._owner_key,
                    selector=selector,
                )
            )
            return _state_payload("executed", state)
        if action == "fill":
            selector = str(args.get("selector", "")).strip()
            value = str(args.get("value", ""))
            clear_first = bool(args.get("clear_first", True))
            if not selector:
                return {"status": "blocked", "error": "fill step requires args.selector"}
            state = run_browser_io(
                lambda: get_browser_runtime_manager().type_text(
                    session_id=session_id,
                    owner_key=self._owner_key,
                    selector=selector,
                    text=value,
                    clear_first=clear_first,
                )
            )
            return _state_payload("executed", state)
        if action == "screenshot":
            image = run_browser_io(
                lambda: get_browser_runtime_manager().screenshot_png(
                    session_id=session_id,
                    owner_key=self._owner_key,
                )
            )
            state = run_browser_io(
                lambda: get_browser_runtime_manager().get_state(
                    session_id=session_id,
                    owner_key=self._owner_key,
                )
            )
            out = _state_payload("executed", state)
            out["screenshot_path"] = f"in_memory_png:{len(image)}"
            return out
        if action == "wait_for":
            sleep_for = min(max(timeout_ms, 0), 2_000) / 1000.0
            time.sleep(sleep_for)
            state = run_browser_io(
                lambda: get_browser_runtime_manager().get_state(
                    session_id=session_id,
                    owner_key=self._owner_key,
                )
            )
            return _state_payload("executed", state)

        return {
            "status": "blocked",
            "error": (
                f"Browser action '{action}' is not supported by the playwright adapter. "
                "Supported actions: navigate, click, fill, screenshot, wait_for."
            ),
        }

    def close(self) -> None:
        if not self._session_id:
            return
        sid = self._session_id
        self._session_id = None
        try:
            run_browser_io(
                lambda: get_browser_runtime_manager().close_session(
                    session_id=sid,
                    owner_key=self._owner_key,
                )
            )
        except Exception:  # pylint: disable=broad-exception-caught
            return

    def _ensure_session(self) -> str:
        if self._session_id:
            return self._session_id
        state = run_browser_io(
            lambda: get_browser_runtime_manager().create_session(
                owner_key=self._owner_key,
                operator_mode=False,
            )
        )
        self._session_id = str(state["session_id"])
        return self._session_id


@dataclass
class ChromiumBrowserExecutor(PlaywrightBrowserExecutor):
    """
    Chromium option for bridge adapter selection.

    Current implementation uses the same HAM Browser Runtime service (Playwright
    launching Chromium under the hood), while preserving an explicit adapter
    selection path for future dedicated Chromium/CDP backends.
    """


def _state_payload(status: str, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": status,
        "url_before": state.get("current_url"),
        "url_after": state.get("current_url"),
        "dom_excerpt": f"title={state.get('title', '')}",
        "console_errors": [],
        "network_summary": {},
        "error": state.get("last_error"),
    }
