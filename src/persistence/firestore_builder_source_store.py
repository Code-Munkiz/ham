"""Firestore-backed BuilderSourceStore.

Mirrors the file-backed :class:`BuilderSourceStore` Protocol exactly so ham-api
and ham-native-builder-worker share import job / source metadata across Cloud
Run instances. Selected when ``HAM_BUILDER_SOURCE_STORE_BACKEND=firestore``
(default remains file-backed for local/dev/tests).

Layout (one document per record id)::

    {import_jobs_collection}/{import_job_id}
    {project_sources_collection}/{project_source_id}
    {source_snapshots_collection}/{source_snapshot_id}

Env vars (per-store first, shared HAM_FIRESTORE_* fallback):

- ``HAM_BUILDER_SOURCE_FIRESTORE_PROJECT_ID``  -> ``HAM_FIRESTORE_PROJECT_ID``
- ``HAM_BUILDER_SOURCE_FIRESTORE_DATABASE``    -> ``HAM_FIRESTORE_DATABASE``
- ``HAM_BUILDER_SOURCE_FIRESTORE_IMPORT_JOBS_COLLECTION`` (default ``builder_import_jobs``)
- ``HAM_BUILDER_SOURCE_FIRESTORE_PROJECT_SOURCES_COLLECTION`` (default ``builder_project_sources``)
- ``HAM_BUILDER_SOURCE_FIRESTORE_SOURCE_SNAPSHOTS_COLLECTION`` (default ``builder_source_snapshots``)

User-facing APIs surface only safe import-job status fields — never raw bundles,
manifest internals, registry metadata, env names, or secrets.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from pydantic import ValidationError

from src.persistence.builder_source_store import (
    ImportJob,
    ProjectSource,
    SourceSnapshot,
    _utc_now_iso,
)

_LOG = logging.getLogger(__name__)

_BS_FS_PROJECT_ENV = "HAM_BUILDER_SOURCE_FIRESTORE_PROJECT_ID"
_BS_FS_DATABASE_ENV = "HAM_BUILDER_SOURCE_FIRESTORE_DATABASE"
_BS_FS_IMPORT_JOBS_ENV = "HAM_BUILDER_SOURCE_FIRESTORE_IMPORT_JOBS_COLLECTION"
_BS_FS_PROJECT_SOURCES_ENV = "HAM_BUILDER_SOURCE_FIRESTORE_PROJECT_SOURCES_COLLECTION"
_BS_FS_SOURCE_SNAPSHOTS_ENV = "HAM_BUILDER_SOURCE_FIRESTORE_SOURCE_SNAPSHOTS_COLLECTION"

_FALLBACK_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FALLBACK_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"

_DEFAULT_IMPORT_JOBS_COLLECTION = "builder_import_jobs"
_DEFAULT_PROJECT_SOURCES_COLLECTION = "builder_project_sources"
_DEFAULT_SOURCE_SNAPSHOTS_COLLECTION = "builder_source_snapshots"


class FirestoreBuilderSourceStoreError(RuntimeError):
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


class FirestoreBuilderSourceStore:
    """Firestore implementation of :class:`BuilderSourceStoreProtocol`."""

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str | None = None,
        import_jobs_collection: str | None = None,
        project_sources_collection: str | None = None,
        source_snapshots_collection: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._project = project or _resolve_env(_BS_FS_PROJECT_ENV, _FALLBACK_PROJECT_ENV)
        self._database = database or _resolve_env(_BS_FS_DATABASE_ENV, _FALLBACK_DATABASE_ENV)
        self._import_jobs_coll = (
            import_jobs_collection
            or _resolve_env(_BS_FS_IMPORT_JOBS_ENV)
            or _DEFAULT_IMPORT_JOBS_COLLECTION
        ).strip() or _DEFAULT_IMPORT_JOBS_COLLECTION
        self._project_sources_coll = (
            project_sources_collection
            or _resolve_env(_BS_FS_PROJECT_SOURCES_ENV)
            or _DEFAULT_PROJECT_SOURCES_COLLECTION
        ).strip() or _DEFAULT_PROJECT_SOURCES_COLLECTION
        self._source_snapshots_coll = (
            source_snapshots_collection
            or _resolve_env(_BS_FS_SOURCE_SNAPSHOTS_ENV)
            or _DEFAULT_SOURCE_SNAPSHOTS_COLLECTION
        ).strip() or _DEFAULT_SOURCE_SNAPSHOTS_COLLECTION
        self._client = client

    def _db(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.cloud import firestore  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            msg = (
                "google-cloud-firestore is required when "
                "HAM_BUILDER_SOURCE_STORE_BACKEND=firestore."
            )
            raise FirestoreBuilderSourceStoreError(msg) from exc
        kwargs: dict[str, Any] = {}
        if self._project:
            kwargs["project"] = self._project
        if self._database:
            kwargs["database"] = self._database
        self._client = firestore.Client(**kwargs) if kwargs else firestore.Client()
        return self._client

    def _coll(self, name: str) -> Any:
        return self._db().collection(name)

    @staticmethod
    def _wrap(op: str, exc: Exception) -> FirestoreBuilderSourceStoreError:
        return FirestoreBuilderSourceStoreError(
            f"firestore builder source store: {op} failed: {exc}",
        )

    @staticmethod
    def _stream_models(model_cls: type, coll: Any) -> list[Any]:
        records: list[Any] = []
        try:
            snaps = coll.stream()
        except Exception as exc:  # noqa: BLE001
            raise FirestoreBuilderSourceStoreError(f"stream failed: {exc}") from exc
        for snap in snaps:
            data = snap.to_dict() or {}
            try:
                records.append(model_cls.model_validate(data))
            except ValidationError as exc:
                print(
                    f"Warning: skipping malformed {model_cls.__name__} "
                    f"({type(exc).__name__}: {exc})",
                    file=sys.stderr,
                )
        return records

    def list_project_sources(self, *, workspace_id: str, project_id: str) -> list[ProjectSource]:
        try:
            rows = self._stream_models(ProjectSource, self._coll(self._project_sources_coll))
        except FirestoreBuilderSourceStoreError as exc:
            raise self._wrap("list_project_sources", exc) from exc
        filtered = [
            rec for rec in rows if rec.workspace_id == workspace_id and rec.project_id == project_id
        ]
        return sorted(filtered, key=lambda r: (r.updated_at, r.created_at, r.id), reverse=True)

    def list_source_snapshots(self, *, workspace_id: str, project_id: str) -> list[SourceSnapshot]:
        try:
            rows = self._stream_models(SourceSnapshot, self._coll(self._source_snapshots_coll))
        except FirestoreBuilderSourceStoreError as exc:
            raise self._wrap("list_source_snapshots", exc) from exc
        filtered = [
            rec for rec in rows if rec.workspace_id == workspace_id and rec.project_id == project_id
        ]
        return sorted(filtered, key=lambda r: (r.created_at, r.id), reverse=True)

    def list_import_jobs(self, *, workspace_id: str, project_id: str) -> list[ImportJob]:
        try:
            rows = self._stream_models(ImportJob, self._coll(self._import_jobs_coll))
        except FirestoreBuilderSourceStoreError as exc:
            raise self._wrap("list_import_jobs", exc) from exc
        filtered = [
            rec for rec in rows if rec.workspace_id == workspace_id and rec.project_id == project_id
        ]
        return sorted(filtered, key=lambda r: (r.updated_at, r.created_at, r.id), reverse=True)

    def upsert_project_source(self, record: ProjectSource) -> ProjectSource:
        payload = record.model_dump(mode="json")
        try:
            self._coll(self._project_sources_coll).document(record.id).set(payload)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("upsert_project_source", exc) from exc
        return record

    def upsert_source_snapshot(self, record: SourceSnapshot) -> SourceSnapshot:
        payload = record.model_dump(mode="json")
        try:
            self._coll(self._source_snapshots_coll).document(record.id).set(payload)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("upsert_source_snapshot", exc) from exc
        return record

    def upsert_import_job(self, record: ImportJob) -> ImportJob:
        payload = record.model_dump(mode="json")
        try:
            self._coll(self._import_jobs_coll).document(record.id).set(payload)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("upsert_import_job", exc) from exc
        return record

    def create_import_job(
        self,
        *,
        workspace_id: str,
        project_id: str,
        created_by: str,
        phase: str,
        status: str,
        project_source_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ImportJob:
        record = ImportJob(
            workspace_id=workspace_id,
            project_id=project_id,
            created_by=created_by,
            phase=phase,
            status=status,
            project_source_id=project_source_id,
            metadata=dict(metadata or {}),
        )
        return self.upsert_import_job(record)

    def get_import_job(self, *, import_job_id: str) -> ImportJob | None:
        jid = (import_job_id or "").strip()
        if not jid:
            return None
        try:
            snap = self._coll(self._import_jobs_coll).document(jid).get()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("get_import_job", exc) from exc
        if not getattr(snap, "exists", False):
            return None
        data = snap.to_dict() or {}
        try:
            return ImportJob.model_validate(data)
        except ValidationError as exc:
            _LOG.warning(
                "skipping malformed import job %s (%s): %s",
                jid,
                type(exc).__name__,
                exc,
            )
            return None

    def mark_import_job_running(self, *, import_job_id: str, phase: str) -> ImportJob:
        record = self._require_import_job(import_job_id)
        record.phase = phase
        record.status = "running"
        record.error_code = None
        record.error_message = None
        record.updated_at = _utc_now_iso()
        return self.upsert_import_job(record)

    def mark_import_job_succeeded(
        self,
        *,
        import_job_id: str,
        phase: str,
        source_snapshot_id: str,
        stats: dict[str, Any] | None = None,
    ) -> ImportJob:
        record = self._require_import_job(import_job_id)
        record.phase = phase
        record.status = "succeeded"
        record.source_snapshot_id = source_snapshot_id
        record.error_code = None
        record.error_message = None
        record.stats = dict(stats or {})
        record.updated_at = _utc_now_iso()
        return self.upsert_import_job(record)

    def mark_import_job_failed(
        self,
        *,
        import_job_id: str,
        phase: str,
        error_code: str,
        error_message: str,
    ) -> ImportJob:
        record = self._require_import_job(import_job_id)
        record.phase = phase
        record.status = "failed"
        record.error_code = str(error_code or "ZIP_INVALID")
        record.error_message = str(error_message or "Import failed.")
        record.updated_at = _utc_now_iso()
        return self.upsert_import_job(record)

    def _require_import_job(self, import_job_id: str) -> ImportJob:
        record = self.get_import_job(import_job_id=import_job_id)
        if record is None:
            raise KeyError(f"Unknown import job id: {import_job_id}")
        return record
