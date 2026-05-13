"""HAM Claude Agent runner — bounded in-process driver for one coding mission.

Public surface is intentionally narrow. The route handler in
``src/api/claude_agent_build.py`` and the sync facade in
``src/ham/coding_router/claude_agent_provider.py`` are the only intended
callers today.
"""

from __future__ import annotations

from .audit import (
    AuditEvent,
    AuditSink,
    make_list_audit_sink,
    noop_audit_sink,
)
from .permissions import (
    DEFAULT_EDIT_TOOLS,
    DEFAULT_READ_TOOLS,
    HARD_DENY_TOOLS,
    ClaudeAgentPermissionPolicy,
)
from .runner import run_claude_agent_mission
from .types import ClaudeAgentRunResult, RunStatus

__all__ = [
    "AuditEvent",
    "AuditSink",
    "ClaudeAgentPermissionPolicy",
    "ClaudeAgentRunResult",
    "DEFAULT_EDIT_TOOLS",
    "DEFAULT_READ_TOOLS",
    "HARD_DENY_TOOLS",
    "RunStatus",
    "make_list_audit_sink",
    "noop_audit_sink",
    "run_claude_agent_mission",
]
