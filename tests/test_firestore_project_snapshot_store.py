"""Tests for :class:`FirestoreProjectSnapshotStore` env-resolved wiring.

Uses a minimal in-memory fake Firestore client (mirrors the pattern in
``tests/test_firestore_control_plane_run_store.py``) so the tests never
contact GCP or the real ``google.cloud.firestore`` SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from src.ham.managed_workspace.firestore_project_snapshot_store import (
    FirestoreProjectSnapshotStore,
)
from src.ham.managed_workspace.models import ProjectSnapshot
from src.ham.managed_workspace.snapshot_store import (
    MemoryProjectSnapshotStore,
    get_project_snapshot_store,
    set_project_snapshot_store_for_tests,
)

# ---------------------------------------------------------------------------
# Minimal fake Firestore client (in-memory, single collection)
# ---------------------------------------------------------------------------


@dataclass
class _FakeDocSnap:
    id: str
    _data: dict[str, Any] | None

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data) if self._data is not None else {}


@dataclass
class _FakeDocRef:
    root: _FakeFirestoreClient
    coll_name: str
    id: str

    def set(self, data: dict[str, Any]) -> None:
        self.root.docs.setdefault(self.coll_name, {})[self.id] = dict(data)

    def get(self) -> _FakeDocSnap:
        coll = self.root.docs.get(self.coll_name, {})
        return _FakeDocSnap(self.id, coll.get(self.id))


@dataclass
class _FakeCollection:
    root: _FakeFirestoreClient
    name: str

    def document(self, doc_id: str) -> _FakeDocRef:
        return _FakeDocRef(self.root, self.name, doc_id)

    def stream(self):
        coll = self.root.docs.get(self.name, {})
        for doc_id, data in list(coll.items()):
            yield _FakeDocSnap(doc_id, dict(data))


@dataclass
class _FakeFirestoreClient:
    docs: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self, name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _snapshot(
    *,
    project_id: str = "project.pilot",
    snapshot_id: str = "snap-aaaa",
    workspace_id: str = "ws-1",
) -> ProjectSnapshot:
    return ProjectSnapshot(
        project_id=project_id,
        workspace_id=workspace_id,
        snapshot_id=snapshot_id,
        parent_snapshot_id=None,
        created_at="2026-05-12T00:00:00Z",
        bucket="bucket-1",
        object_prefix=f"ws/{workspace_id}/{project_id}/{snapshot_id}/",
        preview_url=f"/preview/{project_id}/{snapshot_id}",
        manifest_object=f"ws/{workspace_id}/{project_id}/{snapshot_id}/manifest.json",
        gcs_uri=None,
        changed_paths_count=1,
        neutral_outcome="succeeded",
    )


# ---------------------------------------------------------------------------
# Env wiring (the core bug being fixed)
# ---------------------------------------------------------------------------


def test_resolves_project_and_database_from_dedicated_envs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_PROJECT_FIRESTORE_PROJECT_ID", "fake-gcp-project")
    monkeypatch.setenv("HAM_PROJECT_FIRESTORE_DATABASE", "ham-workspaces")
    monkeypatch.delenv("HAM_PROJECT_SNAPSHOT_FIRESTORE_COLLECTION", raising=False)
    fs = FirestoreProjectSnapshotStore(client=_FakeFirestoreClient())
    assert fs._project == "fake-gcp-project"
    assert fs._database == "ham-workspaces"
    assert fs._coll_name == "ham_managed_project_snapshots"


def test_falls_back_to_shared_firestore_envs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_PROJECT_FIRESTORE_PROJECT_ID", raising=False)
    monkeypatch.delenv("HAM_PROJECT_FIRESTORE_DATABASE", raising=False)
    monkeypatch.setenv("HAM_FIRESTORE_PROJECT_ID", "shared-gcp")
    monkeypatch.setenv("HAM_FIRESTORE_DATABASE", "shared-db")
    fs = FirestoreProjectSnapshotStore(client=_FakeFirestoreClient())
    assert fs._project == "shared-gcp"
    assert fs._database == "shared-db"


def test_default_collection_when_no_collection_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HAM_PROJECT_SNAPSHOT_FIRESTORE_COLLECTION", raising=False)
    fs = FirestoreProjectSnapshotStore(client=_FakeFirestoreClient())
    assert fs._coll_name == "ham_managed_project_snapshots"


def test_collection_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "HAM_PROJECT_SNAPSHOT_FIRESTORE_COLLECTION", "ham_managed_project_snapshots_unit"
    )
    fs = FirestoreProjectSnapshotStore(client=_FakeFirestoreClient())
    assert fs._coll_name == "ham_managed_project_snapshots_unit"


def test_explicit_kwargs_take_precedence_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_PROJECT_FIRESTORE_PROJECT_ID", "env-gcp")
    monkeypatch.setenv("HAM_PROJECT_FIRESTORE_DATABASE", "env-db")
    fs = FirestoreProjectSnapshotStore(
        client=_FakeFirestoreClient(),
        project="kw-gcp",
        database="kw-db",
        collection="kw-coll",
    )
    assert fs._project == "kw-gcp"
    assert fs._database == "kw-db"
    assert fs._coll_name == "kw-coll"


# ---------------------------------------------------------------------------
# Behavior with fake client
# ---------------------------------------------------------------------------


def test_put_and_get_snapshot_round_trip() -> None:
    fc = _FakeFirestoreClient()
    fs = FirestoreProjectSnapshotStore(client=fc, collection="snaps_unit")
    row = _snapshot()
    fs.put_snapshot(row)
    got = fs.get_snapshot(row.project_id, row.snapshot_id)
    assert got is not None
    assert got.project_id == row.project_id
    assert got.snapshot_id == row.snapshot_id
    assert got.changed_paths_count == 1
    # Stored under the configured collection + correct doc id.
    assert "snaps_unit" in fc.docs
    assert f"{row.project_id}___{row.snapshot_id}" in fc.docs["snaps_unit"]


def test_list_snapshots_filters_by_project_id() -> None:
    fc = _FakeFirestoreClient()
    fs = FirestoreProjectSnapshotStore(client=fc)
    fs.put_snapshot(_snapshot(project_id="project.a", snapshot_id="s-1"))
    fs.put_snapshot(_snapshot(project_id="project.a", snapshot_id="s-2"))
    fs.put_snapshot(_snapshot(project_id="project.b", snapshot_id="s-3"))
    rows = fs.list_snapshots("project.a")
    assert sorted(r.snapshot_id for r in rows) == ["s-1", "s-2"]
    assert fs.list_snapshots("project.unknown") == []


def test_get_snapshot_missing_returns_none() -> None:
    fs = FirestoreProjectSnapshotStore(client=_FakeFirestoreClient())
    assert fs.get_snapshot("project.pilot", "no-such-snap") is None


def test_get_snapshot_malformed_doc_returns_none() -> None:
    """Malformed Firestore payloads must not crash read APIs (list_snapshots already skips)."""
    fc = _FakeFirestoreClient()
    fs = FirestoreProjectSnapshotStore(client=fc, collection="snaps_unit")
    doc_id = "project.pilot___snap-bad"
    fc.docs.setdefault("snaps_unit", {})[doc_id] = {
        "project_id": "project.pilot",
        "snapshot_id": "snap-bad",
        # Missing required fields / wrong types for ProjectSnapshot
        "created_at": "not-a-datetime",
    }
    assert fs.get_snapshot("project.pilot", "snap-bad") is None


def test_satisfies_protocol_shape() -> None:
    """`ProjectSnapshotStore` is a structural Protocol; verify method shape."""
    fs = FirestoreProjectSnapshotStore(client=_FakeFirestoreClient())
    for attr in ("put_snapshot", "list_snapshots", "get_snapshot"):
        assert callable(getattr(fs, attr, None)), f"missing {attr}"


# ---------------------------------------------------------------------------
# Backend selector (mirror existing project-store coverage)
# ---------------------------------------------------------------------------


def test_get_project_snapshot_store_defaults_to_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HAM_PROJECT_STORE_BACKEND", raising=False)
    set_project_snapshot_store_for_tests(None)
    try:
        store = get_project_snapshot_store()
        assert isinstance(store, MemoryProjectSnapshotStore)
    finally:
        set_project_snapshot_store_for_tests(None)


def test_get_project_snapshot_store_selects_firestore_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_PROJECT_STORE_BACKEND", "firestore")
    monkeypatch.setenv("HAM_PROJECT_FIRESTORE_PROJECT_ID", "fake-gcp")
    monkeypatch.setenv("HAM_PROJECT_FIRESTORE_DATABASE", "ham-workspaces")
    set_project_snapshot_store_for_tests(None)
    try:
        store = get_project_snapshot_store()
        assert isinstance(store, FirestoreProjectSnapshotStore)
        assert store._project == "fake-gcp"
        assert store._database == "ham-workspaces"
    finally:
        set_project_snapshot_store_for_tests(None)
