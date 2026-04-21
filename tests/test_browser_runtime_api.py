from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.browser_runtime.sessions import (
    BrowserPolicyError,
    BrowserSessionConflictError,
    BrowserSessionNotFoundError,
    BrowserSessionOwnerMismatchError,
)


class _FakeManager:
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    def policy_snapshot(self) -> dict[str, Any]:
        return {
            "runtime_host": "ham_api_local",
            "session_ownership": "pane_owner_key",
            "screenshot_transport": "binary_png_endpoint",
            "streaming_supported": True,
            "cursor_embedding_supported": False,
            "supported_live_transports": ["screenshot_loop"],
            "allow_private_network": False,
            "allowed_domains": [],
            "blocked_domains": [],
            "session_ttl_seconds": 900,
            "max_actions_per_minute": 120,
            "max_screenshot_bytes": 5000000,
        }

    def create_session(
        self, *, owner_key: str, viewport_width: int = 1280, viewport_height: int = 720
    ) -> dict[str, Any]:
        _ = (viewport_width, viewport_height)
        sid = "brs_test"
        state = {
            "session_id": sid,
            "status": "ready",
            "last_error": None,
            "current_url": "about:blank",
            "title": "Blank",
            "viewport": {"width": 1280, "height": 720},
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "ownership": "pane_owner_key",
            "runtime_host": "ham_api_local",
            "screenshot_transport": "binary_png_endpoint",
            "streaming_supported": True,
            "cursor_embedding_supported": False,
            "stream_state": {
                "status": "disconnected",
                "mode": "none",
                "requested_transport": "none",
                "last_error": None,
            },
            "owner_key": owner_key,
        }
        self._sessions[sid] = state
        return {k: v for k, v in state.items() if k != "owner_key"}

    def get_state(self, *, session_id: str, owner_key: str) -> dict[str, Any]:
        s = self._sessions.get(session_id)
        if not s:
            raise BrowserSessionNotFoundError("Unknown session_id")
        if s["owner_key"] != owner_key:
            raise BrowserSessionOwnerMismatchError("Session owner mismatch.")
        return {k: v for k, v in s.items() if k != "owner_key"}

    def navigate(self, *, session_id: str, owner_key: str, url: str) -> dict[str, Any]:
        s = self._sessions.get(session_id)
        if not s:
            raise BrowserSessionNotFoundError("Unknown session_id")
        if s["owner_key"] != owner_key:
            raise BrowserSessionOwnerMismatchError("Session owner mismatch.")
        if "localhost" in url:
            raise BrowserPolicyError("Local/private network targets are blocked.")
        s["current_url"] = url
        return {k: v for k, v in s.items() if k != "owner_key"}

    def click(self, *, session_id: str, owner_key: str, selector: str) -> dict[str, Any]:
        if selector == "conflict":
            raise BrowserSessionConflictError("Session is in error state.")
        return self.get_state(session_id=session_id, owner_key=owner_key)

    def type_text(
        self, *, session_id: str, owner_key: str, selector: str, text: str, clear_first: bool
    ) -> dict[str, Any]:
        _ = (selector, text, clear_first)
        return self.get_state(session_id=session_id, owner_key=owner_key)

    def screenshot_png(self, *, session_id: str, owner_key: str) -> bytes:
        self.get_state(session_id=session_id, owner_key=owner_key)
        return b"\x89PNG\r\n\x1a\nfake"

    def reset(self, *, session_id: str, owner_key: str) -> dict[str, Any]:
        s = self.get_state(session_id=session_id, owner_key=owner_key)
        s["current_url"] = "about:blank"
        self._sessions[session_id]["current_url"] = "about:blank"
        return s

    def close_session(self, *, session_id: str, owner_key: str) -> None:
        _ = self.get_state(session_id=session_id, owner_key=owner_key)
        self._sessions.pop(session_id, None)

    def click_xy(
        self, *, session_id: str, owner_key: str, x: float, y: float, button: str
    ) -> dict[str, Any]:
        _ = button
        if x < 0 or y < 0:
            raise BrowserPolicyError("Click coordinates out of viewport bounds.")
        return self.get_state(session_id=session_id, owner_key=owner_key)

    def scroll(
        self, *, session_id: str, owner_key: str, delta_x: float, delta_y: float
    ) -> dict[str, Any]:
        _ = (delta_x, delta_y)
        return self.get_state(session_id=session_id, owner_key=owner_key)

    def key_press(self, *, session_id: str, owner_key: str, key: str) -> dict[str, Any]:
        _ = key
        return self.get_state(session_id=session_id, owner_key=owner_key)

    def start_stream(
        self, *, session_id: str, owner_key: str, requested_transport: str
    ) -> dict[str, Any]:
        _ = requested_transport
        self.get_state(session_id=session_id, owner_key=owner_key)
        return {
            "status": "live",
            "mode": "screenshot_loop",
            "requested_transport": "screenshot_loop",
            "last_error": None,
        }

    def get_stream_state(self, *, session_id: str, owner_key: str) -> dict[str, Any]:
        self.get_state(session_id=session_id, owner_key=owner_key)
        return {
            "status": "live",
            "mode": "screenshot_loop",
            "requested_transport": "screenshot_loop",
            "last_error": None,
        }

    def stop_stream(self, *, session_id: str, owner_key: str) -> dict[str, Any]:
        self.get_state(session_id=session_id, owner_key=owner_key)
        return {
            "status": "disconnected",
            "mode": "none",
            "requested_transport": "screenshot_loop",
            "last_error": None,
        }

    def handle_webrtc_offer(
        self, *, session_id: str, owner_key: str, sdp: str, offer_type: str
    ) -> dict[str, Any]:
        _ = (sdp, offer_type)
        self.get_state(session_id=session_id, owner_key=owner_key)
        raise BrowserSessionConflictError("WebRTC handshake is not enabled on this HAM host.")

    def handle_webrtc_candidate(
        self, *, session_id: str, owner_key: str, candidate: str
    ) -> dict[str, Any]:
        _ = candidate
        self.get_state(session_id=session_id, owner_key=owner_key)
        raise BrowserSessionConflictError("WebRTC candidate handling is not enabled on this HAM host.")


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import src.api.browser_runtime as api_mod

    manager = _FakeManager()
    monkeypatch.setattr(api_mod, "get_browser_runtime_manager", lambda: manager)
    return TestClient(app)


