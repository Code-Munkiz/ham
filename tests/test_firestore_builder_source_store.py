"""Firestore-backed BuilderSourceStore — cross-instance import job durability.

Mirrors :class:`test_native_build_context_store` patterns: file-backed fallback
for local/dev, Firestore for hosted split ham-api / worker deployments.
"""

from __future__ import annotations

import json
from typing import Any

from src.persistence.builder_source_store import (
    BuilderSourceStore,
    ImportJob,
    ProjectSource,
    SourceSnapshot,
    build_builder_source_store,
)
from src.persistence.firestore_builder_source_store import FirestoreBuilderSourceStore

_FORBIDDEN_TOKENS = (
    "registry_v2",
    "proposal_digest",
    "base_revision",
    "hermes_native_build",
    "inline_files",
    "hermes-builder",
    "hermes_gateway",
    "openrouter",
)


class _FakeDocSnap:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data) if self._data is not None else {}


class _FakeDocRef:
    def __init__(self, bag: dict[str, dict[str, Any]], doc_id: str) -> None:
        self._bag = bag
        self._id = doc_id

    def set(self, payload: dict[str, Any]) -> None:
        self._bag[self._id] = dict(payload)

    def get(self) -> _FakeDocSnap:
        return _FakeDocSnap(self._bag.get(self._id))


class _FakeCollection:
    def __init__(self, bag: dict[str, dict[str, Any]]) -> None:
        self._bag = bag

    def document(self, doc_id: str) -> _FakeDocRef:
        return _FakeDocRef(self._bag, doc_id)

    def stream(self):
        for doc_id, data in list(self._bag.items()):
            snap = _FakeDocSnap(dict(data))
            snap.id = doc_id  # type: ignore[attr-defined]
            yield snap


class _FakeFirestoreClient:
    def __init__(self) -> None:
        self.tree: dict[str, dict[str, dict[str, Any]]] = {}

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self.tree.setdefault(name, {}))


def _api_store(client: _FakeFirestoreClient) -> FirestoreBuilderSourceStore:
    return FirestoreBuilderSourceStore(
        client=client,
        import_jobs_collection="builder_import_jobs_test",
        project_sources_collection="builder_project_sources_test",
        source_snapshots_collection="builder_source_snapshots_test",
    )


def test_file_store_cross_instance_reload(tmp_path) -> None:
    path = tmp_path / "builder_sources.json"
    writer = BuilderSourceStore(store_path=path)
    created = writer.create_import_job(
        workspace_id="ws_a",
        project_id="project.a",
        created_by="user",
        phase="received",
        status="queued",
    )

    reader = BuilderSourceStore(store_path=path)
    loaded = reader.get_import_job(import_job_id=created.id)
    assert loaded is not None
    assert loaded.status == "queued"


def test_firestore_store_create_then_get_by_id() -> None:
    store = _api_store(_FakeFirestoreClient())
    created = store.create_import_job(
        workspace_id="ws_a",
        project_id="project.a",
        created_by="user",
        phase="received",
        status="queued",
    )
    loaded = store.get_import_job(import_job_id=created.id)
    assert loaded is not None
    assert loaded.id == created.id


def test_firestore_store_cross_instance_import_job_lifecycle() -> None:
    """ham-api writer and worker reader share import job state via Firestore."""
    client = _FakeFirestoreClient()
    api_store = _api_store(client)
    worker_store = _api_store(client)

    created = api_store.create_import_job(
        workspace_id="ws_v2",
        project_id="proj_v2",
        created_by="user_v2",
        phase="queued",
        status="queued",
    )

    running = worker_store.mark_import_job_running(
        import_job_id=created.id,
        phase="generating",
    )
    assert running.status == "running"

    succeeded = worker_store.mark_import_job_succeeded(
        import_job_id=created.id,
        phase="materialized",
        source_snapshot_id="ssnp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        stats={"file_count": 2},
    )
    assert succeeded.status == "succeeded"

    polled = api_store.get_import_job(import_job_id=created.id)
    assert polled is not None
    assert polled.status == "succeeded"
    assert polled.stats["file_count"] == 2


def test_firestore_store_list_import_jobs_filters_workspace_project() -> None:
    client = _FakeFirestoreClient()
    store = _api_store(client)
    store.create_import_job(
        workspace_id="ws_a",
        project_id="project.a",
        created_by="user",
        phase="received",
        status="queued",
    )
    store.create_import_job(
        workspace_id="ws_b",
        project_id="project.b",
        created_by="user",
        phase="received",
        status="queued",
    )
    rows = store.list_import_jobs(workspace_id="ws_a", project_id="project.a")
    assert len(rows) == 1
    assert rows[0].workspace_id == "ws_a"


def test_firestore_store_upsert_project_source_and_snapshot_round_trip() -> None:
    client = _FakeFirestoreClient()
    api_store = _api_store(client)
    worker_store = _api_store(client)

    source = ProjectSource(
        id="psrc_11111111111111111111111111111111",
        workspace_id="ws_a",
        project_id="project.a",
        display_name="native source",
    )
    api_store.upsert_project_source(source)

    snapshot = SourceSnapshot(
        id="ssnp_22222222222222222222222222222222",
        workspace_id="ws_a",
        project_id="project.a",
        project_source_id=source.id,
        manifest={"kind": "inline_text_bundle", "file_count": 1},
    )
    worker_store.upsert_source_snapshot(snapshot)

    sources = api_store.list_project_sources(workspace_id="ws_a", project_id="project.a")
    snaps = api_store.list_source_snapshots(workspace_id="ws_a", project_id="project.a")
    assert [row.id for row in sources] == [source.id]
    assert [row.id for row in snaps] == [snapshot.id]


def test_backend_selector_defaults_to_file(monkeypatch) -> None:
    monkeypatch.delenv("HAM_BUILDER_SOURCE_STORE_BACKEND", raising=False)
    assert isinstance(build_builder_source_store(), BuilderSourceStore)


def test_backend_selector_selects_firestore(monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_STORE_BACKEND", "firestore")
    assert isinstance(build_builder_source_store(), FirestoreBuilderSourceStore)


def test_backend_selector_follows_native_context_firestore(monkeypatch) -> None:
    monkeypatch.delenv("HAM_BUILDER_SOURCE_STORE_BACKEND", raising=False)
    monkeypatch.setenv("HAM_NATIVE_BUILD_CONTEXT_STORE_BACKEND", "firestore")
    assert isinstance(build_builder_source_store(), FirestoreBuilderSourceStore)


def test_import_job_payload_carries_no_internals() -> None:
    job = ImportJob(workspace_id="ws", project_id="proj", phase="queued", status="queued")
    payload = json.dumps(job.model_dump(mode="json")).lower()
    for token in _FORBIDDEN_TOKENS:
        assert token not in payload
