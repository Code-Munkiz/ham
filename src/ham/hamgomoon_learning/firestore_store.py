"""Firestore-backed HAMgomoon learning records store (M1 F3 implementation).

Implements the ``FirestoreHamgomoonLearningStore`` backend for the
``HamgomoonLearningStoreProtocol``. Selected by the factory in
:mod:`src.ham.hamgomoon_learning.store` when
``HAM_HAMGOMOON_LEARNING_BACKEND=firestore``.

Collection layout::

    ham_hamgomoon_learning/{record_id}

Each document stores a :class:`~src.ham.hamgomoon_learning.models.LearningRecord`
serialised via ``model_dump()`` after the full redaction pipeline
(:func:`~src.ham.hamgomoon_learning.redaction.redact_learning_record`) is applied.

Redaction pipeline preserved end-to-end:
    ``redact_learning_record`` scrubs bearer tokens, Telegram bot tokens,
    ``xai-`` keys, ``HAM_*TOKEN=`` env patterns, URL query auth parameters,
    and collapses ``external_platform_id`` values via ``redact_external_id``.

Fail-closed:
    Any exception from the Firestore SDK is wrapped in
    :class:`FirestoreHamgomoonLearningStoreError` and re-raised.  The store
    **never** silently falls back to the file backend.

Per-store env-var overrides::

    HAM_HAMGOMOON_LEARNING_FIRESTORE_PROJECT_ID  -> HAM_FIRESTORE_PROJECT_ID
    HAM_HAMGOMOON_LEARNING_FIRESTORE_DATABASE    -> HAM_FIRESTORE_DATABASE
    HAM_HAMGOMOON_LEARNING_FIRESTORE_COLLECTION  (default ham_hamgomoon_learning)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.ham.hamgomoon_learning.models import LearningRecord
from src.ham.hamgomoon_learning.redaction import redact_learning_record

_FS_PROJECT_ENV = "HAM_HAMGOMOON_LEARNING_FIRESTORE_PROJECT_ID"
_FS_DATABASE_ENV = "HAM_HAMGOMOON_LEARNING_FIRESTORE_DATABASE"
_FS_COLLECTION_ENV = "HAM_HAMGOMOON_LEARNING_FIRESTORE_COLLECTION"
_FALLBACK_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FALLBACK_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"
_DEFAULT_COLLECTION = "ham_hamgomoon_learning"


def _resolve_env(primary: str, fallback: str | None = None) -> str | None:
    val = (os.environ.get(primary) or "").strip()
    if val:
        return val
    if fallback is not None:
        val = (os.environ.get(fallback) or "").strip()
        if val:
            return val
    return None


def _matches(
    data: dict[str, Any],
    *,
    workspace_id: str | None,
    project_id: str | None,
    channel: str | None,
) -> bool:
    if workspace_id is not None and data.get("workspace_id") != workspace_id:
        return False
    if project_id is not None and data.get("project_id") != project_id:
        return False
    if channel is not None and data.get("channel") != channel:
        return False
    return True


def _summarize_from_records(records: list[LearningRecord]) -> dict[str, list[str]]:  # noqa: C901
    """Bucket recent learning records into hint categories.

    Mirrors :func:`~src.ham.hamgomoon_learning.store.summarize_learning_hints`
    without the file-I/O layer so the Firestore backend can reuse the logic.
    """
    recent_lessons: list[str] = []
    avoid_list: list[str] = []
    good_examples: list[str] = []
    recurring_preferences: list[str] = []
    reason_counts: dict[str, int] = {}

    for rec in records:
        critique = rec.critique
        if critique is not None:
            if critique.reusable_lesson:
                recent_lessons.append(critique.reusable_lesson)
            for flag in critique.risk_flags:
                if not flag:
                    continue
                if flag not in avoid_list:
                    avoid_list.append(flag)
        review = rec.review
        if review is not None:
            if review.decision == "approved":
                snippet = (rec.draft.draft_text or "").strip()
                if snippet:
                    snippet_short = snippet if len(snippet) <= 160 else snippet[:157] + "..."
                    good_examples.append(snippet_short)
            for tag in review.reason_tags:
                if not tag:
                    continue
                reason_counts[tag] = reason_counts.get(tag, 0) + 1

    for tag, count in sorted(reason_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if count >= 2:
            recurring_preferences.append(tag)

    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
        return out

    return {
        "recent_lessons": _dedupe(recent_lessons),
        "avoid_list": _dedupe(avoid_list),
        "good_examples": _dedupe(good_examples),
        "recurring_preferences": _dedupe(recurring_preferences),
    }


class FirestoreHamgomoonLearningStoreError(RuntimeError):
    """Wrapper for unexpected errors from the Firestore SDK.

    Raised by every method when the Firestore client raises, ensuring callers
    never silently swallow SDK errors and the API layer can convert them to
    structured ``503 firestore_unavailable`` responses.
    """


class FirestoreHamgomoonLearningStore:
    """Firestore-backed HAMgomoon learning records store.

    Satisfies :class:`~src.ham.hamgomoon_learning.store.HamgomoonLearningStoreProtocol`.

    The constructor accepts an injected ``client`` for tests; in production
    the real ``google.cloud.firestore.Client`` is constructed lazily on first
    method call so importing this module never contacts Firestore at import time.
    """

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str | None = None,
        collection: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._project = project or _resolve_env(_FS_PROJECT_ENV, _FALLBACK_PROJECT_ENV)
        self._database = database or _resolve_env(_FS_DATABASE_ENV, _FALLBACK_DATABASE_ENV)
        coll = collection or _resolve_env(_FS_COLLECTION_ENV) or _DEFAULT_COLLECTION
        self._coll_name = coll.strip() or _DEFAULT_COLLECTION
        self._client = client

    # ------------------------------------------------------------------
    # Lazy client helper
    # ------------------------------------------------------------------

    def _db(self) -> Any:
        """Return the Firestore client, constructing it lazily when not injected."""
        if self._client is not None:
            return self._client
        try:
            from google.cloud import firestore  # noqa: PLC0415
        except ImportError as exc:
            msg = (
                "google-cloud-firestore is required when HAM_HAMGOMOON_LEARNING_BACKEND=firestore."
            )
            raise FirestoreHamgomoonLearningStoreError(msg) from exc
        kwargs: dict[str, Any] = {}
        if self._project:
            kwargs["project"] = self._project
        if self._database:
            kwargs["database"] = self._database
        self._client = firestore.Client(**kwargs) if kwargs else firestore.Client()
        return self._client

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def append_learning_record(
        self,
        record: LearningRecord,
        *,
        path: Path | None = None,  # ignored for Firestore backend
    ) -> LearningRecord:
        """Redact and persist a learning record to Firestore.

        Applies the full redaction pipeline before writing: ``redact_text``,
        banned-secret-name scrub, and ``redact_external_id`` for the delivery
        outcome's ``external_platform_id``.

        Args:
            record: The learning record to persist.
            path:   Ignored for the Firestore backend (kept for Protocol compat).

        Returns:
            The redacted :class:`LearningRecord` that was persisted.

        Raises:
            FirestoreHamgomoonLearningStoreError: On any Firestore SDK error.
        """
        redacted = redact_learning_record(record)
        payload = redacted.model_dump()
        db = self._db()
        try:
            db.collection(self._coll_name).document(redacted.record_id).set(payload)
        except FirestoreHamgomoonLearningStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FirestoreHamgomoonLearningStoreError(
                f"Firestore append_learning_record failed: {exc}"
            ) from exc
        return redacted

    def list_recent_learning_records(
        self,
        *,
        workspace_id: str | None = None,
        project_id: str | None = None,
        channel: str | None = None,
        limit: int = 50,
        path: Path | None = None,  # ignored for Firestore backend
    ) -> list[LearningRecord]:
        """Return the ``limit`` most recent learning records, oldest-first.

        Filters by ``workspace_id``, ``project_id``, and ``channel`` when
        provided. Streams all documents and sorts by ``created_at`` in Python
        (no server-side ordering required).

        An empty collection returns ``[]`` (not an error).

        Args:
            workspace_id: Optional workspace filter.
            project_id:   Optional project filter.
            channel:      Optional channel filter (``"telegram"`` etc.).
            limit:        Maximum number of records (clamped to [1, 500]).
            path:         Ignored for the Firestore backend.

        Raises:
            FirestoreHamgomoonLearningStoreError: On any Firestore SDK error or
                if a stored document fails schema validation (skipped gracefully).
        """
        db = self._db()
        try:
            docs = list(db.collection(self._coll_name).stream())
        except FirestoreHamgomoonLearningStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FirestoreHamgomoonLearningStoreError(
                f"Firestore list_recent_learning_records failed: {exc}"
            ) from exc

        clamped = max(1, min(int(limit), 500))
        candidates: list[LearningRecord] = []
        for snap in docs:
            data = snap.to_dict() or {}
            if not _matches(
                data, workspace_id=workspace_id, project_id=project_id, channel=channel
            ):
                continue
            try:
                candidates.append(LearningRecord.model_validate(data))
            except (ValidationError, Exception):  # noqa: BLE001, S112
                continue

        # Sort chronologically (ascending created_at) to match file-backend order.
        candidates.sort(key=lambda r: r.created_at)
        # Return the most-recent ``limit`` records in chronological order.
        return candidates[-clamped:] if len(candidates) > clamped else candidates

    def summarize_learning_hints(
        self,
        *,
        workspace_id: str | None = None,
        project_id: str | None = None,
        channel: str | None = None,
        limit: int = 50,
        path: Path | None = None,  # ignored for Firestore backend
    ) -> dict[str, list[str]]:
        """Roll recent records into rough hint buckets for future drafts.

        Mirrors :func:`~src.ham.hamgomoon_learning.store.summarize_learning_hints`
        using the Firestore backend as the data source.

        Raises:
            FirestoreHamgomoonLearningStoreError: On any Firestore SDK error.
        """
        records = self.list_recent_learning_records(
            workspace_id=workspace_id,
            project_id=project_id,
            channel=channel,
            limit=limit,
            path=path,
        )
        return _summarize_from_records(records)


__all__ = [
    "FirestoreHamgomoonLearningStore",
    "FirestoreHamgomoonLearningStoreError",
]
