"""Firestore-backed chat session store — durable across Cloud Run revisions (shared GCP project)."""
from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Any, Sequence
from uuid import uuid4

from google.cloud import firestore
from google.cloud.firestore import transactional

from src.persistence.chat_session_store import ChatSessionRecord, ChatSessionSummary, ChatTurn, _normalize_turns


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class FirestoreChatSessionStore:
    """
    One document per session: ``{collection}/{session_id}`` with fields
    ``upstream_ref``, ``created_at``, ``turns`` (array of {role, content}), ``turn_count``.

    Uses transactions on append. Firestore documents are capped (~1 MiB); very long threads may
    need a subcollection-backed store later.
    """

    def __init__(
        self,
        collection_name: str,
        *,
        project: str | None = None,
        client: firestore.Client | None = None,
    ) -> None:
        self._lock = RLock()
        self._coll_name = collection_name.strip() or "ham_chat_sessions"
        if client is not None:
            self._db = client
        else:
            self._db = firestore.Client(project=project) if project else firestore.Client()

    def _coll(self) -> firestore.CollectionReference:
        return self._db.collection(self._coll_name)

    def create_session(self) -> str:
        sid = str(uuid4())
        now = _utc_now_iso()
        with self._lock:
            self._coll().document(sid).set(
                {
                    "upstream_ref": None,
                    "created_at": now,
                    "turns": [],
                    "turn_count": 0,
                },
            )
        return sid

    def get_session(self, session_id: str) -> ChatSessionRecord | None:
        with self._lock:
            snap = self._coll().document(session_id).get()
            if not snap.exists:
                return None
            data = snap.to_dict() or {}
            turns_raw = data.get("turns") or []
            turns = [ChatTurn(role=str(t.get("role", "")), content=str(t.get("content", ""))) for t in turns_raw]
            return ChatSessionRecord(
                session_id=session_id,
                turns=turns,
                upstream_ref=data.get("upstream_ref"),
                created_at=str(data.get("created_at")) if data.get("created_at") is not None else None,
            )

    def append_turns(self, session_id: str, turns: Sequence[ChatTurn | dict[str, Any]]) -> None:
        normalized = _normalize_turns(turns)
        doc_ref = self._coll().document(session_id)
        new_chunks = [{"role": t.role, "content": t.content} for t in normalized]

        @transactional
        def _append(transaction: firestore.Transaction, ref: firestore.DocumentReference) -> None:
            snap = ref.get(transaction=transaction)
            if not snap.exists:
                raise KeyError(session_id)
            data = snap.to_dict() or {}
            cur = list(data.get("turns") or [])
            cur.extend(new_chunks)
            transaction.update(
                ref,
                {
                    "turns": cur,
                    "turn_count": len(cur),
                },
            )

        transaction = self._db.transaction()
        with self._lock:
            _append(transaction, doc_ref)

    def set_upstream_ref(self, session_id: str, ref: str | None) -> None:
        doc_ref = self._coll().document(session_id)

        @transactional
        def _set(transaction: firestore.Transaction, r: firestore.DocumentReference) -> None:
            snap = r.get(transaction=transaction)
            if not snap.exists:
                raise KeyError(session_id)
            transaction.update(r, {"upstream_ref": ref})

        transaction = self._db.transaction()
        with self._lock:
            _set(transaction, doc_ref)

    def list_messages(self, session_id: str) -> list[dict[str, str]]:
        rec = self.get_session(session_id)
        if rec is None:
            raise KeyError(session_id)
        return [{"role": t.role, "content": t.content} for t in rec.turns]

    def list_sessions(self, *, limit: int = 50, offset: int = 0) -> list[ChatSessionSummary]:
        """
        Newest first by ``created_at``. Over-fetches when ``offset`` is large (MVP); prefer cursors later.
        """
        cap = min(2000, max(limit + offset + 25, limit * 3))
        with self._lock:
            q = self._coll().order_by("created_at", direction=firestore.Query.DESCENDING).limit(cap)
            candidates: list[ChatSessionSummary] = []
            for doc in q.stream():
                data = doc.to_dict() or {}
                tc = int(data.get("turn_count", 0))
                if tc <= 0:
                    continue
                turns = data.get("turns") or []
                first_user = ""
                for t in turns:
                    if str(t.get("role", "")) == "user":
                        first_user = str(t.get("content", ""))
                        break
                preview = (first_user[:120] + "…") if len(first_user) > 120 else first_user
                candidates.append(
                    ChatSessionSummary(
                        session_id=doc.id,
                        preview=preview,
                        turn_count=tc,
                        created_at=str(data["created_at"]) if data.get("created_at") is not None else None,
                    ),
                )
        return candidates[offset : offset + limit]
