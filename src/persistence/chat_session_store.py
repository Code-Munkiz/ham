"""
Ham-owned chat session persistence (in-memory MVP; swap for SQLite/DB later).

Session IDs are issued by Ham. Upstream gateway conversation refs stay server-side only.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from threading import RLock
from typing import Any, Protocol, Sequence, runtime_checkable


@dataclass
class ChatTurn:
    role: str
    content: str


@dataclass
class ChatSessionRecord:
    session_id: str
    turns: list[ChatTurn] = field(default_factory=list)
    upstream_ref: str | None = None


def _normalize_turns(turns: Sequence[ChatTurn | dict[str, Any]]) -> list[ChatTurn]:
    out: list[ChatTurn] = []
    for t in turns:
        if isinstance(t, ChatTurn):
            out.append(t)
        else:
            role = str(t.get("role", "")).strip()
            content = str(t.get("content", ""))
            out.append(ChatTurn(role=role, content=content))
    return out


@runtime_checkable
class ChatSessionStore(Protocol):
    """Contract for chat persistence (implementations: memory, SQLite, …)."""

    def create_session(self) -> str: ...

    def get_session(self, session_id: str) -> ChatSessionRecord | None: ...

    def append_turns(self, session_id: str, turns: Sequence[ChatTurn | dict[str, Any]]) -> None: ...

    def set_upstream_ref(self, session_id: str, ref: str | None) -> None: ...

    def list_messages(self, session_id: str) -> list[dict[str, str]]: ...


class InMemoryChatSessionStore:
    """Thread-safe in-process store for development and tests."""

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSessionRecord] = {}
        self._lock = RLock()

    def create_session(self) -> str:
        sid = str(uuid.uuid4())
        with self._lock:
            self._sessions[sid] = ChatSessionRecord(session_id=sid, turns=[], upstream_ref=None)
        return sid

    def get_session(self, session_id: str) -> ChatSessionRecord | None:
        with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                return None
            return replace(rec, turns=list(rec.turns))

    def append_turns(self, session_id: str, turns: Sequence[ChatTurn | dict[str, Any]]) -> None:
        normalized = _normalize_turns(turns)
        with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                raise KeyError(session_id)
            rec.turns.extend(normalized)

    def set_upstream_ref(self, session_id: str, ref: str | None) -> None:
        with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                raise KeyError(session_id)
            rec.upstream_ref = ref

    def list_messages(self, session_id: str) -> list[dict[str, str]]:
        with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                raise KeyError(session_id)
            return [{"role": t.role, "content": t.content} for t in rec.turns]
