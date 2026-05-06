"""In-memory chat session store scoping."""
from __future__ import annotations

from src.persistence.chat_session_store import ChatTurn, InMemoryChatSessionStore


def _create_with_turn(
    store: InMemoryChatSessionStore,
    text: str,
    *,
    user_id: str | None = None,
    workspace_id: str | None = None,
) -> str:
    sid = store.create_session(user_id=user_id, workspace_id=workspace_id)
    store.append_turns(sid, [ChatTurn(role="user", content=text)])
    return sid


def test_memory_scoped_sessions_are_private_by_user_and_workspace() -> None:
    store = InMemoryChatSessionStore()
    user_a_ws_1 = _create_with_turn(store, "a/w1", user_id="user-a", workspace_id="ws-1")
    user_b_ws_1 = _create_with_turn(store, "b/w1", user_id="user-b", workspace_id="ws-1")
    user_a_ws_2 = _create_with_turn(store, "a/w2", user_id="user-a", workspace_id="ws-2")

    scoped = store.list_sessions(user_id="user-a", workspace_id="ws-1")
    assert [s.session_id for s in scoped] == [user_a_ws_1]
    assert scoped[0].user_id == "user-a"
    assert scoped[0].workspace_id == "ws-1"

    assert user_b_ws_1 not in {s.session_id for s in scoped}
    assert user_a_ws_2 not in {s.session_id for s in scoped}


def test_memory_legacy_sessions_remain_unscoped_but_hidden_from_scoped_lists() -> None:
    store = InMemoryChatSessionStore()
    legacy = _create_with_turn(store, "legacy")
    scoped = _create_with_turn(store, "scoped", user_id="user-a", workspace_id="ws-1")

    assert {s.session_id for s in store.list_sessions()} == {legacy, scoped}
    assert [s.session_id for s in store.list_sessions(user_id="user-a", workspace_id="ws-1")] == [scoped]
    assert legacy not in {s.session_id for s in store.list_sessions(workspace_id="ws-1")}


def test_memory_unscoped_actor_sees_legacy_and_own_sessions_only() -> None:
    store = InMemoryChatSessionStore()
    legacy = _create_with_turn(store, "legacy")
    mine = _create_with_turn(store, "mine", user_id="user-a", workspace_id="ws-1")
    other = _create_with_turn(store, "other", user_id="user-b", workspace_id="ws-1")

    visible = store.list_sessions(unscoped_actor_user_id="user-a")
    assert {s.session_id for s in visible} == {legacy, mine}
    assert other not in {s.session_id for s in visible}

