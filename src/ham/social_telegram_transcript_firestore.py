"""Firestore-backed Telegram inbound transcript store (M1 F4 implementation).

Implements the ``FirestoreTelegramTranscriptStore`` backend for the
``TelegramTranscriptStoreProtocol``. Selected by the factory in
:mod:`src.ham.social_telegram_transcript_store` when
``HAM_TELEGRAM_TRANSCRIPT_BACKEND=firestore``.

Collection layout::

    ham_social_telegram_transcripts/{doc_uuid}

Each document stores a transcript row with the redacted, allow-listed fields
matching the existing JSONL contract used by ``social_telegram_inbound.py``:
``source``, ``role``, ``text``, ``chat_id``, ``author_id``, ``message_id``,
``created_at`` (plus optional ``chat_type`` and ``already_answered``).

Redaction:
    Free-form ``text`` is passed through
    :func:`~src.ham.hamgomoon_learning.redaction.redact_text` before storage.
    ``chat_id``, ``author_id``, and ``message_id`` are preserved as integers
    (masking is applied downstream by the inbound discoverer's ``_mask_ref``).

Fail-closed:
    Any exception from the Firestore SDK is wrapped in
    :class:`FirestoreTelegramTranscriptStoreError` and re-raised.  The store
    **never** silently falls back to the file backend.

Per-store env-var overrides::

    HAM_TELEGRAM_TRANSCRIPT_FIRESTORE_PROJECT_ID  -> HAM_FIRESTORE_PROJECT_ID
    HAM_TELEGRAM_TRANSCRIPT_FIRESTORE_DATABASE    -> HAM_FIRESTORE_DATABASE
    HAM_TELEGRAM_TRANSCRIPT_FIRESTORE_COLLECTION  (default ham_social_telegram_transcripts)
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from typing import Any

_FS_PROJECT_ENV = "HAM_TELEGRAM_TRANSCRIPT_FIRESTORE_PROJECT_ID"
_FS_DATABASE_ENV = "HAM_TELEGRAM_TRANSCRIPT_FIRESTORE_DATABASE"
_FS_COLLECTION_ENV = "HAM_TELEGRAM_TRANSCRIPT_FIRESTORE_COLLECTION"
_FALLBACK_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FALLBACK_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"
_DEFAULT_COLLECTION = "ham_social_telegram_transcripts"

# Allow-listed row fields (matches the JSONL contract in social_telegram_inbound.py)
_TRANSCRIPT_ROW_FIELDS = frozenset(
    {
        "source",
        "role",
        "text",
        "chat_id",
        "author_id",
        "message_id",
        "created_at",
        "chat_type",
        "already_answered",
    }
)


def _resolve_env(primary: str, fallback: str | None = None) -> str | None:
    val = (os.environ.get(primary) or "").strip()
    if val:
        return val
    if fallback is not None:
        val = (os.environ.get(fallback) or "").strip()
        if val:
            return val
    return None


def _redact_row_text(text: Any) -> Any:
    """Apply text redaction to the ``text`` field of a transcript row.

    Fail-closed on both import failure and runtime failure:

    * ``ImportError`` — the redaction module is unavailable; raises
      :class:`FirestoreTelegramTranscriptStoreError` so the row is never
      persisted with unredacted text.
    * Any other exception from ``redact_text()`` — also raises
      :class:`FirestoreTelegramTranscriptStoreError` for the same reason.

    Under no circumstances is unredacted free-form text silently returned.
    """
    if not isinstance(text, str):
        return text
    try:
        from src.ham.hamgomoon_learning.redaction import redact_text  # noqa: PLC0415
    except ImportError as exc:
        raise FirestoreTelegramTranscriptStoreError(
            "Redaction module unavailable; refusing to persist unredacted text."
        ) from exc
    try:
        return redact_text(text)
    except Exception as exc:  # noqa: BLE001
        raise FirestoreTelegramTranscriptStoreError(
            f"redact_text() failed; refusing to persist unredacted text: {exc}"
        ) from exc


class FirestoreTelegramTranscriptStoreError(RuntimeError):
    """Wrapper for unexpected errors from the Firestore SDK.

    Raised by every method when the Firestore client raises, ensuring callers
    never silently swallow SDK errors and the API layer can convert them to
    structured ``503 firestore_unavailable`` responses.
    """


class FirestoreTelegramTranscriptStore:
    """Firestore-backed Telegram inbound transcript store.

    Satisfies :class:`~src.ham.social_telegram_transcript_store.TelegramTranscriptStoreProtocol`.

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
                "google-cloud-firestore is required when HAM_TELEGRAM_TRANSCRIPT_BACKEND=firestore."
            )
            raise FirestoreTelegramTranscriptStoreError(msg) from exc
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

    def append_row(self, row: dict[str, Any]) -> None:
        """Redact and persist one allow-listed transcript row to Firestore.

        Applies the allow-list (``_TRANSCRIPT_ROW_FIELDS``) and redacts free-form
        ``text`` via :func:`~src.ham.hamgomoon_learning.redaction.redact_text`
        before writing. Numeric IDs (``chat_id``, ``author_id``, ``message_id``)
        are preserved as integers.

        Args:
            row: Transcript row dict. Extra keys are silently dropped.

        Raises:
            FirestoreTelegramTranscriptStoreError: On any Firestore SDK error.
        """
        # Apply allow-list
        safe: dict[str, Any] = {k: v for k, v in row.items() if k in _TRANSCRIPT_ROW_FIELDS}
        # Redact free-form text
        if "text" in safe:
            safe["text"] = _redact_row_text(safe["text"])
        # Preserve integer IDs
        for id_field in ("chat_id", "author_id", "message_id"):
            if id_field in safe and safe[id_field] is not None:
                try:
                    safe[id_field] = int(safe[id_field])
                except (TypeError, ValueError):
                    pass

        doc_id = str(uuid.uuid4())
        db = self._db()
        try:
            db.collection(self._coll_name).document(doc_id).set(safe)
        except FirestoreTelegramTranscriptStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FirestoreTelegramTranscriptStoreError(
                f"Firestore append_row failed: {exc}"
            ) from exc

    def iter_rows(self) -> Iterator[dict[str, Any]]:
        """Yield all stored transcript rows from Firestore.

        An empty collection yields nothing (zero rows) rather than raising.
        Only Firestore SDK errors raise
        :class:`FirestoreTelegramTranscriptStoreError`.

        Raises:
            FirestoreTelegramTranscriptStoreError: On any Firestore SDK error.
        """
        db = self._db()
        try:
            docs = list(db.collection(self._coll_name).stream())
        except FirestoreTelegramTranscriptStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FirestoreTelegramTranscriptStoreError(
                f"Firestore iter_rows failed: {exc}"
            ) from exc

        for snap in docs:
            data = snap.to_dict() or {}
            # Yield only allow-listed fields (defensive; should already be filtered at write)
            yield {k: v for k, v in data.items() if k in _TRANSCRIPT_ROW_FIELDS}


__all__ = [
    "FirestoreTelegramTranscriptStore",
    "FirestoreTelegramTranscriptStoreError",
]
