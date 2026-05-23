"""Firestore-backed Telegram getUpdates offset store (M1 F4 implementation).

Implements the ``FirestoreTelegramOffsetStore`` backend for the
``TelegramOffsetStoreProtocol``. Selected by the factory in
:mod:`src.ham.social_telegram_offset_store` when
``HAM_TELEGRAM_OFFSET_BACKEND=firestore``.

Collection layout::

    ham_social_telegram_poller_state/{bot_digest}

Each document has a single field ``update_offset: int``.  The document ID is
the ``bot_digest`` (``sha256(token)[:16]``) so each bot token has exactly one
document, and writes are idempotent at the document level.

Atomicity:
    ``write_offset`` uses Firestore ``set(merge=True)`` to merge only the
    ``update_offset`` field into the existing document.  This preserves any
    ``last_run_at`` / ``last_error`` metadata previously written by
    ``write_poller_metadata``, and is atomic at the document level — either the
    full merged payload is written or nothing is.  No explicit transaction is
    needed for a single-field single-document write.

Idempotency:
    Writing the same offset twice simply overwrites the document with the same
    value.  Because the document ID is the ``bot_digest``, collection size
    remains ``1`` after duplicate writes.

Fail-closed:
    Any exception from the Firestore SDK is wrapped in
    :class:`FirestoreTelegramOffsetStoreError` and re-raised.  The store
    **never** silently falls back to the file backend.

Per-store env-var overrides::

    HAM_TELEGRAM_OFFSET_FIRESTORE_PROJECT_ID  -> HAM_FIRESTORE_PROJECT_ID
    HAM_TELEGRAM_OFFSET_FIRESTORE_DATABASE    -> HAM_FIRESTORE_DATABASE
    HAM_TELEGRAM_OFFSET_FIRESTORE_COLLECTION  (default ham_social_telegram_poller_state)
"""

from __future__ import annotations

import os
from typing import Any

from src.ham.social_telegram_offset_store import PollerMetadata

_FS_PROJECT_ENV = "HAM_TELEGRAM_OFFSET_FIRESTORE_PROJECT_ID"
_FS_DATABASE_ENV = "HAM_TELEGRAM_OFFSET_FIRESTORE_DATABASE"
_FS_COLLECTION_ENV = "HAM_TELEGRAM_OFFSET_FIRESTORE_COLLECTION"
_FALLBACK_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FALLBACK_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"
_DEFAULT_COLLECTION = "ham_social_telegram_poller_state"


def _resolve_env(primary: str, fallback: str | None = None) -> str | None:
    val = (os.environ.get(primary) or "").strip()
    if val:
        return val
    if fallback is not None:
        val = (os.environ.get(fallback) or "").strip()
        if val:
            return val
    return None


class FirestoreTelegramOffsetStoreError(RuntimeError):
    """Wrapper for unexpected errors from the Firestore SDK.

    Raised by every method when the Firestore client raises, ensuring callers
    never silently swallow SDK errors and the API layer can convert them to
    structured ``503 firestore_unavailable`` responses.
    """


