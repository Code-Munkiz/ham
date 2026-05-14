"""Result type for one OpenCode managed-workspace mission.

Mirrors the shape of :class:`src.ham.claude_agent_runner.ClaudeAgentRunResult`
so the rest of the post-exec pipeline (deletion guard, snapshot emit,
ControlPlaneRun terminal write) can consume both providers uniformly.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

OpenCodeRunStatus = Literal[
    "success",
    "failure",
    "permission_denied",
    "timeout",
    "serve_unavailable",
    "runner_error",
    "disabled",
    "auth_missing",
    # Set when an explicit backend-resolved model/provider was not configured
    # for the launch. Returned before ``opencode serve`` is spawned so the
    # subprocess never starts in this branch.
    "provider_not_configured",
    # Set when the OpenCode subprocess / SSE stream ended without emitting a
    # recognised completion envelope (no ``session.idle``, no ``session.error``).
    # Mapped by callers to ``status_reason="opencode:session_no_completion"``.
    "session_no_completion",
]


@dataclass(frozen=True)
class OpenCodeRunResult:
    """Bounded, secret-free outcome of one OpenCode coding mission.

    ``changed_paths`` / ``deleted_paths`` are POSIX-relative strings already
    redacted of host details. ``assistant_summary`` and ``error_summary``
    are likewise pre-redacted and capped by the runner.
    """

    status: OpenCodeRunStatus
    changed_paths: tuple[str, ...] = ()
    deleted_paths: tuple[str, ...] = ()
    assistant_summary: str = ""
    tool_calls_count: int = 0
    denied_tool_calls_count: int = 0
    error_kind: str | None = None
    error_summary: str | None = None
    duration_seconds: float = 0.0
    runner_version: str | None = None
    provider_metadata: Mapping[str, Any] = field(default_factory=dict)


__all__ = ["OpenCodeRunResult", "OpenCodeRunStatus"]
