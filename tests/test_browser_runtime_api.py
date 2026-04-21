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
            "streaming_supported": False,
            "cursor_embedding_supported": False,
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
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "ownership": "pane_owner_key",
            "runtime_host": "ham_api_local",
            "screenshot_transport": "binary_png_endpoint",
            "streaming_supported": False,
            "cursor_embedding_supported": False,
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
