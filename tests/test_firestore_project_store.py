"""
Tests for :class:`FirestoreProjectStore` plus the
:func:`build_project_store` backend selector.

Uses a minimal in-memory fake client to avoid real GCP / network I/O.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from src.persistence.firestore_project_store import (
    FirestoreProjectStore,
    FirestoreProjectStoreError,
)
from src.persistence.project_store import (
    ProjectStore,
    ProjectStoreProtocol,
    build_project_store,
    set_project_store_for_tests,
)
from src.registry.projects import ProjectRecord

# ---------------------------------------------------------------------------
# Minimal fake Firestore client (in-memory, single collection)
# ---------------------------------------------------------------------------


@dataclass
class _FakeDocSnap:
    id: str
    _data: dict[str, Any] | None

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data) if self._data is not None else {}


@dataclass
class _FakeDocRef:
    root: _FakeFirestoreClient
    coll_name: str
    id: str

    def set(self, data: dict[str, Any]) -> None:
        self.root.docs.setdefault(self.coll_name, {})[self.id] = dict(data)

    def get(self) -> _FakeDocSnap:
        coll = self.root.docs.get(self.coll_name, {})
        return _FakeDocSnap(self.id, coll.get(self.id))

    def delete(self) -> None:
        coll = self.root.docs.get(self.coll_name, {})
        coll.pop(self.id, None)


@dataclass
class _FakeCollection:
    root: _FakeFirestoreClient
    name: str

    def document(self, doc_id: str) -> _FakeDocRef:
        return _FakeDocRef(self.root, self.name, doc_id)

    def stream(self):
        coll = self.root.docs.get(self.name, {})
        for doc_id, data in list(coll.items()):
            yield _FakeDocSnap(doc_id, dict(data))


@dataclass
class _FakeFirestoreClient:
    docs: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self, name)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_client() -> _FakeFirestoreClient:
    return _FakeFirestoreClient()


@pytest.fixture
def store(fake_client: _FakeFirestoreClient) -> FirestoreProjectStore:
    return FirestoreProjectStore(client=fake_client, collection="ham_projects_test")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_list_projects_empty(store: FirestoreProjectStore) -> None:
    assert store.list_projects() == []


def test_make_record_stable_id_matches_file_backend(store: FirestoreProjectStore) -> None:
    fs = store.make_record(name="My App", root="/tmp/my-app")
    file_store = ProjectStore(store_path=Path("/dev/null"))
    fb = file_store.make_record(name="My App", root="/tmp/my-app")
    assert fs.id == fb.id
    assert fs.id.startswith("project.my-app-")


def test_register_and_get(store: FirestoreProjectStore) -> None:
    rec = store.make_record(name="Alpha", root="/tmp/alpha")
    store.register(rec)
    fetched = store.get_project(rec.id)
    assert fetched == rec


def test_register_replaces_by_id(store: FirestoreProjectStore) -> None:
    rec = ProjectRecord(id="project.alpha-aaaaaa", name="Alpha", root="/tmp/alpha", description="v1")
    store.register(rec)
    rec2 = ProjectRecord(id=rec.id, name="Alpha", root="/tmp/alpha", description="v2")
    store.register(rec2)
    rows = store.list_projects()
    assert len(rows) == 1
    assert rows[0].description == "v2"


def test_get_project_missing_returns_none(store: FirestoreProjectStore) -> None:
    assert store.get_project("project.missing-000000") is None


def test_get_project_blank_id_returns_none(store: FirestoreProjectStore) -> None:
    assert store.get_project("") is None


def test_remove_existing(store: FirestoreProjectStore) -> None:
    rec = store.make_record(name="Alpha", root="/tmp/alpha")
    store.register(rec)
    assert store.remove(rec.id) is True
    assert store.list_projects() == []


def test_remove_missing(store: FirestoreProjectStore) -> None:
    assert store.remove("project.missing-000000") is False


def test_remove_blank_id(store: FirestoreProjectStore) -> None:
    assert store.remove("") is False


def test_multiple_projects(store: FirestoreProjectStore) -> None:
    a = store.make_record(name="A", root="/tmp/a")
    b = store.make_record(name="B", root="/tmp/b")
    store.register(a)
    store.register(b)
    ids = {p.id for p in store.list_projects()}
    assert ids == {a.id, b.id}


# ---------------------------------------------------------------------------
# Build Lane fields round-trip
# ---------------------------------------------------------------------------


def test_register_preserves_build_lane_enabled_and_github_repo(
    store: FirestoreProjectStore,
) -> None:
    rec = ProjectRecord(
        id="project.bl-aaaaaa",
        name="bl",
        root="/tmp/bl",
        build_lane_enabled=True,
        github_repo="Code-Munkiz/ham",
    )
    store.register(rec)
    out = store.get_project(rec.id)
    assert out is not None
    assert out.build_lane_enabled is True
    assert out.github_repo == "Code-Munkiz/ham"


def test_register_round_trip_defaults_keep_build_lane_off(
    store: FirestoreProjectStore,
) -> None:
    rec = store.make_record(name="Plain", root="/tmp/plain-fs")
    store.register(rec)
    out = store.get_project(rec.id)
    assert out is not None
    assert out.build_lane_enabled is False
    assert out.github_repo is None


# ---------------------------------------------------------------------------
# Backward compatibility (legacy docs predating P1 fields)
# ---------------------------------------------------------------------------


def test_legacy_record_without_build_fields_loads_with_defaults(
    fake_client: _FakeFirestoreClient,
) -> None:
    fake_client.docs["ham_projects_test"] = {
        "project.legacy-zzzzzz": {
            "id": "project.legacy-zzzzzz",
            "version": "1.0.0",
            "name": "legacy",
            "root": "/tmp/legacy",
            "description": "",
            "metadata": {},
        }
    }
    store = FirestoreProjectStore(client=fake_client, collection="ham_projects_test")
    rows = store.list_projects()
    assert len(rows) == 1
    rec = rows[0]
    assert rec.id == "project.legacy-zzzzzz"
    assert rec.build_lane_enabled is False
    assert rec.github_repo is None


def test_malformed_doc_skipped_in_list(
    fake_client: _FakeFirestoreClient, caplog: pytest.LogCaptureFixture
) -> None:
    fake_client.docs["ham_projects_test"] = {
        "project.bad-aaaaaa": {"id": "project.bad-aaaaaa", "MISSING_name": True},
        "project.good-bbbbbb": {
            "id": "project.good-bbbbbb",
            "name": "good",
            "root": "/tmp/good",
        },
    }
    store = FirestoreProjectStore(client=fake_client, collection="ham_projects_test")
    rows = store.list_projects()
    assert [r.id for r in rows] == ["project.good-bbbbbb"]


def test_malformed_doc_returns_none_in_get(fake_client: _FakeFirestoreClient) -> None:
    fake_client.docs["ham_projects_test"] = {
        "project.bad-aaaaaa": {"id": "project.bad-aaaaaa", "MISSING_name": True},
    }
    store = FirestoreProjectStore(client=fake_client, collection="ham_projects_test")
    assert store.get_project("project.bad-aaaaaa") is None


# ---------------------------------------------------------------------------
# Default cursor metadata seeder (parity with file-backed store)
# ---------------------------------------------------------------------------


def test_register_applies_default_cursor_metadata_from_env(
    store: FirestoreProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_DEFAULT_PROJECT_ID", "project.app-f53b52")
    monkeypatch.setenv("HAM_DEFAULT_CURSOR_REPOSITORY", "Code-Munkiz/ham")
    monkeypatch.setenv("HAM_DEFAULT_CURSOR_REF", "main")
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
    store: FirestoreProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_DEFAULT_PROJECT_ID", "project.app-f53b52")
    monkeypatch.setenv("HAM_DEFAULT_CURSOR_REPOSITORY", "Code-Munkiz/ham")
    monkeypatch.setenv("HAM_DEFAULT_CURSOR_REF", "main")
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


def test_ensure_default_cursor_metadata_creates_default_when_missing(
    store: FirestoreProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_DEFAULT_PROJECT_ID", "project.app-f53b52")
    monkeypatch.setenv("HAM_DEFAULT_CURSOR_REPOSITORY", "Code-Munkiz/ham")
    monkeypatch.setenv("HAM_DEFAULT_CURSOR_REF", "main")
    monkeypatch.setenv("HAM_DEFAULT_PROJECT_ROOT", "/app")
    assert store.list_projects() == []
    assert store.ensure_default_cursor_metadata() is True
    created = store.get_project("project.app-f53b52")
    assert created is not None
    assert created.name == "app"
    assert created.root == "/app"
    assert created.metadata.get("cursor_cloud_repository") == "Code-Munkiz/ham"
    assert created.metadata.get("cursor_cloud_ref") == "main"


def test_ensure_default_cursor_metadata_backfills_existing_project(
    fake_client: _FakeFirestoreClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_DEFAULT_PROJECT_ID", "project.app-f53b52")
    monkeypatch.setenv("HAM_DEFAULT_CURSOR_REPOSITORY", "Code-Munkiz/ham")
    monkeypatch.setenv("HAM_DEFAULT_CURSOR_REF", "main")
    fake_client.docs["ham_projects_test"] = {
        "project.app-f53b52": {
            "id": "project.app-f53b52",
            "version": "1.0.0",
            "name": "app",
            "root": "/app",
            "description": "",
            "metadata": {},
            "build_lane_enabled": False,
            "github_repo": None,
        }
    }
    store = FirestoreProjectStore(client=fake_client, collection="ham_projects_test")
    assert store.ensure_default_cursor_metadata() is True
    updated = store.get_project("project.app-f53b52")
    assert updated is not None
    assert updated.metadata.get("cursor_cloud_repository") == "Code-Munkiz/ham"
    assert updated.metadata.get("cursor_cloud_ref") == "main"


def test_ensure_default_cursor_metadata_noop_without_env(
    store: FirestoreProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HAM_DEFAULT_PROJECT_ID", raising=False)
    monkeypatch.delenv("HAM_DEFAULT_CURSOR_REPOSITORY", raising=False)
    monkeypatch.delenv("HAM_DEFAULT_CURSOR_REF", raising=False)
    assert store.ensure_default_cursor_metadata() is False
    assert store.list_projects() == []


# ---------------------------------------------------------------------------
# No-secrets guard
# ---------------------------------------------------------------------------


_FORBIDDEN_KEY_HINTS = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "credential",
    "access_key",
)


def test_register_does_not_persist_secret_like_keys(
    store: FirestoreProjectStore, fake_client: _FakeFirestoreClient
) -> None:
    """``ProjectRecord`` only allows id/name/root/description/metadata/build_lane/github_repo;
    metadata is a free-form dict but the schema reviewed in this PR contains nothing secret-like.
    Document the guarantee with a sweep on every persisted document."""
    rec = ProjectRecord(
        id="project.guard-aaaaaa",
        name="guard",
        root="/tmp/guard",
        metadata={"cursor_cloud_repository": "Code-Munkiz/ham"},
        build_lane_enabled=True,
        github_repo="Code-Munkiz/ham",
    )
    store.register(rec)
    coll = fake_client.docs["ham_projects_test"]
    blob = json.dumps(coll, default=str).lower()
    for hint in _FORBIDDEN_KEY_HINTS:
        assert hint not in blob, f"persisted document leaked secret-like key: {hint}"


# ---------------------------------------------------------------------------
# Backend selector + env wiring
# ---------------------------------------------------------------------------


def test_build_project_store_defaults_to_file_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("HAM_PROJECT_STORE_BACKEND", raising=False)
    set_project_store_for_tests(None)
    try:
        store = build_project_store()
        assert isinstance(store, ProjectStore)
    finally:
        set_project_store_for_tests(None)


def test_build_project_store_unknown_backend_falls_back_to_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_PROJECT_STORE_BACKEND", "totally-not-a-backend")
    set_project_store_for_tests(None)
    try:
        store = build_project_store()
        assert isinstance(store, ProjectStore)
    finally:
        set_project_store_for_tests(None)


def test_build_project_store_selects_firestore_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_PROJECT_STORE_BACKEND", "firestore")
    monkeypatch.setenv("HAM_PROJECT_FIRESTORE_PROJECT_ID", "fake-gcp-project")
    monkeypatch.setenv("HAM_PROJECT_FIRESTORE_DATABASE", "(default)")
    monkeypatch.setenv("HAM_PROJECT_FIRESTORE_COLLECTION", "ham_projects_unit")
    set_project_store_for_tests(None)
    try:
        store = build_project_store()
        assert isinstance(store, FirestoreProjectStore)
        assert store._project == "fake-gcp-project"
        assert store._database == "(default)"
        assert store._coll_name == "ham_projects_unit"
    finally:
        set_project_store_for_tests(None)


def test_firestore_store_falls_back_to_shared_firestore_envs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HAM_PROJECT_FIRESTORE_PROJECT_ID", raising=False)
    monkeypatch.delenv("HAM_PROJECT_FIRESTORE_DATABASE", raising=False)
    monkeypatch.setenv("HAM_FIRESTORE_PROJECT_ID", "shared-gcp-project")
    monkeypatch.setenv("HAM_FIRESTORE_DATABASE", "shared-db")
    monkeypatch.delenv("HAM_PROJECT_FIRESTORE_COLLECTION", raising=False)
    fs = FirestoreProjectStore(client=_FakeFirestoreClient())
    assert fs._project == "shared-gcp-project"
    assert fs._database == "shared-db"
    assert fs._coll_name == "ham_projects"


def test_firestore_store_default_collection_when_no_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HAM_PROJECT_FIRESTORE_COLLECTION", raising=False)
    fs = FirestoreProjectStore(client=_FakeFirestoreClient())
    assert fs._coll_name == "ham_projects"


def test_firestore_store_satisfies_protocol(
    fake_client: _FakeFirestoreClient,
) -> None:
    fs = FirestoreProjectStore(client=fake_client)
    assert isinstance(fs, ProjectStoreProtocol)


# ---------------------------------------------------------------------------
# Error wrapping
# ---------------------------------------------------------------------------


class _ExplodingClient:
    def collection(self, name: str) -> Any:
        return self

    def document(self, doc_id: str) -> Any:
        return self

    def stream(self) -> Any:
        raise RuntimeError("simulated firestore outage")

    def get(self) -> Any:
        raise RuntimeError("simulated firestore outage")

    def set(self, _data: dict[str, Any]) -> None:
        raise RuntimeError("simulated firestore outage")

    def delete(self) -> None:
        raise RuntimeError("simulated firestore outage")


def test_firestore_errors_are_wrapped() -> None:
    fs = FirestoreProjectStore(client=_ExplodingClient())
    with pytest.raises(FirestoreProjectStoreError):
        fs.list_projects()
    with pytest.raises(FirestoreProjectStoreError):
        fs.get_project("project.x-aaaaaa")
    with pytest.raises(FirestoreProjectStoreError):
        fs.register(
            ProjectRecord(id="project.x-aaaaaa", name="x", root="/tmp/x"),
        )
