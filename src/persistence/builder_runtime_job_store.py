from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

_DEFAULT_STORE_PATH = Path.home() / ".ham" / "builder_runtime_jobs.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_job_id() -> str:
    return f"crjb_{uuid.uuid4().hex}"


class CloudRuntimeJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_job_id)
    version: str = "1.0.0"
    workspace_id: str
    project_id: str
    source_snapshot_id: str | None = None
    runtime_session_id: str | None = None
    status: str = "queued"
    phase: str = "received"
    provider: str = "disabled"
    requested_by: str | None = None
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    completed_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    logs_summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class BuilderRuntimeJobStoreProtocol(Protocol):
    def list_cloud_runtime_jobs(self, *, workspace_id: str, project_id: str) -> list[CloudRuntimeJob]: ...

    def get_cloud_runtime_job(self, *, workspace_id: str, project_id: str, job_id: str) -> CloudRuntimeJob | None: ...

    def upsert_cloud_runtime_job(self, record: CloudRuntimeJob) -> CloudRuntimeJob: ...


class BuilderRuntimeJobStore:
    def __init__(self, store_path: Path | None = None) -> None:
        self._path = Path(store_path) if store_path is not None else _DEFAULT_STORE_PATH

    def list_cloud_runtime_jobs(self, *, workspace_id: str, project_id: str) -> list[CloudRuntimeJob]:
        out: list[CloudRuntimeJob] = []
        for item in self._load_raw().get("cloud_runtime_jobs", []):
            try:
                rec = CloudRuntimeJob.model_validate(item)
            except ValidationError as exc:
                print(
                    f"Warning: skipping malformed cloud runtime job ({type(exc).__name__}: {exc})",
                    file=sys.stderr,
                )
                continue
            if rec.workspace_id != workspace_id or rec.project_id != project_id:
                continue
            out.append(rec)
        return sorted(out, key=lambda row: (row.updated_at, row.created_at, row.id), reverse=True)

    def get_cloud_runtime_job(self, *, workspace_id: str, project_id: str, job_id: str) -> CloudRuntimeJob | None:
        for row in self.list_cloud_runtime_jobs(workspace_id=workspace_id, project_id=project_id):
            if row.id == job_id:
                return row
        return None

    def upsert_cloud_runtime_job(self, record: CloudRuntimeJob) -> CloudRuntimeJob:
        raw = self._load_raw()
        rows = [r for r in raw.get("cloud_runtime_jobs", []) if str(r.get("id") or "") != record.id]
        rows.append(record.model_dump(mode="json"))
        raw["cloud_runtime_jobs"] = rows
        self._save_raw(raw)
        return record

    def _load_raw(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {"cloud_runtime_jobs": []}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"cloud_runtime_jobs": []}
        if not isinstance(data, dict):
            return {"cloud_runtime_jobs": []}
        data.setdefault("cloud_runtime_jobs", [])
        return data

    def _save_raw(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self._path)


_STORE_SINGLETON: list[BuilderRuntimeJobStoreProtocol | None] = [None]


def get_builder_runtime_job_store() -> BuilderRuntimeJobStoreProtocol:
    if _STORE_SINGLETON[0] is None:
        _STORE_SINGLETON[0] = BuilderRuntimeJobStore()
    return _STORE_SINGLETON[0]


def set_builder_runtime_job_store_for_tests(store: BuilderRuntimeJobStoreProtocol | None) -> None:
    _STORE_SINGLETON[0] = store
