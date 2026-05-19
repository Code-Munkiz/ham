"""Firestore-backed BuilderRuntimeJobStore — Phase 2.5.

Mirrors the file-backed :class:`BuilderRuntimeJobStore` Protocol exactly so
callers do not need to know which backend is active. Selected when
``HAM_BUILDER_RUNTIME_JOB_STORE_BACKEND=firestore`` (default remains
file-backed).

Layout::

    {collection}/{job_id}

The legacy ``succeeded`` / ``success`` status aliases are normalised to
``completed`` on read (see ADR-0005). The same field-serializer that the
file backend uses (``Phase 0 Literal → wire format``) applies on write,
so the on-disk shape is identical across backends.

Env vars (per-store first, shared HAM_FIRESTORE_* fallback):

- ``HAM_BUILDER_RUNTIME_JOB_FIRESTORE_PROJECT_ID``  -> ``HAM_FIRESTORE_PROJECT_ID``
- ``HAM_BUILDER_RUNTIME_JOB_FIRESTORE_DATABASE``    -> ``HAM_FIRESTORE_DATABASE``
- ``HAM_BUILDER_RUNTIME_JOB_FIRESTORE_COLLECTION``  (default ``builder_runtime_jobs``)

See ADR-0014 / docs/PHASE_2_5_DESIGN.md.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from src.persistence.builder_runtime_job_store import CloudRuntimeJob

_LOG = logging.getLogger(__name__)

_BRJ_FS_PROJECT_ENV = "HAM_BUILDER_RUNTIME_JOB_FIRESTORE_PROJECT_ID"
_BRJ_FS_DATABASE_ENV = "HAM_BUILDER_RUNTIME_JOB_FIRESTORE_DATABASE"
_BRJ_FS_COLLECTION_ENV = "HAM_BUILDER_RUNTIME_JOB_FIRESTORE_COLLECTION"

_FALLBACK_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FALLBACK_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"

_DEFAULT_COLLECTION = "builder_runtime_jobs"

# Mirror the file-backed store's legacy-status handling so storage layout is
# uniform across backends (ADR-0005).
_VALID_STATUSES = frozenset(
    {"queued", "running", "cancelling", "cancelled", "completed", "failed", "unsupported", "succeeded"}
)
_LEGACY_STATUS_ALIASES = {"succeeded": "completed", "success": "completed"}


class FirestoreBuilderRuntimeJobStoreError(RuntimeError):
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


def _normalize_legacy_record(item: dict[str, Any]) -> dict[str, Any]:
    """Tolerate old records with legacy status aliases or unknown statuses."""
    if not isinstance(item, dict):
        return item
    status = item.get("status")
    if not isinstance(status, str):
        return item
    alias = _LEGACY_STATUS_ALIASES.get(status)
    if alias is not None:
        item = dict(item)
        item["status"] = alias
    elif status not in _VALID_STATUSES:
        item = dict(item)
        item["status"] = "failed"
    return item


class FirestoreBuilderRuntimeJobStore:
    """Firestore implementation of :class:`BuilderRuntimeJobStoreProtocol`.

    Each :class:`CloudRuntimeJob` is one document. The document ID is the
    job ``id`` (already a stable ``crjb_<uuid>``).
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
            _BRJ_FS_PROJECT_ENV, _FALLBACK_PROJECT_ENV,
        )
        self._database = database or _resolve_env(
            _BRJ_FS_DATABASE_ENV, _FALLBACK_DATABASE_ENV,
        )
        coll = (
            collection
            or _resolve_env(_BRJ_FS_COLLECTION_ENV)
            or _DEFAULT_COLLECTION
        )
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
                "HAM_BUILDER_RUNTIME_JOB_STORE_BACKEND=firestore."
            )
            raise FirestoreBuilderRuntimeJobStoreError(msg) from exc
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
    def _wrap(op: str, exc: Exception) -> FirestoreBuilderRuntimeJobStoreError:
        return FirestoreBuilderRuntimeJobStoreError(
            f"firestore builder runtime job store: {op} failed: {exc}",
        )

    @staticmethod
    def _hydrate_datetimes(raw: dict[str, Any]) -> dict[str, Any]:
        out = dict(raw)
        for k, v in list(out.items()):
            if isinstance(v, datetime) and v.tzinfo is None:
                out[k] = v.replace(tzinfo=UTC)
        return out

    @classmethod
    def _validate(cls, snap: Any) -> CloudRuntimeJob | None:
        data = snap.to_dict() or {}
        normalised = _normalize_legacy_record(cls._hydrate_datetimes(data))
        try:
            return CloudRuntimeJob.model_validate(normalised)
        except ValidationError as exc:
            doc_id = getattr(snap, "id", "<unknown>")
            _LOG.warning(
                "skipping malformed cloud runtime job %s (%s): %s",
                doc_id,
                type(exc).__name__,
                exc,
            )
            return None

    # ------------------------------------------------------------------
    # Public API (mirrors file-backed BuilderRuntimeJobStore)
    # ------------------------------------------------------------------

    def list_cloud_runtime_jobs(
        self,
        *,
        workspace_id: str,
        project_id: str,
    ) -> list[CloudRuntimeJob]:
        ws = (workspace_id or "").strip()
        proj = (project_id or "").strip()
        if not ws or not proj:
            return []
        try:
            stream = self._coll().stream()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("list_cloud_runtime_jobs", exc) from exc
        out: list[CloudRuntimeJob] = []
        for snap in stream:
            data = (snap.to_dict() or {}) if hasattr(snap, "to_dict") else {}
            if str(data.get("workspace_id") or "") != ws:
                continue
            if str(data.get("project_id") or "") != proj:
                continue
            row = self._validate(snap)
            if row is not None:
                out.append(row)
        return sorted(
            out,
            key=lambda row: (row.updated_at, row.created_at, row.id),
            reverse=True,
        )

    def get_cloud_runtime_job(
        self,
        *,
        workspace_id: str,
        project_id: str,
        job_id: str,
    ) -> CloudRuntimeJob | None:
        jid = (job_id or "").strip()
        if not jid:
            return None
        try:
            snap = self._coll().document(jid).get()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("get_cloud_runtime_job", exc) from exc
        if not getattr(snap, "exists", False):
            return None
        row = self._validate(snap)
        if row is None:
            return None
        # Enforce workspace + project scope at the read boundary so callers
        # that supply mismatched context don't accidentally see another
        # workspace's job.
        if row.workspace_id != workspace_id or row.project_id != project_id:
            return None
        return row

    def get_cloud_runtime_job_by_id(self, *, job_id: str) -> CloudRuntimeJob | None:
        """Cross-workspace lookup. Used by Worker startup and the SSE endpoint.

        Not part of :class:`BuilderRuntimeJobStoreProtocol` — callers use
        ``hasattr`` to feature-detect (matches the file backend's escape
        hatch).
        """
        jid = (job_id or "").strip()
        if not jid:
            return None
        try:
            snap = self._coll().document(jid).get()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("get_cloud_runtime_job_by_id", exc) from exc
        if not getattr(snap, "exists", False):
            return None
        return self._validate(snap)

    def upsert_cloud_runtime_job(self, record: CloudRuntimeJob) -> CloudRuntimeJob:
        # Mirror the file-backed coercion + last_error backfill so on-disk
        # shape is uniform across backends.
        coerced_status_raw = record.status
        if coerced_status_raw in _LEGACY_STATUS_ALIASES:
            coerced_status_raw = _LEGACY_STATUS_ALIASES[coerced_status_raw]  # type: ignore[index]
        if coerced_status_raw != record.status:
            record = record.model_copy(update={"status": coerced_status_raw})
        if record.last_error is not None:
            record = record.model_copy(
                update={
                    "error_code": record.last_error.error_code,
                    "error_message": record.last_error.error_message,
                }
            )
        payload = record.model_dump(mode="json")
        try:
            # `set` (no merge) so updates fully replace the document and we
            # don't accumulate stale fields. This matches the file backend's
            # remove-then-append semantics.
            self._coll().document(record.id).set(payload)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("upsert_cloud_runtime_job", exc) from exc
        return record
