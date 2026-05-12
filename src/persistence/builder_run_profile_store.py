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

_DEFAULT_STORE_PATH = Path.home() / ".ham" / "builder_run_profiles.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_builder_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class LocalRunProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: _new_builder_id("rprf"))
    version: str = "1.0.0"
    workspace_id: str
    project_id: str
    source_snapshot_id: str | None = None
    display_name: str = ""
    working_directory: str = "."
    install_command_argv: list[str] | None = None
    dev_command_argv: list[str]
    build_command_argv: list[str] | None = None
    test_command_argv: list[str] | None = None
    expected_preview_url: str | None = None
    execution_mode: str = "local_only"
    status: str = "configured"
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class BuilderRunProfileStoreProtocol(Protocol):
    def list_local_run_profiles(self, *, workspace_id: str, project_id: str) -> list[LocalRunProfile]: ...
    def upsert_local_run_profile(self, record: LocalRunProfile) -> LocalRunProfile: ...
    def get_active_local_run_profile(self, *, workspace_id: str, project_id: str) -> LocalRunProfile | None: ...
    def clear_active_local_run_profile(self, *, workspace_id: str, project_id: str) -> LocalRunProfile | None: ...


class BuilderRunProfileStore:
    """File-backed local run profile store (~/.ham/builder_run_profiles.json)."""

    def __init__(self, store_path: Path | None = None) -> None:
        self._path = Path(store_path) if store_path is not None else _DEFAULT_STORE_PATH

    def list_local_run_profiles(self, *, workspace_id: str, project_id: str) -> list[LocalRunProfile]:
        out: list[LocalRunProfile] = []
        for item in self._load_raw().get("local_run_profiles", []):
            try:
                rec = LocalRunProfile.model_validate(item)
            except ValidationError as exc:
                print(
                    f"Warning: skipping malformed local run profile ({type(exc).__name__}: {exc})",
                    file=sys.stderr,
                )
                continue
            if rec.workspace_id == workspace_id and rec.project_id == project_id:
                out.append(rec)
        return sorted(out, key=lambda r: (r.updated_at, r.created_at, r.id), reverse=True)

    def upsert_local_run_profile(self, record: LocalRunProfile) -> LocalRunProfile:
        existing = self.get_active_local_run_profile(workspace_id=record.workspace_id, project_id=record.project_id)
        if existing is not None and existing.id != record.id:
            existing.status = "disabled"
            existing.updated_at = _utc_now_iso()
            self._upsert_raw(existing)
        record.updated_at = _utc_now_iso()
        self._upsert_raw(record)
        return record

    def get_active_local_run_profile(self, *, workspace_id: str, project_id: str) -> LocalRunProfile | None:
        for row in self.list_local_run_profiles(workspace_id=workspace_id, project_id=project_id):
            if row.status in {"configured", "draft"}:
                return row
        return None

    def clear_active_local_run_profile(self, *, workspace_id: str, project_id: str) -> LocalRunProfile | None:
        current = self.get_active_local_run_profile(workspace_id=workspace_id, project_id=project_id)
        if current is None:
            return None
        current.status = "disabled"
        current.updated_at = _utc_now_iso()
        self._upsert_raw(current)
        return current

    def _upsert_raw(self, record: LocalRunProfile) -> None:
        raw = self._load_raw()
        rows = [r for r in raw.get("local_run_profiles", []) if str(r.get("id") or "") != record.id]
        rows.append(record.model_dump(mode="json"))
        raw["local_run_profiles"] = rows
        self._save_raw(raw)

    def _load_raw(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {"local_run_profiles": []}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"local_run_profiles": []}
        if not isinstance(data, dict):
            return {"local_run_profiles": []}
        data.setdefault("local_run_profiles", [])
        return data

    def _save_raw(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self._path)


_STORE_SINGLETON: list[BuilderRunProfileStoreProtocol | None] = [None]


def get_builder_run_profile_store() -> BuilderRunProfileStoreProtocol:
    if _STORE_SINGLETON[0] is None:
        _STORE_SINGLETON[0] = BuilderRunProfileStore()
    return _STORE_SINGLETON[0]


def set_builder_run_profile_store_for_tests(store: BuilderRunProfileStoreProtocol | None) -> None:
    _STORE_SINGLETON[0] = store


_RUN_PROFILE_ID_RE = re.compile(r"^rprf_[0-9a-f]{32}$")


def is_valid_local_run_profile_id(value: str | None) -> bool:
    if value is None:
        return False
    return bool(_RUN_PROFILE_ID_RE.match(str(value)))
