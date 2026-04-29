"""Env-driven chat session store factory."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.persistence.chat_session_store import build_chat_session_store
from src.persistence.sqlite_chat_session_store import SqliteChatSessionStore


def test_factory_sqlite_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_CHAT_SESSION_STORE", raising=False)
    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    store = build_chat_session_store()
    assert isinstance(store, SqliteChatSessionStore)
    sid = store.create_session()
    assert sid


def test_factory_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CHAT_SESSION_STORE", "memory")
    from src.persistence.chat_session_store import InMemoryChatSessionStore

    store = build_chat_session_store()
    assert isinstance(store, InMemoryChatSessionStore)


def test_factory_firestore(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CHAT_SESSION_STORE", "firestore")
    monkeypatch.setenv("HAM_CHAT_SESSION_FIRESTORE_COLLECTION", "ham_test_sessions")
    monkeypatch.delenv("HAM_CHAT_SESSION_FIRESTORE_DATABASE", raising=False)
    sentinel = object()
    with patch("src.persistence.firestore_chat_session_store.FirestoreChatSessionStore") as mock_fs:
        mock_fs.return_value = sentinel
        store = build_chat_session_store()
        mock_fs.assert_called_once_with("ham_test_sessions", project=None, database=None)
        assert store is sentinel


def test_factory_firestore_database_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CHAT_SESSION_STORE", "firestore")
    monkeypatch.setenv("HAM_CHAT_SESSION_FIRESTORE_COLLECTION", "c1")
    monkeypatch.setenv("HAM_CHAT_SESSION_FIRESTORE_DATABASE", "ham-chat-db")
    sentinel = object()
    with patch("src.persistence.firestore_chat_session_store.FirestoreChatSessionStore") as mock_fs:
        mock_fs.return_value = sentinel
        store = build_chat_session_store()
        mock_fs.assert_called_once_with("c1", project=None, database="ham-chat-db")
        assert store is sentinel


def test_factory_postgres_not_implemented(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CHAT_SESSION_STORE", "postgres")
    with pytest.raises(RuntimeError, match="not implemented"):
        build_chat_session_store()
