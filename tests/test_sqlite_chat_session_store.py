"""SQLite chat session store."""
from __future__ import annotations

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
