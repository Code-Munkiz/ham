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
from src.persistence.builder_runtime_job_store import (
    BuilderRuntimeJobStore,
    CloudRuntimeJob,
    set_builder_runtime_job_store_for_tests,
)
from src.persistence.builder_runtime_store import BuilderRuntimeStore, set_builder_runtime_store_for_tests
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    ProjectSource,
    SourceSnapshot,
    set_builder_source_store_for_tests,
)
from src.persistence.builder_usage_event_store import (
    BuilderUsageEventStore,
    set_builder_usage_event_store_for_tests,
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
    set_builder_runtime_job_store_for_tests(
        BuilderRuntimeJobStore(store_path=tmp_path / "builder_runtime_jobs.json")
    )
    set_builder_usage_event_store_for_tests(
        BuilderUsageEventStore(store_path=tmp_path / "builder_usage_events.json")
    )
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    return client, ws_id, project.id


def _cleanup() -> None:
    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)
    set_builder_runtime_job_store_for_tests(None)
    set_builder_usage_event_store_for_tests(None)


def test_post_job_disabled_provider_returns_unsupported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "disabled")
    client, ws_id, project_id = _seed_context(tmp_path)
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
        json={},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["job"]["status"] == "unsupported"
    assert body["job"]["provider"] == "disabled"
    assert body["cloud_runtime"]["status"] == "unsupported"
    _cleanup()


def test_post_job_local_mock_completes_safely_without_preview_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "local_mock")
    client, ws_id, project_id = _seed_context(tmp_path)
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
        json={},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["job"]["status"] == "succeeded"
    assert body["job"]["phase"] == "completed"
    assert body["job"]["runtime_session_id"]
    assert body["runtime_session"] is not None
    assert body["preview_status"]["preview_url"] is None
    assert body["cloud_runtime"]["status"] == "running"
    _cleanup()


def test_post_job_rejects_snapshot_from_other_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "local_mock")
    client, ws_id, project_id = _seed_context(tmp_path)
    source_store = BuilderSourceStore(store_path=tmp_path / "builder_sources.json")
    other_project = "project.other"
    source = source_store.upsert_project_source(
        ProjectSource(workspace_id=ws_id, project_id=other_project, kind="zip_upload")
    )
    snapshot = source_store.upsert_source_snapshot(
        SourceSnapshot(
            workspace_id=ws_id,
            project_id=other_project,
            project_source_id=source.id,
        )
    )
    set_builder_source_store_for_tests(source_store)
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
        json={"source_snapshot_id": snapshot.id},
    )
    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "SOURCE_SNAPSHOT_NOT_FOUND"
    _cleanup()


def test_list_and_get_jobs_are_scoped_and_sorted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "disabled")
    client, ws_id, project_id = _seed_context(tmp_path)
    job_store = BuilderRuntimeJobStore(store_path=tmp_path / "builder_runtime_jobs.json")
    first = job_store.upsert_cloud_runtime_job(
        CloudRuntimeJob(workspace_id=ws_id, project_id=project_id, status="queued", phase="received")
    )
    second = job_store.upsert_cloud_runtime_job(
        CloudRuntimeJob(workspace_id=ws_id, project_id=project_id, status="failed", phase="failed")
    )
    # Make ordering deterministic even when jobs are created in the same second.
    first.updated_at = "2026-01-01T00:00:00Z"
    second.updated_at = "2026-01-01T00:00:01Z"
    job_store.upsert_cloud_runtime_job(first)
    job_store.upsert_cloud_runtime_job(second)
    set_builder_runtime_job_store_for_tests(job_store)
    listed = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs")
    assert listed.status_code == 200
    rows = listed.json()["jobs"]
    assert rows[0]["id"] == second.id
    detail = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs/{first.id}")
    assert detail.status_code == 200
    assert detail.json()["job"]["id"] == first.id
    _cleanup()


def test_get_job_not_found_returns_404(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "disabled")
    client, ws_id, project_id = _seed_context(tmp_path)
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs/crjb_missing")
    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "CLOUD_RUNTIME_JOB_NOT_FOUND"
    _cleanup()


def test_post_job_does_not_execute_shell_or_processes(tmp_path: Path, monkeypatch) -> None:
    import subprocess

    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "local_mock")

    def _boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("Cloud runtime jobs must not execute shell commands")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    client, ws_id, project_id = _seed_context(tmp_path)
    res = client.post(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs", json={})
    assert res.status_code == 200, res.text
    assert res.json()["job"]["status"] == "succeeded"
    _cleanup()


def test_activity_includes_cloud_runtime_job_item(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "local_mock")
    client, ws_id, project_id = _seed_context(tmp_path)
    create = client.post(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs", json={})
    assert create.status_code == 200
    activity = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/activity")
    assert activity.status_code == 200
    assert any("Cloud runtime job" in row["title"] for row in activity.json()["items"])
    _cleanup()


def test_usage_events_written_for_requested_and_completed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "local_mock")
    client, ws_id, project_id = _seed_context(tmp_path)
    create = client.post(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs", json={})
    assert create.status_code == 200
    usage = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/usage-events")
    assert usage.status_code == 200
    names = {str(row.get("metadata", {}).get("event_name") or "") for row in usage.json()["usage_events"]}
    assert "cloud_runtime_job_requested" in names
    assert "cloud_runtime_poc_completed" in names
    _cleanup()


def test_auth_and_workspace_scope_enforced(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "disabled")
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
    set_builder_runtime_job_store_for_tests(
        BuilderRuntimeJobStore(store_path=tmp_path / "builder_runtime_jobs.json")
    )
    set_builder_usage_event_store_for_tests(
        BuilderUsageEventStore(store_path=tmp_path / "builder_usage_events.json")
    )

    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    forbidden = client.post(f"/api/workspaces/{ws_b}/projects/{p_b.id}/builder/cloud-runtime/jobs", json={})
    wrong_project_workspace = client.post(
        f"/api/workspaces/{ws_a}/projects/{p_b.id}/builder/cloud-runtime/jobs",
        json={},
    )
    ok = client.post(f"/api/workspaces/{ws_a}/projects/{p_a.id}/builder/cloud-runtime/jobs", json={})
    assert forbidden.status_code == 403
    assert wrong_project_workspace.status_code == 404
    assert ok.status_code == 200

    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.delenv("HAM_LOCAL_DEV_WORKSPACE_BYPASS", raising=False)
    unauth = TestClient(_build_app(actor=None, ws_store=ws_store))
    unauth_res = unauth.post(f"/api/workspaces/{ws_a}/projects/{p_a.id}/builder/cloud-runtime/jobs", json={})
    assert unauth_res.status_code == 401
    assert unauth_res.json()["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"
    _cleanup()
