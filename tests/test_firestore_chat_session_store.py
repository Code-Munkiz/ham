"""Firestore chat session store (in-memory fake client; transactional short-circuit for tests)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from google.cloud.firestore import Query

from src.persistence.chat_session_store import ChatTurn
from src.persistence.firestore_chat_session_store import FirestoreChatSessionStore


@dataclass
class _FakeDocSnap:
    id: str
    _data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


@dataclass
class _FakeDocRef:
    root: _FakeFirestoreClient
    id: str

    def set(self, data: dict[str, Any], _merge: bool = False) -> None:
        self.root.docs[self.id] = dict(data)

    def get(self, transaction: Any = None) -> Any:
        data = self.root.docs.get(self.id)

        class _Snap:
            exists = data is not None

            def to_dict(self) -> dict[str, Any]:
                return dict(data) if data else {}

        return _Snap()


@dataclass
class _FakeQuery:
    root: _FakeFirestoreClient
    field: str
    desc: bool
    _limit: int = 1000

    def limit(self, n: int) -> _FakeQuery:
        self._limit = n
        return self

    def stream(self):
        rows = [(doc_id, dict(d)) for doc_id, d in self.root.docs.items()]
        rows.sort(key=lambda x: str(x[1].get(self.field, "")), reverse=self.desc)
        for doc_id, data in rows[: self._limit]:
            yield _FakeDocSnap(doc_id, data)


@dataclass
class _FakeCollection:
    root: _FakeFirestoreClient
    name: str

    def document(self, sid: str) -> _FakeDocRef:
        return _FakeDocRef(self.root, sid)

    def order_by(self, field: str, direction: str | None = None) -> _FakeQuery:
        desc = direction == Query.DESCENDING
        return _FakeQuery(self.root, field, desc)


@dataclass
class _FakeTxn:
    root: _FakeFirestoreClient

    def update(self, ref: _FakeDocRef, patch: dict[str, Any]) -> None:
        cur = dict(self.root.docs[ref.id])
        if "turns" in patch:
            cur["turns"] = list(patch["turns"])
        if "turn_count" in patch:
            cur["turn_count"] = patch["turn_count"]
        if "upstream_ref" in patch:
            cur["upstream_ref"] = patch["upstream_ref"]
        self.root.docs[ref.id] = cur


class _FakeFirestoreClient:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self, name)

    def transaction(self) -> _FakeTxn:
        return _FakeTxn(self)


@pytest.fixture(autouse=True)
def _transactional_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid real Begin/Commit; exercise the same @transactional-wrapped callables as production."""

    from google.cloud.firestore_v1.transaction import _Transactional

    def _call(self, transaction, *args, **kwargs):
        return self.to_wrap(transaction, *args, **kwargs)

    monkeypatch.setattr(_Transactional, "__call__", _call)


def test_firestore_create_append_list_messages() -> None:
    fake = _FakeFirestoreClient()
    store = FirestoreChatSessionStore("sessions", client=fake)  # type: ignore[arg-type]
    sid = store.create_session(user_id="user-a", workspace_id="ws-1")
    assert fake.docs[sid]["user_id"] == "user-a"
    assert fake.docs[sid]["workspace_id"] == "ws-1"
    store.append_turns(sid, [ChatTurn(role="user", content="hi")])
    store.append_turns(sid, [ChatTurn(role="assistant", content="yo")])
    rec = store.get_session(sid)
    assert rec is not None
    assert rec.user_id == "user-a"
    assert rec.workspace_id == "ws-1"
    assert store.list_messages(sid) == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "yo"},
    ]


def test_firestore_get_session_unknown() -> None:
    fake = _FakeFirestoreClient()
    store = FirestoreChatSessionStore("sessions", client=fake)  # type: ignore[arg-type]
    assert store.get_session("missing") is None


def test_firestore_append_unknown_raises() -> None:
    fake = _FakeFirestoreClient()
    store = FirestoreChatSessionStore("sessions", client=fake)  # type: ignore[arg-type]
    with pytest.raises(KeyError):
        store.append_turns("nope", [ChatTurn(role="user", content="x")])


