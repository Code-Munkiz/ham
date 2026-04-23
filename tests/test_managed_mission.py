"""Managed mission store + v1 read API (file-backed, bounded fields)."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api import cursor_managed_missions as cmm
from src.api.server import app
from src.persistence.control_plane_run import (
    ControlPlaneRun,
    ControlPlaneRunStore,
    utc_now_iso,
)
from src.persistence.managed_mission import (
    ManagedMission,
    ManagedMissionStore,
    map_cursor_to_mission_lifecycle,
    new_mission_registry_id,
)


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
    d = client.get(f"/api/cursor/managed/missions/{mid}")
    assert d.status_code == 200
    assert d.json()["cursor_agent_id"] == "c-agent-1"
    f = client.get("/api/cursor/managed/missions", params={"cursor_agent_id": "c-agent-1"})
    assert f.status_code == 200
    assert len(f.json()["missions"]) == 1


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    cmm._store = ManagedMissionStore(base_dir=tmp_path)
    return TestClient(app)
