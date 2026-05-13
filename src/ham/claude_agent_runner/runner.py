"""Bounded HAM Claude Agent runner.

In-process driver for one Claude Agent coding mission against a managed
working tree. The runner never raises: every error path collapses into a
``ClaudeAgentRunResult`` with a redacted ``error_summary``.

All ``claude_agent_sdk`` imports are confined to the ``_import_*`` helpers
below so the module is importable without the SDK installed and so tests
can patch the indirection symbols via :func:`unittest.mock.patch.object`.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from src.ham.worker_adapters.claude_agent_adapter import (
    _claude_runtime_anthropic_env_overlay,
    _ham_preferred_cli_path,
    _redact_diagnostic_text,
    _text_from_sdk_message,
)

from .audit import AuditEvent, AuditSink, noop_audit_sink
from .hooks import make_posttooluse_recorder, make_pretooluse_guard
from .paths import safe_path_in_root
from .permissions import (
    DEFAULT_EDIT_TOOLS,
    ClaudeAgentPermissionPolicy,
    make_can_use_tool,
)
from .types import ClaudeAgentRunResult

DEFAULT_MAX_TURNS = 25
DEFAULT_TIMEOUT_SECONDS = 600
SUMMARY_CAP = 4000
ERROR_SUMMARY_CAP = 2000
MAX_CHANGED_PATHS = 256
MAX_ASSISTANT_TEXT_CHARS = 64_000


def _import_client() -> Any:
    from claude_agent_sdk import ClaudeSDKClient  # type: ignore[import-not-found]

    return ClaudeSDKClient


def _import_options() -> Any:
    from claude_agent_sdk import ClaudeAgentOptions  # type: ignore[import-not-found]

    return ClaudeAgentOptions


def _import_hook_matcher() -> Any:
    from claude_agent_sdk import HookMatcher  # type: ignore[import-not-found]

    return HookMatcher


def _import_sdk_version() -> str | None:
    try:
        import claude_agent_sdk  # type: ignore[import-not-found]
    except Exception:
        return None
    return getattr(claude_agent_sdk, "__version__", None)


def _import_query() -> Any:
    """Test mocking seam — the runner uses ``ClaudeSDKClient`` for execution.

    The Mission-1 readiness path uses ``query()`` directly; this seam is
    exported here so unit tests that already know to patch
    ``_import_query`` continue to work even though the runner does not
    call ``query()`` itself.
    """
    from claude_agent_sdk import query  # type: ignore[import-not-found]

    return query


async def _safe_audit_emit(sink: AuditSink | None, event: AuditEvent) -> None:
    if sink is None:
        return
    try:
        await sink(event)
    except Exception:
        return


def _extract_cost_and_usage(msg: Any) -> tuple[float | None, dict[str, Any]]:
    cost = getattr(msg, "total_cost_usd", None)
    if cost is None:
        cost = getattr(msg, "cost_usd", None)
    cost_val: float | None
    try:
        cost_val = float(cost) if cost is not None else None
    except (TypeError, ValueError):
        cost_val = None
    usage_raw = getattr(msg, "usage", None)
    usage: dict[str, Any] = {}
    if isinstance(usage_raw, dict):
        for k, v in usage_raw.items():
            if isinstance(k, str) and isinstance(v, (int, float, str, bool)):
                usage[k] = v
    return cost_val, usage


async def run_claude_agent_mission(  # noqa: C901
    *,
    project_root: Path,
    user_prompt: str,
    policy: ClaudeAgentPermissionPolicy,
    system_prompt: str | None = None,
    audit_sink: AuditSink | None = None,
    max_turns: int = DEFAULT_MAX_TURNS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    model: str | None = None,
    actor: Any = None,
) -> ClaudeAgentRunResult:
    """Run one bounded Claude Agent coding mission inside ``project_root``.

    Constraints:
    - Uses :class:`ClaudeSDKClient` (required for ``can_use_tool``).
    - Defense-in-depth permission stack: ``disallowed_tools`` + ``can_use_tool``
      + ``PreToolUse`` hook.
    - Never uses ``permission_mode="bypassPermissions"``.
    - All diagnostic strings are redacted before being returned.
    - Returns a :class:`ClaudeAgentRunResult`; never raises.
    """
    start = time.monotonic()
    sink: AuditSink = audit_sink or noop_audit_sink
    sdk_version = _import_sdk_version()

    changed_paths: set[str] = set()
    tool_calls_count = 0
    denied_tool_calls_count = 0
    assistant_chunks: list[str] = []
    cost_usd: float | None = None
    usage: dict[str, Any] = {}

    async def _tracking_sink(event: AuditEvent) -> None:
        nonlocal tool_calls_count, denied_tool_calls_count
        try:
            if event.kind == "tool_post":
                tool_calls_count += 1
                detail = dict(event.detail or {})
                if detail.get("success") and event.tool_name in DEFAULT_EDIT_TOOLS:
                    raw_path = detail.get("path")
                    if (
                        isinstance(raw_path, str)
                        and raw_path
                        and safe_path_in_root(raw_path, policy.project_root)
                        and len(changed_paths) < MAX_CHANGED_PATHS
                    ):
                        try:
                            resolved = Path(raw_path).expanduser().resolve(strict=False)
                            changed_paths.add(str(resolved))
                        except (OSError, RuntimeError, ValueError):
                            pass
            elif event.kind in {"denied_tool", "denied_path"}:
                denied_tool_calls_count += 1
        finally:
            await _safe_audit_emit(sink, event)

    await _safe_audit_emit(
        sink,
        AuditEvent(
            kind="run_start",
            tool_name="",
            detail={"project_root": str(policy.project_root)},
            ts=time.monotonic(),
        ),
    )

    try:
        try:
            client_cls = _import_client()
            options_cls = _import_options()
            hook_matcher_cls = _import_hook_matcher()
        except ImportError as exc:
            duration = time.monotonic() - start
            err = _redact_diagnostic_text(
                "claude-agent-sdk not installed on this host.",
                cap=ERROR_SUMMARY_CAP,
            )
            result = ClaudeAgentRunResult(
                status="sdk_missing",
                error_kind="ImportError",
                error_summary=err,
                duration_seconds=duration,
                sdk_version=sdk_version,
            )
            await _safe_audit_emit(
                sink,
                AuditEvent(
                    kind="run_end",
                    tool_name="",
                    detail={"status": result.status, "error_kind": "ImportError"},
                    ts=time.monotonic(),
                ),
            )
            del exc
            return result

        stderr_lines: list[str] = []

        def _stderr_cb(line: str) -> None:
            stderr_lines.append(line)
            while len(stderr_lines) > 128:
                stderr_lines.pop(0)

        env_overlay = _claude_runtime_anthropic_env_overlay(actor)
        pretooluse = make_pretooluse_guard(policy, _tracking_sink)
        posttooluse = make_posttooluse_recorder(_tracking_sink)
        can_use_tool = make_can_use_tool(policy, _tracking_sink)

        opts_kwargs: dict[str, Any] = {
            "cwd": str(policy.project_root),
            "allowed_tools": policy.sdk_allowed_tools(),
            "disallowed_tools": policy.sdk_disallowed_tools(),
            "permission_mode": policy.permission_mode,
            "max_turns": max_turns,
            "can_use_tool": can_use_tool,
            "hooks": {
                "PreToolUse": [hook_matcher_cls(matcher="", hooks=[pretooluse])],
                "PostToolUse": [hook_matcher_cls(matcher="", hooks=[posttooluse])],
            },
            "mcp_servers": {},
            "extra_args": {"bare": None},
            "env": dict(env_overlay),
            "stderr": _stderr_cb,
        }
        cli = _ham_preferred_cli_path()
        if cli:
            opts_kwargs["cli_path"] = cli
        if system_prompt:
            opts_kwargs["system_prompt"] = system_prompt
        if model:
            opts_kwargs["model"] = model

        options = options_cls(**opts_kwargs)

        async def _execute() -> None:
            nonlocal cost_usd, usage
            client = client_cls(options=options)
            async with client as session:
                await session.query(user_prompt)
                async for msg in session.receive_response():
                    text_part = _text_from_sdk_message(msg)
                    if text_part and len("".join(assistant_chunks)) < MAX_ASSISTANT_TEXT_CHARS:
                        assistant_chunks.append(text_part)
                    c, u = _extract_cost_and_usage(msg)
                    if c is not None:
                        cost_usd = c
                    if u:
                        usage.update(u)

        try:
            await asyncio.wait_for(_execute(), timeout=timeout_seconds)
        except TimeoutError:
            duration = time.monotonic() - start
            result = ClaudeAgentRunResult(
                status="timeout",
                changed_paths=tuple(sorted(changed_paths)),
                assistant_summary=_redact_diagnostic_text(
                    "".join(assistant_chunks), cap=SUMMARY_CAP
                ),
                tool_calls_count=tool_calls_count,
                denied_tool_calls_count=denied_tool_calls_count,
                error_kind="TimeoutError",
                error_summary=_redact_diagnostic_text(
                    f"Claude Agent mission exceeded {timeout_seconds}s timeout.",
                    cap=ERROR_SUMMARY_CAP,
                ),
                duration_seconds=duration,
                sdk_version=sdk_version,
                cost_usd=cost_usd,
                usage=usage,
            )
            await _safe_audit_emit(
                sink,
                AuditEvent(
                    kind="run_end",
                    tool_name="",
                    detail={"status": result.status},
                    ts=time.monotonic(),
                ),
            )
            return result

        combined = "".join(assistant_chunks)
        summary = _redact_diagnostic_text(combined, cap=SUMMARY_CAP)
        duration = time.monotonic() - start

        if denied_tool_calls_count > 0 and tool_calls_count == 0 and not changed_paths:
            status = "blocked_by_policy"
        else:
            status = "success"

        result = ClaudeAgentRunResult(
            status=status,
            changed_paths=tuple(sorted(changed_paths)),
            assistant_summary=summary,
            tool_calls_count=tool_calls_count,
            denied_tool_calls_count=denied_tool_calls_count,
            error_kind=None,
            error_summary=None,
            duration_seconds=duration,
            sdk_version=sdk_version,
            cost_usd=cost_usd,
            usage=usage,
        )
        await _safe_audit_emit(
            sink,
            AuditEvent(
                kind="run_end",
                tool_name="",
                detail={
                    "status": result.status,
                    "tool_calls_count": tool_calls_count,
                    "denied_tool_calls_count": denied_tool_calls_count,
                    "changed_paths_count": len(changed_paths),
                },
                ts=time.monotonic(),
            ),
        )
        return result
    except Exception as exc:
        duration = time.monotonic() - start
        result = ClaudeAgentRunResult(
            status="sdk_error",
            changed_paths=tuple(sorted(changed_paths)),
            assistant_summary=_redact_diagnostic_text("".join(assistant_chunks), cap=SUMMARY_CAP),
            tool_calls_count=tool_calls_count,
            denied_tool_calls_count=denied_tool_calls_count,
            error_kind=type(exc).__name__,
            error_summary=_redact_diagnostic_text(
                str(exc) or type(exc).__name__,
                cap=ERROR_SUMMARY_CAP,
            ),
            duration_seconds=duration,
            sdk_version=sdk_version,
            cost_usd=cost_usd,
            usage=usage,
        )
        await _safe_audit_emit(
            sink,
            AuditEvent(
                kind="run_end",
                tool_name="",
                detail={"status": result.status, "error_kind": type(exc).__name__},
                ts=time.monotonic(),
            ),
        )
        return result


__all__ = [
    "DEFAULT_MAX_TURNS",
    "DEFAULT_TIMEOUT_SECONDS",
    "ERROR_SUMMARY_CAP",
    "MAX_CHANGED_PATHS",
    "SUMMARY_CAP",
    "run_claude_agent_mission",
]
