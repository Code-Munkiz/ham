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
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    ProjectSource,
    set_builder_source_store_for_tests,
)
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


def test_builder_sources_lists_empty_arrays_and_shapes(tmp_path: Path) -> None:
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(
        ws_store,
        workspace_id=ws_id,
        org_id="org_a",
        owner_user_id="user_a",
        slug="alpha",
    )

    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(
        name="alpha-project",
        root=str(tmp_path),
        metadata={"workspace_id": ws_id},
    )
    project_store.register(project)
    set_project_store_for_tests(project_store)

    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))
    app = _build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store)
    client = TestClient(app)

    sources_res = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/sources")
    snapshots_res = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/source-snapshots")
    jobs_res = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/import-jobs")

    assert sources_res.status_code == 200, sources_res.text
    assert snapshots_res.status_code == 200, snapshots_res.text
    assert jobs_res.status_code == 200, jobs_res.text

    assert sources_res.json() == {"project_id": project.id, "workspace_id": ws_id, "sources": []}
    assert snapshots_res.json() == {
        "project_id": project.id,
        "workspace_id": ws_id,
        "source_snapshots": [],
    }
    assert jobs_res.json() == {"project_id": project.id, "workspace_id": ws_id, "import_jobs": []}

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)


def test_builder_sources_workspace_project_scope_enforced(tmp_path: Path) -> None:
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

    builder_store = BuilderSourceStore(store_path=tmp_path / "builder_sources.json")
    builder_store.upsert_project_source(
        ProjectSource(
            id="psrc_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            workspace_id=ws_a,
            project_id=p_a.id,
            display_name="seed",
        )
    )
    set_builder_source_store_for_tests(builder_store)

    app = _build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store)
    client = TestClient(app)

    ok = client.get(f"/api/workspaces/{ws_a}/projects/{p_a.id}/builder/sources")
    wrong_project_workspace = client.get(f"/api/workspaces/{ws_a}/projects/{p_b.id}/builder/sources")
    forbidden_workspace = client.get(f"/api/workspaces/{ws_b}/projects/{p_b.id}/builder/sources")

    assert ok.status_code == 200, ok.text
    assert len(ok.json()["sources"]) == 1
    assert wrong_project_workspace.status_code == 404
    assert wrong_project_workspace.json()["detail"]["error"]["code"] == "PROJECT_NOT_FOUND"
    assert forbidden_workspace.status_code == 403
    assert forbidden_workspace.json()["detail"]["error"]["code"] == "HAM_WORKSPACE_FORBIDDEN"

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)


def test_builder_sources_requires_session_when_auth_enforced(
    tmp_path: Path,
    monkeypatch,
) -> None:
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

    app = _build_app(actor=None, ws_store=ws_store)
    client = TestClient(app)
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/sources")
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