def test_policy_endpoint(api_client: TestClient) -> None:
    res = api_client.get("/api/browser/policy")
    assert res.status_code == 200
    assert res.json()["runtime_host"] == "ham_api_local"


def test_session_lifecycle_endpoints(api_client: TestClient) -> None:
    created = api_client.post("/api/browser/sessions", json={"owner_key": "pane_a"})
    assert created.status_code == 200
    sid = created.json()["session_id"]

    state = api_client.get(f"/api/browser/sessions/{sid}", params={"owner_key": "pane_a"})
    assert state.status_code == 200

    nav = api_client.post(
        f"/api/browser/sessions/{sid}/navigate",
        json={"owner_key": "pane_a", "url": "https://example.com"},
    )
    assert nav.status_code == 200
    assert nav.json()["current_url"] == "https://example.com"

    click = api_client.post(
        f"/api/browser/sessions/{sid}/actions/click",
        json={"owner_key": "pane_a", "selector": "button"},
    )
    assert click.status_code == 200

    typed = api_client.post(
        f"/api/browser/sessions/{sid}/actions/type",
        json={"owner_key": "pane_a", "selector": "input", "text": "hello", "clear_first": True},
    )
    assert typed.status_code == 200

    shot = api_client.post(f"/api/browser/sessions/{sid}/screenshot", json={"owner_key": "pane_a"})
    assert shot.status_code == 200
    assert shot.headers["content-type"].startswith("image/png")
    assert shot.content.startswith(b"\x89PNG")

    reset = api_client.post(f"/api/browser/sessions/{sid}/reset", json={"owner_key": "pane_a"})
    assert reset.status_code == 200
    assert reset.json()["current_url"] == "about:blank"

    closed = api_client.delete(f"/api/browser/sessions/{sid}", params={"owner_key": "pane_a"})
    assert closed.status_code == 200
    assert closed.json()["ok"] is True


def test_error_mapping_not_found_owner_mismatch_policy_conflict(api_client: TestClient) -> None:
    created = api_client.post("/api/browser/sessions", json={"owner_key": "pane_a"})
    sid = created.json()["session_id"]

    missing = api_client.get("/api/browser/sessions/unknown", params={"owner_key": "pane_a"})
    assert missing.status_code == 404

    mismatch = api_client.get(f"/api/browser/sessions/{sid}", params={"owner_key": "pane_b"})
    assert mismatch.status_code == 403

    policy = api_client.post(
        f"/api/browser/sessions/{sid}/navigate",
        json={"owner_key": "pane_a", "url": "http://localhost:3000"},
    )
    assert policy.status_code == 422

    conflict = api_client.post(
        f"/api/browser/sessions/{sid}/actions/click",
        json={"owner_key": "pane_a", "selector": "conflict"},
    )
    assert conflict.status_code == 409


def test_live_stream_and_interactive_endpoints(api_client: TestClient) -> None:
    created = api_client.post("/api/browser/sessions", json={"owner_key": "pane_a"})
    sid = created.json()["session_id"]

    started = api_client.post(
        f"/api/browser/sessions/{sid}/stream/start",
        json={"owner_key": "pane_a", "requested_transport": "screenshot_loop"},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "live"

    stream_state = api_client.get(f"/api/browser/sessions/{sid}/stream/state", params={"owner_key": "pane_a"})
    assert stream_state.status_code == 200
    assert stream_state.json()["mode"] == "screenshot_loop"

    click_xy = api_client.post(
        f"/api/browser/sessions/{sid}/actions/click-xy",
        json={"owner_key": "pane_a", "x": 100, "y": 80, "button": "left"},
    )
    assert click_xy.status_code == 200

    click_xy_bad = api_client.post(
        f"/api/browser/sessions/{sid}/actions/click-xy",
        json={"owner_key": "pane_a", "x": -1, "y": 80, "button": "left"},
    )
    assert click_xy_bad.status_code == 422

    scroll = api_client.post(
        f"/api/browser/sessions/{sid}/actions/scroll",
        json={"owner_key": "pane_a", "delta_x": 0, "delta_y": 120},
    )
    assert scroll.status_code == 200

    key = api_client.post(
        f"/api/browser/sessions/{sid}/actions/key",
        json={"owner_key": "pane_a", "key": "Enter"},
    )
    assert key.status_code == 200

    offer = api_client.post(
        f"/api/browser/sessions/{sid}/stream/offer",
        json={"owner_key": "pane_a", "type": "offer", "sdp": "v=0"},
    )
    assert offer.status_code == 409

    candidate = api_client.post(
        f"/api/browser/sessions/{sid}/stream/candidate",
        json={"owner_key": "pane_a", "candidate": "candidate:1 1 udp 2122260223 127.0.0.1 9 typ host"},
    )
    assert candidate.status_code == 409

    stopped = api_client.post(f"/api/browser/sessions/{sid}/stream/stop", json={"owner_key": "pane_a"})
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "disconnected"