def test_firestore_list_messages_unknown_raises() -> None:
    fake = _FakeFirestoreClient()
    store = FirestoreChatSessionStore("sessions", client=fake)  # type: ignore[arg-type]
    with pytest.raises(KeyError):
        store.list_messages("nope")


def test_firestore_list_sessions_skips_empty() -> None:
    fake = _FakeFirestoreClient()
    store = FirestoreChatSessionStore("sessions", client=fake)  # type: ignore[arg-type]
    a = store.create_session()
    b = store.create_session()
    store.append_turns(b, [ChatTurn(role="user", content="second")])
    summaries = store.list_sessions(limit=10, offset=0)
    ids = {s.session_id for s in summaries}
    assert a not in ids
    assert b in ids
    assert summaries[0].session_id == b


def test_firestore_set_upstream_ref() -> None:
    fake = _FakeFirestoreClient()
    store = FirestoreChatSessionStore("sessions", client=fake)  # type: ignore[arg-type]
    sid = store.create_session()
    store.set_upstream_ref(sid, "gw-123")
    rec = store.get_session(sid)
    assert rec is not None
    assert rec.upstream_ref == "gw-123"


def test_firestore_upsert_assistant_turn_updates_single_turn() -> None:
    fake = _FakeFirestoreClient()
    store = FirestoreChatSessionStore("sessions", client=fake)  # type: ignore[arg-type]
    sid = store.create_session()
    store.append_turns(sid, [ChatTurn(role="user", content="hello")])
    store.upsert_assistant_turn(sid, "turn-1", "partial")
    store.upsert_assistant_turn(sid, "turn-1", "final")
    assert store.list_messages(sid) == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "final"},
    ]


def _create_with_turn(
    store: FirestoreChatSessionStore,
    text: str,
    *,
    user_id: str | None = None,
    workspace_id: str | None = None,
) -> str:
    sid = store.create_session(user_id=user_id, workspace_id=workspace_id)
    store.append_turns(sid, [ChatTurn(role="user", content=text)])
    return sid


def test_firestore_scoped_sessions_are_private_by_user_and_workspace() -> None:
    fake = _FakeFirestoreClient()
    store = FirestoreChatSessionStore("sessions", client=fake)  # type: ignore[arg-type]
    user_a_ws_1 = _create_with_turn(store, "a/w1", user_id="user-a", workspace_id="ws-1")
    user_b_ws_1 = _create_with_turn(store, "b/w1", user_id="user-b", workspace_id="ws-1")
    user_a_ws_2 = _create_with_turn(store, "a/w2", user_id="user-a", workspace_id="ws-2")

    scoped = store.list_sessions(user_id="user-a", workspace_id="ws-1")
    assert [s.session_id for s in scoped] == [user_a_ws_1]
    assert scoped[0].user_id == "user-a"
    assert scoped[0].workspace_id == "ws-1"

    assert user_b_ws_1 not in {s.session_id for s in scoped}
    assert user_a_ws_2 not in {s.session_id for s in scoped}


def test_firestore_legacy_sessions_remain_unscoped_but_hidden_from_scoped_lists() -> None:
    fake = _FakeFirestoreClient()
    store = FirestoreChatSessionStore("sessions", client=fake)  # type: ignore[arg-type]
    legacy = _create_with_turn(store, "legacy")
    scoped = _create_with_turn(store, "scoped", user_id="user-a", workspace_id="ws-1")

    assert {s.session_id for s in store.list_sessions()} == {legacy, scoped}
    assert [s.session_id for s in store.list_sessions(user_id="user-a", workspace_id="ws-1")] == [scoped]
    assert legacy not in {s.session_id for s in store.list_sessions(workspace_id="ws-1")}


def test_firestore_unscoped_actor_sees_legacy_and_own_sessions_only() -> None:
    fake = _FakeFirestoreClient()
    store = FirestoreChatSessionStore("sessions", client=fake)  # type: ignore[arg-type]
    legacy = _create_with_turn(store, "legacy")
    mine = _create_with_turn(store, "mine", user_id="user-a", workspace_id="ws-1")
    other = _create_with_turn(store, "other", user_id="user-b", workspace_id="ws-1")

    visible = store.list_sessions(unscoped_actor_user_id="user-a")
    assert {s.session_id for s in visible} == {legacy, mine}
    assert other not in {s.session_id for s in visible}
