from __future__ import annotations

import pytest

from src.ham.browser_runtime.sessions import (
    BrowserPolicyError,
    BrowserScreenshotTooLargeError,
    BrowserSessionConflictError,
    BrowserSessionManager,
    BrowserSessionNotFoundError,
    BrowserSessionOwnerMismatchError,
)


class _FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"
        self._title = "Blank"
        self.fail_next_goto = False
        self.mouse = _FakeMouse()
        self.keyboard = _FakeKeyboard()

    def goto(self, url: str, wait_until: str, timeout: int) -> None:
        if self.fail_next_goto:
            self.fail_next_goto = False
            raise RuntimeError("goto failed")
        self.url = url
        self._title = "Loaded Page"

    def click(self, selector: str, timeout: int) -> None:
        if not selector:
            raise RuntimeError("empty selector")

    def fill(self, selector: str, text: str, timeout: int) -> None:
        if not selector:
            raise RuntimeError("empty selector")

    def type(self, selector: str, text: str, timeout: int) -> None:
        if not selector:
            raise RuntimeError("empty selector")

    def screenshot(self, type: str, full_page: bool) -> bytes:
        return b"\x89PNG\r\n\x1a\nfake"

    def title(self) -> str:
        return self._title


class _FakeContext:
    def __init__(self) -> None:
        self.page = _FakePage()

    def new_page(self) -> _FakePage:
        return self.page

    def close(self) -> None:
        return None


class _FakeBrowser:
    def __init__(self) -> None:
        self.contexts: list[_FakeContext] = []

    def new_context(self, viewport: dict[str, int]) -> _FakeContext:
        ctx = _FakeContext()
        self.contexts.append(ctx)
        return ctx


class _FakeMouse:
    def click(self, x: float, y: float, button: str = "left") -> None:
        _ = (x, y, button)

    def wheel(self, delta_x: float, delta_y: float) -> None:
        _ = (delta_x, delta_y)


class _FakeKeyboard:
    def press(self, key: str) -> None:
        _ = key


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> BrowserSessionManager:
    monkeypatch.delenv("HAM_BROWSER_ALLOW_PRIVATE_NETWORK", raising=False)
    monkeypatch.delenv("HAM_BROWSER_ALLOWED_DOMAINS", raising=False)
    monkeypatch.delenv("HAM_BROWSER_BLOCKED_DOMAINS", raising=False)
    monkeypatch.setenv("HAM_BROWSER_MAX_SCREENSHOT_BYTES", "100000")
    mgr = BrowserSessionManager()
    fake_browser = _FakeBrowser()
    monkeypatch.setattr(mgr, "_ensure_browser", lambda: fake_browser)
    return mgr


def test_create_get_reset_close_session(manager: BrowserSessionManager) -> None:
    created = manager.create_session(owner_key="pane_a")
    sid = created["session_id"]
    state = manager.get_state(session_id=sid, owner_key="pane_a")
    assert state["ownership"] == "pane_owner_key"
    assert state["runtime_host"] == "ham_api_local"
    reset_state = manager.reset(session_id=sid, owner_key="pane_a")
    assert reset_state["current_url"] == "about:blank"
    manager.close_session(session_id=sid, owner_key="pane_a")
    with pytest.raises(BrowserSessionNotFoundError):
        manager.get_state(session_id=sid, owner_key="pane_a")


def test_navigate_success_and_fail_sets_error(manager: BrowserSessionManager) -> None:
    created = manager.create_session(owner_key="pane_a")
    sid = created["session_id"]
    ok = manager.navigate(session_id=sid, owner_key="pane_a", url="https://example.com")
    assert ok["current_url"] == "https://example.com"
    rec = manager._sessions[sid]
    rec.page.fail_next_goto = True
    with pytest.raises(Exception):
        manager.navigate(session_id=sid, owner_key="pane_a", url="https://example.com/page")
    assert manager._sessions[sid].status == "error"
    with pytest.raises(BrowserSessionConflictError):
        manager.click(session_id=sid, owner_key="pane_a", selector="button")


