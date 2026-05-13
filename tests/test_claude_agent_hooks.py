"""Unit tests for ``src.ham.claude_agent_runner.hooks``.

The PreToolUse / PostToolUse hooks are pure functions: they never invoke
the Claude Agent SDK, so no mocking of ``claude_agent_sdk`` is required.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from src.ham.claude_agent_runner import (
    ClaudeAgentPermissionPolicy,
    make_list_audit_sink,
)
from src.ham.claude_agent_runner.hooks import (
    make_posttooluse_recorder,
    make_pretooluse_guard,
)


def _policy(root: Path) -> ClaudeAgentPermissionPolicy:
    return ClaudeAgentPermissionPolicy(project_root=root)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_pretooluse_guard_denies_tool_not_in_allow_list(tmp_path: Path) -> None:
    sink, events = make_list_audit_sink()
    guard = make_pretooluse_guard(_policy(tmp_path), sink)
    out = _run(
        guard(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            None,
            None,
        )
    )
    assert out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
    assert any(e.kind == "denied_tool" for e in events)


def test_pretooluse_guard_denies_path_outside_root(tmp_path: Path) -> None:
    sink, events = make_list_audit_sink()
    guard = make_pretooluse_guard(_policy(tmp_path), sink)
    out = _run(
        guard(
            {"tool_name": "Write", "tool_input": {"file_path": "/etc/passwd"}},
            None,
            None,
        )
    )
    assert out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
    assert any(e.kind == "denied_path" for e in events)


def test_pretooluse_guard_allows_in_scope_edit(tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    target.write_text("hi", encoding="utf-8")
    sink, events = make_list_audit_sink()
    guard = make_pretooluse_guard(_policy(tmp_path), sink)
    out = _run(
        guard(
            {"tool_name": "Edit", "tool_input": {"file_path": str(target)}},
            None,
            None,
        )
    )
    assert out == {}
    assert any(e.kind == "tool_pre" for e in events)


def test_pretooluse_guard_emits_audit_event_on_allow_and_deny(
    tmp_path: Path,
) -> None:
    target = tmp_path / "a.txt"
    target.write_text("hi", encoding="utf-8")
    sink, events = make_list_audit_sink()
    guard = make_pretooluse_guard(_policy(tmp_path), sink)
    _run(
        guard(
            {"tool_name": "Edit", "tool_input": {"file_path": str(target)}},
            None,
            None,
        )
    )
    _run(
        guard(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            None,
            None,
        )
    )
    kinds = [e.kind for e in events]
    assert "tool_pre" in kinds
    assert "denied_tool" in kinds


def test_pretooluse_guard_never_raises_on_audit_sink_error(tmp_path: Path) -> None:
    async def _bad_sink(_event: Any) -> None:
        raise RuntimeError("audit broken")

    guard = make_pretooluse_guard(_policy(tmp_path), _bad_sink)
    out = _run(
        guard(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            None,
            None,
        )
    )
    assert isinstance(out, dict)


@pytest.mark.parametrize(
    "forbidden",
    [
        "ANTHROPIC_API_KEY",
        "CLAUDE_AGENT_ENABLED",
        "HAM_CLAUDE_AGENT_EXEC_TOKEN",
        "sk-ant",
    ],
)
def test_pretooluse_guard_deny_reason_contains_no_secret_or_env_name(
    tmp_path: Path, forbidden: str
) -> None:
    guard = make_pretooluse_guard(_policy(tmp_path))
    out = _run(
        guard(
            {"tool_name": "Write", "tool_input": {"file_path": "/etc/passwd"}},
            None,
            None,
        )
    )
    reason = out.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
    assert forbidden not in reason

    out2 = _run(
        guard(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            None,
            None,
        )
    )
    reason2 = out2.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
    assert forbidden not in reason2


def test_posttooluse_recorder_emits_audit_event(tmp_path: Path) -> None:
    sink, events = make_list_audit_sink()
    recorder = make_posttooluse_recorder(sink)
    _run(
        recorder(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(tmp_path / "a.txt")},
                "tool_result_status": "ok",
            },
            None,
            None,
        )
    )
    assert any(e.kind == "tool_post" and e.tool_name == "Edit" for e in events)


def test_posttooluse_recorder_returns_empty_dict(tmp_path: Path) -> None:
    recorder = make_posttooluse_recorder()
    out = _run(
        recorder(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(tmp_path / "a.txt")},
                "tool_result_status": "ok",
            },
            None,
            None,
        )
    )
    assert out == {}
