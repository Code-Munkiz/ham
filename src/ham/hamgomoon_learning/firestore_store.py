"""Firestore-backed HAMgomoon learning records store (skeleton).

Full implementation: M1 F3 (delivery-and-learning-firestore-stores).

Per-store env-var overrides:
- ``HAM_HAMGOMOON_LEARNING_FIRESTORE_PROJECT_ID``  -> ``HAM_FIRESTORE_PROJECT_ID``
- ``HAM_HAMGOMOON_LEARNING_FIRESTORE_DATABASE``    -> ``HAM_FIRESTORE_DATABASE``
- ``HAM_HAMGOMOON_LEARNING_FIRESTORE_COLLECTION``  (default ``ham_hamgomoon_learning``)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.ham.hamgomoon_learning.models import LearningRecord

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


class FirestoreHamgomoonLearningStoreError(RuntimeError):
    """Wrapper for unexpected errors from the Firestore SDK."""


class FirestoreHamgomoonLearningStore:
    """Firestore-backed HAMgomoon learning records store (skeleton; full impl in F3)."""

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

    def append_learning_record(
        self,
        record: LearningRecord,
        *,
        path: Path | None = None,
    ) -> LearningRecord:
        raise NotImplementedError(
            "FirestoreHamgomoonLearningStore.append_learning_record — implemented in F3"
        )

    def list_recent_learning_records(
        self,
        *,
        workspace_id: str | None = None,
        project_id: str | None = None,
        channel: str | None = None,
        limit: int = 50,
        path: Path | None = None,
    ) -> list[LearningRecord]:
        raise NotImplementedError(
            "FirestoreHamgomoonLearningStore.list_recent_learning_records — implemented in F3"
        )

    def summarize_learning_hints(
        self,
        *,
        workspace_id: str | None = None,
        project_id: str | None = None,
        channel: str | None = None,
        limit: int = 50,
        path: Path | None = None,
    ) -> dict[str, list[str]]:
        raise NotImplementedError(
            "FirestoreHamgomoonLearningStore.summarize_learning_hints — implemented in F3"
        )


__all__ = [
    "FirestoreHamgomoonLearningStore",
    "FirestoreHamgomoonLearningStoreError",
]
