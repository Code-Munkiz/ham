from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.persistence.project_store import ProjectStore
from src.registry.projects import ProjectRecord


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(store_path=tmp_path / "projects.json")


def test_list_projects_empty(store: ProjectStore):
    assert store.list_projects() == []


def test_make_record_stable_id(store: ProjectStore):
    r1 = store.make_record(name="My App", root="/tmp/my-app")
    r2 = store.make_record(name="My App", root="/tmp/my-app")
    assert r1.id == r2.id
    assert r1.id.startswith("project.my-app-")


def test_make_record_different_root_different_id(store: ProjectStore):
    r1 = store.make_record(name="App", root="/tmp/a")
    r2 = store.make_record(name="App", root="/tmp/b")
    assert r1.id != r2.id


def test_make_record_resolves_root(store: ProjectStore, tmp_path: Path):
    r = store.make_record(name="X", root=str(tmp_path))
    assert Path(r.root).is_absolute()


def test_register_and_list(store: ProjectStore):
    r = store.make_record(name="Alpha", root="/tmp/alpha")
    store.register(r)
    projects = store.list_projects()
    assert len(projects) == 1
    assert projects[0].id == r.id


def test_register_idempotent(store: ProjectStore):
    r = store.make_record(name="Alpha", root="/tmp/alpha")
    store.register(r)
    store.register(r)
    assert len(store.list_projects()) == 1


def test_register_replaces_by_id(store: ProjectStore):
    r = store.make_record(name="Alpha", root="/tmp/alpha", description="v1")
    store.register(r)
    r2 = ProjectRecord(id=r.id, name="Alpha", root="/tmp/alpha", description="v2")
    store.register(r2)
    projects = store.list_projects()
    assert len(projects) == 1
    assert projects[0].description == "v2"


def test_get_project_found(store: ProjectStore):
    r = store.make_record(name="Alpha", root="/tmp/alpha")
    store.register(r)
    assert store.get_project(r.id) == r


def test_get_project_not_found(store: ProjectStore):
    assert store.get_project("project.missing-000000") is None


def test_remove_existing(store: ProjectStore):
    r = store.make_record(name="Alpha", root="/tmp/alpha")
    store.register(r)
    assert store.remove(r.id) is True
    assert store.list_projects() == []


def test_remove_missing(store: ProjectStore):
    assert store.remove("project.missing-000000") is False


def test_multiple_projects(store: ProjectStore):
    a = store.make_record(name="A", root="/tmp/a")
    b = store.make_record(name="B", root="/tmp/b")
    store.register(a)
    store.register(b)
    ids = {p.id for p in store.list_projects()}
    assert ids == {a.id, b.id}


def test_persists_across_instances(tmp_path: Path):
    path = tmp_path / "projects.json"
    s1 = ProjectStore(store_path=path)
    r = s1.make_record(name="Persist", root="/tmp/persist")
    s1.register(r)

    s2 = ProjectStore(store_path=path)
    assert s2.get_project(r.id) is not None


def test_atomic_write_uses_tmp(store: ProjectStore, tmp_path: Path):
    r = store.make_record(name="A", root="/tmp/a")
    store.register(r)
    tmp_file = tmp_path / "projects.json.tmp"
    assert not tmp_file.exists()


def test_malformed_entry_skipped(tmp_path: Path):
    path = tmp_path / "projects.json"
    path.write_text(
        json.dumps({"projects": [{"id": "bad", "MISSING_name": True}]}),
        encoding="utf-8",
    )
    store = ProjectStore(store_path=path)
    assert store.list_projects() == []


def test_corrupt_file_returns_empty(tmp_path: Path):
    path = tmp_path / "projects.json"
    path.write_text("not json", encoding="utf-8")
    store = ProjectStore(store_path=path)
    assert store.list_projects() == []


def test_register_applies_default_cursor_metadata_from_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("HAM_DEFAULT_PROJECT_ID", "project.app-f53b52")
    monkeypatch.setenv("HAM_DEFAULT_CURSOR_REPOSITORY", "Code-Munkiz/ham")
    monkeypatch.setenv("HAM_DEFAULT_CURSOR_REF", "main")
    store = ProjectStore(store_path=tmp_path / "projects.json")
    record = ProjectRecord(
        id="project.app-f53b52",
        name="app",
        root="/app",
        description="",
        metadata={},
    )
    store.register(record)
    updated = store.get_project("project.app-f53b52")
    assert updated is not None
    assert updated.metadata.get("cursor_cloud_repository") == "Code-Munkiz/ham"
    assert updated.metadata.get("cursor_cloud_ref") == "main"
    assert "api_key" not in updated.metadata


def test_register_keeps_explicit_metadata_over_default_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("HAM_DEFAULT_PROJECT_ID", "project.app-f53b52")
    monkeypatch.setenv("HAM_DEFAULT_CURSOR_REPOSITORY", "Code-Munkiz/ham")
    monkeypatch.setenv("HAM_DEFAULT_CURSOR_REF", "main")
    store = ProjectStore(store_path=tmp_path / "projects.json")
    record = ProjectRecord(
        id="project.app-f53b52",
        name="app",
        root="/app",
        description="",
        metadata={
            "cursor_cloud_repository": "Code-Munkiz/custom-repo",
            "cursor_cloud_ref": "release",
        },
    )
    store.register(record)
    updated = store.get_project("project.app-f53b52")
    assert updated is not None
    assert updated.metadata.get("cursor_cloud_repository") == "Code-Munkiz/custom-repo"
    assert updated.metadata.get("cursor_cloud_ref") == "release"


