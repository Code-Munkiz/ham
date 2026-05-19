"""Persistence for SSE event log per CloudRuntimeJob — Contract 4.

Supports append (assigns monotonic seq) and read_from (Last-Event-ID
replay). File-backed for dev; Protocol-typed; swappable via
set_builder_run_events_store_for_tests().

Spec: docs/PHASE_0_CONTRACTS.md § Contract 4
ADR: docs/adr/0002-sse-with-replay-for-worker-events.md
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import ValidationError

from src.ham.builder_plan import SSEEvent

_DEFAULT_STORE_PATH = Path.home() / ".ham" / "builder_run_events.json"


@runtime_checkable
class BuilderRunEventsStoreProtocol(Protocol):
    def append(self, event: SSEEvent) -> SSEEvent: ...

    def read_from(self, *, job_id: str, since_seq: int = 0) -> list[SSEEvent]: ...

    def latest_seq(self, *, job_id: str) -> int: ...


class BuilderRunEventsStore:
    def __init__(self, store_path: Path | None = None) -> None:
        self._path = Path(store_path) if store_path is not None else _DEFAULT_STORE_PATH
        self._lock = threading.Lock()

    def append(self, event: SSEEvent) -> SSEEvent:
        with self._lock:
            raw = self._load_raw()
            events_for_job = raw.get(event.job_id, [])
            next_seq = (events_for_job[-1]["seq"] if events_for_job else 0) + 1
            updated = event.model_copy(update={"seq": next_seq})
            events_for_job.append(updated.model_dump(mode="json"))
            raw[event.job_id] = events_for_job
            self._save_raw(raw)
            return updated

    def read_from(self, *, job_id: str, since_seq: int = 0) -> list[SSEEvent]:
        raw = self._load_raw()
        events_for_job = raw.get(job_id, [])
        out: list[SSEEvent] = []
        for item in events_for_job:
            try:
                evt = SSEEvent.model_validate(item)
            except ValidationError as exc:
                print(
                    f"Warning: skipping malformed event ({type(exc).__name__}: {exc})",
                    file=sys.stderr,
                )
                continue
            if evt.seq > since_seq:
                out.append(evt)
        return sorted(out, key=lambda e: e.seq)

    def latest_seq(self, *, job_id: str) -> int:
        raw = self._load_raw()
        events_for_job = raw.get(job_id, [])
        if not events_for_job:
            return 0
        try:
            return int(events_for_job[-1].get("seq") or 0)
        except (ValueError, TypeError):
            return 0

    def _load_raw(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        return data

    def _save_raw(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self._path)


_STORE_SINGLETON: list[BuilderRunEventsStoreProtocol | None] = [None]

_BACKEND_ENV = "HAM_BUILDER_RUN_EVENTS_STORE_BACKEND"


def build_builder_run_events_store() -> BuilderRunEventsStoreProtocol:
    """Pick the events store backend based on env.

    Defaults to the file-backed implementation so local dev keeps working
    without any env vars. ``HAM_BUILDER_RUN_EVENTS_STORE_BACKEND=firestore``
    selects :class:`FirestoreBuilderRunEventsStore` (lazy import so the SDK
    is not required for local dev).
    """
    backend = (os.environ.get(_BACKEND_ENV) or "").strip().lower()
    if backend == "firestore":
        from src.persistence.firestore_builder_run_events_store import (  # noqa: PLC0415
            FirestoreBuilderRunEventsStore,
        )

        return FirestoreBuilderRunEventsStore()
    return BuilderRunEventsStore()


def get_builder_run_events_store() -> BuilderRunEventsStoreProtocol:
    if _STORE_SINGLETON[0] is None:
        _STORE_SINGLETON[0] = build_builder_run_events_store()
    return _STORE_SINGLETON[0]


def set_builder_run_events_store_for_tests(store: BuilderRunEventsStoreProtocol | None) -> None:
    _STORE_SINGLETON[0] = store
