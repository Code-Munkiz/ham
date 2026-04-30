"""Operator layer: topology checks, heuristics, preview/apply wiring."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.ham.agent_profiles import PRIMARY_AGENT_DEFAULT_ID, HamAgentProfile, HamAgentsConfig
from src.ham.chat_operator import (
    ChatOperatorPayload,
    format_operator_assistant_message,
    process_operator_turn,
    project_root_accessible,
    try_heuristic_intent,
)
from src.ham.managed_mission_wiring import set_managed_mission_store_for_tests
from src.ham.settings_write import SettingsChanges
from src.persistence.control_plane_run import utc_now_iso
from src.persistence.managed_mission import ManagedMission, ManagedMissionStore, new_mission_registry_id
from src.persistence.project_store import ProjectStore


def test_project_root_accessible(tmp_path: Path) -> None:
    ok, msg = project_root_accessible(tmp_path)
    assert ok and msg == ""
    bad, why = project_root_accessible(tmp_path / "nope")
    assert not bad
    assert "Not a directory" in why


def test_heuristic_list_projects() -> None:
    h = try_heuristic_intent("please list projects", default_project_id=None)
    assert h is not None
    assert h[0] == "list_projects"


def test_heuristic_inspect_agents_uses_default_project() -> None:
    h = try_heuristic_intent("show agents", default_project_id="project.x-abc123")
    assert h is not None
    assert h[0] == "inspect_agents"
    assert h[1]["project_id"] == "project.x-abc123"


def test_heuristic_cloud_agent_preview_routing() -> None:
    h = try_heuristic_intent(
        "create a cloud agent preview to update the sdk adapter",
        default_project_id="project.x-abc123",
    )
    assert h is not None
    assert h[0] == "cursor_agent_preview"
    assert h[1]["project_id"] == "project.x-abc123"
    assert "sdk adapter" in h[1]["cursor_task_prompt"]


def test_heuristic_cloud_agent_launch_routing() -> None:
    h = try_heuristic_intent(
        "fire up a cloud agent to patch flaky tests",
        default_project_id="project.x-abc123",
    )
    assert h is not None
    assert h[0] == "cursor_agent_launch"
    assert h[1]["project_id"] == "project.x-abc123"
    assert "flaky tests" in h[1]["cursor_task_prompt"]


def test_heuristic_cloud_agent_launch_extracts_repo_and_branch() -> None:
    h = try_heuristic_intent(
        "launch a cursor cloud agent for repo Code-Munkiz/ham on branch main to update docs",
        default_project_id=None,
    )
    assert h is not None
    assert h[0] == "cursor_agent_launch"
    assert h[1]["cursor_repository"] == "Code-Munkiz/ham"
    assert h[1]["cursor_ref"] == "main"


def test_process_operator_cursor_launch_missing_project_uses_stable_reason_code(tmp_path: Path) -> None:
    store = ProjectStore(store_path=tmp_path / "projects.json")
    op = process_operator_turn(
        user_text="have Cursor implement the SDK adapter fix",
        project_store=store,
        default_project_id=None,
        operator_payload=None,
        ham_operator_authorization=None,
    )
    assert op is not None and op.handled
    assert op.intent == "cursor_agent_launch"
    assert not op.ok
    assert op.data.get("reason_code") == "missing_project_context"
    assert (op.blocking_reason or "").startswith("missing_project_context:")


def test_process_operator_cursor_launch_unknown_default_project_returns_project_context_reason(
    tmp_path: Path,
) -> None:
    store = ProjectStore(store_path=tmp_path / "projects.json")
    op = process_operator_turn(
        user_text="fire up an agent to update the SDK adapter",
        project_store=store,
        default_project_id="project.ghost-123456",
        operator_payload=None,
        ham_operator_authorization=None,
    )
    assert op is not None and op.handled
    assert op.intent == "cursor_agent_launch"
    assert not op.ok
    assert op.data.get("reason_code") == "missing_project_context"
    assert (op.blocking_reason or "").startswith("missing_project_context:")


def test_process_operator_cursor_launch_explicit_repo_without_mapping_uses_mapping_reason(tmp_path: Path) -> None:
    store = ProjectStore(store_path=tmp_path / "projects.json")
    op = process_operator_turn(
        user_text="launch a cursor cloud agent for repo Code-Munkiz/ham on branch main to update docs",
        project_store=store,
        default_project_id=None,
        operator_payload=None,
        ham_operator_authorization=None,
    )
    assert op is not None and op.handled
    assert op.intent == "cursor_agent_launch"
    assert not op.ok
    assert op.data.get("reason_code") == "missing_project_mapping"
    assert (op.blocking_reason or "").startswith("missing_project_mapping:")


def test_process_operator_cursor_launch_passes_repo_and_ref_into_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    store = ProjectStore(store_path=tmp_path / "projects.json")
    rec = store.make_record(
        name="ham",
        root=str(tmp_path),
        description="",
        metadata={"cursor_cloud_repository": "https://github.com/Code-Munkiz/ham"},
    )
    store.register(rec)
    with patch("src.ham.chat_operator.build_cursor_agent_preview") as mock_preview:
        from src.ham.cursor_agent_workflow import CursorAgentPreviewResult

        mock_preview.return_value = CursorAgentPreviewResult(
            ok=True,
            blocking_reason=None,
            proposal_digest="d" * 64,
            base_revision="cursor-agent-v2",
            repository="Code-Munkiz/ham",
            mutates=False,
            summary_preview="ok",
            project_id=rec.id,
        )
        op = process_operator_turn(
            user_text="launch a cursor cloud agent for repo Code-Munkiz/ham on branch main to update docs",
            project_store=store,
            default_project_id=None,
            operator_payload=None,
            ham_operator_authorization=None,
        )
    assert op is not None and op.handled
    assert mock_preview.call_count == 1
    kwargs = mock_preview.call_args.kwargs
    assert kwargs["cursor_repository"] == "Code-Munkiz/ham"
    assert kwargs["cursor_ref"] == "main"


def test_process_operator_cursor_launch_uses_project_default_ref_when_missing_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    store = ProjectStore(store_path=tmp_path / "projects.json")
    rec = store.make_record(
        name="ham",
        root=str(tmp_path),
        description="",
        metadata={
            "cursor_cloud_repository": "https://github.com/Code-Munkiz/ham",
            "default_branch": "release/2026",
        },
    )
    store.register(rec)
    with patch("src.ham.chat_operator.build_cursor_agent_preview") as mock_preview:
        from src.ham.cursor_agent_workflow import CursorAgentPreviewResult

        mock_preview.return_value = CursorAgentPreviewResult(
            ok=True,
            blocking_reason=None,
            proposal_digest="d" * 64,
            base_revision="cursor-agent-v2",
            repository="Code-Munkiz/ham",
            mutates=False,
            summary_preview="ok",
            project_id=rec.id,
        )
        op = process_operator_turn(
            user_text="fire up an agent to update the sdk adapter",
            project_store=store,
            default_project_id=rec.id,
            operator_payload=None,
            ham_operator_authorization=None,
        )
    assert op is not None and op.handled
    kwargs = mock_preview.call_args.kwargs
    assert kwargs["cursor_repository"] is None
    assert kwargs["cursor_ref"] == "release/2026"


def test_process_operator_cursor_launch_backfills_cursor_metadata_from_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    store = ProjectStore(store_path=tmp_path / "projects.json")
    rec = store.make_record(
        name="ham",
        root=str(tmp_path),
        description="",
        metadata={},
    )
    store.register(rec)

    class _Done:
        def __init__(self, stdout: str, returncode: int = 0) -> None:
            self.stdout = stdout
            self.returncode = returncode

    responses = iter(
        [
            _Done("git@github.com:Code-Munkiz/ham.git\n"),
            _Done("origin/main\n"),
        ]
    )

    def _fake_run(*_args, **_kwargs):
        return next(responses)

    monkeypatch.setattr("src.ham.chat_operator.subprocess.run", _fake_run)
    with (
        patch("src.ham.chat_operator.build_cursor_agent_preview") as mock_preview,
        patch("src.ham.chat_operator.run_cursor_agent_launch") as mock_launch,
    ):
        from src.ham.cursor_agent_workflow import CursorAgentPreviewResult

        mock_preview.return_value = CursorAgentPreviewResult(
            ok=True,
            blocking_reason=None,
            proposal_digest="d" * 64,
            base_revision="cursor-agent-v2",
            repository="Code-Munkiz/ham",
            mutates=False,
            summary_preview="ok",
            project_id=rec.id,
        )
        mock_launch.return_value = (
            True,
            {
                "agent_id": "cursor-agent-test",
                "status": "running",
                "repository": "Code-Munkiz/ham",
                "ref": "main",
            },
            None,
            "ham-run-test",
        )
        op = process_operator_turn(
            user_text="fire up an agent to update docs",
            project_store=store,
            default_project_id=rec.id,
            operator_payload=None,
            ham_operator_authorization=None,
        )
    assert op is not None and op.handled and op.ok
    kwargs = mock_preview.call_args.kwargs
    assert kwargs["cursor_ref"] == "main"
    updated = store.get_project(rec.id)
    assert updated is not None
    assert dict(updated.metadata).get("cursor_cloud_repository") == "Code-Munkiz/ham"
    assert dict(updated.metadata).get("cursor_cloud_ref") == "main"


def test_heuristic_factory_route_blocks_with_stable_reason() -> None:
    h = try_heuristic_intent(
        "send this to Factory Droid to patch flaky tests",
        default_project_id="project.x-abc123",
    )
    assert h is not None
    assert h[0] == "agent_router_blocked"
    assert h[1]["reason_code"] == "provider_not_implemented"
    assert h[1]["provider"] == "factory"


def test_heuristic_claude_route_blocks_with_stable_reason() -> None:
    h = try_heuristic_intent(
        "use Claude to implement this",
        default_project_id="project.x-abc123",
    )
    assert h is not None
    assert h[0] == "agent_router_blocked"
    assert h[1]["reason_code"] == "provider_not_implemented"
    assert h[1]["provider"] == "claude"


def test_heuristic_normal_chat_remains_normal() -> None:
    h = try_heuristic_intent(
        "explain what a cloud is",
        default_project_id="project.x-abc123",
    )
    assert h is None


def test_process_list_projects(tmp_path: Path) -> None:
    store_path = tmp_path / "proj.json"
    store = ProjectStore(store_path=store_path)
    rec = store.make_record(name="t", root=str(tmp_path), description="")
    store.register(rec)
    op = process_operator_turn(
        user_text="list all projects",
        project_store=store,
        default_project_id=None,
        operator_payload=None,
        ham_operator_authorization=None,
    )
    assert op is not None and op.handled and op.ok
    assert op.data.get("count") == 1
    text = format_operator_assistant_message(op)
    assert "t" in text and rec.id in text


def test_inspect_project_inaccessible_root(tmp_path: Path) -> None:
    store_path = tmp_path / "proj.json"
    store = ProjectStore(store_path=store_path)
    missing = tmp_path / "missing-dir"
    rec = store.make_record(name="ghost", root=str(missing), description="")
    store.register(rec)
    op = process_operator_turn(
        user_text=f"inspect project {rec.id}",
        project_store=store,
        default_project_id=None,
        operator_payload=None,
        ham_operator_authorization=None,
    )
    assert op is not None and op.handled
    assert not op.ok
    assert op.blocking_reason


def test_update_agents_preview_roundtrip(tmp_path: Path) -> None:
    ham = tmp_path / ".ham"
    ham.mkdir()
    settings = {
        "agents": {
            "profiles": [
                {
                    "id": PRIMARY_AGENT_DEFAULT_ID,
                    "name": "HAM",
                    "description": "",
                    "skills": [],
                    "enabled": True,
                }
            ],
            "primary_agent_id": PRIMARY_AGENT_DEFAULT_ID,
        }
    }
    (ham / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    store_path = tmp_path / "reg.json"
    store = ProjectStore(store_path=store_path)
    rec = store.make_record(name="p", root=str(tmp_path), description="")
    store.register(rec)
    # pick a catalog id that exists in vendored catalog
    from src.ham.hermes_skills_catalog import list_catalog_entries

    entries = list_catalog_entries()
    assert entries, "need at least one hermes catalog entry"
    cid = str(entries[0]["catalog_id"])
    op = process_operator_turn(
        user_text=f"add skill {cid} to profile {PRIMARY_AGENT_DEFAULT_ID}",
        project_store=store,
        default_project_id=rec.id,
        operator_payload=None,
        ham_operator_authorization=None,
    )
    assert op is not None and op.handled and op.ok
    assert op.pending_apply is not None
    assert op.pending_apply.get("project_id") == rec.id
    ch = op.pending_apply.get("changes") or {}
    assert "agents" in ch


def test_explicit_apply_requires_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException

    ham = tmp_path / ".ham"
    ham.mkdir()
    cfg = HamAgentsConfig(
        profiles=[
            HamAgentProfile(
                id=PRIMARY_AGENT_DEFAULT_ID,
                name="HAM",
                skills=[],
            )
        ],
        primary_agent_id=PRIMARY_AGENT_DEFAULT_ID,
    )
    (ham / "settings.json").write_text(
        json.dumps({"agents": cfg.model_dump(mode="json")}),
        encoding="utf-8",
    )
    store_path = tmp_path / "reg.json"
    store = ProjectStore(store_path=store_path)
    rec = store.make_record(name="p", root=str(tmp_path), description="")
    store.register(rec)
    changes = SettingsChanges(agents=cfg)
    preview = __import__(
        "src.ham.settings_write",
        fromlist=["preview_project_settings"],
    ).preview_project_settings(tmp_path, changes)
    monkeypatch.delenv("HAM_SETTINGS_WRITE_TOKEN", raising=False)
    payload = ChatOperatorPayload(
        phase="apply_settings",
        confirmed=True,
        project_id=rec.id,
        changes=changes.model_dump(mode="json", exclude_none=True),
        base_revision=preview.base_revision,
    )
    with pytest.raises(HTTPException) as ei:
        process_operator_turn(
            user_text="x",
            project_store=store,
            default_project_id=None,
            operator_payload=payload,
            ham_operator_authorization=None,
        )
    assert ei.value.status_code == 403


def test_launch_blocked_without_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HAM_RUN_LAUNCH_TOKEN", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    store_path = tmp_path / "reg.json"
    store = ProjectStore(store_path=store_path)
    rec = store.make_record(name="p", root=str(tmp_path), description="")
    store.register(rec)
    op = process_operator_turn(
        user_text=f"launch run on {rec.id}: hello",
        project_store=store,
        default_project_id=rec.id,
        operator_payload=None,
        ham_operator_authorization=None,
    )
    assert op is not None and op.handled
    assert not op.ok
    assert "HAM_RUN_LAUNCH_TOKEN" in (op.blocking_reason or "")


def test_heuristic_status_phrase_maps_to_cursor_agent_status() -> None:
    h = try_heuristic_intent("how is the agent doing", default_project_id="project.demo-abc123")
    assert h is not None
    assert h[0] == "cursor_agent_status"
    assert h[1]["project_id"] == "project.demo-abc123"


def test_heuristic_logs_phrase_maps_to_cursor_agent_logs() -> None:
    h = try_heuristic_intent("show checkpoints", default_project_id="project.demo-abc123")
    assert h is not None
    assert h[0] == "cursor_agent_logs"
    assert h[1]["project_id"] == "project.demo-abc123"


def test_heuristic_local_repo_operation_not_routed_to_mission_status() -> None:
    h = try_heuristic_intent("gh auth status", default_project_id=None)
    assert h is not None
    assert h[0] == "local_repo_operation"
    assert "commands" in h[1]


def test_heuristic_multiline_repo_commands_classified_local_repo_ops() -> None:
    prompt = (
        "cd /home/user/.hermes/hermes-agent\n"
        "gh auth setup-git\n"
        "git pull --rebase origin main\n"
        "git push origin main"
    )
    h = try_heuristic_intent(prompt, default_project_id=None)
    assert h is not None
    assert h[0] == "local_repo_operation"
    commands = h[1].get("commands") or []
    assert any("git pull --rebase origin main" in x for x in commands)
    assert any("git push origin main" in x for x in commands)


def test_heuristic_cloud_agent_status_still_mission_scoped() -> None:
    h = try_heuristic_intent("check the cloud agent status", default_project_id="project.demo-abc123")
    assert h is not None
    assert h[0] == "cursor_agent_status"


def test_heuristic_cancel_this_mission_still_mission_scoped() -> None:
    h = try_heuristic_intent("cancel this mission", default_project_id="project.demo-abc123")
    assert h is not None
    assert h[0] == "cursor_agent_cancel"


def test_process_operator_local_repo_operations_no_mission_block(tmp_path: Path) -> None:
    store = ProjectStore(store_path=tmp_path / "projects.json")
    op = process_operator_turn(
        user_text="git pull --rebase origin main && git push origin main",
        project_store=store,
        default_project_id=None,
        operator_payload=None,
        ham_operator_authorization=None,
    )
    assert op is not None and op.handled and op.ok
    assert op.intent == "local_repo_operation"
    assert op.data.get("reason_code") == "local_repo_operation"
    assert "missing_mission_context" not in (op.blocking_reason or "")


def test_local_repo_operation_redacts_pat_in_output(tmp_path: Path) -> None:
    store = ProjectStore(store_path=tmp_path / "projects.json")
    op = process_operator_turn(
        user_text="gh auth login --with-token ghp_SUPERSECRET1234567890",
        project_store=store,
        default_project_id=None,
        operator_payload=None,
        ham_operator_authorization=None,
    )
    assert op is not None and op.handled and op.ok
    msg = format_operator_assistant_message(op)
    assert "ghp_SUPERSECRET1234567890" not in msg
    assert "<redacted>" in msg


def test_status_resolves_latest_managed_mission_without_agent_id(tmp_path: Path) -> None:
    store = ProjectStore(store_path=tmp_path / "projects.json")
    rec = store.make_record(
        name="ham",
        root=str(tmp_path),
        description="",
        metadata={"cursor_cloud_repository": "Code-Munkiz/ham"},
    )
    store.register(rec)
    missions = ManagedMissionStore(base_dir=tmp_path / "missions")
    set_managed_mission_store_for_tests(missions)
    try:
        now = utc_now_iso()
        row = ManagedMission(
            mission_registry_id=new_mission_registry_id(),
            cursor_agent_id="bc_latest_1",
            mission_handling="managed",
            repository_observed="Code-Munkiz/ham",
            ref_observed="main",
            mission_lifecycle="open",
            cursor_status_last_observed="RUNNING",
            status_reason_last_observed="mapped:RUNNING",
            mission_checkpoint_latest="running",
            mission_checkpoint_updated_at=now,
            created_at=now,
            updated_at=now,
            last_server_observed_at=now,
        )
        missions.save(row)
        op = process_operator_turn(
            user_text="status",
            project_store=store,
            default_project_id=rec.id,
            operator_payload=None,
            ham_operator_authorization=None,
        )
    finally:
        set_managed_mission_store_for_tests(None)
    assert op is not None and op.handled and op.ok
    assert op.intent == "cursor_agent_status"
    assert (op.data or {}).get("mission_registry_id") == row.mission_registry_id
    assert (op.data or {}).get("mission_checkpoint") == "running"


def test_logs_returns_recent_checkpoint_events(tmp_path: Path) -> None:
    store = ProjectStore(store_path=tmp_path / "projects.json")
    rec = store.make_record(name="ham", root=str(tmp_path), description="", metadata={})
    store.register(rec)
    missions = ManagedMissionStore(base_dir=tmp_path / "missions")
    set_managed_mission_store_for_tests(missions)
    try:
        now = utc_now_iso()
        row = ManagedMission(
            mission_registry_id=new_mission_registry_id(),
            cursor_agent_id="bc_logs_1",
            mission_handling="managed",
            mission_lifecycle="open",
            cursor_status_last_observed="RUNNING",
            status_reason_last_observed="mapped:RUNNING",
            mission_checkpoint_latest="running",
            mission_checkpoint_updated_at=now,
            mission_checkpoint_events=[
                {"checkpoint": "launched", "observed_at": now, "reason": "managed_launch_created"},
                {"checkpoint": "running", "observed_at": now, "reason": "cursor_status:RUNNING"},
            ],
            created_at=now,
            updated_at=now,
            last_server_observed_at=now,
        )
        missions.save(row)
        op = process_operator_turn(
            user_text="show logs",
            project_store=store,
            default_project_id=rec.id,
            operator_payload=None,
            ham_operator_authorization=None,
        )
    finally:
        set_managed_mission_store_for_tests(None)
    assert op is not None and op.handled and op.ok
    assert op.intent == "cursor_agent_logs"
    events = (op.data or {}).get("checkpoint_events")
    assert isinstance(events, list)
    assert len(events) == 2


def test_cancel_returns_stable_cancel_not_supported_with_mission(tmp_path: Path) -> None:
    store = ProjectStore(store_path=tmp_path / "projects.json")
    rec = store.make_record(name="ham", root=str(tmp_path), description="", metadata={})
    store.register(rec)
    missions = ManagedMissionStore(base_dir=tmp_path / "missions")
    set_managed_mission_store_for_tests(missions)
    try:
        now = utc_now_iso()
        row = ManagedMission(
            mission_registry_id=new_mission_registry_id(),
            cursor_agent_id="bc_cancel_1",
            mission_handling="managed",
            mission_lifecycle="open",
            created_at=now,
            updated_at=now,
            last_server_observed_at=now,
        )
        missions.save(row)
        op = process_operator_turn(
            user_text="stop the agent",
            project_store=store,
            default_project_id=rec.id,
            operator_payload=None,
            ham_operator_authorization=None,
        )
    finally:
        set_managed_mission_store_for_tests(None)
    assert op is not None and op.handled and op.ok
    assert op.intent == "cursor_agent_cancel"
    assert (op.data or {}).get("reason_code") == "cancel_not_supported"
    assert (op.data or {}).get("mission_registry_id") == row.mission_registry_id
