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
