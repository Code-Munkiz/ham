"""Unit tests for ``src.ham.claude_agent_runner.permissions``.

The ``claude_agent_sdk`` ``PermissionResultAllow`` / ``PermissionResultDeny``
classes are mocked via ``_import_permission_results`` so the suite never
requires the real SDK installed.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.ham.claude_agent_runner import (
    DEFAULT_EDIT_TOOLS,
    DEFAULT_READ_TOOLS,
    HARD_DENY_TOOLS,
    ClaudeAgentPermissionPolicy,
    make_list_audit_sink,
)
from src.ham.claude_agent_runner import permissions as permissions_module
from src.ham.claude_agent_runner.permissions import make_can_use_tool


class _FakeAllow:
    def __init__(self, updated_input: Any = None) -> None:
        self.behavior = "allow"
        self.updated_input = updated_input


class _FakeDeny:
    def __init__(self, *, message: str = "", interrupt: bool = False) -> None:
        self.behavior = "deny"
        self.message = message
        self.interrupt = interrupt


def _patch_results() -> Any:
    return patch.object(
        permissions_module,
        "_import_permission_results",
        lambda: (_FakeAllow, _FakeDeny),
    )


def test_policy_post_init_rejects_bypass_permissions(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ClaudeAgentPermissionPolicy(project_root=tmp_path, permission_mode="bypassPermissions")


def test_policy_post_init_rejects_overlap_between_allow_and_deny(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError):
        ClaudeAgentPermissionPolicy(
            project_root=tmp_path,
            allowed_tools=("Read", "Bash"),
            disallowed_tools=("Bash",),
        )


def test_policy_sdk_allowed_tools_returns_list(tmp_path: Path) -> None:
    policy = ClaudeAgentPermissionPolicy(project_root=tmp_path)
    out = policy.sdk_allowed_tools()
    assert isinstance(out, list)
    assert set(out) >= {"Read", "Edit"}


def test_can_use_tool_allows_in_scope_read(tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    target.write_text("hi", encoding="utf-8")
    sink, _events = make_list_audit_sink()
    policy = ClaudeAgentPermissionPolicy(project_root=tmp_path)
    with _patch_results():
        can_use = make_can_use_tool(policy, sink)
        out = asyncio.run(can_use("Read", {"file_path": str(target)}, None))
    assert isinstance(out, _FakeAllow)


def test_can_use_tool_denies_disallowed_tool(tmp_path: Path) -> None:
    sink, _events = make_list_audit_sink()
    policy = ClaudeAgentPermissionPolicy(project_root=tmp_path)
    with _patch_results():
        can_use = make_can_use_tool(policy, sink)
        out = asyncio.run(can_use("Bash", {"command": "ls"}, None))
    assert isinstance(out, _FakeDeny)


def test_can_use_tool_denies_out_of_scope_path(tmp_path: Path) -> None:
    sink, _events = make_list_audit_sink()
    policy = ClaudeAgentPermissionPolicy(project_root=tmp_path)
    with _patch_results():
        can_use = make_can_use_tool(policy, sink)
        out = asyncio.run(can_use("Read", {"file_path": "/etc/passwd"}, None))
    assert isinstance(out, _FakeDeny)


def test_can_use_tool_denies_path_traversal(tmp_path: Path) -> None:
    sink, _events = make_list_audit_sink()
    policy = ClaudeAgentPermissionPolicy(project_root=tmp_path)
    with _patch_results():
        can_use = make_can_use_tool(policy, sink)
        out = asyncio.run(
            can_use(
                "Read",
                {"file_path": str(tmp_path / ".." / "outside.txt")},
                None,
            )
        )
    assert isinstance(out, _FakeDeny)


def test_can_use_tool_never_returns_updated_input(tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    target.write_text("hi", encoding="utf-8")
    sink, _events = make_list_audit_sink()
    policy = ClaudeAgentPermissionPolicy(project_root=tmp_path)
    with _patch_results():
        can_use = make_can_use_tool(policy, sink)
        out = asyncio.run(can_use("Read", {"file_path": str(target)}, None))
    assert isinstance(out, _FakeAllow)
    assert out.updated_input is None


def test_default_allowed_tools_match_design_spec() -> None:
    expected = ("Read", "Glob", "Grep", "Edit", "MultiEdit", "Write", "NotebookEdit")
    combined = tuple(DEFAULT_READ_TOOLS) + tuple(DEFAULT_EDIT_TOOLS)
    assert combined == expected


def test_hard_deny_tools_contain_unsafe_set() -> None:
    unsafe = {"Bash", "WebFetch", "WebSearch", "Task"}
    assert unsafe <= set(HARD_DENY_TOOLS)
