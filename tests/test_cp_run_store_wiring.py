"""Regression tests for Tier 1 persistence fix: every ControlPlaneRun write/read
path must go through get_control_plane_run_store() so the configured backend
(file or Firestore) is respected.

Before this fix, several callsites directly instantiated ControlPlaneRunStore()
which always hit the file backend regardless of HAM_CONTROL_PLANE_RUN_STORE_BACKEND.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.persistence.control_plane_run import (
    ControlPlaneRun,
    ControlPlaneRunStore,
    get_control_plane_run_store,
    set_control_plane_run_store_for_tests,
    utc_now_iso,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(*, ham_run_id: str | None = None, provider: str = "cursor_cloud_agent") -> ControlPlaneRun:
    now = utc_now_iso()
    hid = ham_run_id or str(uuid.uuid4())
    return ControlPlaneRun(
        ham_run_id=hid,
        provider=provider,
        action_kind="launch",
        project_id="project.test-wiring",
        created_by=None,
        created_at=now,
        updated_at=now,
        committed_at=now,
        started_at=now,
        finished_at=None,
        last_observed_at=now,
        status="running",
        status_reason="none",
        proposal_digest="a" * 64,
        base_revision="cursor-agent-v2",
        external_id="ext-abc",
        workflow_id=None,
        summary=None,
        error_summary=None,
        last_provider_status=None,
        audit_ref=None,
        output_target="managed_workspace",
    )


# ---------------------------------------------------------------------------
# 1. cursor_agent_workflow — run_cursor_agent_launch uses configured store
# ---------------------------------------------------------------------------


def test_cursor_agent_launch_uses_configured_store(tmp_path: Path) -> None:
    """When no store is injected, run_cursor_agent_launch must route writes
    through get_control_plane_run_store(), not a bare ControlPlaneRunStore()."""
    from src.ham.cursor_agent_workflow import run_cursor_agent_launch
    from src.integrations.cursor_cloud_client import CursorCloudApiError

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    injected = ControlPlaneRunStore(base_dir=runs_dir)
    set_control_plane_run_store_for_tests(injected)
    try:
        # Simulate a launch that fails immediately at the API call so we still
        # get a ControlPlaneRun row persisted with status="failed".
        with patch(
            "src.ham.cursor_agent_workflow.cursor_api_launch_agent",
            side_effect=CursorCloudApiError("rate limited", status_code=429),
        ):
            ok, payload, blocking, ham_run_id = run_cursor_agent_launch(
                api_key="fake-key",
                project_id="project.wiring-test",
                repository="org/repo",
                ref=None,
                model="default",
                auto_create_pr=False,
                branch_name=None,
                expected_deliverable=None,
                task_prompt="tidy docs",
                proposal_digest="b" * 64,
                project_root_for_mirror=None,
            )
        assert not ok
        assert ham_run_id is not None
        row = injected.get(ham_run_id)
        assert row is not None, "row must be persisted in the injected store"
        assert row.status == "failed"
        assert row.provider == "cursor_cloud_agent"
    finally:
        set_control_plane_run_store_for_tests(None)


def test_cursor_agent_launch_injected_store_wins(tmp_path: Path) -> None:
    """An explicit control_plane_run_store= arg takes precedence over the singleton."""
    from src.ham.cursor_agent_workflow import run_cursor_agent_launch
    from src.integrations.cursor_cloud_client import CursorCloudApiError

    global_dir = tmp_path / "global"
    global_dir.mkdir()
    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    global_store = ControlPlaneRunStore(base_dir=global_dir)
    explicit_store = ControlPlaneRunStore(base_dir=explicit_dir)
    set_control_plane_run_store_for_tests(global_store)
    try:
        with patch(
            "src.ham.cursor_agent_workflow.cursor_api_launch_agent",
            side_effect=CursorCloudApiError("bad", status_code=400),
        ):
            _, _, _, ham_run_id = run_cursor_agent_launch(
                api_key="x",
                project_id="project.x",
                repository="o/r",
                ref=None,
                model="default",
                auto_create_pr=False,
                branch_name=None,
                expected_deliverable=None,
                task_prompt="t",
                proposal_digest="c" * 64,
                project_root_for_mirror=None,
                control_plane_run_store=explicit_store,
            )
        assert ham_run_id is not None
        assert explicit_store.get(ham_run_id) is not None
        assert global_store.get(ham_run_id) is None, "global store must not receive the row"
    finally:
        set_control_plane_run_store_for_tests(None)


# ---------------------------------------------------------------------------
# 2. cursor_agent_workflow — run_cursor_agent_status uses configured store
# ---------------------------------------------------------------------------


def test_cursor_agent_status_uses_configured_store(tmp_path: Path) -> None:
    """run_cursor_agent_status without an injected store routes through
    get_control_plane_run_store()."""
    from src.ham.cursor_agent_workflow import run_cursor_agent_status
    from src.integrations.cursor_cloud_client import CursorCloudApiError

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    injected = ControlPlaneRunStore(base_dir=runs_dir)
    # Pre-seed a run so the status path can find an existing row to update.
    existing = _make_run()
    injected.save(existing)
    set_control_plane_run_store_for_tests(injected)
    try:
        with patch(
            "src.ham.cursor_agent_workflow.cursor_api_get_agent",
            side_effect=CursorCloudApiError("timeout", status_code=504),
        ):
            ok, _, _, rid = run_cursor_agent_status(
                api_key="fake",
                project_id="project.test-wiring",
                agent_id="ext-abc",
                project_root_for_mirror=None,
            )
        # On API error the existing row is updated in the injected store.
        assert rid == existing.ham_run_id
        updated = injected.get(existing.ham_run_id)
        assert updated is not None
        assert updated.status == "unknown"
    finally:
        set_control_plane_run_store_for_tests(None)


# ---------------------------------------------------------------------------
# 3. chat_operator._mission_project_id uses configured store
# ---------------------------------------------------------------------------


def test_mission_project_id_uses_configured_store(tmp_path: Path) -> None:
    """_mission_project_id must read from get_control_plane_run_store(), not a
    bare ControlPlaneRunStore()."""
    from src.ham.chat_operator import _mission_project_id
    from src.persistence.managed_mission import (
        ManagedMission,
        new_mission_registry_id,
    )

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    injected = ControlPlaneRunStore(base_dir=runs_dir)
    run = _make_run()
    run_with_project = run.model_copy(update={"project_id": "project.chat-op-test"})
    injected.save(run_with_project)
    set_control_plane_run_store_for_tests(injected)
    try:
        now = utc_now_iso()
        mission = ManagedMission(
            mission_registry_id=new_mission_registry_id(),
            cursor_agent_id="ext-abc",
            control_plane_ham_run_id=run_with_project.ham_run_id,
            mission_handling="managed",
            uplink_id=None,
            repo_key=None,
            mission_lifecycle="open",
            created_at=now,
            updated_at=now,
            last_server_observed_at=now,
        )
        pid = _mission_project_id(mission)
        assert pid == "project.chat-op-test"
    finally:
        set_control_plane_run_store_for_tests(None)


def test_mission_project_id_returns_none_when_store_has_no_row(tmp_path: Path) -> None:
    """_mission_project_id returns None when the run_id is absent from the configured store."""
    from src.ham.chat_operator import _mission_project_id
    from src.persistence.managed_mission import ManagedMission, new_mission_registry_id

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    injected = ControlPlaneRunStore(base_dir=empty_dir)
    set_control_plane_run_store_for_tests(injected)
    try:
        now = utc_now_iso()
        mission = ManagedMission(
            mission_registry_id=new_mission_registry_id(),
            cursor_agent_id="ext-abc",
            control_plane_ham_run_id=str(uuid.uuid4()),
            mission_handling="managed",
            uplink_id=None,
            repo_key=None,
            mission_lifecycle="open",
            created_at=now,
            updated_at=now,
            last_server_observed_at=now,
        )
        assert _mission_project_id(mission) is None
    finally:
        set_control_plane_run_store_for_tests(None)


# ---------------------------------------------------------------------------
# 4. managed_mission_wiring.try_control_plane_ham_run_id uses configured store
# ---------------------------------------------------------------------------


def test_try_control_plane_ham_run_id_uses_configured_store(tmp_path: Path) -> None:
    """try_control_plane_ham_run_id must read from get_control_plane_run_store()."""
    from src.ham.managed_mission_wiring import try_control_plane_ham_run_id

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    injected = ControlPlaneRunStore(base_dir=runs_dir)
    run = _make_run()
    injected.save(run)
    set_control_plane_run_store_for_tests(injected)
    try:
        result = try_control_plane_ham_run_id(agent_id=run.external_id or "ext-abc")
        assert result == run.ham_run_id
    finally:
        set_control_plane_run_store_for_tests(None)


def test_try_control_plane_ham_run_id_returns_none_for_unknown_agent(tmp_path: Path) -> None:
    from src.ham.managed_mission_wiring import try_control_plane_ham_run_id

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    injected = ControlPlaneRunStore(base_dir=runs_dir)
    set_control_plane_run_store_for_tests(injected)
    try:
        assert try_control_plane_ham_run_id(agent_id="nonexistent-agent-id") is None
    finally:
        set_control_plane_run_store_for_tests(None)


# ---------------------------------------------------------------------------
# 5. HermesGatewayBroker reads from configured store
# ---------------------------------------------------------------------------


def test_hermes_gateway_broker_uses_configured_store(tmp_path: Path) -> None:
    """HermesGatewayBroker must build its _cp_store from get_control_plane_run_store()
    so the gateway snapshot reflects Firestore-backed runs, not file-backed ones."""
    from src.ham.hermes_gateway.broker import HermesGatewayBroker

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    injected = ControlPlaneRunStore(base_dir=runs_dir)
    set_control_plane_run_store_for_tests(injected)
    try:
        broker = HermesGatewayBroker()
        assert broker._cp_store is injected
    finally:
        set_control_plane_run_store_for_tests(None)


# ---------------------------------------------------------------------------
# 6. cursor_managed_missions._control_plane_store delegates to global singleton
# ---------------------------------------------------------------------------


def test_cursor_managed_missions_store_delegates_to_global(tmp_path: Path) -> None:
    """_control_plane_store() in cursor_managed_missions must return the global
    singleton store, not create its own ControlPlaneRunStore() instance."""
    from src.api import cursor_managed_missions as cmm

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    injected = ControlPlaneRunStore(base_dir=runs_dir)
    cmm.set_control_plane_run_store_for_tests(injected)
    try:
        assert cmm._control_plane_store() is injected
        assert get_control_plane_run_store() is injected
    finally:
        cmm.set_control_plane_run_store_for_tests(None)


def test_cursor_managed_missions_set_hook_clears_global(tmp_path: Path) -> None:
    """cmm.set_control_plane_run_store_for_tests(None) must reset the global singleton."""
    from src.api import cursor_managed_missions as cmm

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    injected = ControlPlaneRunStore(base_dir=runs_dir)
    cmm.set_control_plane_run_store_for_tests(injected)
    cmm.set_control_plane_run_store_for_tests(None)
    # After reset the singleton is None; next call rebuilds from env.
    from src.persistence.control_plane_run import _cp_run_store_singleton
    assert _cp_run_store_singleton is None


# ---------------------------------------------------------------------------
# 7. execute_droid_workflow uses configured store when none is injected
# ---------------------------------------------------------------------------


def test_execute_droid_workflow_uses_configured_store(tmp_path: Path) -> None:
    """execute_droid_workflow without explicit store must dispatch through
    get_control_plane_run_store(), not bare ControlPlaneRunStore()."""
    from src.ham.droid_workflows.preview_launch import execute_droid_workflow

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    project_root = tmp_path / "project"
    project_root.mkdir()

    injected = ControlPlaneRunStore(base_dir=runs_dir)
    set_control_plane_run_store_for_tests(injected)
    try:
        with patch(
            "src.ham.droid_workflows.preview_launch.run_droid_argv",
            return_value=MagicMock(
                exit_code=0,
                timed_out=False,
                stdout='{"result": "ok"}',
                stderr="",
                stdout_truncated=False,
                stderr_truncated=False,
                started_at="t0",
                ended_at="t1",
                duration_ms=1,
            ),
        ):
            result = execute_droid_workflow(
                workflow_id="safe_edit_low",
                project_root=project_root,
                user_prompt="tidy docs",
                project_id="project.droid-wiring",
                proposal_digest="d" * 64,
            )
        assert result.ham_run_id is not None
        row = injected.get(result.ham_run_id)
        assert row is not None, "run row must land in the injected store"
        assert row.project_id == "project.droid-wiring"
    finally:
        set_control_plane_run_store_for_tests(None)


def test_execute_droid_workflow_injected_store_wins(tmp_path: Path) -> None:
    """Explicit control_plane_run_store= takes precedence over the global singleton."""
    from src.ham.droid_workflows.preview_launch import execute_droid_workflow

    project_root = tmp_path / "project"
    project_root.mkdir()
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()

    global_store = ControlPlaneRunStore(base_dir=global_dir)
    explicit_store = ControlPlaneRunStore(base_dir=explicit_dir)
    set_control_plane_run_store_for_tests(global_store)
    try:
        with patch(
            "src.ham.droid_workflows.preview_launch.run_droid_argv",
            return_value=MagicMock(
                exit_code=0,
                timed_out=False,
                stdout='{"result": "ok"}',
                stderr="",
                stdout_truncated=False,
                stderr_truncated=False,
                started_at="t0",
                ended_at="t1",
                duration_ms=1,
            ),
        ):
            result = execute_droid_workflow(
                workflow_id="safe_edit_low",
                project_root=project_root,
                user_prompt="write tests",
                project_id="project.inj",
                proposal_digest="e" * 64,
                control_plane_run_store=explicit_store,
            )
        assert result.ham_run_id is not None
        assert explicit_store.get(result.ham_run_id) is not None
        assert global_store.get(result.ham_run_id) is None
    finally:
        set_control_plane_run_store_for_tests(None)


# ---------------------------------------------------------------------------
# 8. No remaining direct ControlPlaneRunStore() in production src paths
# ---------------------------------------------------------------------------


def test_no_direct_cp_store_instantiation_in_production_src() -> None:
    """Structural check: grep confirms zero remaining bare ControlPlaneRunStore()
    callsites outside the factory module itself."""
    import subprocess

    result = subprocess.run(
        [
            "grep", "-r", "--include=*.py",
            r"ControlPlaneRunStore()",
            "src/",
        ],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )
    hits = [
        line for line in result.stdout.splitlines()
        if "control_plane_run.py" not in line  # factory itself is allowed
    ]
    assert not hits, (
        "Direct ControlPlaneRunStore() instantiations still present in src/:\n"
        + "\n".join(hits)
    )
