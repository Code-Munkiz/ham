"""Durable execution-context store for HAM Native Builder v2.

`start_native_build_job` persists a :class:`NativeBuildContext` keyed by
``import_job_id`` and returns immediately; an out-of-process worker (Cloud Tasks
-> internal endpoint, or a Cloud Run Job) later loads it by id to reconstruct the
``execute_native_build_job`` arguments.

On Cloud Run the worker request may land on a *different* instance than the one
that enqueued the build, so the context must live in a shared, durable backend.
This module mirrors the file-backed + Firestore selector pattern used by the
builder runtime job / plan / run-event stores:

- default: file-backed (``~/.ham/native_build_contexts.json``) for local/dev/tests
- ``HAM_NATIVE_BUILD_CONTEXT_STORE_BACKEND=firestore`` selects
  :class:`FirestoreNativeBuildContextStore` (lazy import)

The context is stored server-side only and is never surfaced through the
import-jobs status API or any other user-facing surface. It carries no build-kit
internals, provider ids, registry metadata, digests, or secrets.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

_DEFAULT_STORE_PATH = Path.home() / ".ham" / "native_build_contexts.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class NativeBuildContext(BaseModel):
    """Durable execution context for an out-of-process native build worker.

    Persisted by ``import_job_id`` so a worker on any instance can reconstruct the
    ``execute_native_build_job`` arguments without relying on in-memory thread
    state or instance-local files. Stored server-side only and never surfaced
    through the import-jobs status API.
    """

    model_config = ConfigDict(extra="forbid")

    import_job_id: str
    version: str = "1.0.0"
    project_id: str
    workspace_id: str
    session_id: str = ""
    user_prompt: str = ""
    created_by: str = ""
    created_at: str = Field(default_factory=_utc_now_iso)


@runtime_checkable
class NativeBuildContextStoreProtocol(Protocol):
    def put_native_build_context(self, record: NativeBuildContext) -> NativeBuildContext: ...
    def get_native_build_context(self, *, import_job_id: str) -> NativeBuildContext | None: ...


class NativeBuildContextStore:
    """File-backed native build context store (``~/.ham/native_build_contexts.json``).

    Suitable for local/dev and tests. Not safe across Cloud Run instances (the
    worker may run on a different instance than the enqueuer); select the
    Firestore backend via ``HAM_NATIVE_BUILD_CONTEXT_STORE_BACKEND=firestore``
    for hosted deployments.
    """

    def __init__(self, store_path: Path | None = None) -> None:
        self._path = Path(store_path) if store_path is not None else _DEFAULT_STORE_PATH

    def put_native_build_context(self, record: NativeBuildContext) -> NativeBuildContext:
        raw = self._load_raw()
        rows = [
            r
            for r in raw.get("native_build_contexts", [])
            if str(r.get("import_job_id") or "") != record.import_job_id
        ]
        rows.append(record.model_dump(mode="json"))
        raw["native_build_contexts"] = rows
        self._save_raw(raw)
        return record

    def get_native_build_context(self, *, import_job_id: str) -> NativeBuildContext | None:
        jid = (import_job_id or "").strip()
        if not jid:
            return None
        for item in self._load_raw().get("native_build_contexts", []):
            try:
                rec = NativeBuildContext.model_validate(item)
            except ValidationError:
                continue
            if rec.import_job_id == jid:
                return rec
        return None

    def _load_raw(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {"native_build_contexts": []}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"native_build_contexts": []}
        if not isinstance(data, dict):
            return {"native_build_contexts": []}
        data.setdefault("native_build_contexts", [])
        return data

    def _save_raw(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self._path)


_STORE_SINGLETON: list[NativeBuildContextStoreProtocol | None] = [None]

_BACKEND_ENV = "HAM_NATIVE_BUILD_CONTEXT_STORE_BACKEND"
_BUILDER_SOURCE_BACKEND_ENV = "HAM_BUILDER_SOURCE_STORE_BACKEND"


def build_native_build_context_store() -> NativeBuildContextStoreProtocol:
    """Pick the native build context store backend based on env.

    Defaults to the file-backed implementation. ``HAM_NATIVE_BUILD_CONTEXT_STORE_BACKEND
    =firestore`` selects :class:`FirestoreNativeBuildContextStore` (lazy import).

    When only the builder *source* store is set to Firestore, execution context
    must share that backend too (otherwise the worker cannot load context).
    """
    backend = (os.environ.get(_BACKEND_ENV) or "").strip().lower()
    if not backend:
        src_backend = (os.environ.get(_BUILDER_SOURCE_BACKEND_ENV) or "").strip().lower()
        if src_backend == "firestore":
            backend = "firestore"
    if backend == "firestore":
        from src.persistence.firestore_native_build_context_store import (  # noqa: PLC0415
            FirestoreNativeBuildContextStore,
        )

        return FirestoreNativeBuildContextStore()
    return NativeBuildContextStore()


def get_native_build_context_store() -> NativeBuildContextStoreProtocol:
    if _STORE_SINGLETON[0] is None:
        _STORE_SINGLETON[0] = build_native_build_context_store()
    return _STORE_SINGLETON[0]


def set_native_build_context_store_for_tests(store: NativeBuildContextStoreProtocol | None) -> None:
    _STORE_SINGLETON[0] = store
