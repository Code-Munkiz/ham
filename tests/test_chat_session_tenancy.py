"""Phase 2a PR 2: chat session API tenancy when workspace_id is supplied."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import src.api.chat as chat_mod
from src.api.server import app
from src.ham.clerk_auth import HamActor
from src.persistence.chat_session_store import ChatTurn, InMemoryChatSessionStore

client = TestClient(app)


def _actor(user_id: str) -> HamActor:
    return HamActor(
        user_id=user_id,
        org_id="org_test",
        session_id=f"sess_{user_id}",
        email=f"{user_id}@example.com",
        permissions=frozenset(),
        org_role="org:member",
        raw_permission_claim=None,
    )


def _install_auth(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")

    def _verify(token: str) -> HamActor:
        if token == "user-b.jwt":
            return _actor("user_b")
        return _actor("user_a")

    return patch("src.api.clerk_gate.verify_clerk_session_jwt", side_effect=_verify)


@pytest.fixture
def chat_store(monkeypatch: pytest.MonkeyPatch) -> InMemoryChatSessionStore:
    store = InMemoryChatSessionStore()
    monkeypatch.setattr(chat_mod, "_chat_store", store)
    return store


def test_scoped_chat_create_stores_user_and_workspace(
    chat_store: InMemoryChatSessionStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")
    with _install_auth(monkeypatch):
        res = client.post(
            "/api/chat",
            headers={"Authorization": "Bearer user-a.jwt"},
            json={
                "workspace_id": "ws_a",
                "messages": [{"role": "user", "content": "hello scoped"}],
            },
        )

    assert res.status_code == 200, res.text
    rec = chat_store.get_session(res.json()["session_id"])
    assert rec is not None
    assert rec.user_id == "user_a"
    assert rec.workspace_id == "ws_a"


def test_scoped_session_create_stores_user_and_workspace(
    chat_store: InMemoryChatSessionStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _install_auth(monkeypatch):
        res = client.post(
            "/api/chat/sessions",
            params={"workspace_id": "ws_a"},
            headers={"Authorization": "Bearer user-a.jwt"},
        )

    assert res.status_code == 200, res.text
    rec = chat_store.get_session(res.json()["session_id"])
    assert rec is not None
    assert rec.user_id == "user_a"
    assert rec.workspace_id == "ws_a"


def test_scoped_list_only_returns_matching_user_and_workspace(
    chat_store: InMemoryChatSessionStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keep = chat_store.create_session(user_id="user_a", workspace_id="ws_a")
    other_workspace = chat_store.create_session(user_id="user_a", workspace_id="ws_b")
    other_user = chat_store.create_session(user_id="user_b", workspace_id="ws_a")
    legacy = chat_store.create_session()
    for sid, text in (
        (keep, "keep"),
        (other_workspace, "other workspace"),
        (other_user, "other user"),
        (legacy, "legacy"),
    ):
        chat_store.append_turns(sid, [ChatTurn(role="user", content=text)])

    with _install_auth(monkeypatch):
        res = client.get(
            "/api/chat/sessions",
            params={"workspace_id": "ws_a"},
            headers={"Authorization": "Bearer user-a.jwt"},
        )

    assert res.status_code == 200, res.text
    assert [row["session_id"] for row in res.json()["sessions"]] == [keep]


def test_cross_workspace_session_access_is_not_found(
    chat_store: InMemoryChatSessionStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sid = chat_store.create_session(user_id="user_a", workspace_id="ws_a")
    chat_store.append_turns(sid, [ChatTurn(role="user", content="secret")])

    with _install_auth(monkeypatch):
        res = client.get(
            f"/api/chat/sessions/{sid}",
            params={"workspace_id": "ws_b"},
            headers={"Authorization": "Bearer user-a.jwt"},
        )

    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "SESSION_NOT_FOUND"


def test_scoped_session_created_by_chat_cannot_be_loaded_from_other_workspace(
    chat_store: InMemoryChatSessionStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")
    with _install_auth(monkeypatch):
        created = client.post(
            "/api/chat",
            headers={"Authorization": "Bearer user-a.jwt"},
            json={
                "workspace_id": "ws_b",
                "messages": [{"role": "user", "content": "workspace b"}],
            },
        )
        assert created.status_code == 200, created.text
        sid = created.json()["session_id"]

        wrong_workspace = client.get(
            f"/api/chat/sessions/{sid}",
            params={"workspace_id": "ws_a"},
            headers={"Authorization": "Bearer user-a.jwt"},
        )
        listed = client.get(
            "/api/chat/sessions",
            params={"workspace_id": "ws_a"},
            headers={"Authorization": "Bearer user-a.jwt"},
        )

    assert wrong_workspace.status_code == 404
    assert wrong_workspace.json()["detail"]["error"]["code"] == "SESSION_NOT_FOUND"
    assert listed.status_code == 200, listed.text
    assert sid not in {row["session_id"] for row in listed.json()["sessions"]}


def test_scoped_request_does_not_load_legacy_unowned_session(
    chat_store: InMemoryChatSessionStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = chat_store.create_session()
    chat_store.append_turns(legacy, [ChatTurn(role="user", content="legacy")])

    with _install_auth(monkeypatch):
        scoped = client.get(
            f"/api/chat/sessions/{legacy}",
            params={"workspace_id": "ws_a"},
            headers={"Authorization": "Bearer user-a.jwt"},
        )
        unscoped = client.get(
            f"/api/chat/sessions/{legacy}",
            headers={"Authorization": "Bearer user-a.jwt"},
        )

    assert scoped.status_code == 404
    assert scoped.json()["detail"]["error"]["code"] == "SESSION_NOT_FOUND"
    assert unscoped.status_code == 200, unscoped.text
    assert unscoped.json()["messages"] == [{"role": "user", "content": "legacy"}]


def test_post_chat_omitting_workspace_id_cannot_append_to_other_users_scoped_session(
    chat_store: InMemoryChatSessionStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: omitting workspace_id must not bypass user ownership on scoped sessions."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")
    sid = chat_store.create_session(user_id="user_a", workspace_id="ws_a")
    chat_store.append_turns(sid, [ChatTurn(role="user", content="victim")])

    with _install_auth(monkeypatch):
        res = client.post(
            "/api/chat",
            headers={"Authorization": "Bearer user-b.jwt"},
            json={
                "session_id": sid,
                "messages": [{"role": "user", "content": "injected"}],
            },
        )

    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "SESSION_NOT_FOUND"
    rec = chat_store.get_session(sid)
    assert rec is not None
    assert len(rec.turns) == 1
    assert rec.turns[0].content == "victim"


def test_get_session_omitting_workspace_id_requires_owner_for_scoped_sessions(
    chat_store: InMemoryChatSessionStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sid = chat_store.create_session(user_id="user_a", workspace_id="ws_a")
    chat_store.append_turns(sid, [ChatTurn(role="user", content="secret")])

    with _install_auth(monkeypatch):
        res = client.get(
            f"/api/chat/sessions/{sid}",
            headers={"Authorization": "Bearer user-b.jwt"},
        )

    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "SESSION_NOT_FOUND"


def test_delete_session_omitting_workspace_id_requires_owner_for_scoped_sessions(
    chat_store: InMemoryChatSessionStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sid = chat_store.create_session(user_id="user_a", workspace_id="ws_a")
    chat_store.append_turns(sid, [ChatTurn(role="user", content="x")])

    with _install_auth(monkeypatch):
        res = client.delete(
            f"/api/chat/sessions/{sid}",
            headers={"Authorization": "Bearer user-b.jwt"},
        )

    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "SESSION_NOT_FOUND"
    assert chat_store.get_session(sid) is not None


def test_cross_user_session_access_is_not_found(
    chat_store: InMemoryChatSessionStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sid = chat_store.create_session(user_id="user_a", workspace_id="ws_a")
    chat_store.append_turns(sid, [ChatTurn(role="user", content="secret")])

    with _install_auth(monkeypatch):
        res = client.get(
            f"/api/chat/sessions/{sid}",
            params={"workspace_id": "ws_a"},
            headers={"Authorization": "Bearer user-b.jwt"},
        )

    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "SESSION_NOT_FOUND"


def test_legacy_unscoped_session_access_remains_compatible(
    chat_store: InMemoryChatSessionStore,
) -> None:
    legacy = chat_store.create_session()
    scoped = chat_store.create_session(user_id="user_a", workspace_id="ws_a")
    chat_store.append_turns(legacy, [ChatTurn(role="user", content="legacy")])
    chat_store.append_turns(scoped, [ChatTurn(role="user", content="scoped")])

    listed = client.get("/api/chat/sessions")
    fetched = client.get(f"/api/chat/sessions/{legacy}")

    assert listed.status_code == 200, listed.text
    assert {row["session_id"] for row in listed.json()["sessions"]} == {legacy, scoped}
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["messages"] == [{"role": "user", "content": "legacy"}]
