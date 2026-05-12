from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

_DEFAULT_STORE_PATH = Path.home() / ".ham" / "builder_usage_events.json"
_SENSITIVE_KEY_RE = re.compile(r"(token|secret|password|passwd|api[_-]?key|bearer|authorization)", re.IGNORECASE)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_usage_event_id() -> str:
    return f"uevt_{uuid.uuid4().hex}"


def _safe_text(value: Any, *, fallback: str = "") -> str:
    raw = str(value if value is not None else "").strip()
    if not raw:
        return fallback
    text = " ".join(raw.replace("\r", " ").replace("\n", " ").split())
    return text[:240]


def _sanitize_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for idx, (key, value) in enumerate(raw.items()):
        if idx >= 20:
            break
        key_text = _safe_text(key)[:64]
        if not key_text or _SENSITIVE_KEY_RE.search(key_text):
            continue
        if isinstance(value, bool) or value is None:
            out[key_text] = value
        elif isinstance(value, int):
            out[key_text] = value
        elif isinstance(value, float):
            out[key_text] = round(value, 6)
        else:
            text = _safe_text(value)
            if text:
                out[key_text] = text
    return out


class UsageEventAttribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str | None = None
    worker_provider: str | None = None
    source_snapshot_id: str | None = None
    runtime_session_id: str | None = None
    build_job_id: str | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any] | None) -> "UsageEventAttribution":
        payload = dict(raw or {})
        return cls(
            provider=_safe_text(payload.get("provider"), fallback="") or None,
            worker_provider=_safe_text(payload.get("worker_provider"), fallback="") or None,
            source_snapshot_id=_safe_text(payload.get("source_snapshot_id"), fallback="") or None,
            runtime_session_id=_safe_text(payload.get("runtime_session_id"), fallback="") or None,
            build_job_id=_safe_text(payload.get("build_job_id"), fallback="") or None,
        )


class UsageEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_usage_event_id)
    workspace_id: str
    project_id: str | None = None
    category: Literal[
        "source_ingest",
        "artifact_storage",
        "preview_runtime",
        "build_runtime",
        "model_call",
        "worker_job",
    ]
    quantity: float = Field(ge=0.0)
    unit: Literal["bytes", "seconds", "count", "tokens"]
    attribution: UsageEventAttribution = Field(default_factory=UsageEventAttribution)
    timestamp: str = Field(default_factory=_utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class BuilderUsageEventStoreProtocol(Protocol):
    def list_usage_events(self, *, workspace_id: str, project_id: str) -> list[UsageEvent]: ...

    def append_usage_event(self, record: UsageEvent) -> UsageEvent: ...


class BuilderUsageEventStore:
    """File-backed usage event store (~/.ham/builder_usage_events.json)."""

    def __init__(self, store_path: Path | None = None) -> None:
        self._path = Path(store_path) if store_path is not None else _DEFAULT_STORE_PATH

    def list_usage_events(self, *, workspace_id: str, project_id: str) -> list[UsageEvent]:
        out: list[UsageEvent] = []
        for item in self._load_raw().get("usage_events", []):
            try:
                rec = UsageEvent.model_validate(item)
            except ValidationError as exc:
                print(
                    f"Warning: skipping malformed usage event ({type(exc).__name__}: {exc})",
                    file=sys.stderr,
                )
                continue
            if rec.workspace_id != workspace_id:
                continue
            if rec.project_id != project_id:
                continue
            out.append(rec)
        return sorted(out, key=lambda row: (row.timestamp, row.id), reverse=True)

    def append_usage_event(self, record: UsageEvent) -> UsageEvent:
        normalized = record.model_copy(
            update={
                "workspace_id": _safe_text(record.workspace_id),
                "project_id": _safe_text(record.project_id, fallback="") or None,
                "attribution": UsageEventAttribution.from_raw(record.attribution.model_dump(mode="json")),
                "metadata": _sanitize_metadata(record.metadata),
            }
        )
        raw = self._load_raw()
        rows = list(raw.get("usage_events", []))
        rows.append(normalized.model_dump(mode="json"))
        raw["usage_events"] = rows
        self._save_raw(raw)
        return normalized

    def _load_raw(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {"usage_events": []}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"usage_events": []}
        if not isinstance(data, dict):
            return {"usage_events": []}
        data.setdefault("usage_events", [])
        return data

    def _save_raw(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self._path)


_STORE_SINGLETON: list[BuilderUsageEventStoreProtocol | None] = [None]


def get_builder_usage_event_store() -> BuilderUsageEventStoreProtocol:
    if _STORE_SINGLETON[0] is None:
        _STORE_SINGLETON[0] = BuilderUsageEventStore()
    return _STORE_SINGLETON[0]


def set_builder_usage_event_store_for_tests(store: BuilderUsageEventStoreProtocol | None) -> None:
    _STORE_SINGLETON[0] = store
