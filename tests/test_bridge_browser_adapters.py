from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.bridge.browser_adapters import (
    ChromiumBrowserExecutor,
    PlaywrightBrowserExecutor,
    build_browser_executor,
    resolve_browser_adapter_name,
)
from src.bridge.contracts import BrowserStepSpec


def test_resolve_browser_adapter_name_with_fallback():
    assert resolve_browser_adapter_name("playwright") == "playwright"
    assert resolve_browser_adapter_name("chromium") == "chromium"
    assert resolve_browser_adapter_name("unknown") == "playwright"


def test_build_browser_executor_variants():
    assert isinstance(build_browser_executor("playwright"), PlaywrightBrowserExecutor)
    assert isinstance(build_browser_executor("chromium"), ChromiumBrowserExecutor)


@dataclass
class _FakeManager:
    calls: list[str] = field(default_factory=list)
    session_id: str = "brs_test_123"

    def create_session(self, *, owner_key: str, operator_mode: bool = False) -> dict[str, Any]:
        self.calls.append(f"create_session:{owner_key}:{operator_mode}")
        return {
            "session_id": self.session_id,
            "current_url": "about:blank",
            "title": "",
            "last_error": None,
        }

    def navigate(self, *, session_id: str, owner_key: str, url: str) -> dict[str, Any]:
        self.calls.append(f"navigate:{session_id}:{owner_key}:{url}")
        return {
            "session_id": session_id,
            "current_url": url,
            "title": "Page",
            "last_error": None,
        }

    def click(self, *, session_id: str, owner_key: str, selector: str) -> dict[str, Any]:
        self.calls.append(f"click:{session_id}:{owner_key}:{selector}")
        return {
            "session_id": session_id,
            "current_url": "https://example.com",
            "title": "Page",
            "last_error": None,
        }

    def type_text(
        self, *, session_id: str, owner_key: str, selector: str, text: str, clear_first: bool
    ) -> dict[str, Any]:
        self.calls.append(f"type:{session_id}:{owner_key}:{selector}:{text}:{clear_first}")
        return {
            "session_id": session_id,
            "current_url": "https://example.com",
            "title": "Typed",
            "last_error": None,
        }

    def screenshot_png(self, *, session_id: str, owner_key: str) -> bytes:
        self.calls.append(f"screenshot:{session_id}:{owner_key}")
        return b"png-bytes"

    def get_state(self, *, session_id: str, owner_key: str) -> dict[str, Any]:
        self.calls.append(f"state:{session_id}:{owner_key}")
        return {
            "session_id": session_id,
            "current_url": "https://example.com/after",
            "title": "After",
            "last_error": None,
        }

    def close_session(self, *, session_id: str, owner_key: str) -> None:
        self.calls.append(f"close:{session_id}:{owner_key}")


def test_playwright_executor_maps_actions(monkeypatch):
    fake = _FakeManager()

    import src.bridge.browser_adapters as mod

    monkeypatch.setattr(mod, "get_browser_runtime_manager", lambda: fake)
    monkeypatch.setattr(mod, "run_browser_io", lambda fn: fn())

    exe = PlaywrightBrowserExecutor()
    nav = exe.execute_step(
        BrowserStepSpec(step_id="s1", action="navigate", args={"url": "https://example.com"}),
        timeout_ms=1000,
    )
    clk = exe.execute_step(
        BrowserStepSpec(step_id="s2", action="click", args={"selector": "#go"}),
        timeout_ms=1000,
    )
    fill = exe.execute_step(
        BrowserStepSpec(
            step_id="s3",
            action="fill",
            args={"selector": "#q", "value": "ham", "clear_first": True},
        ),
        timeout_ms=1000,
    )
    shot = exe.execute_step(
        BrowserStepSpec(step_id="s4", action="screenshot", args={}),
        timeout_ms=1000,
    )
    unsupported = exe.execute_step(
        BrowserStepSpec(step_id="s5", action="extract_text", args={"selector": "main"}),
        timeout_ms=1000,
    )
    exe.close()

    assert nav["status"] == "executed"
    assert clk["status"] == "executed"
    assert fill["status"] == "executed"
    assert shot["status"] == "executed"
    assert "in_memory_png:" in str(shot.get("screenshot_path", ""))
    assert unsupported["status"] == "blocked"
    assert any(c.startswith("create_session:") for c in fake.calls)
    assert any(c.startswith("close:") for c in fake.calls)