def test_owner_key_enforcement(manager: BrowserSessionManager) -> None:
    sid = manager.create_session(owner_key="pane_a")["session_id"]
    with pytest.raises(BrowserSessionOwnerMismatchError):
        manager.get_state(session_id=sid, owner_key="pane_b")


def test_policy_blocks_private_local_by_default(manager: BrowserSessionManager) -> None:
    sid = manager.create_session(owner_key="pane_a")["session_id"]
    with pytest.raises(BrowserPolicyError):
        manager.navigate(session_id=sid, owner_key="pane_a", url="http://localhost:3000")


def test_policy_blocks_domain_and_subdomain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_BROWSER_BLOCKED_DOMAINS", "example.com")
    mgr = BrowserSessionManager()
    monkeypatch.setattr(mgr, "_ensure_browser", lambda: _FakeBrowser())
    sid = mgr.create_session(owner_key="pane_a")["session_id"]
    with pytest.raises(BrowserPolicyError):
        mgr.navigate(session_id=sid, owner_key="pane_a", url="https://sub.example.com/path")


def test_invalid_scheme_rejected(manager: BrowserSessionManager) -> None:
    sid = manager.create_session(owner_key="pane_a")["session_id"]
    with pytest.raises(BrowserPolicyError):
        manager.navigate(session_id=sid, owner_key="pane_a", url="file:///etc/hosts")


def test_click_and_type(manager: BrowserSessionManager) -> None:
    sid = manager.create_session(owner_key="pane_a")["session_id"]
    click_state = manager.click(session_id=sid, owner_key="pane_a", selector="button")
    assert click_state["status"] == "ready"
    type_state = manager.type_text(
        session_id=sid,
        owner_key="pane_a",
        selector="input[name=q]",
        text="hello",
        clear_first=True,
    )
    assert type_state["status"] == "ready"


def test_screenshot_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BigShotPage(_FakePage):
        def screenshot(self, type: str, full_page: bool) -> bytes:
            return b"\x89PNG" + (b"x" * 40000)

    class _BigShotContext(_FakeContext):
        def __init__(self) -> None:
            self.page = _BigShotPage()

    class _BigShotBrowser(_FakeBrowser):
        def new_context(self, viewport: dict[str, int]) -> _BigShotContext:
            ctx = _BigShotContext()
            self.contexts.append(ctx)
            return ctx

    monkeypatch.setenv("HAM_BROWSER_MAX_SCREENSHOT_BYTES", "32768")
    mgr = BrowserSessionManager()
    monkeypatch.setattr(mgr, "_ensure_browser", lambda: _BigShotBrowser())
    sid = mgr.create_session(owner_key="pane_a")["session_id"]
    with pytest.raises(BrowserScreenshotTooLargeError):
        mgr.screenshot_png(session_id=sid, owner_key="pane_a")


def test_stream_and_interactive_input_paths(manager: BrowserSessionManager) -> None:
    sid = manager.create_session(owner_key="pane_a")["session_id"]

    started = manager.start_stream(
        session_id=sid,
        owner_key="pane_a",
        requested_transport="screenshot_loop",
    )
    assert started["status"] == "live"
    assert started["mode"] == "screenshot_loop"

    click_state = manager.click_xy(session_id=sid, owner_key="pane_a", x=120, y=80)
    assert click_state["status"] == "ready"

    scroll_state = manager.scroll(session_id=sid, owner_key="pane_a", delta_x=0, delta_y=150)
    assert scroll_state["status"] == "ready"

    key_state = manager.key_press(session_id=sid, owner_key="pane_a", key="Enter")
    assert key_state["status"] == "ready"

    stopped = manager.stop_stream(session_id=sid, owner_key="pane_a")
    assert stopped["status"] == "disconnected"
