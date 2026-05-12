from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

_DEFAULT_STORE_PATH = Path.home() / ".ham" / "builder_runtime.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_runtime_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class RuntimeSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: _new_runtime_id("rtms"))
    version: str = "1.0.0"
    workspace_id: str
    project_id: str
    snapshot_id: str | None = None
    mode: str = "local"
    status: str = "not_connected"
    health: str = "unknown"
    preview_endpoint_id: str | None = None
    message: str | None = None
    started_at: str | None = None
    updated_at: str = Field(default_factory=_utc_now_iso)
    expires_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PreviewEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: _new_runtime_id("prve"))
    version: str = "1.0.0"
    workspace_id: str
    project_id: str
    runtime_session_id: str
    url: str = ""
    access_mode: str = "local_url"
    status: str = "provisioning"
    last_checked_at: str | None = None
    expires_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class BuilderRuntimeStoreProtocol(Protocol):
    def list_runtime_sessions(self, *, workspace_id: str, project_id: str) -> list[RuntimeSession]: ...
    def list_preview_endpoints(self, *, workspace_id: str, project_id: str) -> list[PreviewEndpoint]: ...
    def upsert_runtime_session(self, record: RuntimeSession) -> RuntimeSession: ...
    def upsert_preview_endpoint(self, record: PreviewEndpoint) -> PreviewEndpoint: ...


class BuilderRuntimeStore:
    """File-backed runtime metadata store (~/.ham/builder_runtime.json)."""

    def __init__(self, store_path: Path | None = None) -> None:
        self._path = Path(store_path) if store_path is not None else _DEFAULT_STORE_PATH

    def list_runtime_sessions(self, *, workspace_id: str, project_id: str) -> list[RuntimeSession]:
        out: list[RuntimeSession] = []
        for item in self._load_raw().get("runtime_sessions", []):
            try:
                rec = RuntimeSession.model_validate(item)
            except ValidationError as exc:
                print(
                    f"Warning: skipping malformed runtime session ({type(exc).__name__}: {exc})",
                    file=sys.stderr,
                )
                continue
            if rec.workspace_id == workspace_id and rec.project_id == project_id:
                out.append(rec)
        return sorted(out, key=lambda r: (r.updated_at, r.id), reverse=True)

    def list_preview_endpoints(self, *, workspace_id: str, project_id: str) -> list[PreviewEndpoint]:
        out: list[PreviewEndpoint] = []
        for item in self._load_raw().get("preview_endpoints", []):
            try:
                rec = PreviewEndpoint.model_validate(item)
            except ValidationError as exc:
                print(
                    f"Warning: skipping malformed preview endpoint ({type(exc).__name__}: {exc})",
                    file=sys.stderr,
                )
                continue
            if rec.workspace_id == workspace_id and rec.project_id == project_id:
                out.append(rec)
        return sorted(out, key=lambda r: (r.last_checked_at or "", r.id), reverse=True)

    def upsert_runtime_session(self, record: RuntimeSession) -> RuntimeSession:
        raw = self._load_raw()
        rows = [r for r in raw.get("runtime_sessions", []) if str(r.get("id") or "") != record.id]
        rows.append(record.model_dump(mode="json"))
        raw["runtime_sessions"] = rows
        self._save_raw(raw)
        return record

    def upsert_preview_endpoint(self, record: PreviewEndpoint) -> PreviewEndpoint:
        raw = self._load_raw()
        rows = [r for r in raw.get("preview_endpoints", []) if str(r.get("id") or "") != record.id]
        rows.append(record.model_dump(mode="json"))
        raw["preview_endpoints"] = rows
        self._save_raw(raw)
        return record

    def _load_raw(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {"runtime_sessions": [], "preview_endpoints": []}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"runtime_sessions": [], "preview_endpoints": []}
        if not isinstance(data, dict):
            return {"runtime_sessions": [], "preview_endpoints": []}
        data.setdefault("runtime_sessions", [])
        data.setdefault("preview_endpoints", [])
        return data

    def _save_raw(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self._path)


_STORE_SINGLETON: list[BuilderRuntimeStoreProtocol | None] = [None]


def get_builder_runtime_store() -> BuilderRuntimeStoreProtocol:
    if _STORE_SINGLETON[0] is None:
        _STORE_SINGLETON[0] = BuilderRuntimeStore()
    return _STORE_SINGLETON[0]


def set_builder_runtime_store_for_tests(store: BuilderRuntimeStoreProtocol | None) -> None:
    _STORE_SINGLETON[0] = store
