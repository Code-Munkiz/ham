"""PreToolUse / PostToolUse hooks for the Claude Agent runner.

The hooks are defense-in-depth: ``can_use_tool`` already vets every tool call,
but the SDK guarantees the PreToolUse hook fires regardless of permission
mode (including a hypothetical future ``bypassPermissions``). All SDK symbol
imports are confined to ``_import_hook_matcher`` so this module stays
importable without ``claude_agent_sdk`` installed.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from .audit import AuditEvent, AuditSink, noop_audit_sink
from .paths import PATH_ARG_KEYS, safe_path_in_root
from .permissions import ClaudeAgentPermissionPolicy


def _import_hook_matcher() -> Any:
    from claude_agent_sdk import HookMatcher  # type: ignore[import-not-found]

    return HookMatcher


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }


def make_pretooluse_guard(
    policy: ClaudeAgentPermissionPolicy,
    audit_sink: AuditSink | None = None,
) -> Callable[[dict[str, Any], str | None, Any], Awaitable[dict[str, Any]]]:
    sink: AuditSink = audit_sink or noop_audit_sink

    async def _emit(event: AuditEvent) -> None:
        try:
            await sink(event)
        except Exception:  # noqa: S110, BLE001
            return

    async def guard(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: Any,
    ) -> dict[str, Any]:
        del tool_use_id, context
        try:
            tool_name = str(input_data.get("tool_name", "") or "")
            tool_input = input_data.get("tool_input", {}) or {}
            if not isinstance(tool_input, dict):
                tool_input = {}
            if tool_name not in policy.allowed_tools:
                await _emit(
                    AuditEvent(
                        kind="denied_tool",
                        tool_name=tool_name,
                        detail={"reason": "not_in_allow_list", "stage": "pretooluse"},
                        ts=time.monotonic(),
                    ),
                )
                return _deny("tool not allowed")
            for key in PATH_ARG_KEYS:
                if key not in tool_input:
                    continue
                raw = tool_input.get(key)
                if not isinstance(raw, (str,)):
                    await _emit(
                        AuditEvent(
                            kind="denied_path",
                            tool_name=tool_name,
                            detail={
                                "key": key,
                                "reason": "non_string_path",
                                "stage": "pretooluse",
                            },
                            ts=time.monotonic(),
                        ),
                    )
                    return _deny("path outside project root")
                if not safe_path_in_root(raw, policy.project_root):
                    await _emit(
                        AuditEvent(
                            kind="denied_path",
                            tool_name=tool_name,
                            detail={
                                "key": key,
                                "reason": "out_of_scope",
                                "stage": "pretooluse",
                            },
                            ts=time.monotonic(),
                        ),
                    )
                    return _deny("path outside project root")
            edited_path: str | None = None
            for key in PATH_ARG_KEYS:
                raw = tool_input.get(key) if isinstance(tool_input, dict) else None
                if isinstance(raw, str) and raw:
                    edited_path = raw
                    break
            await _emit(
                AuditEvent(
                    kind="tool_pre",
                    tool_name=tool_name,
                    detail={"path": edited_path} if edited_path else {},
                    ts=time.monotonic(),
                ),
            )
        except Exception:
            return {}
        return {}

    return guard


def make_posttooluse_recorder(
    audit_sink: AuditSink | None = None,
) -> Callable[[dict[str, Any], str | None, Any], Awaitable[dict[str, Any]]]:
    sink: AuditSink = audit_sink or noop_audit_sink

    async def _emit(event: AuditEvent) -> None:
        try:
            await sink(event)
        except Exception:  # noqa: S110, BLE001
            return

    async def recorder(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: Any,
    ) -> dict[str, Any]:
        del tool_use_id, context
        try:
            tool_name = str(input_data.get("tool_name", "") or "")
            status = str(input_data.get("tool_result_status", "ok") or "ok")
            tool_input = input_data.get("tool_input", {}) or {}
            if not isinstance(tool_input, dict):
                tool_input = {}
            edited_path: str | None = None
            for key in PATH_ARG_KEYS:
                raw = tool_input.get(key)
                if isinstance(raw, str) and raw:
                    edited_path = raw
                    break
            detail: dict[str, Any] = {"success": status == "ok"}
            if edited_path:
                detail["path"] = edited_path
            await _emit(
                AuditEvent(
                    kind="tool_post",
                    tool_name=tool_name,
                    detail=detail,
                    ts=time.monotonic(),
                ),
            )
        except Exception:
            return {}
        return {}

    return recorder


__all__ = [
    "make_posttooluse_recorder",
    "make_pretooluse_guard",
]
