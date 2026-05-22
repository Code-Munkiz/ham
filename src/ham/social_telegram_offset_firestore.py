"""Firestore-backed Telegram getUpdates offset store (skeleton).

Full implementation: M1 F4 (telegram-transcript-and-offset-firestore-stores).

Per-store env-var overrides:
- ``HAM_TELEGRAM_OFFSET_FIRESTORE_PROJECT_ID``  -> ``HAM_FIRESTORE_PROJECT_ID``
- ``HAM_TELEGRAM_OFFSET_FIRESTORE_DATABASE``    -> ``HAM_FIRESTORE_DATABASE``
- ``HAM_TELEGRAM_OFFSET_FIRESTORE_COLLECTION``  (default ``ham_social_telegram_poller_state``)
"""

from __future__ import annotations

import os
from typing import Any

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
    """Wrapper for unexpected errors from the Firestore SDK."""


class FirestoreTelegramOffsetStore:
    """Firestore-backed Telegram offset store (skeleton; full impl in F4)."""

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
            msg = "google-cloud-firestore is required when HAM_TELEGRAM_OFFSET_BACKEND=firestore."
            raise FirestoreTelegramOffsetStoreError(msg) from exc
        kwargs: dict[str, Any] = {}
        if self._project:
            kwargs["project"] = self._project
        if self._database:
            kwargs["database"] = self._database
        self._client = firestore.Client(**kwargs) if kwargs else firestore.Client()
        return self._client

    def read_offset(self, bot_digest: str) -> int | None:
        raise NotImplementedError("FirestoreTelegramOffsetStore.read_offset — implemented in F4")

    def write_offset(self, bot_digest: str, update_offset: int) -> None:
        raise NotImplementedError("FirestoreTelegramOffsetStore.write_offset — implemented in F4")


__all__ = [
    "FirestoreTelegramOffsetStore",
    "FirestoreTelegramOffsetStoreError",
]
