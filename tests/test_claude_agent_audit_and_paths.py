"""Unit tests for ``src.ham.claude_agent_runner.audit`` and ``.paths``.

Pure-function tests; no SDK or network involvement.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.ham.claude_agent_runner.audit import (
    AuditEvent,
    make_list_audit_sink,
    noop_audit_sink,
)
from src.ham.claude_agent_runner.paths import PATH_ARG_KEYS, safe_path_in_root


# ---------------------------------------------------------------------------
# safe_path_in_root
# ---------------------------------------------------------------------------


def test_safe_path_in_root_accepts_in_scope_relative(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text("x", encoding="utf-8")
    assert safe_path_in_root(str(target), tmp_path) is True


def test_safe_path_in_root_rejects_out_of_scope(tmp_path: Path) -> None:
    assert safe_path_in_root("/etc/passwd", tmp_path) is False


def test_safe_path_in_root_rejects_dotdot_escape(tmp_path: Path) -> None:
    outside = tmp_path / ".." / "outside.txt"
    assert safe_path_in_root(str(outside), tmp_path) is False


def test_safe_path_in_root_handles_symlink(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = project_root / "link.txt"
    try:
        os.symlink(outside, link)
    except OSError:
        pytest.skip("symlinks not supported on this platform")
    assert safe_path_in_root(str(link), project_root) is False


def test_safe_path_in_root_handles_os_error(tmp_path: Path) -> None:
    with patch(
        "src.ham.claude_agent_runner.paths.Path.expanduser",
        side_effect=OSError("boom"),
    ):
        assert safe_path_in_root("/some/path", tmp_path) is False


def test_path_arg_keys_includes_file_path_and_notebook_path() -> None:
    assert "file_path" in PATH_ARG_KEYS
    assert "notebook_path" in PATH_ARG_KEYS


# ---------------------------------------------------------------------------
# Audit sinks
# ---------------------------------------------------------------------------


def test_audit_noop_sink_returns_none_on_any_event() -> None:
    out = asyncio.run(
        noop_audit_sink(AuditEvent(kind="run_start", tool_name="", detail={}, ts=0.0))
    )
    assert out is None


def test_audit_make_list_sink_captures_events_in_order() -> None:
    sink, events = make_list_audit_sink()
    e1 = AuditEvent(kind="run_start", tool_name="", detail={"a": 1}, ts=0.0)
    e2 = AuditEvent(kind="tool_pre", tool_name="Read", detail={}, ts=0.0)
    e3 = AuditEvent(kind="run_end", tool_name="", detail={"status": "success"}, ts=0.0)

    async def _drive() -> None:
        await sink(e1)
        await sink(e2)
        await sink(e3)

    asyncio.run(_drive())
    assert events == [e1, e2, e3]
