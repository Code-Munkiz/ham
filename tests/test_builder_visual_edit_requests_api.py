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
from src.persistence.builder_source_store import BuilderSourceStore, ProjectSource, SourceSnapshot, set_builder_source_store_for_tests
from src.persistence.builder_visual_edit_request_store import BuilderVisualEditRequestStore, set_builder_visual_edit_request_store_for_tests
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


def _seed_project_context(tmp_path: Path) -> tuple[str, str, InMemoryWorkspaceStore]:
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")

    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)

    source_store = BuilderSourceStore(store_path=tmp_path / "builder_sources.json")
    source = source_store.upsert_project_source(ProjectSource(workspace_id=ws_id, project_id=project.id))
    source_store.upsert_source_snapshot(
        SourceSnapshot(
            workspace_id=ws_id,
            project_id=project.id,
            project_source_id=source.id,
            artifact_uri="builder-artifact://bzip_1",
        )
    )
    set_builder_source_store_for_tests(source_store)
    set_builder_visual_edit_request_store_for_tests(
        BuilderVisualEditRequestStore(store_path=tmp_path / "builder_visual_edit_requests.json")
    )
    return ws_id, project.id, ws_store


def _cleanup() -> None:
    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_visual_edit_request_store_for_tests(None)


def test_visual_edit_request_accepts_target_and_sanitizes_route(tmp_path: Path) -> None:
    ws_id, project_id, ws_store = _seed_project_context(tmp_path)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/visual-edit-requests",
        json={
            "route": "https://example.com/dashboard?token=abc#frag",
            "preview_url_kind": "local",
            "target": {
                "x": 13,
                "y": 27,
                "width": 32,
                "height": 24,
                "viewport_width": 1024,
                "viewport_height": 640,
                "device_mode": "desktop",
                "selector_hints": [".hero .cta", "api_key=redact"],
                "element_text": "Save changes",
            },
            "instruction": "Make the button more prominent",
            "selector_hints": [".hero .cta", "password=drop"],
            "metadata": {"note": "safe", "api_key": "drop"},
        },
    )
    assert res.status_code == 200, res.text
    row = res.json()["visual_edit_request"]
    assert row["route"] == "/dashboard"
    assert row["bbox"] == {"x": 13.0, "y": 27.0, "width": 32.0, "height": 24.0}
    assert row["selector_hints"] == [".hero .cta"]
    assert row["metadata"]["note"] == "safe"
    assert row["metadata"]["preview_url_kind"] == "local"
    assert row["metadata"]["target"]["device_mode"] == "desktop"
    assert row["metadata"]["target"]["selector_hints"] == [".hero .cta"]
    _cleanup()


def test_visual_edit_request_rejects_invalid_target_and_bounds_selector_hints(tmp_path: Path) -> None:
    ws_id, project_id, ws_store = _seed_project_context(tmp_path)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    bad_target = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/visual-edit-requests",
        json={"instruction": "Move card", "target": {"x": "abc", "y": 2, "width": 10, "height": 10}},
    )
    assert bad_target.status_code == 422
    assert bad_target.json()["detail"]["error"]["code"] == "VISUAL_EDIT_TARGET_INVALID"

    long_hints = [f".selector-{idx:02d}" for idx in range(40)]
    ok = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/visual-edit-requests",
        json={"instruction": "Align cards", "selector_hints": long_hints},
    )
    assert ok.status_code == 200, ok.text
    hints = ok.json()["visual_edit_request"]["selector_hints"]
    assert len(hints) == 20
    _cleanup()


def test_visual_edit_request_scope_enforced_and_no_cross_project_leakage(tmp_path: Path) -> None:
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
    set_builder_visual_edit_request_store_for_tests(
        BuilderVisualEditRequestStore(store_path=tmp_path / "builder_visual_edit_requests.json")
    )

    foreign = TestClient(_build_app(actor=_actor("user_b", org_id="org_b"), ws_store=ws_store))
    forbidden = foreign.post(
        f"/api/workspaces/{ws_a}/projects/{p_a.id}/builder/visual-edit-requests",
        json={"instruction": "No access"},
    )
    assert forbidden.status_code == 403

    owner = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    ok = owner.post(
        f"/api/workspaces/{ws_a}/projects/{p_a.id}/builder/visual-edit-requests",
        json={"instruction": "Allowed request"},
    )
    assert ok.status_code == 200, ok.text
    leaked = owner.get(f"/api/workspaces/{ws_b}/projects/{p_b.id}/builder/visual-edit-requests")
    assert leaked.status_code == 403
    _cleanup()


def test_visual_edit_request_does_not_mutate_sources_or_execute_worker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ws_id, project_id, ws_store = _seed_project_context(tmp_path)
    source_store = BuilderSourceStore(store_path=tmp_path / "builder_sources_verify.json")
    source = source_store.upsert_project_source(ProjectSource(workspace_id=ws_id, project_id=project_id))
    source_store.upsert_source_snapshot(
        SourceSnapshot(
            workspace_id=ws_id,
            project_id=project_id,
            project_source_id=source.id,
            artifact_uri="builder-artifact://bzip_2",
        )
    )
    set_builder_source_store_for_tests(source_store)

    called = {"worker": False}

    def _unexpected(*args, **kwargs):
        called["worker"] = True
        raise AssertionError("worker execution should not run for visual edit request")

    monkeypatch.setattr("src.api.builder_sources.execute_cloud_runtime_job", _unexpected)
    before_sources = source_store.list_project_sources(workspace_id=ws_id, project_id=project_id)
    before_snapshots = source_store.list_source_snapshots(workspace_id=ws_id, project_id=project_id)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/visual-edit-requests",
        json={"instruction": "Change card spacing"},
    )
    assert res.status_code == 200, res.text
    after_sources = source_store.list_project_sources(workspace_id=ws_id, project_id=project_id)
    after_snapshots = source_store.list_source_snapshots(workspace_id=ws_id, project_id=project_id)
    assert called["worker"] is False
    assert len(after_sources) == len(before_sources)
    assert len(after_snapshots) == len(before_snapshots)
    _cleanup()
