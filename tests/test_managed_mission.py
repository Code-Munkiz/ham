"""Managed mission store + v1 read API (file-backed, bounded fields)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api import cursor_managed_missions as cmm
from src.api.server import app
from src.ham.managed_mission_wiring import (
    create_mission_after_managed_launch,
    set_managed_mission_store_for_tests,
)
from src.persistence.control_plane_run import (
    ControlPlaneRun,
    ControlPlaneRunStore,
    utc_now_iso,
)
from src.persistence.managed_mission import (
    ManagedMission,
    ManagedMissionStore,
    append_mission_checkpoint_event,
    derive_mission_checkpoint,
    map_cursor_to_mission_lifecycle,
    new_mission_registry_id,
)
from src.persistence.project_store import ProjectStore, set_project_store_for_tests


def _cp_run(*, eid: str) -> str:
    now = utc_now_iso()
    hid = str(uuid.uuid4())
    r = ControlPlaneRun(
        ham_run_id=hid,
        provider="cursor_cloud_agent",
        action_kind="launch",
        project_id="p-test",
        created_by=None,
        created_at=now,
        updated_at=now,
        committed_at=now,
        started_at=now,
        finished_at=None,
        last_observed_at=now,
        status="running",
        status_reason="t",
        proposal_digest="a" * 64,
        base_revision="v1",
        external_id=eid,
        workflow_id=None,
        summary="s",
        error_summary=None,
        last_provider_status="RUNNING",
        audit_ref=None,
        project_root=None,
    )
    return hid, r


def test_find_by_provider_and_external(tmp_path: Path) -> None:
    store = ControlPlaneRunStore(base_dir=tmp_path)
    eid = "agt-ext-1"
    hid, run = _cp_run(eid=eid)
    store.save(run, project_root_for_mirror=None)
    found = store.find_by_provider_and_external(
        provider="cursor_cloud_agent",
        external_id=eid,
    )
    assert found is not None
    assert found.ham_run_id == hid


def test_mission_lifecycle_sticky() -> None:
    lc, reason = map_cursor_to_mission_lifecycle(
        current="succeeded",
        cursor_status_raw="RUNNING",
        previous_reason="mapped:FINISHED",
    )
    assert lc == "succeeded"
    assert reason == "mapped:FINISHED"


def test_derive_checkpoint_pr_opened_from_completed_with_pr() -> None:
    cp, reason = derive_mission_checkpoint(
        mission_lifecycle="open",
        cursor_status_raw="FINISHED",
        status_reason=None,
        pr_url="https://github.com/o/r/pull/12",
        previous_checkpoint=None,
    )
    assert cp == "pr_opened"
    assert reason == "cursor_completed_with_pr"


def test_derive_checkpoint_blocked_from_reason_context() -> None:
    cp, reason = derive_mission_checkpoint(
        mission_lifecycle="open",
        cursor_status_raw="RUNNING",
        status_reason="policy: awaiting approval from operator",
        pr_url=None,
        previous_checkpoint="running",
    )
    assert cp == "blocked"
    assert reason == "status_reason_blocked"


def test_append_checkpoint_events_is_capped() -> None:
    events = []
    for i in range(30):
        events = append_mission_checkpoint_event(
            existing=events,
            checkpoint="running",
            observed_at=f"2026-01-01T00:00:{i:02d}Z",
            reason=f"tick-{i}",
        )
    assert len(events) == 24
    assert events[0].reason == "tick-6"
    assert events[-1].reason == "tick-29"


def test_mission_store_roundtrip(tmp_path: Path) -> None:
    st = ManagedMissionStore(base_dir=tmp_path)
    mid = new_mission_registry_id()
    n = utc_now_iso()
    m = ManagedMission(
        mission_registry_id=mid,
        cursor_agent_id="a1",
        control_plane_ham_run_id=None,
        mission_handling="managed",
        uplink_id=None,
        repo_key="o/r",
        mission_lifecycle="open",
        cursor_status_last_observed="PENDING",
        status_reason_last_observed="r",
        created_at=n,
        updated_at=n,
        last_server_observed_at=n,
    )
    st.save(m)
    m2 = st.get(mid)
    assert m2 is not None
    assert m2.cursor_agent_id == "a1"
    f = st.find_by_cursor_agent_id("a1")
    assert f is not None
    assert f.mission_registry_id == mid
    assert f.mission_deploy_approval_mode == "off"


@pytest.fixture
def isolated_stores(tmp_path: Path):
    m = ManagedMissionStore(base_dir=tmp_path / "missions")
    p = ProjectStore(store_path=tmp_path / "projects.json")
    set_managed_mission_store_for_tests(m)
    set_project_store_for_tests(p)
    yield m, p
    set_managed_mission_store_for_tests(None)
    set_project_store_for_tests(None)


def _register_project(
    pstore: ProjectStore,
    *,
    name: str,
    root: Path,
    default_mode: str | None,
) -> str:
    root.mkdir(parents=True, exist_ok=True)
    meta: dict = {}
    if default_mode is not None:
        meta["default_deploy_approval_mode"] = default_mode
    rec = pstore.make_record(name=name, root=str(root), metadata=meta)
    pstore.register(rec)
    return rec.id


def test_managed_create_no_project_yields_off(isolated_stores) -> None:
    m, _p = isolated_stores
    create_mission_after_managed_launch(
        mission_handling="managed",
        launch_response={"id": "ag-no-proj-1"},
        body_repository="https://github.com/o/r",
        body_ref="main",
        body_branch_name=None,
        project_id=None,
    )
    row = m.find_by_cursor_agent_id("ag-no-proj-1")
    assert row is not None
    assert row.mission_deploy_approval_mode == "off"


def test_managed_create_invalid_project_metadata_default_yields_off(
    isolated_stores, tmp_path: Path
) -> None:
    m, p = isolated_stores
    pid = _register_project(
        p, name="pbad", root=tmp_path / "rbad", default_mode="not-a-mode"
    )
    create_mission_after_managed_launch(
        mission_handling="managed",
        launch_response={"id": "ag-bad-meta-1"},
        body_repository="https://github.com/o/r",
        body_ref=None,
        body_branch_name=None,
        project_id=pid,
    )
    row = m.find_by_cursor_agent_id("ag-bad-meta-1")
    assert row is not None
    assert row.mission_deploy_approval_mode == "off"


def test_managed_create_unknown_project_id_yields_off(isolated_stores) -> None:
    m, _p = isolated_stores
    create_mission_after_managed_launch(
        mission_handling="managed",
        launch_response={"id": "ag-bad-pid-1"},
        body_repository="https://github.com/o/r",
        body_ref="main",
        body_branch_name=None,
        project_id="project.unknown-ffffff",
    )
    row = m.find_by_cursor_agent_id("ag-bad-pid-1")
    assert row is not None
    assert row.mission_deploy_approval_mode == "off"


def test_managed_create_inherits_project_default_audit(isolated_stores, tmp_path: Path) -> None:
    m, p = isolated_stores
    pid = _register_project(
        p, name="p1", root=tmp_path / "repo-a", default_mode="audit"
    )
    create_mission_after_managed_launch(
        mission_handling="managed",
        launch_response={"id": "ag-audit-1"},
        body_repository="https://github.com/o/r",
        body_ref="main",
        body_branch_name=None,
        project_id=pid,
    )
    row = m.find_by_cursor_agent_id("ag-audit-1")
    assert row is not None
    assert row.mission_deploy_approval_mode == "audit"


def test_managed_create_inherits_soft_and_hard(isolated_stores, tmp_path: Path) -> None:
    m, p = isolated_stores
    pid_soft = _register_project(
        p, name="p-soft", root=tmp_path / "rs", default_mode="soft"
    )
    create_mission_after_managed_launch(
        mission_handling="managed",
        launch_response={"id": "ag-soft-1"},
        body_repository="https://github.com/o/r",
        body_ref=None,
        body_branch_name=None,
        project_id=pid_soft,
    )
    s = m.find_by_cursor_agent_id("ag-soft-1")
    assert s is not None
    assert s.mission_deploy_approval_mode == "soft"

    pid_hard = _register_project(
        p, name="p-hard", root=tmp_path / "rh", default_mode="hard"
    )
    create_mission_after_managed_launch(
        mission_handling="managed",
        launch_response={"id": "ag-hard-1"},
        body_repository="https://github.com/o/r2",
        body_ref=None,
        body_branch_name=None,
        project_id=pid_hard,
    )
    h = m.find_by_cursor_agent_id("ag-hard-1")
    assert h is not None
    assert h.mission_deploy_approval_mode == "hard"


def test_changing_project_default_after_create_does_not_mutate_mission(
    isolated_stores, tmp_path: Path
) -> None:
    m, p = isolated_stores
    rdir = tmp_path / "rmut"
    pid = _register_project(p, name="pmut", root=rdir, default_mode="audit")
    create_mission_after_managed_launch(
        mission_handling="managed",
        launch_response={"id": "ag-mut-1"},
        body_repository="https://github.com/o/r",
        body_ref="main",
        body_branch_name=None,
        project_id=pid,
    )
    rec = p.get_project(pid)
    assert rec is not None
    p.register(rec.model_copy(update={"metadata": {**rec.metadata, "default_deploy_approval_mode": "hard"}}))
    row = m.find_by_cursor_agent_id("ag-mut-1")
    assert row is not None
    assert row.mission_deploy_approval_mode == "audit"
    m2 = m.get(row.mission_registry_id)
    assert m2 is not None
    assert m2.mission_deploy_approval_mode == "audit"


def test_legacy_mission_json_without_approval_mode_loads_as_off(tmp_path: Path) -> None:
    st = ManagedMissionStore(base_dir=tmp_path)
    mid = new_mission_registry_id()
    n = utc_now_iso()
    raw = {
        "mission_registry_id": mid,
        "cursor_agent_id": "leg-z",
        "control_plane_ham_run_id": None,
        "mission_handling": "managed",
        "uplink_id": None,
        "repo_key": "a/b",
        "repository_observed": None,
        "ref_observed": None,
        "branch_name_launch": None,
        "mission_lifecycle": "open",
        "cursor_status_last_observed": None,
        "status_reason_last_observed": "x",
        "created_at": n,
        "updated_at": n,
        "last_server_observed_at": n,
    }
    (st.base_path / f"{mid}.json").write_text(json.dumps(raw), encoding="utf-8")
    got = st.get(mid)
    assert got is not None
    assert got.mission_deploy_approval_mode == "off"


def test_non_managed_launch_does_not_create_mission(isolated_stores) -> None:
    m, _p = isolated_stores
    create_mission_after_managed_launch(
        mission_handling="direct",
        launch_response={"id": "ag-dir-1"},
        body_repository="https://github.com/o/r",
        body_ref="main",
        body_branch_name=None,
        project_id="any-project",
    )
    assert m.find_by_cursor_agent_id("ag-dir-1") is None


def test_missions_list_api(client: TestClient) -> None:
    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="c-agent-1",
            control_plane_ham_run_id=None,
            mission_handling="managed",
            uplink_id="u1",
            repo_key="a/b",
            mission_lifecycle="open",
            cursor_status_last_observed=None,
            status_reason_last_observed="s",
            created_at=n,
            updated_at=n,
            last_server_observed_at=n,
        )
    )
    r = client.get("/api/cursor/managed/missions", params={"limit": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "managed_mission_list"
    assert len(body["missions"]) == 1
    assert body["missions"][0]["mission_registry_id"] == mid
    assert body["missions"][0]["latest_checkpoint"] is None
    assert isinstance(body["missions"][0]["checkpoint_events"], list)
    d = client.get(f"/api/cursor/managed/missions/{mid}")
    assert d.status_code == 200
    assert d.json()["cursor_agent_id"] == "c-agent-1"
    f = client.get("/api/cursor/managed/missions", params={"cursor_agent_id": "c-agent-1"})
    assert f.status_code == 200
    assert len(f.json()["missions"]) == 1


def test_mission_feed_endpoint_returns_events(client: TestClient) -> None:
    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="c-agent-feed-1",
            control_plane_ham_run_id=None,
            mission_handling="managed",
            uplink_id=None,
            repo_key="a/b",
            repository_observed="Code-Munkiz/ham",
            ref_observed="main",
            mission_lifecycle="open",
            cursor_status_last_observed="RUNNING",
            status_reason_last_observed="mapped:RUNNING",
            created_at=n,
            updated_at=n,
            last_server_observed_at=n,
        )
    )
    r = client.get(f"/api/cursor/managed/missions/{mid}/feed")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mission_id"] == mid
    assert isinstance(body["events"], list)
    assert len(body["events"]) >= 1
    assert body["events"][0]["kind"] in ("mission_started", "checkpoint")


def test_mission_message_endpoint_records_followup_when_provider_unsupported(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="c-agent-followup-1",
            control_plane_ham_run_id=None,
            mission_handling="managed",
            uplink_id=None,
            repo_key="a/b",
            mission_lifecycle="open",
            cursor_status_last_observed="RUNNING",
            status_reason_last_observed="mapped:RUNNING",
            created_at=n,
            updated_at=n,
            last_server_observed_at=n,
        )
    )
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.setattr(cmm, "get_effective_cursor_api_key", lambda: None)
    r = client.post(
        f"/api/cursor/managed/missions/{mid}/messages",
        json={"message": "Please run tests before finishing."},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert body["reason_code"] in ("provider_followup_not_supported", "mission_followup_not_supported")
    feed = client.get(f"/api/cursor/managed/missions/{mid}/feed")
    assert feed.status_code == 200
    events = feed.json()["events"]
    assert any(e.get("kind") == "followup_instruction" for e in events)


def test_mission_cancel_endpoint_returns_stable_unsupported_reason(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="c-agent-cancel-1",
            control_plane_ham_run_id=None,
            mission_handling="managed",
            uplink_id=None,
            repo_key="a/b",
            mission_lifecycle="open",
            cursor_status_last_observed="RUNNING",
            status_reason_last_observed="mapped:RUNNING",
            created_at=n,
            updated_at=n,
            last_server_observed_at=n,
        )
    )
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.setattr(cmm, "get_effective_cursor_api_key", lambda: None)
    r = client.post(f"/api/cursor/managed/missions/{mid}/cancel")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert body["reason_code"] == "cancel_not_supported"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    cmm._store = ManagedMissionStore(base_dir=tmp_path)
    return TestClient(app)
