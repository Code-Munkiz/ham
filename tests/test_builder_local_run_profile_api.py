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
from src.persistence.builder_run_profile_store import (
    BuilderRunProfileStore,
    set_builder_run_profile_store_for_tests,
)
from src.persistence.builder_runtime_store import BuilderRuntimeStore, set_builder_runtime_store_for_tests
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
    set_builder_run_profile_store_for_tests(BuilderRunProfileStore(store_path=tmp_path / "builder_run_profiles.json"))
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    return client, ws_id, project.id


def _cleanup() -> None:
    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)
    set_builder_run_profile_store_for_tests(None)


def test_local_run_profile_get_empty_not_configured(tmp_path: Path) -> None:
    client, ws_id, project_id = _seed_context(tmp_path)
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-run-profile")
    assert res.status_code == 200
    assert res.json()["configured"] is False
    assert res.json()["profile"] is None
    _cleanup()


def test_local_run_profile_put_and_get_round_trip(tmp_path: Path) -> None:
    client, ws_id, project_id = _seed_context(tmp_path)
    put = client.put(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-run-profile",
        json={
            "display_name": "Vite dev",
            "working_directory": ".",
            "dev_command": "npm run dev",
            "install_command": "npm install",
            "build_command": "npm run build",
            "test_command": "npm test",
            "expected_preview_url": "http://localhost:5173/?token=x",
            "metadata": {"note": "safe"},
        },
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["configured"] is True
    assert body["profile"]["dev_command_argv"] == ["npm", "run", "dev"]
    assert body["profile"]["expected_preview_url"] == "http://localhost:5173/"
    get = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-run-profile")
    assert get.status_code == 200
    assert get.json()["profile"]["id"] == body["profile"]["id"]
    _cleanup()


def test_local_run_profile_delete_disables_profile(tmp_path: Path) -> None:
    client, ws_id, project_id = _seed_context(tmp_path)
    client.put(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-run-profile",
        json={"display_name": "Vite dev", "working_directory": ".", "dev_command": "npm run dev"},
    )
    delete = client.delete(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-run-profile")
    assert delete.status_code == 200
    assert delete.json()["status"] == "disabled"
    get = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-run-profile")
    assert get.status_code == 200
    assert get.json()["configured"] is False
    assert get.json()["profile"] is None
    _cleanup()


def test_local_run_profile_scope_enforced(tmp_path: Path) -> None:
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
    set_builder_run_profile_store_for_tests(BuilderRunProfileStore(store_path=tmp_path / "builder_run_profiles.json"))
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    forbidden = client.put(
        f"/api/workspaces/{ws_b}/projects/{p_b.id}/builder/local-run-profile",
        json={"display_name": "x", "working_directory": ".", "dev_command": "npm run dev"},
    )
    wrong_project_workspace = client.get(
        f"/api/workspaces/{ws_a}/projects/{p_b.id}/builder/local-run-profile"
    )
    assert forbidden.status_code == 403
    assert wrong_project_workspace.status_code == 404
    _cleanup()


def test_local_run_profile_rejects_bad_working_directory(tmp_path: Path) -> None:
    client, ws_id, project_id = _seed_context(tmp_path)
    abs_res = client.put(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-run-profile",
        json={"display_name": "x", "working_directory": "C:/app", "dev_command": "npm run dev"},
    )
    trav_res = client.put(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-run-profile",
        json={"display_name": "x", "working_directory": "../app", "dev_command": "npm run dev"},
    )
    assert abs_res.status_code == 422
    assert trav_res.status_code == 422
    _cleanup()


def test_local_run_profile_rejects_metacharacters_and_unsafe_commands(tmp_path: Path) -> None:
    client, ws_id, project_id = _seed_context(tmp_path)
    meta = client.put(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-run-profile",
        json={"display_name": "x", "working_directory": ".", "dev_command": "npm run dev && echo hi"},
    )
    unsafe = client.put(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-run-profile",
        json={"display_name": "x", "working_directory": ".", "dev_command": "powershell -c whoami"},
    )
    assert meta.status_code == 422
    assert unsafe.status_code == 422
    _cleanup()


def test_local_run_profile_preview_url_accept_reject_and_strip(tmp_path: Path) -> None:
    client, ws_id, project_id = _seed_context(tmp_path)
    ok = client.put(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-run-profile",
        json={
            "display_name": "x",
            "working_directory": ".",
            "dev_command": "npm run dev",
            "expected_preview_url": "http://localhost:5173/app?token=abc#frag",
        },
    )
    bad = client.put(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-run-profile",
        json={
            "display_name": "x",
            "working_directory": ".",
            "dev_command": "npm run dev",
            "expected_preview_url": "https://example.com",
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["profile"]["expected_preview_url"] == "http://localhost:5173/app"
    assert bad.status_code == 422
    _cleanup()


def test_local_run_profile_rejects_snapshot_from_other_project(tmp_path: Path) -> None:
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    p_a = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    p_b = project_store.make_record(name="proj-b", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(p_a)
    project_store.register(p_b)
    set_project_store_for_tests(project_store)
    source_store = BuilderSourceStore(store_path=tmp_path / "builder_sources.json")
    src = source_store.upsert_project_source(ProjectSource(workspace_id=ws_id, project_id=p_b.id))
    snap = source_store.upsert_source_snapshot(
        SourceSnapshot(workspace_id=ws_id, project_id=p_b.id, project_source_id=src.id)
    )
    set_builder_source_store_for_tests(source_store)
    set_builder_runtime_store_for_tests(BuilderRuntimeStore(store_path=tmp_path / "builder_runtime.json"))
    set_builder_run_profile_store_for_tests(BuilderRunProfileStore(store_path=tmp_path / "builder_run_profiles.json"))
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    res = client.put(
        f"/api/workspaces/{ws_id}/projects/{p_a.id}/builder/local-run-profile",
        json={
            "display_name": "x",
            "working_directory": ".",
            "dev_command": "npm run dev",
            "source_snapshot_id": snap.id,
        },
    )
    assert res.status_code == 404
    _cleanup()


def test_local_run_profile_put_does_not_execute_processes(tmp_path: Path, monkeypatch) -> None:
    import subprocess

    client, ws_id, project_id = _seed_context(tmp_path)

    def _boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("process execution should not be called")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    res = client.put(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/local-run-profile",
        json={"display_name": "x", "working_directory": ".", "dev_command": "npm run dev"},
    )
    assert res.status_code == 200, res.text
    _cleanup()
