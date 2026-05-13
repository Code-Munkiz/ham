"""Result types for the bounded HAM Claude Agent runner.

Public surface re-exported from :mod:`src.ham.claude_agent_runner`. Tests and
the conductor / route consume only these types; the runner module itself is
mockable end-to-end without the Claude Agent SDK installed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

RunStatus = Literal[
    "success",
    "failure",
    "blocked_by_policy",
    "timeout",
    "sdk_error",
    "sdk_missing",
    "auth_missing",
    "disabled",
]


@dataclass(frozen=True)
class ClaudeAgentRunResult:
    """Bounded, secret-free outcome of one Claude Agent coding mission."""

    status: RunStatus
    changed_paths: tuple[str, ...] = ()
    assistant_summary: str = ""
    tool_calls_count: int = 0
    denied_tool_calls_count: int = 0
    error_kind: str | None = None
    error_summary: str | None = None
    duration_seconds: float = 0.0
    sdk_version: str | None = None
    cost_usd: float | None = None
    usage: Mapping[str, Any] = field(default_factory=dict)


__all__ = ["ClaudeAgentRunResult", "RunStatus"]
