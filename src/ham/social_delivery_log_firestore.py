"""Firestore-backed social delivery log store (M1 F3 implementation).

Implements the ``FirestoreSocialDeliveryLogStore`` backend for the
``SocialDeliveryLogStoreProtocol``. Selected by the factory in
:mod:`src.ham.social_delivery_log` when
``HAM_SOCIAL_DELIVERY_LOG_BACKEND=firestore``.

Collection layout::

    ham_social_delivery_log/{record_uuid}

Each document stores a delivery record with the allow-listed, redacted fields
produced by :func:`~src.ham.social_delivery_log.build_delivery_record`.

Missing-source semantics (M14 M1c parity):
    An empty collection (no documents) is treated as zero records — exactly
    as a missing JSONL file on the file backend.  Only Firestore SDK errors
    (network failures, IAM errors, etc.) raise
    :class:`FirestoreSocialDeliveryLogStoreError`.

Fail-closed:
    Any exception from the Firestore SDK is wrapped in
    :class:`FirestoreSocialDeliveryLogStoreError` and re-raised.  The store
    **never** silently falls back to the file backend.

Per-store env-var overrides::

    HAM_SOCIAL_DELIVERY_LOG_FIRESTORE_PROJECT_ID  -> HAM_FIRESTORE_PROJECT_ID
    HAM_SOCIAL_DELIVERY_LOG_FIRESTORE_DATABASE    -> HAM_FIRESTORE_DATABASE
    HAM_SOCIAL_DELIVERY_LOG_FIRESTORE_COLLECTION  (default ham_social_delivery_log)
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.ham.social_delivery_log import build_delivery_record, default_delivery_log_path

_FS_PROJECT_ENV = "HAM_SOCIAL_DELIVERY_LOG_FIRESTORE_PROJECT_ID"
_FS_DATABASE_ENV = "HAM_SOCIAL_DELIVERY_LOG_FIRESTORE_DATABASE"
_FS_COLLECTION_ENV = "HAM_SOCIAL_DELIVERY_LOG_FIRESTORE_COLLECTION"
_FALLBACK_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FALLBACK_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"
_DEFAULT_COLLECTION = "ham_social_delivery_log"


def _resolve_env(primary: str, fallback: str | None = None) -> str | None:
    val = (os.environ.get(primary) or "").strip()
    if val:
        return val
    if fallback is not None:
        val = (os.environ.get(fallback) or "").strip()
        if val:
            return val
    return None


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class FirestoreSocialDeliveryLogStoreError(RuntimeError):
    """Wrapper for unexpected errors from the Firestore SDK.

    Raised by every method when the Firestore client raises, ensuring callers
    never silently swallow SDK errors and the API layer can convert them to
    structured ``503 firestore_unavailable`` responses.
    """


class FirestoreSocialDeliveryLogStore:
    """Firestore-backed social delivery log store.

    Satisfies :class:`~src.ham.social_delivery_log.SocialDeliveryLogStoreProtocol`.

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
                "google-cloud-firestore is required when HAM_SOCIAL_DELIVERY_LOG_BACKEND=firestore."
            )
            raise FirestoreSocialDeliveryLogStoreError(msg) from exc
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

    def append_record(
        self,
        record: dict[str, Any],
        path: Path | None = None,  # ignored for Firestore backend
    ) -> Path:
        """Append a redacted delivery record to Firestore.

        Applies :func:`~src.ham.social_delivery_log.build_delivery_record` to
        enforce the allow-list and redaction before writing.

        Args:
            record: Raw delivery record fields; allow-listed and redacted.
            path:   Ignored for the Firestore backend (kept for Protocol compat).

        Returns:
            The file-backend default path (dummy; data is in Firestore).

        Raises:
            FirestoreSocialDeliveryLogStoreError: On any Firestore SDK error.
        """
        safe_record = build_delivery_record(**record)
        doc_id = str(uuid.uuid4())
        db = self._db()
        try:
            db.collection(self._coll_name).document(doc_id).set(safe_record)
        except FirestoreSocialDeliveryLogStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FirestoreSocialDeliveryLogStoreError(
                f"Firestore append_record failed: {exc}"
            ) from exc
        # Return the default file-backend path for Protocol compatibility.
        # The actual data lives in Firestore, not at this path.
        return default_delivery_log_path()

    def successful_delivery_exists(
        self,
        *,
        idempotency_key: str,
        provider_id: str = "telegram",
        path: Path | None = None,  # ignored for Firestore backend
    ) -> bool:
        """Return True if a sent delivery with the given idempotency_key exists.

        Scans the Firestore collection for a document matching ``provider_id``,
        ``idempotency_key``, and ``status == "sent"``.

        An empty collection returns ``False`` (not a Firestore error).

        Raises:
            FirestoreSocialDeliveryLogStoreError: On any Firestore SDK error.
        """
        db = self._db()
        try:
            docs = list(db.collection(self._coll_name).stream())
        except FirestoreSocialDeliveryLogStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FirestoreSocialDeliveryLogStoreError(
                f"Firestore successful_delivery_exists failed: {exc}"
            ) from exc
        for snap in docs:
            data = snap.to_dict() or {}
            if (
                data.get("provider_id") == provider_id
                and data.get("idempotency_key") == idempotency_key
                and data.get("status") == "sent"
            ):
                return True
        return False

    def iter_records_in_window(
        self,
        *,
        start: datetime,
        end: datetime,
        path: Path | None = None,  # ignored for Firestore backend
    ) -> Iterator[dict[str, Any]]:
        """Yield delivery log records whose ``executed_at`` falls within [start, end].

        Preserves the M14 M1c missing-source-zero semantic: an empty collection
        yields nothing (zero records) rather than raising
        :class:`~src.ham.social_autonomy.usage.UsageSourceUnavailable`.

        Only Firestore SDK errors (network, IAM, etc.) raise
        :class:`FirestoreSocialDeliveryLogStoreError`.

        Args:
            start: Window lower bound (inclusive, UTC-aware).
            end:   Window upper bound (inclusive, UTC-aware).
            path:  Ignored for the Firestore backend.

        Raises:
            FirestoreSocialDeliveryLogStoreError: On any Firestore SDK error.
        """
        db = self._db()
        try:
            docs = list(db.collection(self._coll_name).stream())
        except FirestoreSocialDeliveryLogStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FirestoreSocialDeliveryLogStoreError(
                f"Firestore iter_records_in_window failed: {exc}"
            ) from exc

        _start = _to_utc(start)
        _end = _to_utc(end)

        result: list[dict[str, Any]] = []
        for snap in docs:
            record = snap.to_dict() or {}
            raw_ts = record.get("executed_at", "")
            if not isinstance(raw_ts, str) or not raw_ts.strip():
                continue
            try:
                executed_at = _to_utc(datetime.fromisoformat(raw_ts.strip().replace("Z", "+00:00")))
                if _start <= executed_at <= _end:
                    result.append(record)
            except ValueError:
                continue
        return iter(result)


__all__ = [
    "FirestoreSocialDeliveryLogStore",
    "FirestoreSocialDeliveryLogStoreError",
]
