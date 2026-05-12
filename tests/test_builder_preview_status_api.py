from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
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
    ProjectSource,
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


def test_preview_status_active_snapshot_cloud_not_configured_copy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "cloud_run_poc")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "false")
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)
    builder_store = BuilderSourceStore(store_path=tmp_path / "builder_sources.json")
    src = builder_store.upsert_project_source(
        ProjectSource(workspace_id=ws_id, project_id=project.id, kind="chat_scaffold"),
    )
    snap = builder_store.upsert_source_snapshot(
        SourceSnapshot(
            workspace_id=ws_id,
            project_id=project.id,
            project_source_id=src.id,
            artifact_uri="builder-artifact://bzip_test",
            digest_sha256="a" * 64,
        ),
    )
    src.active_snapshot_id = snap.id
    builder_store.upsert_project_source(src)
    set_builder_source_store_for_tests(builder_store)
    set_builder_runtime_store_for_tests(BuilderRuntimeStore(store_path=tmp_path / "builder_runtime.json"))

    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/preview-status")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "cloud"
    assert body["status"] == "waiting"
    assert "not configured" in body["message"].lower()
    assert body["preview_url"] is None

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_preview_status_active_snapshot_preparing_when_cloud_experiments_ready(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "cloud_run_poc")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT", "proj-safe")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION", "us-central1")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_DRY_RUN", "true")
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)
    builder_store = BuilderSourceStore(store_path=tmp_path / "builder_sources.json")
    src = builder_store.upsert_project_source(
        ProjectSource(workspace_id=ws_id, project_id=project.id, kind="chat_scaffold"),
    )
    snap = builder_store.upsert_source_snapshot(
        SourceSnapshot(
            workspace_id=ws_id,
            project_id=project.id,
            project_source_id=src.id,
            artifact_uri="builder-artifact://bzip_test",
            digest_sha256="a" * 64,
        ),
    )
    src.active_snapshot_id = snap.id
    builder_store.upsert_project_source(src)
    set_builder_source_store_for_tests(builder_store)
    set_builder_runtime_store_for_tests(BuilderRuntimeStore(store_path=tmp_path / "builder_runtime.json"))

    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/preview-status")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "cloud"
    assert body["status"] == "building"
    assert "preparing" in body["message"].lower()

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


