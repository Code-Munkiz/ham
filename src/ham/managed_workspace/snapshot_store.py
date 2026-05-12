from __future__ import annotations

import logging
import os
from typing import Protocol

from src.ham.managed_workspace.models import ProjectSnapshot

_LOG = logging.getLogger(__name__)

# Mirror project store split: Memory when file-backed hosts; Firestore when enabled.
_PROJECT_STORE_BACKEND_ENV = "HAM_PROJECT_STORE_BACKEND"


class ProjectSnapshotStore(Protocol):
    def put_snapshot(self, row: ProjectSnapshot) -> None: ...
    def list_snapshots(self, project_id: str) -> list[ProjectSnapshot]: ...
    def get_snapshot(self, project_id: str, snapshot_id: str) -> ProjectSnapshot | None: ...


class MemoryProjectSnapshotStore:
    _instance: MemoryProjectSnapshotStore | None = None

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, ProjectSnapshot]] = {}

    @classmethod
    def singleton(cls) -> MemoryProjectSnapshotStore:
        if cls._instance is None:
            cls._instance = MemoryProjectSnapshotStore()
        return cls._instance

    def put_snapshot(self, row: ProjectSnapshot) -> None:
        m = self._rows.setdefault(row.project_id, {})
        m[row.snapshot_id] = row

    def list_snapshots(self, project_id: str) -> list[ProjectSnapshot]:
        m = self._rows.get(project_id)
        if not m:
            return []
        rows = sorted(m.values(), key=lambda r: r.created_at)
        return list(rows)

    def get_snapshot(self, project_id: str, snapshot_id: str) -> ProjectSnapshot | None:
        return self._rows.get(project_id, {}).get(snapshot_id)


_global_override: ProjectSnapshotStore | None = None


def get_project_snapshot_store() -> ProjectSnapshotStore:
    if _global_override is not None:
        return _global_override
    backend = (os.environ.get(_PROJECT_STORE_BACKEND_ENV) or "file").strip().lower()
    if backend == "firestore":
        from src.ham.managed_workspace.firestore_project_snapshot_store import (  # noqa: PLC0415
            FirestoreProjectSnapshotStore,
        )

        return FirestoreProjectSnapshotStore()
    return MemoryProjectSnapshotStore.singleton()


def set_project_snapshot_store_for_tests(store: ProjectSnapshotStore | None) -> None:
    global _global_override
    _global_override = store
