from __future__ import annotations

import io
import zipfile
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
    SourceSnapshot,
    set_builder_source_store_for_tests,
)
from src.persistence.builder_visual_edit_request_store import (
    BuilderVisualEditRequestStore,
    set_builder_visual_edit_request_store_for_tests,
)
from src.persistence.builder_usage_event_store import (
    BuilderUsageEventStore,
    UsageEvent,
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


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buff = io.BytesIO()
    with zipfile.ZipFile(buff, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, body in entries.items():
            zf.writestr(name, body)
    return buff.getvalue()


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


def test_builder_zip_import_success_creates_records(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")

    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))

    app = _build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store)
    client = TestClient(app)
    payload = _zip_bytes({"src/main.py": b"print('ok')\n"})

    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project.id}/builder/import-jobs/zip",
        files={"file": ("sample.zip", payload, "application/zip")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["import_job"]["status"] == "succeeded"
    assert body["project_source"]["kind"] == "zip_upload"
    assert body["source_snapshot"]["digest_sha256"]

    listed_sources = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/sources")
    listed_snapshots = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/source-snapshots")
    listed_jobs = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/import-jobs")
    assert listed_sources.status_code == 200
    assert listed_snapshots.status_code == 200
    assert listed_jobs.status_code == 200
    assert len(listed_sources.json()["sources"]) == 1
    assert len(listed_snapshots.json()["source_snapshots"]) == 1
    assert listed_jobs.json()["import_jobs"][0]["status"] == "succeeded"

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)


def test_builder_zip_import_rejects_traversal_and_records_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))

    app = _build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store)
    client = TestClient(app)
    payload = _zip_bytes({"../../evil.py": b"x"})
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project.id}/builder/import-jobs/zip",
        files={"file": ("bad.zip", payload, "application/zip")},
    )
    assert res.status_code == 400
    assert res.json()["detail"]["error"]["code"] == "ZIP_PATH_TRAVERSAL"

    jobs = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/import-jobs").json()["import_jobs"]
    assert jobs[0]["status"] == "failed"
    assert jobs[0]["error_code"] == "ZIP_PATH_TRAVERSAL"

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)


def test_builder_zip_import_rejects_absolute_and_size_caps(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("HAM_BUILDER_ZIP_MAX_FILE_COUNT", "1")
    monkeypatch.setenv("HAM_BUILDER_ZIP_MAX_ENTRY_BYTES", "256")
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))

    app = _build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store)
    client = TestClient(app)

    abs_payload = _zip_bytes({"C:/windows/system.ini": b"x"})
    abs_res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project.id}/builder/import-jobs/zip",
        files={"file": ("abs.zip", abs_payload, "application/zip")},
    )
    assert abs_res.status_code == 400
    assert abs_res.json()["detail"]["error"]["code"] == "ZIP_ABSOLUTE_PATH"

    large_payload = _zip_bytes({"a.txt": b"x" * 2048})
    large_res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project.id}/builder/import-jobs/zip",
        files={"file": ("large.zip", large_payload, "application/zip")},
    )
    assert large_res.status_code == 400
    assert large_res.json()["detail"]["error"]["code"] == "ZIP_ENTRY_TOO_LARGE"

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)


def test_builder_zip_import_workspace_scope_enforced(tmp_path: Path) -> None:
    ws_store = InMemoryWorkspaceStore()
    ws_a = "ws_aaaaaaaaaaaaaaaa"
    ws_b = "ws_bbbbbbbbbbbbbbbb"
    _seed_workspace(ws_store, workspace_id=ws_a, org_id="org_a", owner_user_id="user_a", slug="alpha")
    _seed_workspace(ws_store, workspace_id=ws_b, org_id="org_b", owner_user_id="user_b", slug="beta")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    p_b = project_store.make_record(name="proj-b", root=str(tmp_path), metadata={"workspace_id": ws_b})
    project_store.register(p_b)
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))
    app = _build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store)
    client = TestClient(app)

    payload = _zip_bytes({"src/main.py": b"print('ok')"})
    forbidden = client.post(
        f"/api/workspaces/{ws_b}/projects/{p_b.id}/builder/import-jobs/zip",
        files={"file": ("sample.zip", payload, "application/zip")},
    )
    assert forbidden.status_code == 403

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)


