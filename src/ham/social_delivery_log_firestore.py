"""Firestore-backed social delivery log store (skeleton).

Full implementation: M1 F3 (delivery-and-learning-firestore-stores).

Per-store env-var overrides:
- ``HAM_SOCIAL_DELIVERY_LOG_FIRESTORE_PROJECT_ID``  -> ``HAM_FIRESTORE_PROJECT_ID``
- ``HAM_SOCIAL_DELIVERY_LOG_FIRESTORE_DATABASE``    -> ``HAM_FIRESTORE_DATABASE``
- ``HAM_SOCIAL_DELIVERY_LOG_FIRESTORE_COLLECTION``  (default ``ham_social_delivery_log``)
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

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


class FirestoreSocialDeliveryLogStoreError(RuntimeError):
    """Wrapper for unexpected errors from the Firestore SDK."""


class FirestoreSocialDeliveryLogStore:
    """Firestore-backed social delivery log store (skeleton; full impl in F3)."""

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

    def _db(self) -> Any:
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

    def append_record(
        self,
        record: dict[str, Any],
        path: Path | None = None,
    ) -> Path:
        raise NotImplementedError(
            "FirestoreSocialDeliveryLogStore.append_record — implemented in F3"
        )

    def successful_delivery_exists(
        self,
        *,
        idempotency_key: str,
        provider_id: str = "telegram",
        path: Path | None = None,
    ) -> bool:
        raise NotImplementedError(
            "FirestoreSocialDeliveryLogStore.successful_delivery_exists — implemented in F3"
        )

    def iter_records_in_window(
        self,
        *,
        start: datetime,
        end: datetime,
        path: Path | None = None,
    ) -> Iterator[dict[str, Any]]:
        raise NotImplementedError(
            "FirestoreSocialDeliveryLogStore.iter_records_in_window — implemented in F3"
        )


__all__ = [
    "FirestoreSocialDeliveryLogStore",
    "FirestoreSocialDeliveryLogStoreError",
]
