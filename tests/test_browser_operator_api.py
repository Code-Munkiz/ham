"""Tests for /api/browser-operator (proposal create/list/get/approve/deny + dispatch)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.browser_runtime.sessions import (
    BrowserPolicyError,
    BrowserSessionNotFoundError,
    BrowserSessionOwnerMismatchError,
)
from src.persistence.browser_proposal import BrowserProposalStore


# ---------------------------------------------------------------------------
# Fake browser manager: just enough surface for dispatch tests.
# ---------------------------------------------------------------------------


class _FakeManager:
    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def add_session(self, *, session_id: str, owner_key: str, operator_mode: bool = True) -> None:
        self.sessions[session_id] = {
            "owner_key": owner_key,
            "operator_mode_required": operator_mode,
            "current_url": "about:blank",
        }

    def is_operator_mode_required(self, *, session_id: str, owner_key: str) -> bool:
        s = self.sessions.get(session_id)
        if s is None:
            raise BrowserSessionNotFoundError("Unknown session_id")
        if s["owner_key"] != owner_key:
            raise BrowserSessionOwnerMismatchError("Session owner mismatch.")
        return bool(s["operator_mode_required"])

    def _state(self, session_id: str) -> dict[str, Any]:
        s = self.sessions[session_id]
        return {
            "session_id": session_id,
            "status": "ready",
            "last_error": None,
            "current_url": s["current_url"],
            "title": "",
            "viewport": {"width": 1280, "height": 720},
            "operator_mode_required": s["operator_mode_required"],
            "stream_state": {
                "status": "disconnected",
                "mode": "none",
                "requested_transport": "none",
                "last_error": None,
            },
        }

    def navigate(self, *, session_id: str, owner_key: str, url: str) -> dict[str, Any]:
        s = self.sessions.get(session_id)
        if s is None:
            raise BrowserSessionNotFoundError("Unknown session_id")
        if s["owner_key"] != owner_key:
            raise BrowserSessionOwnerMismatchError("Session owner mismatch.")
        if "blocked.example.com" in url:
            raise BrowserPolicyError("Target domain is blocked.")
        s["current_url"] = url
        self.calls.append(("navigate", {"session_id": session_id, "url": url}))
        return self._state(session_id)

    def click_xy(self, *, session_id: str, owner_key: str, x: float, y: float, button: str = "left") -> dict[str, Any]:
        _ = button
        s = self.sessions.get(session_id)
        if s is None:
            raise BrowserSessionNotFoundError("Unknown session_id")
        if s["owner_key"] != owner_key:
            raise BrowserSessionOwnerMismatchError("Session owner mismatch.")
        self.calls.append(("click_xy", {"session_id": session_id, "x": x, "y": y}))
        return self._state(session_id)

    def scroll(self, *, session_id: str, owner_key: str, delta_x: float, delta_y: float) -> dict[str, Any]:
        self.calls.append(("scroll", {"session_id": session_id, "dx": delta_x, "dy": delta_y}))
        return self._state(session_id)

    def key_press(self, *, session_id: str, owner_key: str, key: str) -> dict[str, Any]:
        self.calls.append(("key_press", {"session_id": session_id, "key": key}))
        return self._state(session_id)

    def type_text(
        self, *, session_id: str, owner_key: str, selector: str, text: str, clear_first: bool
    ) -> dict[str, Any]:
        self.calls.append(
            ("type_text", {"session_id": session_id, "selector": selector, "text": text, "clear_first": clear_first})
        )
        return self._state(session_id)

    def reset(self, *, session_id: str, owner_key: str) -> dict[str, Any]:
        self.sessions[session_id]["current_url"] = "about:blank"
        self.calls.append(("reset", {"session_id": session_id}))
        return self._state(session_id)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_manager(monkeypatch: pytest.MonkeyPatch) -> _FakeManager:
    import src.api.browser_operator as bo_mod
    import src.api.browser_runtime as br_mod
    import src.ham.browser_operator.dispatch as disp_mod
    import src.ham.browser_runtime.service as svc_mod

    manager = _FakeManager()

    # Patch every callsite that may resolve get_browser_runtime_manager.
    monkeypatch.setattr(svc_mod, "get_browser_runtime_manager", lambda: manager)
    monkeypatch.setattr(br_mod, "get_browser_runtime_manager", lambda: manager)
    monkeypatch.setattr(disp_mod, "get_browser_runtime_manager", lambda: manager)

    # Run on the calling thread to avoid any pool-related flake.
    def _direct(func: Any) -> Any:
        return func()

    monkeypatch.setattr(svc_mod, "run_browser_io", _direct)
    monkeypatch.setattr(br_mod, "run_browser_io", _direct)
    monkeypatch.setattr(disp_mod, "run_browser_io", _direct)

    # Stash on the module for tests that need to inspect.
    bo_mod._test_manager = manager  # type: ignore[attr-defined]
    return manager


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BrowserProposalStore:
    import src.api.browser_operator as bo_mod

    s = BrowserProposalStore(base_dir=tmp_path)
    monkeypatch.setattr(bo_mod, "get_browser_proposal_store", lambda: s)
    return s


@pytest.fixture
def client(fake_manager: _FakeManager, store: BrowserProposalStore) -> TestClient:
    _ = (fake_manager, store)
    return TestClient(app)


def _add_operator_session(
    fake_manager: _FakeManager,
    *,
    session_id: str = "brs_op_001",
    owner_key: str = "pane_a",
) -> None:
    fake_manager.add_session(session_id=session_id, owner_key=owner_key, operator_mode=True)


def _create_proposal(
    client: TestClient,
    *,
    session_id: str = "brs_op_001",
    owner_key: str = "pane_a",
    action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = {
        "session_id": session_id,
        "owner_key": owner_key,
        "action": action or {"action_type": "browser.navigate", "url": "https://example.com"},
        "proposer": {"kind": "operator", "label": "test"},
    }
    res = client.post("/api/browser-operator/proposals", json=body)
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------------------
# Policy + create/list/get
# ---------------------------------------------------------------------------


def test_policy_returns_allowlist_and_no_header_unlock(client: TestClient) -> None:
    res = client.get("/api/browser-operator/policy")
    assert res.status_code == 200
    body = res.json()
    assert body["approval_only"] is True
    assert body["header_unlock_supported"] is False
    assert "browser.navigate" in body["allowed_action_types"]
    assert "shell.run" not in body["allowed_action_types"]


def test_create_list_get_proposal(fake_manager: _FakeManager, client: TestClient) -> None:
    _add_operator_session(fake_manager)
    created = _create_proposal(client)
    assert created["state"] == "proposed"
    assert created["session_id"] == "brs_op_001"

    listed = client.get(
        "/api/browser-operator/proposals",
        params={"session_id": "brs_op_001", "owner_key": "pane_a"},
    )
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert any(p["proposal_id"] == created["proposal_id"] for p in items)

    fetched = client.get(
        f"/api/browser-operator/proposals/{created['proposal_id']}",
        params={"owner_key": "pane_a"},
    )
    assert fetched.status_code == 200
    assert fetched.json()["proposal_id"] == created["proposal_id"]


def test_unsupported_action_type_rejected(fake_manager: _FakeManager, client: TestClient) -> None:
    _add_operator_session(fake_manager)
    res = client.post(
        "/api/browser-operator/proposals",
        json={
            "session_id": "brs_op_001",
            "owner_key": "pane_a",
            "action": {"action_type": "shell.run", "text": "rm -rf /"},
        },
    )
    assert res.status_code == 422


def test_navigate_proposal_requires_url(fake_manager: _FakeManager, client: TestClient) -> None:
    _add_operator_session(fake_manager)
    res = client.post(
        "/api/browser-operator/proposals",
        json={
            "session_id": "brs_op_001",
            "owner_key": "pane_a",
            "action": {"action_type": "browser.navigate"},
        },
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Approve / deny / dispatch
# ---------------------------------------------------------------------------


def test_approve_dispatches_via_manager(fake_manager: _FakeManager, client: TestClient) -> None:
    _add_operator_session(fake_manager)
    created = _create_proposal(client)
    res = client.post(
        f"/api/browser-operator/proposals/{created['proposal_id']}/approve",
        json={"owner_key": "pane_a"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["state"] == "executed"
    assert body["result_status"] == "ok"
    # Manager call recorded.
    assert any(c[0] == "navigate" for c in fake_manager.calls)


def test_deny_terminal_state(fake_manager: _FakeManager, client: TestClient) -> None:
    _add_operator_session(fake_manager)
    created = _create_proposal(client)
    res = client.post(
        f"/api/browser-operator/proposals/{created['proposal_id']}/deny",
        json={"owner_key": "pane_a", "note": "no thanks"},
    )
    assert res.status_code == 200
    assert res.json()["state"] == "denied"

    # One-shot: cannot approve a denied proposal.
    again = client.post(
        f"/api/browser-operator/proposals/{created['proposal_id']}/approve",
        json={"owner_key": "pane_a"},
    )
    assert again.status_code == 409


def test_owner_mismatch_403(fake_manager: _FakeManager, client: TestClient) -> None:
    _add_operator_session(fake_manager)
    created = _create_proposal(client)
    res = client.post(
        f"/api/browser-operator/proposals/{created['proposal_id']}/approve",
        json={"owner_key": "pane_b"},
    )
    assert res.status_code == 403


def test_blocked_navigate_marks_failed_with_policy(
    fake_manager: _FakeManager, client: TestClient
) -> None:
    _add_operator_session(fake_manager)
    created = _create_proposal(
        client,
        action={"action_type": "browser.navigate", "url": "https://blocked.example.com/path"},
    )
    res = client.post(
        f"/api/browser-operator/proposals/{created['proposal_id']}/approve",
        json={"owner_key": "pane_a"},
    )
    assert res.status_code == 422
    detail = res.json().get("detail")
    assert isinstance(detail, dict)
    assert detail["kind"] == "policy"
    assert detail["proposal"]["state"] == "failed"
    assert detail["proposal"]["result_status"] == "error"


def test_expired_proposal_returns_410(
    fake_manager: _FakeManager,
    client: TestClient,
    store: BrowserProposalStore,
) -> None:
    _add_operator_session(fake_manager)
    created = _create_proposal(client)

    # Force expiry by rewriting the persisted record's expires_at to the past.
    proposal = store.get(created["proposal_id"])
    assert proposal is not None
    expired = proposal.model_copy(update={"expires_at": "2000-01-01T00:00:00Z"})
    store.save(expired)

    res = client.post(
        f"/api/browser-operator/proposals/{created['proposal_id']}/approve",
        json={"owner_key": "pane_a"},
    )
    assert res.status_code == 410


def test_one_shot_approval_rejects_double_approve(
    fake_manager: _FakeManager, client: TestClient
) -> None:
    _add_operator_session(fake_manager)
    created = _create_proposal(client)
    first = client.post(
        f"/api/browser-operator/proposals/{created['proposal_id']}/approve",
        json={"owner_key": "pane_a"},
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/browser-operator/proposals/{created['proposal_id']}/approve",
        json={"owner_key": "pane_a"},
    )
    assert second.status_code == 409


def test_max_pending_cap(
    fake_manager: _FakeManager,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _add_operator_session(fake_manager)
    monkeypatch.setenv("HAM_BROWSER_OPERATOR_MAX_PENDING_PER_SESSION", "2")
    _create_proposal(client)
    _create_proposal(client)
    res = client.post(
        "/api/browser-operator/proposals",
        json={
            "session_id": "brs_op_001",
            "owner_key": "pane_a",
            "action": {"action_type": "browser.navigate", "url": "https://example.com"},
        },
    )
    assert res.status_code == 429