def _seed_project_context(tmp_path: Path) -> tuple[InMemoryWorkspaceStore, str, ProjectStore, str]:
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))
    set_builder_runtime_store_for_tests(BuilderRuntimeStore(store_path=tmp_path / "builder_runtime.json"))
    return ws_store, ws_id, project_store, project.id


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://[::1]:3000",
    ],
)
def test_register_local_preview_accepts_safe_loopback_urls(tmp_path: Path, url: str) -> None:
    ws_store, ws_id, _, project_id = _seed_project_context(tmp_path)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-preview",
        json={"preview_url": url},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["preview_status"]["status"] == "ready"
    assert body["preview_status"]["preview_url"].startswith("http://")

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "file:///tmp/index.html",
        "javascript:alert(1)",
        "http://user:pass@localhost:3000",
        "http://localhost",
    ],
)
def test_register_local_preview_rejects_unsafe_urls(tmp_path: Path, url: str) -> None:
    ws_store, ws_id, _, project_id = _seed_project_context(tmp_path)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-preview",
        json={"preview_url": url},
    )
    assert res.status_code == 400
    assert res.json()["detail"]["error"]["code"] == "LOCAL_PREVIEW_URL_INVALID"

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_register_local_preview_strips_query_and_fragment(tmp_path: Path) -> None:
    ws_store, ws_id, _, project_id = _seed_project_context(tmp_path)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-preview",
        json={"preview_url": "http://localhost:3000/path?token=secret#frag"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["preview_status"]["preview_url"] == "http://localhost:3000/path"

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_clear_local_preview_returns_not_connected(tmp_path: Path) -> None:
    ws_store, ws_id, _, project_id = _seed_project_context(tmp_path)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    reg = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-preview",
        json={"preview_url": "http://localhost:3000"},
    )
    assert reg.status_code == 200
    clear = client.delete(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-preview")
    assert clear.status_code == 200, clear.text
    assert clear.json()["preview_status"]["status"] == "not_connected"
    assert clear.json()["preview_status"]["preview_url"] is None

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_preview_status_ready_after_registration(tmp_path: Path) -> None:
    ws_store, ws_id, _, project_id = _seed_project_context(tmp_path)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    reg = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-preview",
        json={"preview_url": "http://127.0.0.1:3000"},
    )
    assert reg.status_code == 200
    status_res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-status")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "ready"
    assert status_res.json()["preview_url"] == "http://127.0.0.1:3000/"

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_preview_status_cloud_proxy_ready_returns_ham_proxy_url(tmp_path: Path) -> None:
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
            mode="cloud",
            status="running",
            health="unknown",
        )
    )
    runtime_store.upsert_preview_endpoint(
        PreviewEndpoint(
            workspace_id=ws_id,
            project_id=project.id,
            runtime_session_id=runtime.id,
            access_mode="proxy",
            status="ready",
            url="https://ham-preview-123.run.app/",
            metadata={"trusted_proxy_host": "ham-preview-123.run.app"},
        )
    )
    set_builder_runtime_store_for_tests(runtime_store)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/preview-status")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "cloud"
    assert body["status"] == "ready"
    assert body["preview_url"] == f"/api/workspaces/{ws_id}/projects/{project.id}/builder/preview-proxy/"
    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_register_local_preview_scope_enforced(tmp_path: Path) -> None:
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
    set_builder_runtime_store_for_tests(BuilderRuntimeStore(store_path=tmp_path / "builder_runtime.json"))
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    forbidden = client.post(
        f"/api/workspaces/{ws_b}/projects/{p_b.id}/builder/local-preview",
        json={"preview_url": "http://localhost:3000"},
    )
    wrong_project_workspace = client.post(
        f"/api/workspaces/{ws_a}/projects/{p_b.id}/builder/local-preview",
        json={"preview_url": "http://localhost:3000"},
    )
    ok = client.post(
        f"/api/workspaces/{ws_a}/projects/{p_a.id}/builder/local-preview",
        json={"preview_url": "http://localhost:3000"},
    )
    assert forbidden.status_code == 403
    assert wrong_project_workspace.status_code == 404
    assert ok.status_code == 200

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_cloud_runtime_get_returns_experiment_not_enabled_by_default(tmp_path: Path) -> None:
    ws_store, ws_id, _, project_id = _seed_project_context(tmp_path)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "cloud"
    assert body["status"] == "experiment_not_enabled"
    assert body["runtime_session_id"] is None
    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_cloud_runtime_request_tracks_state_without_execution(tmp_path: Path, monkeypatch) -> None:
    import subprocess

    ws_store, ws_id, _, project_id = _seed_project_context(tmp_path)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))

    def _boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("cloud runtime stub must not execute processes")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    post = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/request",
        json={"status": "provisioning", "metadata": {"note": "queued request"}},
    )
    assert post.status_code == 200, post.text
    assert post.json()["cloud_runtime"]["status"] == "provider_ready"
    get = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime")
    assert get.status_code == 200, get.text
    assert get.json()["status"] == "provider_ready"
    assert get.json()["runtime_session_id"]
    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_cloud_runtime_get_returns_config_missing_for_cloud_provider_without_required_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "cloud_run_poc")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_ENABLED", "true")
    monkeypatch.delenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT", raising=False)
    monkeypatch.delenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION", raising=False)
    ws_store, ws_id, _, project_id = _seed_project_context(tmp_path)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "config_missing"
    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_cloud_runtime_get_returns_dry_run_ready_when_experiment_configured(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "cloud_run_poc")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT", "proj-safe")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION", "us-central1")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_DRY_RUN", "true")
    ws_store, ws_id, _, project_id = _seed_project_context(tmp_path)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "dry_run_ready"
    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_cloud_runtime_delete_marks_stub_expired(tmp_path: Path) -> None:
    ws_store, ws_id, _, project_id = _seed_project_context(tmp_path)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    reg = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/request",
        json={"status": "running"},
    )
    assert reg.status_code == 200, reg.text
    delete = client.delete(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime")
    assert delete.status_code == 200, delete.text
    assert delete.json()["cloud_runtime"]["status"] == "expired"
    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_cloud_runtime_scope_enforced(tmp_path: Path) -> None:
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
    set_builder_runtime_store_for_tests(BuilderRuntimeStore(store_path=tmp_path / "builder_runtime.json"))
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    forbidden = client.get(f"/api/workspaces/{ws_b}/projects/{p_b.id}/builder/cloud-runtime")
    wrong_project_workspace = client.get(f"/api/workspaces/{ws_a}/projects/{p_b.id}/builder/cloud-runtime")
    assert forbidden.status_code == 403
    assert wrong_project_workspace.status_code == 404
    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)
