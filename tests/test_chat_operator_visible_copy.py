"""Visible operator transcript copy quarantine tests.

These tests pin VAL-OPERATOR-001..015 by exercising the ``format_operator_assistant_message``
formatter directly. They verify that:
  - Visible assistant text drops env names, token names, raw protocol fields
    (``proposal_digest``, ``base_revision``, ``operator.phase``), filesystem
    paths (``.ham/runs``), workflow internals, infrastructure terms
    (``Cloud Run``, ``GCP``, ``Firestore``, ``ControlPlaneRun``, ``Cloud Agent``),
    and raw provider IDs (``cursor_cloud_agent``, ``claude_code``, ``opencode_cli``,
    ``factory_droid_audit``, ``factory_droid_build``).
  - Structured metadata (``operator_result.blocking_reason``, ``pending_*``,
    ``data.reason_code``) still carries the raw fields needed for diagnostics
    and verify-on-launch safety checks.
"""
from __future__ import annotations

import pytest

from src.ham.chat_operator import (
    OperatorTurnResult,
    _friendly_blocking_reason,
    format_operator_assistant_message,
)


_FORBIDDEN_VISIBLE_TOKENS: tuple[str, ...] = (
    "HERMES_GATEWAY",
    "HERMES_GATEWAY_MODE",
    "HERMES_GATEWAY_BASE_URL",
    "HERMES_GATEWAY_MODEL",
    "HERMES_GATEWAY_API_KEY",
    "OPENROUTER_API_KEY",
    "HAM_RUN_LAUNCH_TOKEN",
    "HAM_DROID_EXEC_TOKEN",
    "HAM_CURSOR_AGENT_LAUNCH_TOKEN",
    "HAM_SETTINGS_WRITE_TOKEN",
    "HAM_SKILLS_WRITE_TOKEN",
    "HAM_CLAUDE_AGENT_SMOKE_TOKEN",
    "proposal_digest",
    "base_revision",
    "operator.phase",
    ".ham/runs",
    "ControlPlaneRun",
    "Cloud Run",
    "GCP",
    "Firestore",
    "cursor_cloud_agent",
    "claude_code",
    "opencode_cli",
    "factory_droid_audit",
    "factory_droid_build",
    "Cloud Agent",
    "Cursor Cloud Agent",
)


def _assert_visible_clean(msg: str) -> None:
    for tok in _FORBIDDEN_VISIBLE_TOKENS:
        assert tok not in msg, f"visible operator copy leaked forbidden token: {tok!r}\n--\n{msg}"


def test_friendly_blocking_reason_replaces_env_and_protocol_tokens() -> None:
    raw = (
        "HAM_RUN_LAUNCH_TOKEN is not set; check HERMES_GATEWAY_MODE and provide "
        "proposal_digest plus base_revision and inspect .ham/runs for operator.phase."
    )
    out = _friendly_blocking_reason(raw)
    for tok in (
        "HAM_RUN_LAUNCH_TOKEN",
        "HERMES_GATEWAY_MODE",
        "proposal_digest",
        "base_revision",
        ".ham/runs",
        "operator.phase",
    ):
        assert tok not in out, f"friendly reason still contains {tok!r}"


def test_blocking_reason_visible_text_is_friendly_metadata_preserved() -> None:
    raw = "HAM_RUN_LAUNCH_TOKEN is not set on this API host."
    op = OperatorTurnResult(
        handled=True,
        intent="launch_run",
        ok=False,
        blocking_reason=raw,
    )
    msg = format_operator_assistant_message(op)
    _assert_visible_clean(msg)
    assert "Blocked:" in msg
    assert "No changes were made." in msg
    # Metadata field still carries the diagnostic value.
    assert op.blocking_reason == raw


def test_pending_apply_visible_friendly_metadata_preserved() -> None:
    op = OperatorTurnResult(
        handled=True,
        intent="update_agents",
        ok=True,
        pending_apply={
            "project_id": "project.ham-abc123",
            "proposal_digest": "deadbeef" * 8,
            "base_revision": "rev-abc",
            "diff": [{"path": "agents", "kind": "add"}],
            "warnings": ["foo"],
        },
    )
    msg = format_operator_assistant_message(op)
    _assert_visible_clean(msg)
    # Visible card-pointer copy
    assert "preview ready" in msg.lower()
    assert "approve" in msg.lower()
    # Metadata preserves the safety fields needed for verify-on-launch.
    assert op.pending_apply["proposal_digest"] == "deadbeef" * 8
    assert op.pending_apply["base_revision"] == "rev-abc"


def test_pending_launch_visible_copy_drops_runs_path_and_token() -> None:
    op = OperatorTurnResult(
        handled=True,
        intent="launch_run",
        ok=True,
        pending_launch={
            "project_id": "project.ham-abc123",
            "profile_id": "alpha",
            "prompt": "do something",
        },
    )
    msg = format_operator_assistant_message(op)
    _assert_visible_clean(msg)
    assert "approve" in msg.lower()
    assert "run history" in msg.lower()


