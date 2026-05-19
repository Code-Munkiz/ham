"""Firestore-backed BuilderRunEventsStore — Phase 2.5.

Mirrors :class:`BuilderRunEventsStoreProtocol` with one extra method
(``latest_seq``) used by the Worker startup guard.

Layout::

    {collection}/{job_id}/events/{seq:010d}

The zero-padded ``seq`` is the document ID so Firestore's lexicographic
ordering matches numeric ordering — no composite index required, no
ordering field in the query.

Selected when ``HAM_BUILDER_RUN_EVENTS_STORE_BACKEND=firestore`` (default
remains file-backed). See ADR-0012, ADR-0013, ADR-0002.

## Seq assignment

The store maintains a per-job in-memory counter (per-process, scoped to
this store instance). On each ``append`` it assigns ``next_seq`` and writes
the event document with ``create()`` — not ``set()`` / ``upsert()``. A
duplicate ``seq`` therefore fails loudly with
:class:`FirestoreBuilderRunEventsDuplicateSeq` rather than silently
overwriting an existing event.

Because the contract guarantees one Worker per ``job_id`` (ADR-0001 +
ADR-0007 + Phase 2.5 Dispatcher transition), the in-memory counter is
safe. The Worker calls ``latest_seq(job_id)`` at startup; if it returns
non-zero for a supposedly-fresh job, the Worker fails loudly before
writing any events.

Env vars (per-store first, shared HAM_FIRESTORE_* fallback):

- ``HAM_BUILDER_RUN_EVENTS_FIRESTORE_PROJECT_ID``  -> ``HAM_FIRESTORE_PROJECT_ID``
- ``HAM_BUILDER_RUN_EVENTS_FIRESTORE_DATABASE``    -> ``HAM_FIRESTORE_DATABASE``
- ``HAM_BUILDER_RUN_EVENTS_FIRESTORE_COLLECTION``  (default ``builder_run_events``)
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from src.ham.builder_plan import SSEEvent

_LOG = logging.getLogger(__name__)

_BRE_FS_PROJECT_ENV = "HAM_BUILDER_RUN_EVENTS_FIRESTORE_PROJECT_ID"
_BRE_FS_DATABASE_ENV = "HAM_BUILDER_RUN_EVENTS_FIRESTORE_DATABASE"
_BRE_FS_COLLECTION_ENV = "HAM_BUILDER_RUN_EVENTS_FIRESTORE_COLLECTION"

_FALLBACK_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FALLBACK_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"

_DEFAULT_COLLECTION = "builder_run_events"
_EVENTS_SUBCOLLECTION = "events"
_SEQ_DOC_FORMAT = "{seq:010d}"


class FirestoreBuilderRunEventsStoreError(RuntimeError):
    """Wrapper for unexpected errors from the Firestore SDK."""


class FirestoreBuilderRunEventsDuplicateSeq(FirestoreBuilderRunEventsStoreError):
    """Raised when a ``create()`` write hits an existing event document.

    This is the storage-layer guardrail that backs ADR-0013: a duplicate
    ``seq`` means our one-Worker-per-job invariant was violated. Fail
    loudly rather than silently overwriting.
    """


def _resolve_env(primary: str, fallback: str | None = None) -> str | None:
    val = (os.environ.get(primary) or "").strip()
    if val:
        return val
    if fallback is not None:
        val = (os.environ.get(fallback) or "").strip()
        if val:
            return val
    return None


class FirestoreBuilderRunEventsStore:
    """Firestore implementation of :class:`BuilderRunEventsStoreProtocol`.

    Plus the :meth:`latest_seq` method required by the Phase 2.5 Worker
    startup guard.
    """

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str | None = None,
        collection: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._project = project or _resolve_env(
            _BRE_FS_PROJECT_ENV, _FALLBACK_PROJECT_ENV,
        )
        self._database = database or _resolve_env(
            _BRE_FS_DATABASE_ENV, _FALLBACK_DATABASE_ENV,
        )
        coll = (
            collection
            or _resolve_env(_BRE_FS_COLLECTION_ENV)
            or _DEFAULT_COLLECTION
        )
        self._coll_name = coll.strip() or _DEFAULT_COLLECTION
        self._client = client
        # Per-process, per-job in-memory counter for seq assignment.
        self._counter_lock = threading.Lock()
        self._counters: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Lazy client + helpers
    # ------------------------------------------------------------------

    def _db(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.cloud import firestore  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            msg = (
                "google-cloud-firestore is required when "
                "HAM_BUILDER_RUN_EVENTS_STORE_BACKEND=firestore."
            )
            raise FirestoreBuilderRunEventsStoreError(msg) from exc
        kwargs: dict[str, Any] = {}
        if self._project:
            kwargs["project"] = self._project
        if self._database:
            kwargs["database"] = self._database
        self._client = firestore.Client(**kwargs) if kwargs else firestore.Client()
        return self._client

    def _job_doc(self, job_id: str) -> Any:
        return self._db().collection(self._coll_name).document(job_id)

    def _events_coll(self, job_id: str) -> Any:
        return self._job_doc(job_id).collection(_EVENTS_SUBCOLLECTION)

    @staticmethod
    def _wrap(op: str, exc: Exception) -> FirestoreBuilderRunEventsStoreError:
        return FirestoreBuilderRunEventsStoreError(
            f"firestore builder run events store: {op} failed: {exc}",
        )

    @staticmethod
    def _hydrate_datetimes(raw: dict[str, Any]) -> dict[str, Any]:
        out = dict(raw)
        for k, v in list(out.items()):
            if isinstance(v, datetime) and v.tzinfo is None:
                out[k] = v.replace(tzinfo=UTC)
        return out

    @classmethod
    def _validate(cls, snap: Any) -> SSEEvent | None:
        data = snap.to_dict() or {}
        try:
            return SSEEvent.model_validate(cls._hydrate_datetimes(data))
        except ValidationError as exc:
            doc_id = getattr(snap, "id", "<unknown>")
            _LOG.warning(
                "skipping malformed event %s (%s): %s",
                doc_id,
                type(exc).__name__,
                exc,
            )
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, event: SSEEvent) -> SSEEvent:
        """Assign the next ``seq`` for ``event.job_id`` and create the doc.

        Contract:
        - Incoming ``event.seq`` is ignored (matches file backend behaviour).
        - Per-job counter starts at 1 in this process; the Worker is expected
          to have called :meth:`latest_seq` at startup and refused to run if
          it found existing events for a supposedly-fresh job.
        - Write uses ``create()``; a duplicate ``seq`` raises
          :class:`FirestoreBuilderRunEventsDuplicateSeq`.
        """
        job_id = event.job_id
        with self._counter_lock:
            current = self._counters.get(job_id, 0)
            next_seq = current + 1
            self._counters[job_id] = next_seq

        updated = event.model_copy(update={"seq": next_seq})
        doc_id = _SEQ_DOC_FORMAT.format(seq=next_seq)
        payload = updated.model_dump(mode="json")

        try:
            self._events_coll(job_id).document(doc_id).create(payload)
        except Exception as exc:  # noqa: BLE001
            # Surface the google.api_core.exceptions.AlreadyExists case as a
            # typed error so callers can distinguish the invariant violation
            # from transient infra errors.
            if exc.__class__.__name__ == "AlreadyExists":
                # Roll the counter back so a caller-recovery retry doesn't
                # leave a permanent off-by-one.
                with self._counter_lock:
                    if self._counters.get(job_id) == next_seq:
                        self._counters[job_id] = current
                raise FirestoreBuilderRunEventsDuplicateSeq(
                    f"Event seq {next_seq} already exists for job {job_id!r} — "
                    "one-Worker-per-job invariant violated."
                ) from exc
            raise self._wrap("append", exc) from exc

        return updated

    def read_from(self, *, job_id: str, since_seq: int = 0) -> list[SSEEvent]:
        jid = (job_id or "").strip()
        if not jid:
            return []
        cursor = max(0, int(since_seq))
        cursor_doc_id = _SEQ_DOC_FORMAT.format(seq=cursor)
        try:
            # `start_after(document_id)` on the ordered subcollection scan
            # gives us strictly greater-than-cursor without needing a where
            # clause. Document IDs are zero-padded so lex order == numeric.
            query = self._events_coll(jid).order_by("__name__").start_after({"__name__": cursor_doc_id})
            stream = query.stream()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("read_from", exc) from exc
        out: list[SSEEvent] = []
        for snap in stream:
            evt = self._validate(snap)
            if evt is not None and evt.seq > cursor:
                out.append(evt)
        return sorted(out, key=lambda e: e.seq)

    def latest_seq(self, *, job_id: str) -> int:
        """Return the largest ``seq`` for ``job_id``, or 0 if none.

        Used by the Worker startup guard (ADR-0013). Falls back to 0 on
        empty / missing.
        """
        jid = (job_id or "").strip()
        if not jid:
            return 0
        try:
            # Reverse-sort by document ID and pull the first doc.
            try:
                from google.cloud.firestore import Query  # noqa: PLC0415

                direction = Query.DESCENDING
            except ImportError:
                direction = "DESCENDING"
            query = self._events_coll(jid).order_by("__name__", direction=direction).limit(1)
            docs = list(query.stream())
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("latest_seq", exc) from exc
        if not docs:
            return 0
        latest = self._validate(docs[0])
        if latest is None:
            return 0
        # Seed the in-memory counter from storage so the very first append in
        # this process picks up after any prior writes. Safe because the
        # Worker startup guard runs BEFORE the first append and refuses to
        # proceed if this value is non-zero for a fresh job.
        with self._counter_lock:
            if self._counters.get(jid, 0) < latest.seq:
                self._counters[jid] = latest.seq
        return latest.seq
