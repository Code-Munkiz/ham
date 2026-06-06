from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_serializer

from src.ham.builder_plan import CloudRuntimeJobStatus, ErrorEnvelope

# Phase 0 Literal + v1.x wire statuses the runtime still emits until fully migrated.
CloudRuntimeJobStoreStatus = CloudRuntimeJobStatus | Literal["unsupported"]

_DEFAULT_STORE_PATH = Path.home() / ".ham" / "builder_runtime_jobs.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_job_id() -> str:
    return f"crjb_{uuid.uuid4().hex}"


class CloudRuntimeJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_job_id)
    version: str = "1.1.0"
    workspace_id: str
    project_id: str
    source_snapshot_id: str | None = None
    runtime_session_id: str | None = None
    status: CloudRuntimeJobStoreStatus = "queued"
    phase: str = "received"
    provider: str = "disabled"
    requested_by: str | None = None
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    completed_at: str | None = None
    # Deprecated: use last_error instead. Kept for one minor version.
    error_code: str | None = None
    error_message: str | None = None
    last_error: ErrorEnvelope | None = None
    cancel_requested_at: str | None = None
    cancel_reason: str | None = None
    # Phase 1 #3 (ADR-0004): job-level TTL. Old records load with defaults.
    ttl_seconds: int = 3600
    ttl_deadline: str | None = None
    logs_summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_serializer("status")
    def _serialize_status_for_wire(self, value: CloudRuntimeJobStoreStatus) -> str:
        # v1.x workers/API use "succeeded"; Phase 0 Literal uses "completed".
        if value == "completed":
            return "succeeded"
        return value


@runtime_checkable
class BuilderRuntimeJobStoreProtocol(Protocol):
    def list_cloud_runtime_jobs(self, *, workspace_id: str, project_id: str) -> list[CloudRuntimeJob]: ...

    def get_cloud_runtime_job(self, *, workspace_id: str, project_id: str, job_id: str) -> CloudRuntimeJob | None: ...

    def upsert_cloud_runtime_job(self, record: CloudRuntimeJob) -> CloudRuntimeJob: ...


class BuilderRuntimeJobStore:
    def __init__(self, store_path: Path | None = None) -> None:
        self._path = Path(store_path) if store_path is not None else _DEFAULT_STORE_PATH

    _VALID_STATUSES = {
        "queued",
        "running",
        "cancelling",
        "cancelled",
        "completed",
        "failed",
        "unsupported",
    }
    _LEGACY_STATUS_ALIASES = {"succeeded": "completed", "success": "completed"}

    def list_cloud_runtime_jobs(self, *, workspace_id: str, project_id: str) -> list[CloudRuntimeJob]:
        out: list[CloudRuntimeJob] = []
        for item in self._load_raw().get("cloud_runtime_jobs", []):
            try:
                item = self._normalize_legacy_record(item)
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

    @classmethod
    def _normalize_legacy_record(cls, item: dict[str, Any]) -> dict[str, Any]:
        """Tolerate old records with free-string status or missing new fields."""
        if not isinstance(item, dict):
            return item
        status = item.get("status")
        if not isinstance(status, str):
            return item
        alias = cls._LEGACY_STATUS_ALIASES.get(status)
        if alias is not None:
            item = dict(item)
            item["status"] = alias
        elif status not in cls._VALID_STATUSES:
            item = dict(item)
            item["status"] = "failed"
        return item

    @classmethod
    def _coerce_incoming_status(cls, status: Any) -> CloudRuntimeJobStoreStatus:
        if isinstance(status, str):
            alias = cls._LEGACY_STATUS_ALIASES.get(status)
            if alias is not None:
                return alias  # type: ignore[return-value]
            if status in cls._VALID_STATUSES:
                return status  # type: ignore[return-value]
        return "failed"

    def get_cloud_runtime_job(self, *, workspace_id: str, project_id: str, job_id: str) -> CloudRuntimeJob | None:
        for row in self.list_cloud_runtime_jobs(workspace_id=workspace_id, project_id=project_id):
            if row.id == job_id:
                return row
        return None

    def upsert_cloud_runtime_job(self, record: CloudRuntimeJob) -> CloudRuntimeJob:
        # Workers may still assign v1.x "succeeded" before Phase 0 Literal lands everywhere.
        coerced_status = self._coerce_incoming_status(record.status)
        if coerced_status != record.status:
            record = record.model_copy(update={"status": coerced_status})
        # Backward-compat: populate deprecated string fields from last_error
        if record.last_error is not None:
            record = record.model_copy(
                update={
                    "error_code": record.last_error.error_code,
                    "error_message": record.last_error.error_message,
                }
            )
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

_BACKEND_ENV = "HAM_BUILDER_RUNTIME_JOB_STORE_BACKEND"


_SOURCE_BACKEND_ENV = "HAM_BUILDER_SOURCE_STORE_BACKEND"
_RUNTIME_BACKEND_ENV = "HAM_BUILDER_RUNTIME_STORE_BACKEND"
_NATIVE_CONTEXT_BACKEND_ENV = "HAM_NATIVE_BUILD_CONTEXT_STORE_BACKEND"


def build_builder_runtime_job_store() -> BuilderRuntimeJobStoreProtocol:
    """Pick the runtime job store backend based on env.

    Defaults to the file-backed implementation. ``HAM_BUILDER_RUNTIME_JOB_STORE_BACKEND
    =firestore`` selects :class:`FirestoreBuilderRuntimeJobStore` (lazy import).

    When the builder source, native build context, or runtime session store is
    Firestore, jobs default to Firestore too so ham-api can list worker-updated
    cloud runtime job status.
    """
    backend = (os.environ.get(_BACKEND_ENV) or "").strip().lower()
    if not backend:
        for env_name in (_SOURCE_BACKEND_ENV, _RUNTIME_BACKEND_ENV, _NATIVE_CONTEXT_BACKEND_ENV):
            if (os.environ.get(env_name) or "").strip().lower() == "firestore":
                backend = "firestore"
                break
    if backend == "firestore":
        from src.persistence.firestore_builder_runtime_job_store import (  # noqa: PLC0415
            FirestoreBuilderRuntimeJobStore,
        )

        return FirestoreBuilderRuntimeJobStore()
    return BuilderRuntimeJobStore()


def get_builder_runtime_job_store() -> BuilderRuntimeJobStoreProtocol:
    if _STORE_SINGLETON[0] is None:
        _STORE_SINGLETON[0] = build_builder_runtime_job_store()
    return _STORE_SINGLETON[0]


def set_builder_runtime_job_store_for_tests(store: BuilderRuntimeJobStoreProtocol | None) -> None:
    _STORE_SINGLETON[0] = store
