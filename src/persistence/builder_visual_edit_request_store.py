from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

_DEFAULT_STORE_PATH = Path.home() / ".ham" / "builder_visual_edit_requests.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_request_id() -> str:
    return f"vedit_{uuid.uuid4().hex}"


class VisualEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_request_id)
    version: str = "1.0.0"
    workspace_id: str
    project_id: str
    source_snapshot_id: str | None = None
    runtime_session_id: str | None = None
    preview_endpoint_id: str | None = None
    route: str | None = None
    selector_hints: list[str] = Field(default_factory=list)
    bbox: dict[str, float] | None = None
    instruction: str
    status: str = "draft"
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class BuilderVisualEditRequestStoreProtocol(Protocol):
    def list_visual_edit_requests(self, *, workspace_id: str, project_id: str) -> list[VisualEditRequest]: ...
    def upsert_visual_edit_request(self, record: VisualEditRequest) -> VisualEditRequest: ...
    def get_visual_edit_request(
        self,
        *,
        workspace_id: str,
        project_id: str,
        request_id: str,
    ) -> VisualEditRequest | None: ...
    def cancel_visual_edit_request(
        self,
        *,
        workspace_id: str,
        project_id: str,
        request_id: str,
    ) -> VisualEditRequest | None: ...


class BuilderVisualEditRequestStore:
    """File-backed visual edit request store (~/.ham/builder_visual_edit_requests.json)."""

    def __init__(self, store_path: Path | None = None) -> None:
        self._path = Path(store_path) if store_path is not None else _DEFAULT_STORE_PATH

    def list_visual_edit_requests(self, *, workspace_id: str, project_id: str) -> list[VisualEditRequest]:
        out: list[VisualEditRequest] = []
        for item in self._load_raw().get("visual_edit_requests", []):
            try:
                rec = VisualEditRequest.model_validate(item)
            except ValidationError as exc:
                print(
                    f"Warning: skipping malformed visual edit request ({type(exc).__name__}: {exc})",
                    file=sys.stderr,
                )
                continue
            if rec.workspace_id == workspace_id and rec.project_id == project_id:
                out.append(rec)
        return sorted(out, key=lambda r: (r.updated_at, r.created_at, r.id), reverse=True)

    def upsert_visual_edit_request(self, record: VisualEditRequest) -> VisualEditRequest:
        record.updated_at = _utc_now_iso()
        raw = self._load_raw()
        rows = [r for r in raw.get("visual_edit_requests", []) if str(r.get("id") or "") != record.id]
        rows.append(record.model_dump(mode="json"))
        raw["visual_edit_requests"] = rows
        self._save_raw(raw)
        return record

    def get_visual_edit_request(
        self,
        *,
        workspace_id: str,
        project_id: str,
        request_id: str,
    ) -> VisualEditRequest | None:
        for row in self.list_visual_edit_requests(workspace_id=workspace_id, project_id=project_id):
            if row.id == request_id:
                return row
        return None

    def cancel_visual_edit_request(
        self,
        *,
        workspace_id: str,
        project_id: str,
        request_id: str,
    ) -> VisualEditRequest | None:
        row = self.get_visual_edit_request(
            workspace_id=workspace_id,
            project_id=project_id,
            request_id=request_id,
        )
        if row is None:
            return None
        row.status = "cancelled"
        row.updated_at = _utc_now_iso()
        return self.upsert_visual_edit_request(row)

    def _load_raw(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {"visual_edit_requests": []}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"visual_edit_requests": []}
        if not isinstance(data, dict):
            return {"visual_edit_requests": []}
        data.setdefault("visual_edit_requests", [])
        return data

    def _save_raw(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self._path)


_STORE_SINGLETON: list[BuilderVisualEditRequestStoreProtocol | None] = [None]


def get_builder_visual_edit_request_store() -> BuilderVisualEditRequestStoreProtocol:
    if _STORE_SINGLETON[0] is None:
        _STORE_SINGLETON[0] = BuilderVisualEditRequestStore()
    return _STORE_SINGLETON[0]


def set_builder_visual_edit_request_store_for_tests(store: BuilderVisualEditRequestStoreProtocol | None) -> None:
    _STORE_SINGLETON[0] = store
