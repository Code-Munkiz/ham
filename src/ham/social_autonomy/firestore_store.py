"""Firestore-backed social autonomy profile store (skeleton).

Full implementation: M1 F2 (autonomy-profile-firestore-store).

This module provides the class skeleton so the factory in
:mod:`src.ham.social_autonomy.store` can return a typed instance when
``HAM_SOCIAL_AUTONOMY_STORE_BACKEND=firestore``.  Every method raises
``NotImplementedError`` until F2 fills them in.

Collection layout (planned for F2)::

    ham_social_autonomy_profiles/{profile_id}
    ham_social_autonomy_profiles/{profile_id}/_audit/{audit_id}
    ham_social_autonomy_profiles/{profile_id}/_backups/{backup_id}

Per-store env-var overrides (all fall back to shared workspace vars):
- ``HAM_SOCIAL_AUTONOMY_FIRESTORE_PROJECT_ID``  -> ``HAM_FIRESTORE_PROJECT_ID``
- ``HAM_SOCIAL_AUTONOMY_FIRESTORE_DATABASE``    -> ``HAM_FIRESTORE_DATABASE``
- ``HAM_SOCIAL_AUTONOMY_FIRESTORE_COLLECTION``  (default ``ham_social_autonomy_profiles``)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import ApplyResult, RollbackResult

_FS_PROJECT_ENV = "HAM_SOCIAL_AUTONOMY_FIRESTORE_PROJECT_ID"
_FS_DATABASE_ENV = "HAM_SOCIAL_AUTONOMY_FIRESTORE_DATABASE"
_FS_COLLECTION_ENV = "HAM_SOCIAL_AUTONOMY_FIRESTORE_COLLECTION"
_FALLBACK_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FALLBACK_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"
_DEFAULT_COLLECTION = "ham_social_autonomy_profiles"


def _resolve_env(primary: str, fallback: str | None = None) -> str | None:
    val = (os.environ.get(primary) or "").strip()
    if val:
        return val
    if fallback is not None:
        val = (os.environ.get(fallback) or "").strip()
        if val:
            return val
    return None


class FirestoreSocialAutonomyStoreError(RuntimeError):
    """Wrapper for unexpected errors from the Firestore SDK."""


class FirestoreSocialAutonomyStore:
    """Firestore-backed social autonomy profile store.

    The constructor accepts an injected ``client`` for tests; in production
    the real ``google.cloud.firestore.Client`` is constructed lazily on first
    method call so importing this module never contacts Firestore at import time.

    Full method implementations land in M1 F2.
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

    def _db(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.cloud import firestore  # noqa: PLC0415
        except ImportError as exc:
            msg = (
                "google-cloud-firestore is required when "
                "HAM_SOCIAL_AUTONOMY_STORE_BACKEND=firestore."
            )
            raise FirestoreSocialAutonomyStoreError(msg) from exc
        kwargs: dict[str, Any] = {}
        if self._project:
            kwargs["project"] = self._project
        if self._database:
            kwargs["database"] = self._database
        self._client = firestore.Client(**kwargs) if kwargs else firestore.Client()
        return self._client

    def read(self, root: Path | None = None) -> GoHamSocialProfile:
        raise NotImplementedError("FirestoreSocialAutonomyStore.read — implemented in F2")

    def preview(
        self,
        root: Path | None,
        candidate: GoHamSocialProfile | dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError("FirestoreSocialAutonomyStore.preview — implemented in F2")

    def apply(
        self,
        root: Path | None,
        candidate: GoHamSocialProfile | dict[str, Any],
        *,
        token: str | None,
        actor: str = "system",
    ) -> ApplyResult:
        raise NotImplementedError("FirestoreSocialAutonomyStore.apply — implemented in F2")

    def save(
        self,
        root: Path | None,
        profile: GoHamSocialProfile,
        *,
        actor: str = "system",
    ) -> ApplyResult:
        raise NotImplementedError("FirestoreSocialAutonomyStore.save — implemented in F2")

    def rollback(
        self,
        root: Path | None,
        backup_id: str,
        *,
        token: str | None,
        actor: str = "system",
    ) -> RollbackResult:
        raise NotImplementedError("FirestoreSocialAutonomyStore.rollback — implemented in F2")

    def writes_enabled(self) -> bool:
        raise NotImplementedError("FirestoreSocialAutonomyStore.writes_enabled — implemented in F2")

    def path(self, root: Path | None = None) -> Path:
        raise NotImplementedError("FirestoreSocialAutonomyStore.path — implemented in F2")


__all__ = [
    "FirestoreSocialAutonomyStore",
    "FirestoreSocialAutonomyStoreError",
]