def test_visual_edit_requests_create_list_cancel_and_sanitize(tmp_path: Path) -> None:
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)
    source_store = BuilderSourceStore(store_path=tmp_path / "builder_sources.json")
    source = source_store.upsert_project_source(ProjectSource(workspace_id=ws_id, project_id=project.id))
    snap = source_store.upsert_source_snapshot(
        SourceSnapshot(workspace_id=ws_id, project_id=project.id, project_source_id=source.id)
    )
    set_builder_source_store_for_tests(source_store)
    set_builder_visual_edit_request_store_for_tests(
        BuilderVisualEditRequestStore(store_path=tmp_path / "builder_visual_edit_requests.json")
    )

    app = _build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store)
    client = TestClient(app)
    created = client.post(
        f"/api/workspaces/{ws_id}/projects/{project.id}/builder/visual-edit-requests",
        json={
            "source_snapshot_id": snap.id,
            "runtime_session_id": "rtms_123",
            "preview_endpoint_id": "prve_123",
            "route": "/dashboard",
            "selector_hints": [".panel .save", "secret=token"],
            "bbox": {"x": 10, "y": 20, "width": 120, "height": 42},
            "instruction": "Move Save button above the form",
            "status": "queued",
            "metadata": {"note": "safe", "api_key": "should-drop"},
        },
    )
    assert created.status_code == 200, created.text
    row = created.json()["visual_edit_request"]
    assert row["source_snapshot_id"] == snap.id
    assert row["status"] == "queued"
    assert row["selector_hints"] == [".panel .save"]
    assert row["metadata"] == {"note": "safe"}
    assert row["bbox"] == {"x": 10.0, "y": 20.0, "width": 120.0, "height": 42.0}

    listed = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/visual-edit-requests")
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["visual_edit_requests"]) == 1

    cancelled = client.delete(
        f"/api/workspaces/{ws_id}/projects/{project.id}/builder/visual-edit-requests/{row['id']}"
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["visual_edit_request"]["status"] == "cancelled"

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_visual_edit_request_store_for_tests(None)


def test_visual_edit_request_rejects_invalid_instruction_and_bbox(tmp_path: Path) -> None:
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))
    set_builder_visual_edit_request_store_for_tests(
        BuilderVisualEditRequestStore(store_path=tmp_path / "builder_visual_edit_requests.json")
    )
    app = _build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store)
    client = TestClient(app)

    bad_instruction = client.post(
        f"/api/workspaces/{ws_id}/projects/{project.id}/builder/visual-edit-requests",
        json={"instruction": "  "},
    )
    assert bad_instruction.status_code == 422
    assert bad_instruction.json()["detail"]["error"]["code"] == "VISUAL_EDIT_INSTRUCTION_INVALID"

    bad_bbox = client.post(
        f"/api/workspaces/{ws_id}/projects/{project.id}/builder/visual-edit-requests",
        json={
            "instruction": "Move logo",
            "bbox": {"x": 1, "y": 2, "width": 100},
        },
    )
    assert bad_bbox.status_code == 422
    assert bad_bbox.json()["detail"]["error"]["code"] == "VISUAL_EDIT_BBOX_INVALID"

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_visual_edit_request_store_for_tests(None)


def test_builder_usage_events_lists_scoped_records(tmp_path: Path) -> None:
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")

    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    other = project_store.make_record(name="proj-b", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    project_store.register(other)
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))

    usage_store = BuilderUsageEventStore(store_path=tmp_path / "builder_usage_events.json")
    usage_store.append_usage_event(
        UsageEvent(
            workspace_id=ws_id,
            project_id=project.id,
            category="artifact_storage",
            quantity=2048,
            unit="bytes",
            metadata={"safe": "ok", "api_key": "should-drop"},
        )
    )
    usage_store.append_usage_event(
        UsageEvent(
            workspace_id=ws_id,
            project_id=other.id,
            category="model_call",
            quantity=512,
            unit="tokens",
        )
    )
    set_builder_usage_event_store_for_tests(usage_store)
    app = _build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store)
    client = TestClient(app)

    res = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/usage-events")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["workspace_id"] == ws_id
    assert body["project_id"] == project.id
    assert len(body["usage_events"]) == 1
    item = body["usage_events"][0]
    assert item["category"] == "artifact_storage"
    assert item["quantity"] == 2048
    assert item["unit"] == "bytes"
    assert item["metadata"] == {"safe": "ok"}

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_usage_event_store_for_tests(None)


def test_builder_usage_events_scope_enforced(tmp_path: Path) -> None:
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
    set_builder_usage_event_store_for_tests(BuilderUsageEventStore(store_path=tmp_path / "builder_usage_events.json"))
    app = _build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store)
    client = TestClient(app)

    forbidden = client.get(f"/api/workspaces/{ws_b}/projects/{p_b.id}/builder/usage-events")
    wrong_project_workspace = client.get(f"/api/workspaces/{ws_a}/projects/{p_b.id}/builder/usage-events")
    ok = client.get(f"/api/workspaces/{ws_a}/projects/{p_a.id}/builder/usage-events")
    assert forbidden.status_code == 403
    assert wrong_project_workspace.status_code == 404
    assert ok.status_code == 200
    assert ok.json()["usage_events"] == []

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_usage_event_store_for_tests(None)


