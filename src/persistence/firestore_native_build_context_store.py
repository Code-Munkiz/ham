"""Firestore-backed NativeBuildContextStore.

Mirrors the file-backed :class:`NativeBuildContextStore` Protocol exactly so
callers do not need to know which backend is active. Selected when
``HAM_NATIVE_BUILD_CONTEXT_STORE_BACKEND=firestore`` (default remains file-backed
for local/dev/tests).

This makes the HAM Native Builder v2 execution context durable across Cloud Run
instances: the enqueuing request persists the context here, and the worker
request — which may land on a different instance — loads it by ``import_job_id``.

Layout::

    {collection}/{import_job_id}

Env vars (per-store first, shared HAM_FIRESTORE_* fallback):

- ``HAM_NATIVE_BUILD_CONTEXT_FIRESTORE_PROJECT_ID`` -> ``HAM_FIRESTORE_PROJECT_ID``
- ``HAM_NATIVE_BUILD_CONTEXT_FIRESTORE_DATABASE``   -> ``HAM_FIRESTORE_DATABASE``
- ``HAM_NATIVE_BUILD_CONTEXT_FIRESTORE_COLLECTION`` (default ``native_build_contexts``)

The context is server-side only and never surfaced through user-facing APIs; it
carries no build-kit internals, provider ids, registry metadata, or secrets.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import ValidationError

from src.persistence.native_build_context_store import NativeBuildContext

_LOG = logging.getLogger(__name__)

_NBC_FS_PROJECT_ENV = "HAM_NATIVE_BUILD_CONTEXT_FIRESTORE_PROJECT_ID"
_NBC_FS_DATABASE_ENV = "HAM_NATIVE_BUILD_CONTEXT_FIRESTORE_DATABASE"
_NBC_FS_COLLECTION_ENV = "HAM_NATIVE_BUILD_CONTEXT_FIRESTORE_COLLECTION"

_FALLBACK_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FALLBACK_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"

_DEFAULT_COLLECTION = "native_build_contexts"


class FirestoreNativeBuildContextStoreError(RuntimeError):
    """Wrapper for unexpected errors from the Firestore SDK."""


def _resolve_env(primary: str, fallback: str | None = None) -> str | None:
    val = (os.environ.get(primary) or "").strip()
    if val:
        return val
    if fallback is not None:
        val = (os.environ.get(fallback) or "").strip()
        if val:
            return val
    return None


class FirestoreNativeBuildContextStore:
    """Firestore implementation of :class:`NativeBuildContextStoreProtocol`.

    Each :class:`NativeBuildContext` is one document whose id is the
    ``import_job_id`` (already a stable ``ijob_<uuid>``).
    """

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str | None = None,
        collection: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._project = project or _resolve_env(_NBC_FS_PROJECT_ENV, _FALLBACK_PROJECT_ENV)
        self._database = database or _resolve_env(_NBC_FS_DATABASE_ENV, _FALLBACK_DATABASE_ENV)
        coll = collection or _resolve_env(_NBC_FS_COLLECTION_ENV) or _DEFAULT_COLLECTION
        self._coll_name = coll.strip() or _DEFAULT_COLLECTION
        self._client = client

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
                "HAM_NATIVE_BUILD_CONTEXT_STORE_BACKEND=firestore."
            )
            raise FirestoreNativeBuildContextStoreError(msg) from exc
        kwargs: dict[str, Any] = {}
        if self._project:
            kwargs["project"] = self._project
        if self._database:
            kwargs["database"] = self._database
        self._client = firestore.Client(**kwargs) if kwargs else firestore.Client()
        return self._client

    def _coll(self) -> Any:
        return self._db().collection(self._coll_name)

    @staticmethod
    def _wrap(op: str, exc: Exception) -> FirestoreNativeBuildContextStoreError:
        return FirestoreNativeBuildContextStoreError(
            f"firestore native build context store: {op} failed: {exc}",
        )

    # ------------------------------------------------------------------
    # Public API (mirrors file-backed NativeBuildContextStore)
    # ------------------------------------------------------------------

    def put_native_build_context(self, record: NativeBuildContext) -> NativeBuildContext:
        payload = record.model_dump(mode="json")
        try:
            # `set` (no merge) fully replaces the document so we never accumulate
            # stale fields — matches the file backend's remove-then-append.
            self._coll().document(record.import_job_id).set(payload)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("put_native_build_context", exc) from exc
        return record

    def get_native_build_context(self, *, import_job_id: str) -> NativeBuildContext | None:
        jid = (import_job_id or "").strip()
        if not jid:
            return None
        try:
            snap = self._coll().document(jid).get()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("get_native_build_context", exc) from exc
        if not getattr(snap, "exists", False):
            return None
        data = snap.to_dict() or {}
        try:
            return NativeBuildContext.model_validate(data)
        except ValidationError as exc:
            _LOG.warning(
                "skipping malformed native build context %s (%s): %s",
                jid,
                type(exc).__name__,
                exc,
            )
            return None
