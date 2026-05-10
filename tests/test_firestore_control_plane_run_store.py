"""
Tests for :class:`FirestoreControlPlaneRunStore` plus the
:func:`build_control_plane_run_store` backend selector.

Uses a minimal in-memory fake client modeled on
``tests/test_firestore_project_store.py`` to avoid real GCP / network I/O.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from src.persistence.control_plane_run import (
    ControlPlaneRun,
    ControlPlaneRunStore,
    ControlPlaneRunStoreProtocol,
    build_control_plane_run_store,
    get_control_plane_run_store,
    new_ham_run_id,
    set_control_plane_run_store_for_tests,
    utc_now_iso,
)
from src.persistence.firestore_control_plane_run_store import (
    FirestoreControlPlaneRunStore,
    FirestoreControlPlaneRunStoreError,
)

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
        self.root.docs.get(self.coll_name, {}).pop(self.id, None)


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
# Fixtures + helpers
# ---------------------------------------------------------------------------


_TEST_COLL = "ham_control_plane_runs_test"


@pytest.fixture
def fake_client() -> _FakeFirestoreClient:
    return _FakeFirestoreClient()


@pytest.fixture
def store(fake_client: _FakeFirestoreClient) -> FirestoreControlPlaneRunStore:
    return FirestoreControlPlaneRunStore(client=fake_client, collection=_TEST_COLL)


def _new_run(
    *,
    ham_run_id: str | None = None,
    project_id: str = "project.cp-aaaaaa",
    provider: str = "factory_droid",
    status: str = "running",
    external_id: str | None = "ext-1",
    workflow_id: str | None = "readonly_repo_audit",
    pr_url: str | None = None,
    pr_branch: str | None = None,
    pr_commit_sha: str | None = None,
    build_outcome: Any | None = None,
) -> ControlPlaneRun:
    now = utc_now_iso()
    rid = ham_run_id or new_ham_run_id()
    return ControlPlaneRun(
        ham_run_id=rid,
        provider=provider,
        action_kind="launch",
        project_id=project_id,
        created_by=None,
        created_at=now,
        updated_at=now,
        committed_at=now,
        started_at=now,
        finished_at=None,
        last_observed_at=now,
        status=status,
        status_reason="test",
        proposal_digest="a" * 64,
        base_revision="v1",
        external_id=external_id,
        workflow_id=workflow_id,
        summary="s",
        error_summary=None,
        last_provider_status=None,
        audit_ref=None,
        pr_url=pr_url,
        pr_branch=pr_branch,
        pr_commit_sha=pr_commit_sha,
        build_outcome=build_outcome,
    )


# ---------------------------------------------------------------------------
# Save + get round trip
# ---------------------------------------------------------------------------


def test_save_then_get_round_trip(store: FirestoreControlPlaneRunStore) -> None:
    run = _new_run()
    store.save(run, project_root_for_mirror=None)
    out = store.get(run.ham_run_id)
    assert out is not None
    assert out.ham_run_id == run.ham_run_id
    assert out.provider == run.provider
    assert out.project_id == run.project_id
    assert out.proposal_digest == run.proposal_digest


def test_get_blank_id_returns_none(store: FirestoreControlPlaneRunStore) -> None:
    assert store.get("") is None


def test_get_missing_returns_none(store: FirestoreControlPlaneRunStore) -> None:
    assert store.get("11111111-1111-1111-1111-111111111111") is None


def test_save_replaces_existing_doc(store: FirestoreControlPlaneRunStore) -> None:
    run1 = _new_run(status="running")
    store.save(run1, project_root_for_mirror=None)
    run2 = run1.model_copy(update={"status": "succeeded", "status_reason": "done"})
    store.save(run2, project_root_for_mirror=None)
    out = store.get(run1.ham_run_id)
    assert out is not None
    assert out.status == "succeeded"


# ---------------------------------------------------------------------------
# Build Lane fields round-trip + persisted shape parity with file backend
# ---------------------------------------------------------------------------


def test_save_round_trip_build_lane_fields(
    store: FirestoreControlPlaneRunStore,
) -> None:
    run = _new_run(
        pr_url="https://github.com/Code-Munkiz/ham/pull/999",
        pr_branch="ham-droid/abc12345",
        pr_commit_sha="0123456789abcdef0123456789abcdef01234567",
        build_outcome="pr_opened",
        status="succeeded",
    )
    store.save(run, project_root_for_mirror=None)
    out = store.get(run.ham_run_id)
    assert out is not None
    assert out.pr_url == "https://github.com/Code-Munkiz/ham/pull/999"
    assert out.pr_branch == "ham-droid/abc12345"
    assert out.pr_commit_sha == "0123456789abcdef0123456789abcdef01234567"
    assert out.build_outcome == "pr_opened"


def test_persisted_doc_excludes_none_build_fields(
    store: FirestoreControlPlaneRunStore, fake_client: _FakeFirestoreClient,
) -> None:
    """exclude_none parity: file store omits None Build keys; Firestore must too."""
    run = _new_run()
    store.save(run, project_root_for_mirror=None)
    on_disk = fake_client.docs[_TEST_COLL][run.ham_run_id]
    for k in ("pr_url", "pr_branch", "pr_commit_sha", "build_outcome"):
        assert k not in on_disk, f"unexpected None field persisted: {k}"


def test_persisted_doc_keeps_set_build_fields(
    store: FirestoreControlPlaneRunStore, fake_client: _FakeFirestoreClient,
) -> None:
    run = _new_run(
        pr_url="https://github.com/Code-Munkiz/ham/pull/12",
        pr_branch="ham-droid/feature",
        pr_commit_sha="cafebabe" * 5,
        build_outcome="pr_opened",
        status="succeeded",
    )
    store.save(run, project_root_for_mirror=None)
    on_disk = fake_client.docs[_TEST_COLL][run.ham_run_id]
    assert on_disk["pr_url"] == "https://github.com/Code-Munkiz/ham/pull/12"
    assert on_disk["pr_branch"] == "ham-droid/feature"
    assert on_disk["build_outcome"] == "pr_opened"


# ---------------------------------------------------------------------------
# Backward compatibility (legacy docs predating P1 fields)
# ---------------------------------------------------------------------------


def test_legacy_doc_without_build_fields_loads_with_defaults(
    fake_client: _FakeFirestoreClient,
) -> None:
    rid = "55555555-5555-5555-5555-555555555555"
    fake_client.docs[_TEST_COLL] = {
        rid: {
            "ham_run_id": rid,
            "version": 1,
            "provider": "factory_droid",
            "action_kind": "launch",
            "project_id": "p_legacy",
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "committed_at": utc_now_iso(),
            "status": "succeeded",
            "status_reason": "droid:exit 0",
            "proposal_digest": "c" * 64,
            "base_revision": "v1",
        }
    }
    fs = FirestoreControlPlaneRunStore(client=fake_client, collection=_TEST_COLL)
    out = fs.get(rid)
    assert out is not None
    assert out.pr_url is None
    assert out.pr_branch is None
    assert out.pr_commit_sha is None
    assert out.build_outcome is None


def test_malformed_doc_skipped_in_get(fake_client: _FakeFirestoreClient) -> None:
    rid = "66666666-6666-6666-6666-666666666666"
    fake_client.docs[_TEST_COLL] = {rid: {"MISSING_required": True}}
    fs = FirestoreControlPlaneRunStore(client=fake_client, collection=_TEST_COLL)
    assert fs.get(rid) is None


def test_malformed_doc_skipped_in_list(
    fake_client: _FakeFirestoreClient,
) -> None:
    bad_id = "77777777-7777-7777-7777-777777777777"
    good_id = "88888888-8888-8888-8888-888888888888"
    now = utc_now_iso()
    fake_client.docs[_TEST_COLL] = {
        bad_id: {"project_id": "p1", "MISSING": True},
        good_id: {
            "ham_run_id": good_id,
            "version": 1,
            "provider": "factory_droid",
            "action_kind": "launch",
            "project_id": "p1",
            "created_at": now,
            "updated_at": now,
            "committed_at": now,
            "status": "succeeded",
            "status_reason": "droid:exit 0",
            "proposal_digest": "c" * 64,
            "base_revision": "v1",
        },
    }
    fs = FirestoreControlPlaneRunStore(client=fake_client, collection=_TEST_COLL)
    rows = fs.list_for_project("p1")
    assert [r.ham_run_id for r in rows] == [good_id]


# ---------------------------------------------------------------------------
# list_for_project: filtering, limit, ordering
# ---------------------------------------------------------------------------


def test_list_for_project_filters_by_project_id(
    store: FirestoreControlPlaneRunStore,
) -> None:
    keep_id = "aaaaaaaa-1111-1111-1111-111111111111"
    drop_id = "bbbbbbbb-2222-2222-2222-222222222222"
    store.save(_new_run(ham_run_id=keep_id, project_id="project.cp-aaaaaa"))
    store.save(_new_run(ham_run_id=drop_id, project_id="project.other-bbbbbb"))
    rows = store.list_for_project("project.cp-aaaaaa")
    assert [r.ham_run_id for r in rows] == [keep_id]


def test_list_for_project_filters_by_provider(
    store: FirestoreControlPlaneRunStore,
) -> None:
    pid = "project.cp-mixed"
    store.save(
        _new_run(
            ham_run_id="11111111-1111-1111-1111-111111111111",
            project_id=pid,
            provider="cursor_cloud_agent",
            workflow_id=None,
        ),
    )
    store.save(
        _new_run(
            ham_run_id="22222222-2222-2222-2222-222222222222",
            project_id=pid,
            provider="factory_droid",
        ),
    )
    rows = store.list_for_project(pid, provider="factory_droid")
    assert len(rows) == 1
    assert rows[0].provider == "factory_droid"


def test_list_for_project_returns_newest_first_by_ham_run_id(
    store: FirestoreControlPlaneRunStore,
) -> None:
    """Match file-backed semantics: sort by ham_run_id descending."""
    pid = "project.cp-order"
    a = "11111111-1111-1111-1111-111111111111"
    b = "55555555-5555-5555-5555-555555555555"
    c = "99999999-9999-9999-9999-999999999999"
    for rid in (a, c, b):
        store.save(_new_run(ham_run_id=rid, project_id=pid))
    rows = store.list_for_project(pid)
    assert [r.ham_run_id for r in rows] == [c, b, a]


def test_list_for_project_caps_limit_floor(
    store: FirestoreControlPlaneRunStore,
) -> None:
    pid = "project.cp-floor"
    store.save(_new_run(project_id=pid))
    assert len(store.list_for_project(pid, limit=0)) == 1
    assert len(store.list_for_project(pid, limit=-100)) == 1


def test_list_for_project_caps_limit_ceiling(
    store: FirestoreControlPlaneRunStore,
) -> None:
    pid = "project.cp-ceil"
    for i in range(3):
        store.save(_new_run(ham_run_id=f"{i:08d}-0000-0000-0000-000000000000", project_id=pid))
    assert len(store.list_for_project(pid, limit=10_000)) == 3


def test_list_for_project_blank_pid_returns_empty(
    store: FirestoreControlPlaneRunStore,
) -> None:
    assert store.list_for_project("") == []


def test_list_for_project_respects_limit(
    store: FirestoreControlPlaneRunStore,
) -> None:
    pid = "project.cp-limit"
    ids = [
        "33333333-3333-3333-3333-333333333333",
        "55555555-5555-5555-5555-555555555555",
        "77777777-7777-7777-7777-777777777777",
    ]
    for rid in ids:
        store.save(_new_run(ham_run_id=rid, project_id=pid))
    rows = store.list_for_project(pid, limit=2)
    assert [r.ham_run_id for r in rows] == ids[2:0:-1]  # newest 2 desc


# ---------------------------------------------------------------------------
# find_by_*
# ---------------------------------------------------------------------------


def test_find_by_project_and_external(store: FirestoreControlPlaneRunStore) -> None:
    pid = "project.cp-find"
    store.save(
        _new_run(
            ham_run_id="44444444-4444-4444-4444-444444444444",
            project_id=pid,
            provider="cursor_cloud_agent",
            external_id="bc_xyz",
            workflow_id=None,
        ),
    )
    out = store.find_by_project_and_external(
        project_id=pid, provider="cursor_cloud_agent", external_id="bc_xyz",
    )
    assert out is not None
    assert out.external_id == "bc_xyz"


def test_find_by_project_and_external_misses(
    store: FirestoreControlPlaneRunStore,
) -> None:
    pid = "project.cp-find-miss"
    store.save(_new_run(project_id=pid, external_id="bc_present", provider="cursor_cloud_agent", workflow_id=None))
    assert store.find_by_project_and_external(
        project_id=pid, provider="cursor_cloud_agent", external_id="bc_other",
    ) is None
    assert store.find_by_project_and_external(
        project_id=pid, provider="factory_droid", external_id="bc_present",
    ) is None
    assert store.find_by_project_and_external(
        project_id="project.cp-other", provider="cursor_cloud_agent", external_id="bc_present",
    ) is None


def test_find_by_provider_and_external(store: FirestoreControlPlaneRunStore) -> None:
    store.save(
        _new_run(
            project_id="project.cp-A",
            provider="factory_droid",
            external_id="sess-99",
        ),
    )
    out = store.find_by_provider_and_external(provider="factory_droid", external_id="sess-99")
    assert out is not None
    assert out.external_id == "sess-99"


def test_find_by_provider_and_external_blank_inputs(
    store: FirestoreControlPlaneRunStore,
) -> None:
    assert store.find_by_provider_and_external(provider="", external_id="x") is None
    assert store.find_by_provider_and_external(provider="factory_droid", external_id=" ") is None


# ---------------------------------------------------------------------------
# save() applies the same caps as the file-backed store
# ---------------------------------------------------------------------------


def test_save_caps_summary_and_status_reason(
    store: FirestoreControlPlaneRunStore, fake_client: _FakeFirestoreClient,
) -> None:
    run = _new_run()
    long_summary = "x" * 5000
    long_reason = "y" * 1000
    long_err = "z" * 5000
    capped_run = run.model_copy(
        update={
            "summary": long_summary,
            "error_summary": long_err,
            "status_reason": long_reason,
        },
    )
    store.save(capped_run, project_root_for_mirror=None)
    on_disk = fake_client.docs[_TEST_COLL][run.ham_run_id]
    assert len(on_disk["summary"]) <= 2_000
    assert len(on_disk["error_summary"]) <= 2_000
    assert len(on_disk["status_reason"]) <= 512


# ---------------------------------------------------------------------------
# Project-root mirror still writes a filesystem copy
# ---------------------------------------------------------------------------


def test_save_writes_project_root_mirror_when_dir_exists(
    store: FirestoreControlPlaneRunStore, tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run = _new_run()
    store.save(run, project_root_for_mirror=str(repo))
    mirror = repo / ".ham" / "control_plane" / "runs" / f"{run.ham_run_id}.json"
    assert mirror.is_file()
    on_disk = json.loads(mirror.read_text(encoding="utf-8"))
    assert on_disk["ham_run_id"] == run.ham_run_id
    assert on_disk["project_id"] == run.project_id


def test_save_skips_mirror_when_root_missing(
    store: FirestoreControlPlaneRunStore, tmp_path: Path,
) -> None:
    bogus = tmp_path / "no-such-repo"
    run = _new_run()
    store.save(run, project_root_for_mirror=str(bogus))
    # No exception, no mirror file.
    assert not bogus.exists()


# ---------------------------------------------------------------------------
# No secrets persisted
# ---------------------------------------------------------------------------


_FORBIDDEN_KEY_HINTS = (
    "api_key",
    "apikey",
    "password",
    "credential",
    "access_key",
)


def test_save_does_not_leak_secret_like_keys(
    store: FirestoreControlPlaneRunStore, fake_client: _FakeFirestoreClient,
) -> None:
    """ControlPlaneRun has ``extra='forbid'`` so secret-like keys can't be added,
    but verify the whole persisted document blob to lock in the guarantee."""
    run = _new_run(
        pr_url="https://github.com/o/r/pull/1",
        pr_branch="ham-droid/abc",
        pr_commit_sha="0" * 40,
        build_outcome="pr_opened",
        status="succeeded",
    )
    store.save(run, project_root_for_mirror=None)
    blob = json.dumps(fake_client.docs[_TEST_COLL], default=str).lower()
    for hint in _FORBIDDEN_KEY_HINTS:
        assert hint not in blob, f"persisted document leaked secret-like key: {hint}"


# ---------------------------------------------------------------------------
# Backend selector + env precedence
# ---------------------------------------------------------------------------


def test_build_control_plane_run_store_defaults_to_file_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HAM_CONTROL_PLANE_RUN_STORE_BACKEND", raising=False)
    set_control_plane_run_store_for_tests(None)
    try:
        s = build_control_plane_run_store()
        assert isinstance(s, ControlPlaneRunStore)
    finally:
        set_control_plane_run_store_for_tests(None)


def test_build_control_plane_run_store_unknown_falls_back_to_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_CONTROL_PLANE_RUN_STORE_BACKEND", "redis")
    set_control_plane_run_store_for_tests(None)
    try:
        s = build_control_plane_run_store()
        assert isinstance(s, ControlPlaneRunStore)
    finally:
        set_control_plane_run_store_for_tests(None)


def test_build_control_plane_run_store_selects_firestore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_CONTROL_PLANE_RUN_STORE_BACKEND", "firestore")
    monkeypatch.setenv("HAM_CONTROL_PLANE_RUN_FIRESTORE_PROJECT_ID", "fake-gcp")
    monkeypatch.setenv("HAM_CONTROL_PLANE_RUN_FIRESTORE_DATABASE", "(default)")
    monkeypatch.setenv("HAM_CONTROL_PLANE_RUN_FIRESTORE_COLLECTION", "ham_cp_runs_unit")
    set_control_plane_run_store_for_tests(None)
    try:
        s = build_control_plane_run_store()
        assert isinstance(s, FirestoreControlPlaneRunStore)
        assert s._project == "fake-gcp"
        assert s._database == "(default)"
        assert s._coll_name == "ham_cp_runs_unit"
    finally:
        set_control_plane_run_store_for_tests(None)


def test_firestore_store_falls_back_to_shared_firestore_envs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HAM_CONTROL_PLANE_RUN_FIRESTORE_PROJECT_ID", raising=False)
    monkeypatch.delenv("HAM_CONTROL_PLANE_RUN_FIRESTORE_DATABASE", raising=False)
    monkeypatch.setenv("HAM_FIRESTORE_PROJECT_ID", "shared-gcp")
    monkeypatch.setenv("HAM_FIRESTORE_DATABASE", "shared-db")
    monkeypatch.delenv("HAM_CONTROL_PLANE_RUN_FIRESTORE_COLLECTION", raising=False)
    fs = FirestoreControlPlaneRunStore(client=_FakeFirestoreClient())
    assert fs._project == "shared-gcp"
    assert fs._database == "shared-db"
    assert fs._coll_name == "ham_control_plane_runs"


def test_firestore_store_default_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_CONTROL_PLANE_RUN_FIRESTORE_COLLECTION", raising=False)
    fs = FirestoreControlPlaneRunStore(client=_FakeFirestoreClient())
    assert fs._coll_name == "ham_control_plane_runs"


def test_firestore_store_satisfies_protocol(
    fake_client: _FakeFirestoreClient,
) -> None:
    fs = FirestoreControlPlaneRunStore(client=fake_client)
    assert isinstance(fs, ControlPlaneRunStoreProtocol)


def test_get_control_plane_run_store_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HAM_CONTROL_PLANE_RUN_STORE_BACKEND", raising=False)
    set_control_plane_run_store_for_tests(None)
    try:
        a = get_control_plane_run_store()
        b = get_control_plane_run_store()
        assert a is b
        assert isinstance(a, ControlPlaneRunStore)
    finally:
        set_control_plane_run_store_for_tests(None)


def test_set_control_plane_run_store_for_tests_swaps_singleton(
    fake_client: _FakeFirestoreClient,
) -> None:
    fs = FirestoreControlPlaneRunStore(client=fake_client, collection=_TEST_COLL)
    set_control_plane_run_store_for_tests(fs)
    try:
        assert get_control_plane_run_store() is fs
    finally:
        set_control_plane_run_store_for_tests(None)


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


def test_firestore_errors_are_wrapped() -> None:
    fs = FirestoreControlPlaneRunStore(client=_ExplodingClient())
    with pytest.raises(FirestoreControlPlaneRunStoreError):
        fs.get("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    with pytest.raises(FirestoreControlPlaneRunStoreError):
        fs.list_for_project("project.x-aaaaaa")
    with pytest.raises(FirestoreControlPlaneRunStoreError):
        fs.find_by_project_and_external(
            project_id="p", provider="factory_droid", external_id="x",
        )
    with pytest.raises(FirestoreControlPlaneRunStoreError):
        fs.find_by_provider_and_external(provider="factory_droid", external_id="x")
    with pytest.raises(FirestoreControlPlaneRunStoreError):
        fs.save(_new_run(), project_root_for_mirror=None)
