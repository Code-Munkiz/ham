from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.builder_sources import router as builder_sources_router
from src.api.clerk_gate import get_ham_clerk_actor
from src.api.dependencies.workspace import get_workspace_store
from src.ham.clerk_auth import HamActor
from src.ham.workspace_models import WorkspaceMember, WorkspaceRecord
from src.persistence.builder_runtime_store import (
    BuilderRuntimeStore,
    PreviewEndpoint,
    RuntimeSession,
    set_builder_runtime_store_for_tests,
)
from src.persistence.builder_source_store import BuilderSourceStore, set_builder_source_store_for_tests
from src.persistence.project_store import ProjectStore, set_project_store_for_tests
from src.persistence.workspace_store import InMemoryWorkspaceStore


def _actor(user_id: str, *, org_id: str | None, org_role: str | None = "org:admin") -> HamActor:
    return HamActor(
        user_id=user_id,
        org_id=org_id,
        session_id=f"sess_{user_id}",
        email=f"{user_id}@example.com",
        permissions=frozenset(),
        org_role=org_role,
        raw_permission_claim=None,
    )


def _build_app(*, actor: HamActor | None, ws_store: InMemoryWorkspaceStore) -> FastAPI:
    app = FastAPI()
    app.include_router(builder_sources_router)

    async def _override_actor() -> HamActor | None:
        return actor

    def _override_workspace_store() -> InMemoryWorkspaceStore:
        return ws_store

    app.dependency_overrides[get_ham_clerk_actor] = _override_actor
    app.dependency_overrides[get_workspace_store] = _override_workspace_store
    return app


def _seed_workspace(
    store: InMemoryWorkspaceStore,
    *,
    workspace_id: str,
    org_id: str | None,
    owner_user_id: str,
    slug: str,
) -> None:
    now = datetime.now(UTC)
    store.create_workspace(
        WorkspaceRecord(
            workspace_id=workspace_id,
            org_id=org_id,
            owner_user_id=owner_user_id,
            name=slug,
            slug=slug,
            description="",
            status="active",
            created_by=owner_user_id,
            created_at=now,
            updated_at=now,
        )
    )
    store.upsert_member(
        WorkspaceMember(
            workspace_id=workspace_id,
            user_id=owner_user_id,
            role="owner",
            added_by=owner_user_id,
            added_at=now,
        )
    )


def test_preview_status_no_runtime_returns_not_connected(tmp_path: Path) -> None:
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))
    set_builder_runtime_store_for_tests(BuilderRuntimeStore(store_path=tmp_path / "builder_runtime.json"))

    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/preview-status")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "not_connected"
    assert body["preview_url"] is None
    assert body["runtime_session_id"] is None

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_preview_status_ready_runtime_returns_safe_local_url(tmp_path: Path) -> None:
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))
    runtime_store = BuilderRuntimeStore(store_path=tmp_path / "builder_runtime.json")
    runtime = runtime_store.upsert_runtime_session(
        RuntimeSession(
            workspace_id=ws_id,
            project_id=project.id,
            status="running",
            health="healthy",
        )
    )
    runtime_store.upsert_preview_endpoint(
        PreviewEndpoint(
            workspace_id=ws_id,
            project_id=project.id,
            runtime_session_id=runtime.id,
            status="ready",
            url="http://localhost:4173?token=secret",
        )
    )
    set_builder_runtime_store_for_tests(runtime_store)

    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/preview-status")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "ready"
    assert body["preview_url"] == "http://localhost:4173/"

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_preview_status_unsafe_url_not_returned_as_ready(tmp_path: Path) -> None:
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))
    runtime_store = BuilderRuntimeStore(store_path=tmp_path / "builder_runtime.json")
    runtime = runtime_store.upsert_runtime_session(
        RuntimeSession(
            workspace_id=ws_id,
            project_id=project.id,
            status="running",
            health="healthy",
        )
    )
    runtime_store.upsert_preview_endpoint(
        PreviewEndpoint(
            workspace_id=ws_id,
            project_id=project.id,
            runtime_session_id=runtime.id,
            status="ready",
            url="https://evil.example.com/app",
        )
    )
    set_builder_runtime_store_for_tests(runtime_store)

    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/preview-status")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "error"
    assert body["preview_url"] is None

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_preview_status_failed_runtime_reports_error(tmp_path: Path) -> None:
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))
    runtime_store = BuilderRuntimeStore(store_path=tmp_path / "builder_runtime.json")
    runtime_store.upsert_runtime_session(
        RuntimeSession(
            workspace_id=ws_id,
            project_id=project.id,
            status="failed",
            health="unhealthy",
        )
    )
    set_builder_runtime_store_for_tests(runtime_store)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/preview-status")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "error"

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_preview_status_workspace_scope_enforced_and_no_cross_project_leak(tmp_path: Path) -> None:
    ws_store = InMemoryWorkspaceStore()
    ws_a = "ws_aaaaaaaaaaaaaaaa"
    ws_b = "ws_bbbbbbbbbbbbbbbb"
    _seed_workspace(ws_store, workspace_id=ws_a, org_id="org_a", owner_user_id="user_a", slug="alpha")
    _seed_workspace(ws_store, workspace_id=ws_b, org_id="org_b", owner_user_id="user_b", slug="beta")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    p_a = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_a})
    p_b = project_store.make_record(name="proj-b", root=str(tmp_path), metadata={"workspace_id": ws_b})
    project_store.register(p_a)
    project_store.register(p_b)
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))
    runtime_store = BuilderRuntimeStore(store_path=tmp_path / "builder_runtime.json")
    runtime_store.upsert_runtime_session(
        RuntimeSession(
            workspace_id=ws_b,
            project_id=p_b.id,
            status="running",
            health="healthy",
        )
    )
    set_builder_runtime_store_for_tests(runtime_store)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    forbidden = client.get(f"/api/workspaces/{ws_b}/projects/{p_b.id}/builder/preview-status")
    wrong_project_workspace = client.get(f"/api/workspaces/{ws_a}/projects/{p_b.id}/builder/preview-status")
    ok = client.get(f"/api/workspaces/{ws_a}/projects/{p_a.id}/builder/preview-status")
    assert forbidden.status_code == 403
    assert wrong_project_workspace.status_code == 404
    assert ok.status_code == 200
    assert ok.json()["runtime_session_id"] is None

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_preview_status_requires_session_when_auth_enforced(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.delenv("HAM_LOCAL_DEV_WORKSPACE_BYPASS", raising=False)
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))
    set_builder_runtime_store_for_tests(BuilderRuntimeStore(store_path=tmp_path / "builder_runtime.json"))
    client = TestClient(_build_app(actor=None, ws_store=ws_store))
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/preview-status")
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)
