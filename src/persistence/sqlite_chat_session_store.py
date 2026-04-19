"""SQLite-backed chat session store (durable across API restarts)."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any, Sequence
from uuid import uuid4

from src.persistence.chat_session_store import ChatSessionRecord, ChatTurn, _normalize_turns


class SqliteChatSessionStore:
    """Thread-safe persistence using a single SQLite file (WAL mode)."""

    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._conn = sqlite3.connect(
            str(self._path),
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    upstream_ref TEXT
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS turns (
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

    def create_session(self) -> str:
        sid = str(uuid4())
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO sessions (session_id, upstream_ref) VALUES (?, ?)",
                (sid, None),
            )
        return sid

    def get_session(self, session_id: str) -> ChatSessionRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT session_id, upstream_ref FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            cur = self._conn.execute(
                "SELECT role, content FROM turns WHERE session_id = ? ORDER BY seq ASC",
                (session_id,),
            )
            turns = [ChatTurn(role=str(r["role"]), content=str(r["content"])) for r in cur.fetchall()]
            return ChatSessionRecord(
                session_id=str(row["session_id"]),
                turns=turns,
                upstream_ref=row["upstream_ref"],
            )

    def append_turns(self, session_id: str, turns: Sequence[ChatTurn | dict[str, Any]]) -> None:
        normalized = _normalize_turns(turns)
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise KeyError(session_id)
            max_row = self._conn.execute(
                "SELECT COALESCE(MAX(seq), -1) AS m FROM turns WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            start = int(max_row["m"]) + 1
            for i, t in enumerate(normalized):
                self._conn.execute(
                    "INSERT INTO turns (session_id, seq, role, content) VALUES (?, ?, ?, ?)",
                    (session_id, start + i, t.role, t.content),
                )

    def set_upstream_ref(self, session_id: str, ref: str | None) -> None:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE sessions SET upstream_ref = ? WHERE session_id = ?",
                (ref, session_id),
            )
            if cur.rowcount == 0:
                raise KeyError(session_id)

    def list_messages(self, session_id: str) -> list[dict[str, str]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise KeyError(session_id)
            cur = self._conn.execute(
                "SELECT role, content FROM turns WHERE session_id = ? ORDER BY seq ASC",
                (session_id,),
            )
            return [{"role": str(r["role"]), "content": str(r["content"])} for r in cur.fetchall()]
