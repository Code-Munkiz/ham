"""Firestore-backed BuilderRuntimeStore — cross-instance preview runtime durability."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.builder_sources import router as builder_sources_router
from src.api.clerk_gate import get_ham_clerk_actor
from src.api.dependencies.workspace import get_workspace_store
from src.ham.clerk_auth import HamActor
from src.ham.workspace_models import WorkspaceMember, WorkspaceRecord
from src.persistence.builder_runtime_job_store import (
    BuilderRuntimeJobStore,
    CloudRuntimeJob,
    build_builder_runtime_job_store,
)
from src.persistence.builder_runtime_store import (
    BuilderRuntimeStore,
    PreviewEndpoint,
    RuntimeSession,
    build_builder_runtime_store,
    set_builder_runtime_store_for_tests,
)
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    ProjectSource,
    set_builder_source_store_for_tests,
)
from src.persistence.firestore_builder_runtime_store import FirestoreBuilderRuntimeStore
from src.persistence.firestore_builder_runtime_job_store import FirestoreBuilderRuntimeJobStore
from src.persistence.project_store import ProjectStore, set_project_store_for_tests
from src.persistence.workspace_store import InMemoryWorkspaceStore

_FORBIDDEN_TOKENS = (
    "gcp_gke_sandbox",
    "internal_upstream",
    "10.10.20.20",
    "kubernetes",
    "pod_name",
    "ham-preview-rtms",
)


class _FakeDocSnap:
    def __init__(self, data: dict[str, Any] | None, *, doc_id: str = "") -> None:
        self._data = data
        self.id = doc_id

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
        return _FakeDocSnap(self._bag.get(self._id), doc_id=self._id)


class _FakeCollection:
    def __init__(self, bag: dict[str, dict[str, Any]]) -> None:
        self._bag = bag

    def document(self, doc_id: str) -> _FakeDocRef:
        return _FakeDocRef(self._bag, doc_id)

    def stream(self):
        for doc_id, data in list(self._bag.items()):
            yield _FakeDocSnap(dict(data), doc_id=doc_id)


class _FakeFirestoreClient:
    def __init__(self) -> None:
        self.tree: dict[str, dict[str, dict[str, Any]]] = {}

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self.tree.setdefault(name, {}))


def _runtime_store(client: _FakeFirestoreClient) -> FirestoreBuilderRuntimeStore:
    return FirestoreBuilderRuntimeStore(
        client=client,
        sessions_collection="builder_runtime_sessions_test",
        preview_endpoints_collection="builder_preview_endpoints_test",
    )


def _job_store(client: _FakeFirestoreClient) -> FirestoreBuilderRuntimeJobStore:
    return FirestoreBuilderRuntimeJobStore(
        client=client,
        collection="builder_runtime_jobs_test",
    )


def test_file_store_cross_instance_reload(tmp_path) -> None:
    path = tmp_path / "builder_runtime.json"
    writer = BuilderRuntimeStore(store_path=path)
    runtime = writer.upsert_runtime_session(
        RuntimeSession(
            workspace_id="ws_a",
            project_id="project.a",
            mode="cloud",
            status="running",
        )
    )
    reader = BuilderRuntimeStore(store_path=path)
    loaded = reader.get_active_runtime_session(workspace_id="ws_a", project_id="project.a")
    assert loaded is not None
    assert loaded.id == runtime.id


def test_firestore_store_worker_writes_api_reads_runtime_session() -> None:
    """ham-api reader sees cloud runtime session written by worker writer."""
    client = _FakeFirestoreClient()
    worker_store = _runtime_store(client)
    api_store = _runtime_store(client)

    runtime = worker_store.request_cloud_runtime_session(
        workspace_id="ws_v2",
        project_id="proj_v2",
        source_snapshot_id="ssnp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        requested_by="worker",
        metadata={"cloud_runtime_job_id": "crjob_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
    )
    runtime.status = "running"
    runtime.health = "healthy"
    runtime.updated_at = runtime.updated_at
    worker_store.upsert_runtime_session(runtime)
    worker_store.upsert_preview_endpoint(
        PreviewEndpoint(
            workspace_id="ws_v2",
            project_id="proj_v2",
            runtime_session_id=runtime.id,
            access_mode="proxy",
            status="ready",
            url="http://10.105.129.73:3000/",
            metadata={"provider": "gcp_gke_sandbox", "internal_upstream": True},
        )
    )

    polled = api_store.get_active_runtime_session(workspace_id="ws_v2", project_id="proj_v2")
    assert polled is not None
    assert polled.status == "running"
    endpoint = api_store.get_active_preview_endpoint(
        workspace_id="ws_v2",
        project_id="proj_v2",
        runtime_session_id=runtime.id,
    )
    assert endpoint is not None
    assert endpoint.status == "ready"


def test_firestore_store_worker_writes_api_reads_cloud_runtime_job() -> None:
    client = _FakeFirestoreClient()
    worker_jobs = _job_store(client)
    api_jobs = _job_store(client)

    job = CloudRuntimeJob(
        workspace_id="ws_v2",
        project_id="proj_v2",
        source_snapshot_id="ssnp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        provider="gcp_gke_sandbox",
        status="completed",
        phase="completed",
    )
    worker_jobs.upsert_cloud_runtime_job(job)

    rows = api_jobs.list_cloud_runtime_jobs(workspace_id="ws_v2", project_id="proj_v2")
    assert len(rows) == 1
    assert rows[0].status == "completed"


def test_backend_selector_defaults_to_file(monkeypatch) -> None:
    monkeypatch.delenv("HAM_BUILDER_RUNTIME_STORE_BACKEND", raising=False)
    monkeypatch.delenv("HAM_BUILDER_SOURCE_STORE_BACKEND", raising=False)
    monkeypatch.delenv("HAM_BUILDER_RUNTIME_JOB_STORE_BACKEND", raising=False)
    monkeypatch.delenv("HAM_NATIVE_BUILD_CONTEXT_STORE_BACKEND", raising=False)
    assert isinstance(build_builder_runtime_store(), BuilderRuntimeStore)
    from src.persistence.builder_runtime_job_store import BuilderRuntimeJobStore as FileJobStore

    assert isinstance(build_builder_runtime_job_store(), FileJobStore)


def test_backend_selector_selects_firestore(monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_RUNTIME_STORE_BACKEND", "firestore")
    assert isinstance(build_builder_runtime_store(), FirestoreBuilderRuntimeStore)


def test_backend_selector_follows_source_firestore(monkeypatch) -> None:
    monkeypatch.delenv("HAM_BUILDER_RUNTIME_STORE_BACKEND", raising=False)
    monkeypatch.setenv("HAM_BUILDER_SOURCE_STORE_BACKEND", "firestore")
    assert isinstance(build_builder_runtime_store(), FirestoreBuilderRuntimeStore)
    assert isinstance(build_builder_runtime_job_store(), FirestoreBuilderRuntimeJobStore)


def test_backend_selector_follows_native_context_firestore(monkeypatch) -> None:
    monkeypatch.delenv("HAM_BUILDER_RUNTIME_STORE_BACKEND", raising=False)
    monkeypatch.delenv("HAM_BUILDER_SOURCE_STORE_BACKEND", raising=False)
    monkeypatch.delenv("HAM_BUILDER_RUNTIME_JOB_STORE_BACKEND", raising=False)
    monkeypatch.setenv("HAM_NATIVE_BUILD_CONTEXT_STORE_BACKEND", "firestore")
    assert isinstance(build_builder_runtime_store(), FirestoreBuilderRuntimeStore)
    assert isinstance(build_builder_runtime_job_store(), FirestoreBuilderRuntimeJobStore)


def test_runtime_session_payload_carries_no_internals() -> None:
    runtime = RuntimeSession(
        workspace_id="ws",
        project_id="proj",
        mode="cloud",
        status="running",
        metadata={"cloud_runtime_job_id": "crjob_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
    )
    blob = json.dumps(runtime.model_dump(mode="json")).lower()
    for token in _FORBIDDEN_TOKENS:
        assert token not in blob


def _actor(user_id: str, *, org_id: str | None) -> HamActor:
    return HamActor(
        user_id=user_id,
        org_id=org_id,
        session_id=f"sess_{user_id}",
        email=f"{user_id}@example.com",
        permissions=frozenset(),
        org_role="org:admin",
        raw_permission_claim=None,
    )


def _build_app(*, actor: HamActor, ws_store: InMemoryWorkspaceStore) -> FastAPI:
    app = FastAPI()
    app.include_router(builder_sources_router)

    async def _override_actor() -> HamActor:
        return actor

    app.dependency_overrides[get_ham_clerk_actor] = _override_actor
    app.dependency_overrides[get_workspace_store] = lambda: ws_store
    return app


def test_preview_status_ready_when_firestore_runtime_written_by_worker(tmp_path: Path) -> None:
    """preview-status on ham-api returns ready when worker shared Firestore has proxy endpoint."""
    from datetime import UTC, datetime

    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    now = datetime.now(UTC)
    ws_store.create_workspace(
        WorkspaceRecord(
            workspace_id=ws_id,
            org_id="org_a",
            owner_user_id="user_a",
            name="alpha",
            slug="alpha",
            description="",
            status="active",
            created_by="user_a",
            created_at=now,
            updated_at=now,
        )
    )
    ws_store.upsert_member(
        WorkspaceMember(
            workspace_id=ws_id,
            user_id="user_a",
            role="owner",
            added_by="user_a",
            added_at=now,
        )
    )
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(
        name="proj-a",
        root=str(tmp_path),
        metadata={"workspace_id": ws_id},
    )
    project_store.register(project)
    set_project_store_for_tests(project_store)

    builder_store = BuilderSourceStore(store_path=tmp_path / "builder_sources.json")
    src = builder_store.upsert_project_source(
        ProjectSource(workspace_id=ws_id, project_id=project.id, kind="chat_scaffold"),
    )
    src.active_snapshot_id = "ssnp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    builder_store.upsert_project_source(src)
    set_builder_source_store_for_tests(builder_store)

    client_fs = _FakeFirestoreClient()
    worker_store = _runtime_store(client_fs)
    runtime = worker_store.upsert_runtime_session(
        RuntimeSession(
            workspace_id=ws_id,
            project_id=project.id,
            mode="cloud",
            status="running",
            health="healthy",
            snapshot_id=src.active_snapshot_id,
        )
    )
    worker_store.upsert_preview_endpoint(
        PreviewEndpoint(
            workspace_id=ws_id,
            project_id=project.id,
            runtime_session_id=runtime.id,
            access_mode="proxy",
            status="ready",
            url="http://10.105.129.73:3000/",
            metadata={"provider": "gcp_gke_sandbox", "internal_upstream": True},
        )
    )
    set_builder_runtime_store_for_tests(worker_store)

    api_client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    res = api_client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/preview-status")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "ready"
    assert body["preview_url"] == f"/api/workspaces/{ws_id}/projects/{project.id}/builder/preview-proxy/"
    assert "10.105.129.73" not in json.dumps(body)

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)