def test_builder_worker_capabilities_returns_known_worker_kinds(tmp_path: Path) -> None:
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
    project = project_store.make_record(name="alpha-project", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))
    app = _build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store)
    client = TestClient(app)

    res = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/worker-capabilities")
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["workspace_id"] == ws_id
    assert payload["project_id"] == project.id
    workers = payload["workers"]
    assert [row["worker_kind"] for row in workers] == [
        "cursor_cloud_agent",
        "cursor_local_sdk",
        "claude_agent",
        "factory_droid",
        "local_runtime",
        "cloud_runtime_worker",
        "hermes_planner",
    ]
    for row in workers:
        assert row["status"] in {
            "available",
            "needs_connection",
            "unavailable",
            "disabled",
            "unknown",
            "available_mock",
            "available_poc",
        }
        assert "capabilities" in row
        assert "required_setup" in row
        assert "environment_fit" in row

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)


def test_builder_worker_capabilities_does_not_expose_secrets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_DROID_EXEC_TOKEN", "super-secret-token-value")
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))

    res = client.get(f"/api/workspaces/{ws_id}/projects/{project.id}/builder/worker-capabilities")
    assert res.status_code == 200, res.text
    body = res.text.lower()
    assert "super-secret-token-value" not in body
    assert "api_key" not in body
    assert "authorization" not in body

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)


def test_builder_worker_capabilities_enforces_scope_and_auth(tmp_path: Path, monkeypatch) -> None:
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
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    forbidden = client.get(f"/api/workspaces/{ws_b}/projects/{p_b.id}/builder/worker-capabilities")
    wrong_project_workspace = client.get(
        f"/api/workspaces/{ws_a}/projects/{p_b.id}/builder/worker-capabilities"
    )
    ok = client.get(f"/api/workspaces/{ws_a}/projects/{p_a.id}/builder/worker-capabilities")
    assert forbidden.status_code == 403
    assert wrong_project_workspace.status_code == 404
    assert ok.status_code == 200

    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.delenv("HAM_LOCAL_DEV_WORKSPACE_BYPASS", raising=False)
    unauth = TestClient(_build_app(actor=None, ws_store=ws_store))
    unauth_res = unauth.get(f"/api/workspaces/{ws_a}/projects/{p_a.id}/builder/worker-capabilities")
    assert unauth_res.status_code == 401
    assert unauth_res.json()["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"

    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)


def test_builder_default_project_post_idempotent(tmp_path: Path) -> None:
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    r1 = client.post(f"/api/workspaces/{ws_id}/builder/default-project")
    assert r1.status_code == 200, r1.text
    pid = r1.json()["project_id"]
    assert pid
    r2 = client.post(f"/api/workspaces/{ws_id}/builder/default-project")
    assert r2.status_code == 200, r2.text
    assert r2.json()["project_id"] == pid
    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)


def test_builder_inline_snapshot_files_list_and_content(tmp_path: Path) -> None:
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="alpha-project", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)
    builder_store = BuilderSourceStore(store_path=tmp_path / "builder_sources.json")
    src = ProjectSource(
        id="psrc_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        workspace_id=ws_id,
        project_id=project.id,
        display_name="inline",
    )
    builder_store.upsert_project_source(src)
    snap_id = "ssnp_test123456789012345678901234"
    snap = SourceSnapshot(
        id=snap_id,
        workspace_id=ws_id,
        project_id=project.id,
        project_source_id=src.id,
        manifest={
            "kind": "inline_text_bundle",
            "entries": [{"path": "src/App.tsx", "size_bytes": 3}],
            "inline_files": {"src/App.tsx": "abc"},
        },
    )
    builder_store.upsert_source_snapshot(snap)
    set_builder_source_store_for_tests(builder_store)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    r_list = client.get(
        f"/api/workspaces/{ws_id}/projects/{project.id}/builder/source-snapshots/{snap_id}/files",
    )
    assert r_list.status_code == 200, r_list.text
    body = r_list.json()
    assert body["source_snapshot_id"] == snap_id
    assert len(body["files"]) == 1
    assert body["files"][0]["path"] == "src/App.tsx"
    r_content = client.get(
        f"/api/workspaces/{ws_id}/projects/{project.id}/builder/source-snapshots/{snap_id}/files/content",
        params={"path": "src/App.tsx"},
    )
    assert r_content.status_code == 200, r_content.text
    assert r_content.json()["content"] == "abc"
    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