def test_pending_register_visible_copy_drops_settings_token() -> None:
    op = OperatorTurnResult(
        handled=True,
        intent="register_project",
        ok=True,
        pending_register={
            "name": "myproj",
            "root": "/tmp/myproj",
        },
    )
    msg = format_operator_assistant_message(op)
    _assert_visible_clean(msg)
    assert "approve" in msg.lower()


def test_pending_droid_visible_copy_drops_protocol_fields_metadata_preserved() -> None:
    op = OperatorTurnResult(
        handled=True,
        intent="droid_preview",
        ok=True,
        pending_droid={
            "project_id": "project.ham-abc123",
            "workflow_id": "factory_droid_build",
            "proposal_digest": "f" * 64,
            "base_revision": "main-1",
            "droid_user_prompt": "do x",
            "mutates": True,
            "tier": "build",
            "summary_preview": "Plan summary line.",
        },
    )
    msg = format_operator_assistant_message(op)
    _assert_visible_clean(msg)
    assert "Plan summary line." in msg
    assert "approve" in msg.lower()
    # Metadata preserves digest/revision for verify-on-launch.
    pd = op.pending_droid or {}
    assert pd.get("proposal_digest") == "f" * 64
    assert pd.get("base_revision") == "main-1"


def test_pending_cursor_agent_visible_copy_uses_cursor_brand() -> None:
    op = OperatorTurnResult(
        handled=True,
        intent="cursor_agent_preview",
        ok=True,
        pending_cursor_agent={
            "project_id": "project.ham-abc123",
            "repository": "Code-Munkiz/ham",
            "ref": "main",
            "proposal_digest": "a" * 64,
            "base_revision": "cursor-agent-v2",
            "cursor_task_prompt": "update docs",
            "summary_preview": "Cursor preview line.",
        },
    )
    msg = format_operator_assistant_message(op)
    _assert_visible_clean(msg)
    assert "Cursor mission preview" in msg
    assert "Cursor preview line." in msg
    pc = op.pending_cursor_agent or {}
    assert pc.get("proposal_digest") == "a" * 64
    assert pc.get("base_revision") == "cursor-agent-v2"


def test_launch_run_visible_copy_omits_runs_path() -> None:
    op = OperatorTurnResult(
        handled=True,
        intent="launch_run",
        ok=True,
        data={
            "run_id": "run-abcdef012345",
            "bridge_status": "ok",
            "persist_path": "/repo/.ham/runs/run-abcdef012345.json",
        },
    )
    msg = format_operator_assistant_message(op)
    _assert_visible_clean(msg)
    assert "Run completed" in msg
    # Underlying data still has the operator identifiers for diagnostics.
    assert op.data["run_id"] == "run-abcdef012345"
    assert op.data["persist_path"].endswith("run-abcdef012345.json")


def test_droid_launch_visible_copy_drops_workflow_internals() -> None:
    op = OperatorTurnResult(
        handled=True,
        intent="droid_launch",
        ok=True,
        data={
            "workflow_id": "factory_droid_build",
            "audit_id": "audit-1",
            "runner_id": "runner-1",
            "cwd": "/tmp/proj",
            "exit_code": 0,
            "duration_ms": 12,
            "session_id": "sess-1",
            "summary": "did the thing",
            "parsed_json": {"k": "v"},
        },
    )
    msg = format_operator_assistant_message(op)
    _assert_visible_clean(msg)
    assert "did the thing" in msg
    # Underlying data still has the IDs for diagnostics/operator console.
    assert op.data["workflow_id"] == "factory_droid_build"
    assert op.data["runner_id"] == "runner-1"


def test_cursor_agent_launch_visible_copy_uses_cursor_brand_no_cloud_agent() -> None:
    op = OperatorTurnResult(
        handled=True,
        intent="cursor_agent_launch",
        ok=True,
        data={
            "provider": "cursor_cloud_agent",
            "mission_registry_id": "mission-1",
            "agent_id": "bc_abc",
            "external_id": "bc_abc",
            "repository": "Code-Munkiz/ham",
            "ref": "main",
            "status": "running",
            "mission_checkpoint": "launched",
            "reason_code": "mission_launched",
        },
    )
    msg = format_operator_assistant_message(op)
    _assert_visible_clean(msg)
    assert "Cursor mission launched" in msg
    # Underlying data still has the raw provider id and IDs for follow-up.
    assert op.data["provider"] == "cursor_cloud_agent"
    assert op.data["mission_registry_id"] == "mission-1"
    assert op.data["agent_id"] == "bc_abc"


