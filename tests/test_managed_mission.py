"""Managed mission store + v1 read API (file-backed, bounded fields)."""
from __future__ import annotations

import json
import os
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
    sync_mission_board_state_with_lifecycle,
)
from src.persistence.project_store import ProjectStore, set_project_store_for_tests
from src.integrations.cursor_cloud_client import CursorCloudApiError


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
    pp = body.get("provider_projection") or {}
    assert pp.get("mode") == "rest_projection"
    assert pp.get("native_realtime_stream") is False
    assert pp.get("status") in ("ok", "unavailable", "error")


def test_mission_feed_repeated_get_does_not_duplicate_provider_events(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="c-agent-dedupe-1",
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
    monkeypatch.setattr(cmm, "get_effective_cursor_api_key", lambda: "crsr_test_value_123456")
    monkeypatch.setattr(
        cmm,
        "cursor_api_get_agent",
        lambda **_: {"id": "c-agent-dedupe-1", "status": "RUNNING"},
    )

    def _conv(**_: object) -> dict:
        return {
            "events": [
                {
                    "id": "stable-proj-1",
                    "createdAt": "2026-01-01T00:00:00Z",
                    "type": "message",
                    "role": "assistant",
                    "message": "hello from provider",
                }
            ]
        }

    monkeypatch.setattr(cmm, "cursor_api_get_agent_conversation", _conv)
    url = f"/api/cursor/managed/missions/{mid}/feed"
    r1 = client.get(url)
    r2 = client.get(url)
    assert r1.status_code == 200 and r2.status_code == 200
    e1 = r1.json()["events"]
    e2 = r2.json()["events"]
    assert len(e1) == len(e2)
    cursor_evts = [e for e in e2 if e.get("source") == "cursor"]
    assert sum(1 for e in cursor_evts if "hello from provider" in str(e.get("message"))) == 1


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


def test_mission_message_smoke_followup_success_appends_forwarded_event(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When Cursor follow-up succeeds, feed shows instruction then forwarded (smoke for event chain)."""
    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="c-agent-followup-ok",
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
    monkeypatch.setattr(cmm, "get_effective_cursor_api_key", lambda: "test-key")
    monkeypatch.setattr(
        cmm,
        "cursor_api_followup_agent",
        lambda **kwargs: {"status": "ok"},
    )
    r = client.post(
        f"/api/cursor/managed/missions/{mid}/messages",
        json={"message": "Run the linter."},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["reason_code"] == "followup_forwarded"
    feed = client.get(f"/api/cursor/managed/missions/{mid}/feed")
    assert feed.status_code == 200
    kinds = [e.get("kind") for e in feed.json()["events"]]
    assert "followup_instruction" in kinds
    assert "followup_forwarded" in kinds
    assert "followup_rejected" not in kinds


def test_mission_message_smoke_followup_404_appends_rejected_event(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When Cursor returns 404/405/409/422, feed records followup_rejected with mission_followup_not_supported."""
    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="c-agent-followup-404",
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
    monkeypatch.setattr(cmm, "get_effective_cursor_api_key", lambda: "test-key")

    def _boom(**kwargs):
        raise CursorCloudApiError("not found", status_code=404, body_excerpt="{}")

    monkeypatch.setattr(cmm, "cursor_api_followup_agent", _boom)
    r = client.post(
        f"/api/cursor/managed/missions/{mid}/messages",
        json={"message": "Ping."},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert body["reason_code"] == "mission_followup_not_supported"
    feed = client.get(f"/api/cursor/managed/missions/{mid}/feed")
    assert feed.status_code == 200
    events = feed.json()["events"]
    kinds = [e.get("kind") for e in events]
    assert "followup_instruction" in kinds
    assert "followup_rejected" in kinds
    rejected = [e for e in events if e.get("kind") == "followup_rejected"]
    assert rejected and rejected[-1].get("reason_code") == "mission_followup_not_supported"


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


def test_mission_feed_projects_provider_conversation_events_safely(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="c-agent-provider-1",
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
    monkeypatch.setattr(cmm, "get_effective_cursor_api_key", lambda: "crsr_test_value_123456")
    monkeypatch.setattr(
        cmm,
        "cursor_api_get_agent",
        lambda **_: {"id": "c-agent-provider-1", "status": "RUNNING"},
    )
    monkeypatch.setattr(
        cmm,
        "cursor_api_get_agent_conversation",
        lambda **_: {
            "events": [
                {
                    "createdAt": "2026-01-01T00:00:00Z",
                    "type": "tool_progress",
                    "message": "Running checks with token crsr_ABCDEF1234567890",
                }
            ]
        },
    )
    r = client.get(f"/api/cursor/managed/missions/{mid}/feed")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider_projection_state"] == "ok"
    pp = body.get("provider_projection") or {}
    assert pp.get("native_realtime_stream") is False
    assert pp.get("status") == "ok"
    events = body["events"]
    assert any(e.get("kind") == "status" for e in events)
    assert all("crsr_ABCDEF1234567890" not in str(e.get("message")) for e in events)


def test_mission_feed_falls_back_when_provider_conversation_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="c-agent-provider-2",
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
    monkeypatch.setattr(cmm, "get_effective_cursor_api_key", lambda: "crsr_test_value_123456")
    monkeypatch.setattr(
        cmm,
        "cursor_api_get_agent",
        lambda **_: {"id": "c-agent-provider-2", "status": "RUNNING"},
    )

    def _raise_conv(**_: object) -> dict:
        raise cmm.CursorCloudApiError("conversation unavailable", status_code=404)

    monkeypatch.setattr(cmm, "cursor_api_get_agent_conversation", _raise_conv)
    r = client.get(f"/api/cursor/managed/missions/{mid}/feed")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider_projection_state"] == "fallback"
    assert str(body.get("provider_projection_reason", "")).startswith("provider_conversation_unavailable")
    pp = body.get("provider_projection") or {}
    assert pp.get("status") == "unavailable"
    assert pp.get("native_realtime_stream") is False
    assert isinstance(body.get("events"), list)
    assert len(body["events"]) >= 1


def test_mission_feed_uses_sdk_bridge_when_enabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="bc-sdk-1",
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
    monkeypatch.setattr(cmm, "get_effective_cursor_api_key", lambda: "crsr_test_value_123456")
    monkeypatch.setattr(cmm, "cursor_sdk_bridge_enabled", lambda: True)
    monkeypatch.setattr(
        cmm,
        "stream_cursor_sdk_bridge_events",
        lambda **_: (
            [
                {
                    "provider": "cursor",
                    "agent_id": "bc-sdk-1",
                    "run_id": "run-1",
                    "event_id": "sdk_evt_1",
                    "kind": "thinking",
                    "message": "reasoning",
                    "time": "2026-01-01T00:00:00Z",
                    "metadata": {"a": "b"},
                }
            ],
            None,
        ),
    )
    r = client.get(f"/api/cursor/managed/missions/{mid}/feed")
    assert r.status_code == 200, r.text
    body = r.json()
    pp = body.get("provider_projection") or {}
    assert pp.get("mode") == "sdk_stream_bridge"
    assert pp.get("native_realtime_stream") is True
    assert body.get("provider_projection_reason") is None
    assert any(e.get("kind") == "thinking" for e in body.get("events") or [])


def test_mission_feed_sdk_bridge_repeated_get_dedupes_by_event_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="bc-sdk-dedupe-1",
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
    monkeypatch.setattr(cmm, "get_effective_cursor_api_key", lambda: "crsr_test_value_123456")
    monkeypatch.setattr(cmm, "cursor_sdk_bridge_enabled", lambda: True)
    monkeypatch.setattr(
        cmm,
        "stream_cursor_sdk_bridge_events",
        lambda **_: (
            [
                {
                    "provider": "cursor",
                    "agent_id": "bc-sdk-dedupe-1",
                    "run_id": "run-1",
                    "event_id": "sdk_dup_evt_1",
                    "kind": "assistant_message",
                    "message": "hello",
                    "time": "2026-01-01T00:00:00Z",
                }
            ],
            None,
        ),
    )
    url = f"/api/cursor/managed/missions/{mid}/feed"
    r1 = client.get(url)
    r2 = client.get(url)
    assert r1.status_code == 200 and r2.status_code == 200
    events2 = r2.json().get("events") or []
    assert sum(1 for e in events2 if e.get("message") == "hello") == 1


def test_mission_feed_sdk_bridge_timeout_falls_back_to_rest(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="bc-sdk-fallback-1",
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
    monkeypatch.setattr(cmm, "get_effective_cursor_api_key", lambda: "crsr_test_value_123456")
    monkeypatch.setattr(cmm, "cursor_sdk_bridge_enabled", lambda: True)
    monkeypatch.setattr(cmm, "stream_cursor_sdk_bridge_events", lambda **_: ([], "provider_sdk_bridge_timeout"))
    monkeypatch.setattr(cmm, "cursor_api_get_agent", lambda **_: {"id": "bc-sdk-fallback-1", "status": "RUNNING"})
    monkeypatch.setattr(
        cmm,
        "cursor_api_get_agent_conversation",
        lambda **_: {
            "events": [
                {
                    "id": "fallback-evt",
                    "createdAt": "2026-01-01T00:00:00Z",
                    "type": "message",
                    "role": "assistant",
                    "message": "fallback event",
                }
            ]
        },
    )
    r = client.get(f"/api/cursor/managed/missions/{mid}/feed")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("provider_projection_state") == "fallback"
    assert body.get("provider_projection_reason") == "provider_sdk_bridge_timeout"
    pp = body.get("provider_projection") or {}
    assert pp.get("mode") == "rest_projection"
    assert pp.get("native_realtime_stream") is False
    assert any("fallback event" in str(e.get("message")) for e in body.get("events") or [])


def test_mission_feed_sdk_bridge_malformed_output_falls_back_to_rest(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="bc-sdk-malformed-1",
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
    monkeypatch.setattr(cmm, "get_effective_cursor_api_key", lambda: "crsr_test_value_123456")
    monkeypatch.setattr(cmm, "cursor_sdk_bridge_enabled", lambda: True)
    monkeypatch.setattr(cmm, "stream_cursor_sdk_bridge_events", lambda **_: ([{"bad": "shape"}], None))
    monkeypatch.setattr(cmm, "cursor_api_get_agent", lambda **_: {"id": "bc-sdk-malformed-1", "status": "RUNNING"})
    monkeypatch.setattr(
        cmm,
        "cursor_api_get_agent_conversation",
        lambda **_: {
            "events": [
                {
                    "id": "fallback-malformed-evt",
                    "createdAt": "2026-01-01T00:00:00Z",
                    "type": "message",
                    "role": "assistant",
                    "message": "rest fallback from malformed bridge",
                }
            ]
        },
    )
    r = client.get(f"/api/cursor/managed/missions/{mid}/feed")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("provider_projection_reason") == "provider_sdk_bridge_malformed_output"
    pp = body.get("provider_projection") or {}
    assert pp.get("mode") == "rest_projection"
    assert any("rest fallback from malformed bridge" in str(e.get("message")) for e in body.get("events") or [])


def test_managed_mission_feed_stream_404_unknown_mission(client: TestClient) -> None:
    bogus = str(uuid.uuid4())
    r = client.get(f"/api/cursor/managed/missions/{bogus}/feed/stream")
    assert r.status_code == 404


def test_managed_mission_feed_stream_content_type_and_snapshot_frame(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_MANAGED_FEED_SSE_SESSION_MAX_SECONDS", "2")
    monkeypatch.setattr(cmm, "get_effective_cursor_api_key", lambda: None)
    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="c-agent-sse-1",
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
    buf = b""
    with client.stream(
        "GET",
        f"/api/cursor/managed/missions/{mid}/feed/stream",
    ) as resp:
        assert resp.status_code == 200
        ct = resp.headers.get("content-type") or ""
        assert "text/event-stream" in ct.lower()
        for chunk in resp.iter_bytes(chunk_size=1024):
            buf += chunk
            if buf.find(b"snapshot") != -1 and buf.find(mid.encode()) != -1:
                break
            if len(buf) > 8192:
                break
    assert b"event:" in buf
    assert b"snapshot" in buf


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    cmm._store = ManagedMissionStore(base_dir=tmp_path / "missions")
    cmm.set_control_plane_run_store_for_tests(
        ControlPlaneRunStore(base_dir=tmp_path / "control_plane_runs")
    )
    with TestClient(app) as tc:
        yield tc
    cmm.set_control_plane_run_store_for_tests(None)


def test_sync_board_lane_archive_when_lifecycle_terminal() -> None:
    n = utc_now_iso()
    m = ManagedMission(
        mission_registry_id=new_mission_registry_id(),
        cursor_agent_id="x",
        control_plane_ham_run_id=None,
        mission_handling="managed",
        uplink_id=None,
        repo_key=None,
        mission_lifecycle="succeeded",
        mission_board_state="active",
        cursor_status_last_observed=None,
        status_reason_last_observed="r",
        created_at=n,
        updated_at=n,
        last_server_observed_at=n,
    )
    out = sync_mission_board_state_with_lifecycle(m)
    assert out.mission_board_state == "archive"


def test_sync_board_lane_preserves_backlog_on_terminal() -> None:
    n = utc_now_iso()
    m = ManagedMission(
        mission_registry_id=new_mission_registry_id(),
        cursor_agent_id="y",
        control_plane_ham_run_id=None,
        mission_handling="managed",
        uplink_id=None,
        repo_key=None,
        mission_lifecycle="succeeded",
        mission_board_state="backlog",
        cursor_status_last_observed=None,
        status_reason_last_observed="r",
        created_at=n,
        updated_at=n,
        last_server_observed_at=n,
    )
    out = sync_mission_board_state_with_lifecycle(m)
    assert out.mission_board_state == "backlog"


def test_managed_mission_truth_endpoint(client: TestClient) -> None:
    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="truth-agent",
            control_plane_ham_run_id=None,
            mission_handling="managed",
            uplink_id=None,
            repo_key="a/b",
            mission_lifecycle="open",
            cursor_status_last_observed=None,
            status_reason_last_observed="s",
            created_at=n,
            updated_at=n,
            last_server_observed_at=n,
        )
    )
    r = client.get(f"/api/cursor/managed/missions/{mid}/truth")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "managed_mission_truth_table"
    assert body["mission_registry_id"] == mid
    topics = [row["topic"] for row in body["rows"]]
    assert "Agent execution" in topics
    assert "Mission record & feed" in topics


def test_managed_mission_correlation_embeds_control_plane_run(
    client: TestClient,
) -> None:
    st = cmm._store
    cp = cmm._control_plane_store()
    assert st is not None
    mid = new_mission_registry_id()
    hid, run = _cp_run(eid="corr-ext-1")
    cp.save(run, project_root_for_mirror=None)
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="corr-agent-1",
            control_plane_ham_run_id=hid,
            mission_handling="managed",
            uplink_id=None,
            repo_key="a/b",
            mission_lifecycle="open",
            cursor_status_last_observed=None,
            status_reason_last_observed="s",
            created_at=n,
            updated_at=n,
            last_server_observed_at=n,
        )
    )
    r = client.get(f"/api/cursor/managed/missions/{mid}/correlation")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["control_plane_linked"] is True
    assert body.get("control_plane_run") is not None
    assert body["control_plane_run"]["ham_run_id"] == hid
    assert body["control_plane_run"]["external_id"] == "corr-ext-1"


def test_patch_mission_board_requires_write_token(client: TestClient) -> None:
    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="board-agent",
            control_plane_ham_run_id=None,
            mission_handling="managed",
            uplink_id=None,
            repo_key="a/b",
            mission_lifecycle="open",
            cursor_status_last_observed=None,
            status_reason_last_observed="s",
            created_at=n,
            updated_at=n,
            last_server_observed_at=n,
        )
    )
    prev = os.environ.pop("HAM_MANAGED_MISSION_WRITE_TOKEN", None)
    try:
        r = client.patch(
            f"/api/cursor/managed/missions/{mid}/board",
            json={"mission_board_state": "backlog"},
            headers={"Authorization": "Bearer nope"},
        )
        assert r.status_code == 403
    finally:
        if prev is not None:
            os.environ["HAM_MANAGED_MISSION_WRITE_TOKEN"] = prev


def test_patch_mission_board_with_token(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_MANAGED_MISSION_WRITE_TOKEN", "test-board-token")
    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="board-agent-2",
            control_plane_ham_run_id=None,
            mission_handling="managed",
            uplink_id=None,
            repo_key="a/b",
            mission_lifecycle="open",
            cursor_status_last_observed=None,
            status_reason_last_observed="s",
            created_at=n,
            updated_at=n,
            last_server_observed_at=n,
        )
    )
    r = client.patch(
        f"/api/cursor/managed/missions/{mid}/board",
        json={"mission_board_state": "backlog"},
        headers={"Authorization": "Bearer test-board-token"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["mission"]["mission_board_state"] == "backlog"
    kinds = [e.get("kind") for e in body["mission"].get("mission_feed_events", [])]
    assert "board_state" in kinds


def test_hermes_advisory_endpoint_records_advisory(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_MANAGED_MISSION_WRITE_TOKEN", "test-hermes-token")

    class _StubLLM:
        def call(self, _prompt: str) -> dict:
            # HermesReviewer: ok=True in output requires high confidence and empty notes after normalize.
            return {"ok": True, "confidence": "high", "notes": []}

    monkeypatch.setattr("src.llm_client.get_llm_client", lambda: _StubLLM())

    st = cmm._store
    assert st is not None
    mid = new_mission_registry_id()
    n = utc_now_iso()
    st.save(
        ManagedMission(
            mission_registry_id=mid,
            cursor_agent_id="hermes-agent-1",
            control_plane_ham_run_id=None,
            mission_handling="managed",
            uplink_id=None,
            repo_key="a/b",
            mission_lifecycle="open",
            cursor_status_last_observed=None,
            status_reason_last_observed="s",
            created_at=n,
            updated_at=n,
            last_server_observed_at=n,
        )
    )
    r = client.post(
        f"/api/cursor/managed/missions/{mid}/hermes-advisory",
        headers={"Authorization": "Bearer test-hermes-token"},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["ok"] is True
    d = client.get(f"/api/cursor/managed/missions/{mid}")
    assert d.status_code == 200
    row = d.json()
    assert row.get("hermes_advisory_triggered_at")
    assert row.get("hermes_advisory_ok") is True