def test_ensure_default_cursor_metadata_backfills_existing_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("HAM_DEFAULT_PROJECT_ID", "project.app-f53b52")
    monkeypatch.setenv("HAM_DEFAULT_CURSOR_REPOSITORY", "Code-Munkiz/ham")
    monkeypatch.setenv("HAM_DEFAULT_CURSOR_REF", "main")
    store = ProjectStore(store_path=tmp_path / "projects.json")
    record = ProjectRecord(
        id="project.app-f53b52",
        name="app",
        root="/app",
        description="",
        metadata={},
    )
    store.register(record.model_copy(update={"metadata": {}}))
    path = tmp_path / "projects.json"
    path.write_text(
        json.dumps({"projects": [record.model_dump()]}),
        encoding="utf-8",
    )
    fresh = ProjectStore(store_path=path)
    assert fresh.ensure_default_cursor_metadata() is True
    updated = fresh.get_project("project.app-f53b52")
    assert updated is not None
    assert updated.metadata.get("cursor_cloud_repository") == "Code-Munkiz/ham"
    assert updated.metadata.get("cursor_cloud_ref") == "main"


def test_ensure_default_cursor_metadata_creates_default_project_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("HAM_DEFAULT_PROJECT_ID", "project.app-f53b52")
    monkeypatch.setenv("HAM_DEFAULT_CURSOR_REPOSITORY", "Code-Munkiz/ham")
    monkeypatch.setenv("HAM_DEFAULT_CURSOR_REF", "main")
    monkeypatch.setenv("HAM_DEFAULT_PROJECT_ROOT", "/app")
    store = ProjectStore(store_path=tmp_path / "projects.json")
    assert store.list_projects() == []
    assert store.ensure_default_cursor_metadata() is True
    created = store.get_project("project.app-f53b52")
    assert created is not None
    assert created.name == "app"
    assert created.root == "/app"
    assert created.metadata.get("cursor_cloud_repository") == "Code-Munkiz/ham"
    assert created.metadata.get("cursor_cloud_ref") == "main"


# --------------------------------------------------------------------------
# Build Lane persistence (P1 — fields land dark; no router/UI uses them yet).
# --------------------------------------------------------------------------


def test_make_record_defaults_build_lane_disabled(store: ProjectStore):
    """make_record must not silently enable the Build Lane on new projects."""
    r = store.make_record(name="App", root="/tmp/build-lane-default")
    assert r.build_lane_enabled is False
    assert r.github_repo is None


def test_register_preserves_build_lane_enabled_and_github_repo(store: ProjectStore):
    r = ProjectRecord(
        id="project.bl-aaaaaa",
        name="bl",
        root="/tmp/bl",
        build_lane_enabled=True,
        github_repo="Code-Munkiz/ham",
    )
    store.register(r)
    out = store.get_project(r.id)
    assert out is not None
    assert out.build_lane_enabled is True
    assert out.github_repo == "Code-Munkiz/ham"


def test_persists_build_lane_fields_across_instances(tmp_path: Path):
    path = tmp_path / "projects.json"
    s1 = ProjectStore(store_path=path)
    r = ProjectRecord(
        id="project.bl-bbbbbb",
        name="bl2",
        root="/tmp/bl2",
        build_lane_enabled=True,
        github_repo="Code-Munkiz/ham",
    )
    s1.register(r)
    s2 = ProjectStore(store_path=path)
    out = s2.get_project(r.id)
    assert out is not None
    assert out.build_lane_enabled is True
    assert out.github_repo == "Code-Munkiz/ham"


def test_legacy_record_without_build_fields_loads_with_defaults(tmp_path: Path):
    """Records written before P1 lacked these fields; they must still load."""
    path = tmp_path / "projects.json"
    legacy = {
        "projects": [
            {
                "id": "project.legacy-zzzzzz",
                "version": "1.0.0",
                "name": "legacy",
                "root": "/tmp/legacy",
                "description": "",
                "metadata": {},
            }
        ]
    }
    path.write_text(json.dumps(legacy), encoding="utf-8")
    store = ProjectStore(store_path=path)
    rows = store.list_projects()
    assert len(rows) == 1
    assert rows[0].id == "project.legacy-zzzzzz"
    assert rows[0].build_lane_enabled is False
    assert rows[0].github_repo is None


def test_register_round_trip_from_make_record_keeps_defaults(store: ProjectStore):
    """The most common path (make_record + register + reload) must keep the lane off."""
    r = store.make_record(name="Plain", root="/tmp/plain-build")
    store.register(r)
    out = store.get_project(r.id)
    assert out is not None
    assert out.build_lane_enabled is False
    assert out.github_repo is None
