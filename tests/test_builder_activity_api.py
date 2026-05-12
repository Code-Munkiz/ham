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
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    ImportJob,
    SourceSnapshot,
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


def _seed_context(tmp_path: Path) -> tuple[TestClient, str, str]:
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
    return client, ws_id, project.id


def _cleanup() -> None:
    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_activity_empty_returns_items_empty(tmp_path: Path) -> None:
    client, ws_id, project_id = _seed_context(tmp_path)
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/activity")
    assert res.status_code == 200
    assert res.json()["items"] == []
    _cleanup()


def test_activity_includes_import_job_and_snapshot_records(tmp_path: Path) -> None:
    client, ws_id, project_id = _seed_context(tmp_path)
    store = BuilderSourceStore(store_path=tmp_path / "builder_sources.json")
    job = store.upsert_import_job(
        ImportJob(
            workspace_id=ws_id,
            project_id=project_id,
            status="succeeded",
            phase="materialized",
            stats={"file_count": 2},
        )
    )
    store.upsert_source_snapshot(
        SourceSnapshot(
            workspace_id=ws_id,
            project_id=project_id,
            project_source_id="psrc_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            status="materialized",
            size_bytes=123,
        )
    )
    set_builder_source_store_for_tests(store)
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/activity")
    assert res.status_code == 200
    kinds = [row["kind"] for row in res.json()["items"]]
    assert "source_import" in kinds
    assert "source_snapshot" in kinds
    import_item = next(row for row in res.json()["items"] if row.get("import_job_id") == job.id)
    assert import_item["status"] == "succeeded"
    _cleanup()


def test_activity_failed_import_uses_safe_error_copy(tmp_path: Path) -> None:
    client, ws_id, project_id = _seed_context(tmp_path)
    store = BuilderSourceStore(store_path=tmp_path / "builder_sources.json")
    store.upsert_import_job(
        ImportJob(
            workspace_id=ws_id,
            project_id=project_id,
            status="failed",
            phase="failed",
            error_message="token=abc123 secret failed at C:\\Users\\aaron\\project",
        )
    )
    set_builder_source_store_for_tests(store)
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/activity")
    assert res.status_code == 200
    item = next(row for row in res.json()["items"] if row["kind"] == "source_import")
    assert item["message"] == "Source import failed."
    _cleanup()


def test_activity_includes_preview_connect_and_disconnect(tmp_path: Path) -> None:
    client, ws_id, project_id = _seed_context(tmp_path)
    register = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-preview",
        json={"preview_url": "http://localhost:5173"},
    )
    assert register.status_code == 200
    after_connect = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/activity")
    assert after_connect.status_code == 200
    assert any(row["kind"] == "preview_connected" for row in after_connect.json()["items"])
    clear = client.delete(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-preview")
    assert clear.status_code == 200
    after_clear = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/activity")
    assert after_clear.status_code == 200
    assert any(row["kind"] == "preview_disconnected" for row in after_clear.json()["items"])
    _cleanup()


def test_activity_scope_enforced_and_no_cross_project_leakage(tmp_path: Path) -> None:
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
    source_store = BuilderSourceStore(store_path=tmp_path / "builder_sources.json")
    source_store.upsert_import_job(ImportJob(workspace_id=ws_b, project_id=p_b.id, status="queued"))
    set_builder_source_store_for_tests(source_store)
    runtime_store = BuilderRuntimeStore(store_path=tmp_path / "builder_runtime.json")
    runtime_store.upsert_runtime_session(RuntimeSession(workspace_id=ws_b, project_id=p_b.id, status="running"))
    set_builder_runtime_store_for_tests(runtime_store)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    forbidden = client.get(f"/api/workspaces/{ws_b}/projects/{p_b.id}/builder/activity")
    wrong_project_workspace = client.get(f"/api/workspaces/{ws_a}/projects/{p_b.id}/builder/activity")
    ok = client.get(f"/api/workspaces/{ws_a}/projects/{p_a.id}/builder/activity")
    assert forbidden.status_code == 403
    assert wrong_project_workspace.status_code == 404
    assert ok.status_code == 200
    assert ok.json()["items"] == []
    _cleanup()


def test_activity_ordering_newest_first(tmp_path: Path) -> None:
    client, ws_id, project_id = _seed_context(tmp_path)
    runtime_store = BuilderRuntimeStore(store_path=tmp_path / "builder_runtime.json")
    old_runtime = runtime_store.upsert_runtime_session(
        RuntimeSession(
            workspace_id=ws_id,
            project_id=project_id,
            status="running",
            updated_at="2026-01-01T00:00:00Z",
            message="older event",
        )
    )
    runtime_store.upsert_preview_endpoint(
        PreviewEndpoint(
            workspace_id=ws_id,
            project_id=project_id,
            runtime_session_id=old_runtime.id,
            status="ready",
            url="http://localhost:3000",
            last_checked_at="2026-01-02T00:00:00Z",
        )
    )
    set_builder_runtime_store_for_tests(runtime_store)
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/activity")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) >= 2
    assert items[0]["timestamp"] >= items[1]["timestamp"]
    _cleanup()