class FirestoreTelegramOffsetStore:
    """Firestore-backed Telegram getUpdates offset store.

    Satisfies :class:`~src.ham.social_telegram_offset_store.TelegramOffsetStoreProtocol`.

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
            msg = "google-cloud-firestore is required when HAM_TELEGRAM_OFFSET_BACKEND=firestore."
            raise FirestoreTelegramOffsetStoreError(msg) from exc
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

    def read_offset(self, bot_digest: str) -> int | None:
        """Return the stored offset for ``bot_digest``, or ``None`` if absent.

        An absent document returns ``None`` (not an error).
        Only Firestore SDK errors raise :class:`FirestoreTelegramOffsetStoreError`.

        Args:
            bot_digest: Short hex digest of the bot token (``sha256(token)[:16]``).

        Returns:
            The stored ``update_offset`` integer, or ``None`` when not set.

        Raises:
            FirestoreTelegramOffsetStoreError: On any Firestore SDK error.
        """
        db = self._db()
        key = str(bot_digest).strip()
        try:
            snap = db.collection(self._coll_name).document(key).get()
        except FirestoreTelegramOffsetStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FirestoreTelegramOffsetStoreError(f"Firestore read_offset failed: {exc}") from exc

        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        val = data.get("update_offset")
        if val is None:
            return None
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    def write_offset(self, bot_digest: str, update_offset: int) -> None:
        """Atomically persist ``update_offset`` for ``bot_digest``.

        Uses Firestore ``set(merge=True)`` to merge only the ``update_offset``
        field into the existing document, preserving any ``last_run_at`` /
        ``last_error`` metadata previously written by :meth:`write_poller_metadata`.
        Writing the same offset twice is a no-op in terms of observable state —
        the document simply retains the same value.

        Args:
            bot_digest:    Short hex digest of the bot token.
            update_offset: The new offset value to persist.

        Raises:
            FirestoreTelegramOffsetStoreError: On any Firestore SDK error.
        """
        db = self._db()
        key = str(bot_digest).strip()
        payload: dict[str, Any] = {"update_offset": int(update_offset)}
        try:
            db.collection(self._coll_name).document(key).set(payload, merge=True)
        except FirestoreTelegramOffsetStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FirestoreTelegramOffsetStoreError(
                f"Firestore write_offset failed: {exc}"
            ) from exc

    def read_poller_metadata(self, bot_digest: str) -> PollerMetadata:
        """Return optional metadata stored alongside the offset.

        Reads ``last_run_at`` and ``last_error`` from the Firestore document.
        Both fields default to ``None`` when absent from the document.

        Args:
            bot_digest: Short hex digest of the bot token (``sha256(token)[:16]``).

        Returns:
            :class:`~src.ham.social_telegram_offset_store.PollerMetadata` with
            ``last_run_at`` and ``last_error`` (each ``None`` when not stored).

        Raises:
            FirestoreTelegramOffsetStoreError: On any Firestore SDK error.
        """
        db = self._db()
        key = str(bot_digest).strip()
        try:
            snap = db.collection(self._coll_name).document(key).get()
        except FirestoreTelegramOffsetStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FirestoreTelegramOffsetStoreError(
                f"Firestore read_poller_metadata failed: {exc}"
            ) from exc

        if not snap.exists:
            return PollerMetadata(last_run_at=None, last_error=None)
        data = snap.to_dict() or {}
        raw_run_at = data.get("last_run_at")
        raw_error = data.get("last_error")
        return PollerMetadata(
            last_run_at=str(raw_run_at) if raw_run_at is not None else None,
            last_error=str(raw_error) if raw_error is not None else None,
        )

    def write_poller_metadata(
        self,
        bot_digest: str,
        *,
        last_run_at: str | None = None,
        last_error: str | None = None,
    ) -> None:
        """Merge poller metadata into the Firestore document without losing the stored offset.

        Uses ``set(merge=True)`` to merge only the provided fields into the
        existing document, so ``update_offset`` (and any other existing fields)
        are preserved.  Only fields with non-``None`` values are merged.

        Passing ``last_run_at=None`` (the default) leaves the existing
        ``last_run_at`` field in Firestore unchanged.  Same for ``last_error``.

        Args:
            bot_digest:  Short hex digest of the bot token (``sha256(token)[:16]``).
            last_run_at: ISO-8601 timestamp of the most recent successful poll run.
                         ``None`` means "do not update this field".
            last_error:  Bounded, redacted error message from the most recent
                         failed poll run.  ``None`` means "do not update this field".

        Raises:
            FirestoreTelegramOffsetStoreError: On any Firestore SDK error.
        """
        payload: dict[str, Any] = {}
        if last_run_at is not None:
            payload["last_run_at"] = last_run_at
        if last_error is not None:
            payload["last_error"] = last_error
        if not payload:
            # Nothing to update — avoid an unnecessary Firestore round-trip.
            return
        db = self._db()
        key = str(bot_digest).strip()
        try:
            db.collection(self._coll_name).document(key).set(payload, merge=True)
        except FirestoreTelegramOffsetStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FirestoreTelegramOffsetStoreError(
                f"Firestore write_poller_metadata failed: {exc}"
            ) from exc


__all__ = [
    "FirestoreTelegramOffsetStore",
    "FirestoreTelegramOffsetStoreError",
]
