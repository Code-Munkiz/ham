"""SQLite chat session store."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.persistence.chat_session_store import ChatTurn
from src.persistence.sqlite_chat_session_store import SqliteChatSessionStore


def test_sqlite_create_append_list(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    store = SqliteChatSessionStore(db)
    sid = store.create_session()
    store.append_turns(sid, [ChatTurn(role="user", content="hi")])
    store.append_turns(sid, [ChatTurn(role="assistant", content="yo")])
    msgs = store.list_messages(sid)
    assert msgs == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "yo"},
    ]


def test_sqlite_unknown_session_raises(tmp_path: Path) -> None:
    store = SqliteChatSessionStore(tmp_path / "x.db")
    with pytest.raises(KeyError):
        store.append_turns("nope", [ChatTurn(role="user", content="x")])


def test_sqlite_upsert_assistant_turn_updates_by_turn_id(tmp_path: Path) -> None:
    store = SqliteChatSessionStore(tmp_path / "u.db")
    sid = store.create_session()
    store.append_turns(sid, [ChatTurn(role="user", content="hello")])
    store.upsert_assistant_turn(sid, "turn-1", "partial")
    store.upsert_assistant_turn(sid, "turn-1", "final")
    assert store.list_messages(sid) == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "final"},
    ]


def test_sqlite_delete_session(tmp_path: Path) -> None:
    store = SqliteChatSessionStore(tmp_path / "del.db")
    sid = store.create_session()
    store.append_turns(sid, [ChatTurn(role="user", content="x")])
    assert store.delete_session(sid) is True
    assert store.get_session(sid) is None
    assert store.delete_session(sid) is False


def _create_with_turn(
    store: SqliteChatSessionStore,
    text: str,
    *,
    user_id: str | None = None,
    workspace_id: str | None = None,
) -> str:
    sid = store.create_session(user_id=user_id, workspace_id=workspace_id)
    store.append_turns(sid, [ChatTurn(role="user", content=text)])
    return sid


def test_sqlite_scoped_sessions_are_private_by_user_and_workspace(tmp_path: Path) -> None:
    store = SqliteChatSessionStore(tmp_path / "scoped.db")
    user_a_ws_1 = _create_with_turn(store, "a/w1", user_id="user-a", workspace_id="ws-1")
    user_b_ws_1 = _create_with_turn(store, "b/w1", user_id="user-b", workspace_id="ws-1")
    user_a_ws_2 = _create_with_turn(store, "a/w2", user_id="user-a", workspace_id="ws-2")

    scoped = store.list_sessions(user_id="user-a", workspace_id="ws-1")
    assert [s.session_id for s in scoped] == [user_a_ws_1]
    assert scoped[0].user_id == "user-a"
    assert scoped[0].workspace_id == "ws-1"

    assert user_b_ws_1 not in {s.session_id for s in scoped}
    assert user_a_ws_2 not in {s.session_id for s in scoped}


def test_sqlite_legacy_sessions_remain_unscoped_but_hidden_from_scoped_lists(tmp_path: Path) -> None:
    store = SqliteChatSessionStore(tmp_path / "legacy.db")
    legacy = _create_with_turn(store, "legacy")
    scoped = _create_with_turn(store, "scoped", user_id="user-a", workspace_id="ws-1")

    assert {s.session_id for s in store.list_sessions()} == {legacy, scoped}
    assert [s.session_id for s in store.list_sessions(user_id="user-a", workspace_id="ws-1")] == [scoped]
    assert legacy not in {s.session_id for s in store.list_sessions(workspace_id="ws-1")}


def test_sqlite_migration_adds_scope_columns_to_existing_db(tmp_path: Path) -> None:
    db = tmp_path / "migrate.db"
    conn = sqlite3.connect(db)
    with conn:
        conn.execute(
            """
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY,
                upstream_ref TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                UNIQUE(session_id, seq),
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
            """
        )
        conn.execute("INSERT INTO sessions (session_id, upstream_ref) VALUES (?, ?)", ("legacy", None))
        conn.execute(
            "INSERT INTO turns (session_id, seq, role, content) VALUES (?, ?, ?, ?)",
            ("legacy", 0, "user", "legacy"),
        )
    conn.close()

    store = SqliteChatSessionStore(db)
    rec = store.get_session("legacy")
    assert rec is not None
    assert rec.user_id is None
    assert rec.workspace_id is None
    assert [s.session_id for s in store.list_sessions()] == ["legacy"]
    assert store.list_sessions(user_id="user-a", workspace_id="ws-1") == []

    scoped = _create_with_turn(store, "new", user_id="user-a", workspace_id="ws-1")
    assert [s.session_id for s in store.list_sessions(user_id="user-a", workspace_id="ws-1")] == [scoped]