def test_cursor_agent_status_visible_copy_uses_cursor_brand() -> None:
    op = OperatorTurnResult(
        handled=True,
        intent="cursor_agent_status",
        ok=True,
        data={
            "provider": "cursor_cloud_agent",
            "mission_registry_id": "mission-1",
            "agent_id": "bc_abc",
            "cursor_agent_id": "bc_abc",
            "mission_lifecycle": "open",
            "mission_checkpoint": "running",
            "status": "RUNNING",
            "repository": "Code-Munkiz/ham",
            "ref": "main",
            "pr_url": None,
        },
    )
    msg = format_operator_assistant_message(op)
    _assert_visible_clean(msg)
    assert "Cursor mission status" in msg


def test_cursor_agent_logs_visible_copy_uses_cursor_brand() -> None:
    op = OperatorTurnResult(
        handled=True,
        intent="cursor_agent_logs",
        ok=True,
        data={
            "provider": "cursor_cloud_agent",
            "mission_registry_id": "mission-1",
            "agent_id": "bc_abc",
            "cursor_agent_id": "bc_abc",
            "mission_checkpoint": "running",
            "last_server_observed_at": "2026-05-01T00:00:00Z",
            "checkpoint_events": [
                {"checkpoint": "launched", "observed_at": "2026-05-01T00:00:00Z", "reason": "managed_launch_created"},
                {"checkpoint": "running", "observed_at": "2026-05-01T00:00:01Z", "reason": "cursor_status:RUNNING"},
            ],
        },
    )
    msg = format_operator_assistant_message(op)
    _assert_visible_clean(msg)
    assert "Cursor mission checkpoints" in msg


def test_cursor_agent_cancel_visible_copy_uses_cursor_brand() -> None:
    op = OperatorTurnResult(
        handled=True,
        intent="cursor_agent_cancel",
        ok=True,
        data={
            "provider": "cursor_cloud_agent",
            "mission_registry_id": "mission-1",
            "agent_id": "bc_abc",
            "reason_code": "cancel_not_supported",
            "cancel_message": "Cursor mission cancel is not available in this chat flow yet.",
        },
    )
    msg = format_operator_assistant_message(op)
    _assert_visible_clean(msg)
    assert "Cursor mission cancel" in msg
    # Reason code still present in metadata.
    assert op.data["reason_code"] == "cancel_not_supported"


def test_list_runs_visible_copy_omits_local_run_ids_and_profile() -> None:
    op = OperatorTurnResult(
        handled=True,
        intent="list_runs",
        ok=True,
        data={
            "scope": "project.ham-abc123",
            "runs": [
                {
                    "run_id": "run-abcdef012345",
                    "created_at": "2026-05-01T00:00:00Z",
                    "profile_id": "alpha",
                    "bridge_status": "ok",
                },
                {
                    "run_id": "run-fedcba543210",
                    "created_at": "2026-05-02T00:00:00Z",
                    "profile_id": "beta",
                    "status": "failed",
                },
            ],
        },
    )
    msg = format_operator_assistant_message(op)
    _assert_visible_clean(msg)
    # No raw run IDs or profile IDs in transcript prose.
    assert "run-abcdef012345" not in msg
    assert "run-fedcba543210" not in msg
    assert "alpha" not in msg
    assert "beta" not in msg
    # Visible copy uses friendly status hints instead.
    assert "ok" in msg or "failed" in msg


def test_inspect_run_visible_copy_omits_run_id_and_profile() -> None:
    op = OperatorTurnResult(
        handled=True,
        intent="inspect_run",
        ok=True,
        data={
            "run_id": "run-abcdef012345",
            "log_excerpt": "created_at: 2026-05-01T00:00:00Z\nstatus: ok\nsummary: did x\nstep 1: ok\n",
        },
    )
    msg = format_operator_assistant_message(op)
    _assert_visible_clean(msg)
    assert "run-abcdef012345" not in msg


@pytest.mark.parametrize(
    "intent",
    [
        "launch_run",
        "droid_launch",
        "cursor_agent_launch",
        "cursor_agent_status",
        "cursor_agent_logs",
        "cursor_agent_cancel",
        "list_runs",
        "inspect_run",
    ],
)
def test_visible_copy_never_uses_cloud_agent_brand(intent: str) -> None:
    """VAL-FRONTEND-003 (backend side): Cursor lanes never present as 'Cloud Agent'."""
    op = OperatorTurnResult(
        handled=True,
        intent=intent,
        ok=True,
        data={
            "bridge_status": "ok",
            "summary": "x",
            "provider": "cursor_cloud_agent",
            "repository": "Code-Munkiz/ham",
            "ref": "main",
            "status": "RUNNING",
            "mission_lifecycle": "open",
            "mission_checkpoint": "running",
            "reason_code": "ok",
            "scope": "project.x",
            "runs": [],
            "log_excerpt": "status: ok",
            "checkpoint_events": [],
        },
    )
    msg = format_operator_assistant_message(op)
    assert "Cloud Agent" not in msg
    assert "cursor_cloud_agent" not in msg
