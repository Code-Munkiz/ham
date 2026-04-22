"""ControlPlaneRun model + store; Cursor/Droid provider wiring (targeted)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.ham import cursor_agent_workflow as caw
from src.ham.chat_operator import ChatOperatorPayload, process_operator_turn
from src.ham.droid_workflows.preview_launch import (
    compute_proposal_digest,
    execute_droid_workflow,
)
from src.integrations.cursor_cloud_client import CursorCloudApiError
from src.persistence.control_plane_run import (
    ControlPlaneRun,
    ControlPlaneRunStore,
    cap_last_provider_status,
    map_cursor_raw_status,
    new_ham_run_id,
    utc_now_iso,
)
from src.ham.droid_workflows import build_droid_preview
from src.persistence.project_store import ProjectStore
from src.tools.droid_executor import DroidExecutionRecord


def test_store_round_trip(tmp_path: Path) -> None:
    store = ControlPlaneRunStore(base_dir=tmp_path)
    now = utc_now_iso()
    rid = new_ham_run_id()
    r = ControlPlaneRun(
        ham_run_id=rid,
        provider="factory_droid",
        action_kind="launch",
        project_id="p1",
        created_by=None,
        created_at=now,
        updated_at=now,
        committed_at=now,
        started_at=now,
        finished_at=None,
        last_observed_at=now,
        status="running",
        status_reason="test",
        proposal_digest="a" * 64,
        base_revision="v1",
        external_id="ext-1",
        workflow_id="w1",
        summary="s",
        error_summary=None,
        last_provider_status=None,
        audit_ref=None,
    )
    store.save(r, project_root_for_mirror=None)
    out = store.get(rid)
    assert out is not None
    assert out.provider == "factory_droid"
    assert out.project_id == "p1"
    assert out.proposal_digest == "a" * 64


def test_last_provider_status_capped() -> None:
    long = "x" * 300
    c = cap_last_provider_status(long)
    assert c is not None
    assert len(c) == 256
    assert c.endswith("…")


def test_map_cursor_conservative() -> None:
    assert map_cursor_raw_status("FINISHED")[0] == "succeeded"
    assert map_cursor_raw_status("FAILED")[0] == "failed"
    assert map_cursor_raw_status("CREATING")[0] == "running"
    st, rea = map_cursor_raw_status("WEIRD_UNKNOWN")
    assert st == "unknown"
    assert "unmapped" in rea


@pytest.fixture
def _cp_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "cplane"
    p.mkdir()
    monkeypatch.setenv("HAM_CONTROL_PLANE_RUNS_DIR", str(p))
    return p


@pytest.fixture
def _launch_tok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CURSOR_AGENT_LAUNCH_TOKEN", "launch-secret")


def _register_project(store: ProjectStore, tmp_path: Path) -> ProjectRecord:
    rec = store.make_record(
        name="t",
        root=str(tmp_path / "repo"),
        metadata={"cursor_cloud_repository": "https://github.com/o/r"},
    )
    (tmp_path / "repo").mkdir()
    store.register(rec)
    return rec


@patch.object(caw, "cursor_api_launch_agent")
def test_cursor_committed_launch_success_creates_run(
    mock_launch: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _cp_dir: Path,
    _launch_tok: None,
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    store = ProjectStore(tmp_path / "p.json")
    rec = _register_project(store, tmp_path)
    digest = caw.compute_cursor_proposal_digest(
        project_id=rec.id,
        repository="https://github.com/o/r",
        ref=None,
        model="default",
        auto_create_pr=False,
        branch_name=None,
        expected_deliverable=None,
        task_prompt="fix tests",
    )
    mock_launch.return_value = {
        "id": "bc_xyz",
        "status": "CREATING",
        "summary": "started",
    }
    op = ChatOperatorPayload(
        phase="cursor_agent_launch",
        confirmed=True,
        project_id=rec.id,
        cursor_task_prompt="fix tests",
        cursor_proposal_digest=digest,
        cursor_base_revision="cursor-agent-v1",
    )
    out = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=op,
        ham_operator_authorization="Bearer launch-secret",
    )
    assert out and out.ok
    hid = out.data.get("ham_run_id")
    assert isinstance(hid, str) and len(hid) == 36
    st = ControlPlaneRunStore()
    run = st.get(hid)
    assert run is not None
    assert run.provider == "cursor_cloud_agent"
    assert run.status == "running"
    assert run.external_id == "bc_xyz"
    assert run.proposal_digest == digest


@patch.object(caw, "cursor_api_launch_agent")
def test_cursor_committed_launch_api_failure_creates_failed_row(
    mock_launch: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _cp_dir: Path,
    _launch_tok: None,
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    store = ProjectStore(tmp_path / "p.json")
    rec = _register_project(store, tmp_path)
    digest = caw.compute_cursor_proposal_digest(
        project_id=rec.id,
        repository="https://github.com/o/r",
        ref=None,
        model="default",
        auto_create_pr=False,
        branch_name=None,
        expected_deliverable=None,
        task_prompt="x",
    )
    mock_launch.side_effect = CursorCloudApiError("bad", status_code=500, body_excerpt="{}")
    op = ChatOperatorPayload(
        phase="cursor_agent_launch",
        confirmed=True,
        project_id=rec.id,
        cursor_task_prompt="x",
        cursor_proposal_digest=digest,
        cursor_base_revision="cursor-agent-v1",
    )
    out = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=op,
        ham_operator_authorization="Bearer launch-secret",
    )
    assert out and not out.ok
    hid = out.data.get("ham_run_id")
    assert isinstance(hid, str)
    st = ControlPlaneRunStore()
    run = st.get(hid)
    assert run is not None
    assert run.status == "failed"
    assert run.error_summary


def test_droid_launch_digest_mismatch_no_control_plane_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cp = tmp_path / "cp"
    cp.mkdir()
    monkeypatch.setenv("HAM_CONTROL_PLANE_RUNS_DIR", str(cp))
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    store = ProjectStore(tmp_path / "p.json")
    rec = _register_project(store, tmp_path)
    prev = build_droid_preview(
        workflow_id="readonly_repo_audit",
        project_id=rec.id,
        project_root=Path(rec.root),
        user_prompt="audit",
    )
    assert prev.ok
    op = ChatOperatorPayload(
        phase="droid_launch",
        confirmed=True,
        project_id=rec.id,
        droid_workflow_id="readonly_repo_audit",
        droid_user_prompt=prev.user_prompt,
        droid_proposal_digest="0" * 64,
        droid_base_revision=prev.base_revision,
    )
    out = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=op,
        ham_operator_authorization=None,
    )
    assert out and not out.ok
    assert not list(cp.glob("*.json"))


@patch("src.ham.droid_workflows.preview_launch.run_droid_argv")
def test_droid_success_persists_run(
    mock_run: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cp = tmp_path / "cp"
    cp.mkdir()
    monkeypatch.setenv("HAM_CONTROL_PLANE_RUNS_DIR", str(cp))
    root = tmp_path / "r"
    root.mkdir()
    pid = "project.droid-1"
    d = compute_proposal_digest(
        workflow_id="readonly_repo_audit",
        project_id=pid,
        cwd=str(root.resolve()),
        user_prompt="audit",
    )
    mock_run.return_value = DroidExecutionRecord(
        argv=["droid", "exec"],
        working_dir=str(root),
        exit_code=0,
        timed_out=False,
        stdout=json.dumps({"result": "ok", "session_id": "sess-99"}),
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        started_at="",
        ended_at="",
        duration_ms=5,
    )
    out = execute_droid_workflow(
        workflow_id="readonly_repo_audit",
        project_root=root,
        user_prompt="audit",
        project_id=pid,
        proposal_digest=d,
    )
    assert out.ok
    assert out.ham_run_id
    assert out.control_plane_status == "succeeded"
    st = ControlPlaneRunStore()
    rec = st.get(out.ham_run_id)
    assert rec is not None
    assert rec.provider == "factory_droid"
    assert rec.status == "succeeded"
    assert rec.external_id == "sess-99"
    assert rec.workflow_id == "readonly_repo_audit"


@patch("src.ham.droid_workflows.preview_launch.run_droid_argv")
def test_droid_nonzero_exit_failed(
    mock_run: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cp = tmp_path / "cp"
    cp.mkdir()
    monkeypatch.setenv("HAM_CONTROL_PLANE_RUNS_DIR", str(cp))
    root = tmp_path / "r2"
    root.mkdir()
    pid = "project.droid-2"
    d = compute_proposal_digest(
        workflow_id="readonly_repo_audit",
        project_id=pid,
        cwd=str(root.resolve()),
        user_prompt="x",
    )
    mock_run.return_value = DroidExecutionRecord(
        argv=["droid", "exec"],
        working_dir=str(root),
        exit_code=1,
        timed_out=False,
        stdout="",
        stderr="nope",
        stdout_truncated=False,
        stderr_truncated=False,
        started_at="",
        ended_at="",
        duration_ms=3,
    )
    out = execute_droid_workflow(
        workflow_id="readonly_repo_audit",
        project_root=root,
        user_prompt="x",
        project_id=pid,
        proposal_digest=d,
    )
    assert not out.ok
    assert out.control_plane_status == "failed"
    st = ControlPlaneRunStore()
    r = st.get(out.ham_run_id or "")
    assert r is not None
    assert r.status == "failed"


@patch.object(caw, "cursor_api_launch_agent")
@patch.object(caw, "cursor_api_get_agent")
def test_cursor_status_updates_existing_row(
    mock_get: object,
    mock_launch: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _cp_dir: Path,
    _launch_tok: None,
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    store = ProjectStore(tmp_path / "p.json")
    rec = _register_project(store, tmp_path)
    digest = caw.compute_cursor_proposal_digest(
        project_id=rec.id,
        repository="https://github.com/o/r",
        ref=None,
        model="default",
        auto_create_pr=False,
        branch_name=None,
        expected_deliverable=None,
        task_prompt="fix tests",
    )
    mock_launch.return_value = {
        "id": "bc_status",
        "status": "CREATING",
        "summary": "started",
    }
    out1 = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=ChatOperatorPayload(
            phase="cursor_agent_launch",
            confirmed=True,
            project_id=rec.id,
            cursor_task_prompt="fix tests",
            cursor_proposal_digest=digest,
            cursor_base_revision="cursor-agent-v1",
        ),
        ham_operator_authorization="Bearer launch-secret",
    )
    assert out1 and out1.ok
    hid = out1.data.get("ham_run_id")
    st0 = ControlPlaneRunStore()
    r0 = st0.get(str(hid))
    assert r0 is not None
    lo0 = r0.last_observed_at
    assert lo0
    mock_get.return_value = {
        "id": "bc_status",
        "status": "FINISHED",
        "summary": "all good",
    }
    out2 = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=ChatOperatorPayload(
            phase="cursor_agent_status",
            project_id=rec.id,
            cursor_agent_id="bc_status",
        ),
        ham_operator_authorization=None,
    )
    assert out2 and out2.ok
    st1 = ControlPlaneRunStore()
    r1 = st1.get(str(hid))
    assert r1 is not None
    assert r1.status == "succeeded"
    assert r1.last_provider_status == "FINISHED"
    assert r1.last_observed_at
    if lo0:
        assert r1.last_observed_at >= lo0
    assert r1.ham_run_id == str(hid)


@patch("src.ham.chat_operator.execute_droid_workflow")
def test_operator_droid_includes_ham_run_id_in_data(
    mock_ex: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.ham.droid_workflows.preview_launch import DroidLaunchResult

    monkeypatch.setenv("HAM_DROID_EXEC_TOKEN", "tok")
    repo = tmp_path / "repo"
    repo.mkdir()
    store = ProjectStore(tmp_path / "store.json")
    rec = store.make_record(
        name="p",
        root=str(repo),
        metadata={},
    )
    store.register(rec)
    prev = build_droid_preview(
        workflow_id="readonly_repo_audit",
        project_id=rec.id,
        project_root=repo,
        user_prompt="audit",
    )
    assert prev.ok
    mock_ex.return_value = DroidLaunchResult(
        ok=True,
        blocking_reason=None,
        workflow_id="readonly_repo_audit",
        audit_id="a1",
        runner_id="local",
        cwd=str(repo.resolve()),
        exit_code=0,
        duration_ms=1,
        summary="s",
        stdout="",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        parsed_json={},
        session_id="session-z",
        timed_out=False,
        ham_run_id="00000000-0000-0000-0000-00000000abcd",
        control_plane_status="succeeded",
    )
    out = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=ChatOperatorPayload(
            phase="droid_launch",
            confirmed=True,
            project_id=rec.id,
            droid_workflow_id="readonly_repo_audit",
            droid_user_prompt=prev.user_prompt,
            droid_proposal_digest=prev.proposal_digest,
            droid_base_revision=prev.base_revision,
        ),
        ham_operator_authorization="Bearer tok",
    )
    assert out and out.data.get("ham_run_id") == "00000000-0000-0000-0000-00000000abcd"
    assert out.data.get("control_plane_status") == "succeeded"
    assert out.data.get("external_id") == "session-z"
    assert out.data.get("provider") == "factory_droid"
