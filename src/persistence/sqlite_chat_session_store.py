"""SQLite-backed chat session store (durable across API restarts)."""
from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from src.persistence.chat_session_store import (
    ChatSessionRecord,
    ChatSessionSummary,
    ChatTurn,
    _normalize_turns,
)


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
                    upstream_ref TEXT,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )
                """
            )
            # Backfill: add created_at if upgrading from old schema.
            try:
                self._conn.execute("SELECT created_at FROM sessions LIMIT 0")
            except sqlite3.OperationalError:
                self._conn.execute(
                    "ALTER TABLE sessions ADD COLUMN created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"
                )
            try:
                self._conn.execute("SELECT user_id FROM sessions LIMIT 0")
            except sqlite3.OperationalError:
                self._conn.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT")
            try:
                self._conn.execute("SELECT workspace_id FROM sessions LIMIT 0")
            except sqlite3.OperationalError:
                self._conn.execute("ALTER TABLE sessions ADD COLUMN workspace_id TEXT")
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_workspace_user_created
                ON sessions(workspace_id, user_id, created_at DESC)
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_workspace_created
                ON sessions(user_id, workspace_id, created_at DESC)
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
                    turn_id TEXT,
                    UNIQUE(session_id, seq),
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
                """
            )
            try:
                self._conn.execute("SELECT turn_id FROM turns LIMIT 0")
            except sqlite3.OperationalError:
                self._conn.execute("ALTER TABLE turns ADD COLUMN turn_id TEXT")

    def create_session(
        self,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> str:
        sid = str(uuid4())
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO sessions (session_id, upstream_ref, user_id, workspace_id) VALUES (?, ?, ?, ?)",
                (sid, None, user_id, workspace_id),
            )
        return sid

    def get_session(self, session_id: str) -> ChatSessionRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT session_id, upstream_ref, created_at, user_id, workspace_id FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            cur = self._conn.execute(
                "SELECT role, content, turn_id FROM turns WHERE session_id = ? ORDER BY seq ASC",
                (session_id,),
            )
            turns = [
                ChatTurn(
                    role=str(r["role"]),
                    content=str(r["content"]),
                    turn_id=str(r["turn_id"]) if r["turn_id"] is not None else None,
                )
                for r in cur.fetchall()
            ]
            return ChatSessionRecord(
                session_id=str(row["session_id"]),
                turns=turns,
                upstream_ref=row["upstream_ref"],
                created_at=row["created_at"] if "created_at" in row.keys() else None,
                user_id=row["user_id"] if "user_id" in row.keys() else None,
                workspace_id=row["workspace_id"] if "workspace_id" in row.keys() else None,
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
                    "INSERT INTO turns (session_id, seq, role, content, turn_id) VALUES (?, ?, ?, ?, ?)",
                    (session_id, start + i, t.role, t.content, t.turn_id),
                )

    def upsert_assistant_turn(self, session_id: str, turn_id: str, content: str) -> None:
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise KeyError(session_id)
            existing = self._conn.execute(
                "SELECT seq FROM turns WHERE session_id = ? AND role = 'assistant' AND turn_id = ? ORDER BY seq DESC LIMIT 1",
                (session_id, turn_id),
            ).fetchone()
            if existing is not None:
                self._conn.execute(
                    "UPDATE turns SET content = ? WHERE session_id = ? AND seq = ?",
                    (content, session_id, int(existing["seq"])),
                )
                return
            last = self._conn.execute(
                "SELECT seq FROM turns WHERE session_id = ? ORDER BY seq DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            next_seq = 0 if last is None else int(last["seq"]) + 1
            self._conn.execute(
                "INSERT INTO turns (session_id, seq, role, content, turn_id) VALUES (?, ?, ?, ?, ?)",
                (session_id, next_seq, "assistant", content, turn_id),
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

    def list_sessions(
        self,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
        unscoped_actor_user_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChatSessionSummary]:
        with self._lock:
            # Static SQL only (no f-strings / dynamic WHERE fragments) for tooling safety.
            if workspace_id is not None:
                rows = self._conn.execute(
                    """
                    SELECT
                        s.session_id,
                        s.created_at,
                        s.user_id,
                        s.workspace_id,
                        COUNT(t.id) AS turn_count,
                        (
                            SELECT t2.content FROM turns t2
                            WHERE t2.session_id = s.session_id AND t2.role = 'user'
                            ORDER BY t2.seq ASC LIMIT 1
                        ) AS first_user_content
                    FROM sessions s
                    LEFT JOIN turns t ON t.session_id = s.session_id
                    WHERE (? IS NULL OR s.user_id = ?)
                      AND (? IS NULL OR s.workspace_id = ?)
                    GROUP BY s.session_id
                    HAVING turn_count > 0
                    ORDER BY s.created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (user_id, user_id, workspace_id, workspace_id, limit, offset),
                ).fetchall()
            elif unscoped_actor_user_id is not None:
                rows = self._conn.execute(
                    """
                    SELECT
                        s.session_id,
                        s.created_at,
                        s.user_id,
                        s.workspace_id,
                        COUNT(t.id) AS turn_count,
                        (
                            SELECT t2.content FROM turns t2
                            WHERE t2.session_id = s.session_id AND t2.role = 'user'
                            ORDER BY t2.seq ASC LIMIT 1
                        ) AS first_user_content
                    FROM sessions s
                    LEFT JOIN turns t ON t.session_id = s.session_id
                    WHERE (s.user_id IS NULL AND s.workspace_id IS NULL) OR s.user_id = ?
                    GROUP BY s.session_id
                    HAVING turn_count > 0
                    ORDER BY s.created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (unscoped_actor_user_id, limit, offset),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT
                        s.session_id,
                        s.created_at,
                        s.user_id,
                        s.workspace_id,
                        COUNT(t.id) AS turn_count,
                        (
                            SELECT t2.content FROM turns t2
                            WHERE t2.session_id = s.session_id AND t2.role = 'user'
                            ORDER BY t2.seq ASC LIMIT 1
                        ) AS first_user_content
                    FROM sessions s
                    LEFT JOIN turns t ON t.session_id = s.session_id
                    WHERE (? IS NULL OR s.user_id = ?)
                      AND (? IS NULL OR s.workspace_id = ?)
                    GROUP BY s.session_id
                    HAVING turn_count > 0
                    ORDER BY s.created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (user_id, user_id, workspace_id, workspace_id, limit, offset),
                ).fetchall()
            out: list[ChatSessionSummary] = []
            for r in rows:
                raw = str(r["first_user_content"] or "")
                preview = (raw[:120] + "…") if len(raw) > 120 else raw
                out.append(
                    ChatSessionSummary(
                        session_id=str(r["session_id"]),
                        preview=preview,
                        turn_count=int(r["turn_count"]),
                        created_at=r["created_at"],
                        user_id=r["user_id"],
                        workspace_id=r["workspace_id"],
                    )
                )
            return out

    def delete_session(self, session_id: str) -> bool:
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return False
            self._conn.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            return True
