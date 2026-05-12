from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

_DEFAULT_STORE_PATH = Path.home() / ".ham" / "builder_sources.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_builder_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class ProjectSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: _new_builder_id("psrc"))
    version: str = "1.0.0"
    project_id: str
    workspace_id: str
    kind: str = "workspace_path"
    status: str = "ready"
    display_name: str = ""
    origin_ref: str = ""
    active_snapshot_id: str | None = None
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    created_by: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: _new_builder_id("ssnp"))
    version: str = "1.0.0"
    project_id: str
    workspace_id: str
    project_source_id: str
    status: str = "materialized"
    digest_sha256: str = ""
    size_bytes: int = 0
    artifact_uri: str = ""
    manifest: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_utc_now_iso)
    created_by: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImportJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: _new_builder_id("ijob"))
    version: str = "1.0.0"
    project_id: str
    workspace_id: str
    project_source_id: str | None = None
    source_snapshot_id: str | None = None
    phase: str = "received"
    status: str = "queued"
    error_code: str | None = None
    error_message: str | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    created_by: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class BuilderSourceStoreProtocol(Protocol):
    def list_project_sources(self, *, workspace_id: str, project_id: str) -> list[ProjectSource]: ...
    def list_source_snapshots(self, *, workspace_id: str, project_id: str) -> list[SourceSnapshot]: ...
    def list_import_jobs(self, *, workspace_id: str, project_id: str) -> list[ImportJob]: ...

    def upsert_project_source(self, record: ProjectSource) -> ProjectSource: ...
    def upsert_source_snapshot(self, record: SourceSnapshot) -> SourceSnapshot: ...
    def upsert_import_job(self, record: ImportJob) -> ImportJob: ...
    def create_import_job(
        self,
        *,
        workspace_id: str,
        project_id: str,
        created_by: str,
        phase: str,
        status: str,
        project_source_id: str | None = None,
    ) -> ImportJob: ...
    def mark_import_job_running(self, *, import_job_id: str, phase: str) -> ImportJob: ...
    def mark_import_job_succeeded(
        self,
        *,
        import_job_id: str,
        phase: str,
        source_snapshot_id: str,
        stats: dict[str, Any] | None = None,
    ) -> ImportJob: ...
    def mark_import_job_failed(
        self,
        *,
        import_job_id: str,
        phase: str,
        error_code: str,
        error_message: str,
    ) -> ImportJob: ...


class BuilderSourceStore:
    """File-backed builder source metadata store (~/.ham/builder_sources.json)."""

    def __init__(self, store_path: Path | None = None) -> None:
        self._path = Path(store_path) if store_path is not None else _DEFAULT_STORE_PATH

    def list_project_sources(self, *, workspace_id: str, project_id: str) -> list[ProjectSource]:
        records: list[ProjectSource] = []
        for item in self._load_raw().get("project_sources", []):
            try:
                rec = ProjectSource.model_validate(item)
            except ValidationError as exc:
                print(
                    f"Warning: skipping malformed project source ({type(exc).__name__}: {exc})",
                    file=sys.stderr,
                )
                continue
            if rec.workspace_id == workspace_id and rec.project_id == project_id:
                records.append(rec)
        return sorted(records, key=lambda r: (r.updated_at, r.created_at, r.id), reverse=True)

    def list_source_snapshots(self, *, workspace_id: str, project_id: str) -> list[SourceSnapshot]:
        records: list[SourceSnapshot] = []
        for item in self._load_raw().get("source_snapshots", []):
            try:
                rec = SourceSnapshot.model_validate(item)
            except ValidationError as exc:
                print(
                    f"Warning: skipping malformed source snapshot ({type(exc).__name__}: {exc})",
                    file=sys.stderr,
                )
                continue
            if rec.workspace_id == workspace_id and rec.project_id == project_id:
                records.append(rec)
        return sorted(records, key=lambda r: (r.created_at, r.id), reverse=True)

    def list_import_jobs(self, *, workspace_id: str, project_id: str) -> list[ImportJob]:
        records: list[ImportJob] = []
        for item in self._load_raw().get("import_jobs", []):
            try:
                rec = ImportJob.model_validate(item)
            except ValidationError as exc:
                print(
                    f"Warning: skipping malformed import job ({type(exc).__name__}: {exc})",
                    file=sys.stderr,
                )
                continue
            if rec.workspace_id == workspace_id and rec.project_id == project_id:
                records.append(rec)
        return sorted(records, key=lambda r: (r.updated_at, r.created_at, r.id), reverse=True)

    def upsert_project_source(self, record: ProjectSource) -> ProjectSource:
        raw = self._load_raw()
        rows = [r for r in raw.get("project_sources", []) if str(r.get("id") or "") != record.id]
        rows.append(record.model_dump(mode="json"))
        raw["project_sources"] = rows
        self._save_raw(raw)
        return record

    def upsert_source_snapshot(self, record: SourceSnapshot) -> SourceSnapshot:
        raw = self._load_raw()
        rows = [r for r in raw.get("source_snapshots", []) if str(r.get("id") or "") != record.id]
        rows.append(record.model_dump(mode="json"))
        raw["source_snapshots"] = rows
        self._save_raw(raw)
        return record

    def upsert_import_job(self, record: ImportJob) -> ImportJob:
        raw = self._load_raw()
        rows = [r for r in raw.get("import_jobs", []) if str(r.get("id") or "") != record.id]
        rows.append(record.model_dump(mode="json"))
        raw["import_jobs"] = rows
        self._save_raw(raw)
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
    ) -> ImportJob:
        record = ImportJob(
            workspace_id=workspace_id,
            project_id=project_id,
            created_by=created_by,
            phase=phase,
            status=status,
            project_source_id=project_source_id,
        )
        return self.upsert_import_job(record)

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
        for item in self._load_raw().get("import_jobs", []):
            try:
                rec = ImportJob.model_validate(item)
            except ValidationError:
                continue
            if rec.id == import_job_id:
                return rec
        raise KeyError(f"Unknown import job id: {import_job_id}")

    def _load_raw(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {"project_sources": [], "source_snapshots": [], "import_jobs": []}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"project_sources": [], "source_snapshots": [], "import_jobs": []}
        if not isinstance(data, dict):
            return {"project_sources": [], "source_snapshots": [], "import_jobs": []}
        data.setdefault("project_sources", [])
        data.setdefault("source_snapshots", [])
        data.setdefault("import_jobs", [])
        return data

    def _save_raw(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, self._path)


_STORE_SINGLETON: list[BuilderSourceStoreProtocol | None] = [None]


def get_builder_source_store() -> BuilderSourceStoreProtocol:
    if _STORE_SINGLETON[0] is None:
        _STORE_SINGLETON[0] = BuilderSourceStore()
    return _STORE_SINGLETON[0]


def set_builder_source_store_for_tests(store: BuilderSourceStoreProtocol | None) -> None:
    _STORE_SINGLETON[0] = store


_BUILDER_ID_RE = re.compile(r"^(psrc|ssnp|ijob)_[0-9a-f]{32}$")


def is_valid_builder_record_id(value: str | None) -> bool:
    if value is None:
        return False
    return bool(_BUILDER_ID_RE.match(str(value)))
