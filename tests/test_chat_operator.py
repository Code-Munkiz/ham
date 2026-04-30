"""Operator layer: topology checks, heuristics, preview/apply wiring."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ham.agent_profiles import PRIMARY_AGENT_DEFAULT_ID, HamAgentProfile, HamAgentsConfig
from src.ham.chat_operator import (
    ChatOperatorPayload,
    format_operator_assistant_message,
    process_operator_turn,
    project_root_accessible,
    try_heuristic_intent,
)
from src.ham.settings_write import SettingsChanges
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
    assert op.data.get("reason_code") == "missing_project_ref"
    assert (op.blocking_reason or "").startswith("missing_project_ref:")


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
