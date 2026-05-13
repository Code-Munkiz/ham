"""Permission policy + ``can_use_tool`` factory for the Claude Agent runner.

The policy is a small immutable dataclass; the factory below produces an
async callback the SDK invokes for every tool request. All SDK symbol
imports are confined to ``_import_permission_results`` so this module
stays importable without ``claude_agent_sdk`` installed.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .audit import AuditEvent, AuditSink, noop_audit_sink
from .paths import PATH_ARG_KEYS, safe_path_in_root

DEFAULT_READ_TOOLS: tuple[str, ...] = ("Read", "Glob", "Grep")
DEFAULT_EDIT_TOOLS: tuple[str, ...] = (
    "Edit",
    "MultiEdit",
    "Write",
    "NotebookEdit",
)
HARD_DENY_TOOLS: tuple[str, ...] = (
    "Bash",
    "BashOutput",
    "KillShell",
    "WebFetch",
    "WebSearch",
    "Task",
)
ALLOWED_PERMISSION_MODES: frozenset[str] = frozenset(
    {"default", "acceptEdits", "plan", "dontAsk"},
)


@dataclass(frozen=True)
class ClaudeAgentPermissionPolicy:
    project_root: Path
    allowed_tools: tuple[str, ...] = DEFAULT_READ_TOOLS + DEFAULT_EDIT_TOOLS
    disallowed_tools: tuple[str, ...] = HARD_DENY_TOOLS
    permission_mode: str = "default"

    def __post_init__(self) -> None:
        if self.permission_mode == "bypassPermissions":
            raise ValueError("bypassPermissions is not permitted in HAM")
        if self.permission_mode not in ALLOWED_PERMISSION_MODES:
            raise ValueError(
                f"permission_mode {self.permission_mode!r} is not in the HAM allow-list"
            )
        bad = set(self.allowed_tools) & set(self.disallowed_tools)
        if bad:
            raise ValueError(f"tool(s) {sorted(bad)} are in both allowed and denied lists")

    def sdk_allowed_tools(self) -> list[str]:
        return list(self.allowed_tools)

    def sdk_disallowed_tools(self) -> list[str]:
        return list(self.disallowed_tools)


def _import_permission_results() -> tuple[Any, Any]:
    from claude_agent_sdk import (  # type: ignore[import-not-found]
        PermissionResultAllow,
        PermissionResultDeny,
    )

    return PermissionResultAllow, PermissionResultDeny


def make_can_use_tool(
    policy: ClaudeAgentPermissionPolicy,
    audit_sink: AuditSink | None = None,
) -> Callable[[str, dict[str, Any], Any], Awaitable[Any]]:
    sink: AuditSink = audit_sink or noop_audit_sink

    async def _emit(event: AuditEvent) -> None:
        try:
            await sink(event)
        except Exception:  # noqa: S110, BLE001
            return

    async def can_use_tool(
        tool_name: str,
        input_data: dict[str, Any],
        context: Any,
    ) -> Any:
        del context
        allow_cls, deny_cls = _import_permission_results()
        if tool_name not in policy.allowed_tools:
            await _emit(
                AuditEvent(
                    kind="denied_tool",
                    tool_name=tool_name,
                    detail={"reason": "not_in_allow_list"},
                    ts=time.monotonic(),
                ),
            )
            return deny_cls(
                message="tool not in HAM allow-list",
                interrupt=False,
            )
        for key in PATH_ARG_KEYS:
            if key not in input_data:
                continue
            raw = input_data.get(key)
            if not isinstance(raw, (str, Path)):
                await _emit(
                    AuditEvent(
                        kind="denied_path",
                        tool_name=tool_name,
                        detail={"key": key, "reason": "non_string_path"},
                        ts=time.monotonic(),
                    ),
                )
                return deny_cls(
                    message="path argument has unexpected type",
                    interrupt=False,
                )
            if not safe_path_in_root(raw, policy.project_root):
                await _emit(
                    AuditEvent(
                        kind="denied_path",
                        tool_name=tool_name,
                        detail={"key": key, "reason": "out_of_scope"},
                        ts=time.monotonic(),
                    ),
                )
                return deny_cls(
                    message="path outside project root",
                    interrupt=False,
                )
        await _emit(
            AuditEvent(
                kind="allowed",
                tool_name=tool_name,
                detail={},
                ts=time.monotonic(),
            ),
        )
        return allow_cls()

    return can_use_tool


__all__ = [
    "ALLOWED_PERMISSION_MODES",
    "ClaudeAgentPermissionPolicy",
    "DEFAULT_EDIT_TOOLS",
    "DEFAULT_READ_TOOLS",
    "HARD_DENY_TOOLS",
    "make_can_use_tool",
]
