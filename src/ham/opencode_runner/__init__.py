"""HAM OpenCode runner — bounded driver for one ``opencode serve`` mission.

Public surface is intentionally narrow. The route handler in
``src/api/opencode_build.py`` and the sync facade in
``src/ham/coding_router/opencode_provider.py`` are the only intended
callers today.
"""

from __future__ import annotations

from .event_consumer import (
    AssistantMessageChunk,
    FileChange,
    PermissionRequest,
    ServerConnected,
    SessionComplete,
    SessionError,
    ToolCallStart,
    UnknownEvent,
    consume_events,
    parse_event,
)
from .http_client import (
    HttpClientFactory,
    OpenCodeServeClient,
    default_client_factory,
)
from .permission_broker import (
    DEFAULT_ALLOW_CATEGORIES,
    DEFAULT_BASH_DENYLIST,
    DEFAULT_DENY_CATEGORIES,
    DEFAULT_PERMISSION_TIMEOUT_S,
    REQUIRES_PROJECT_ROOT_SCOPING,
    PermissionContext,
    PermissionDecision,
    apply_timeout,
    decide_permission,
)
from .result import OpenCodeRunResult, OpenCodeRunStatus
from .runner import run_opencode_mission
from .server_process import (
    ServeProcess,
    ServeProcessHandle,
    Spawner,
    default_spawner,
    reap_zombie_children,
    shutdown_serve,
    spawn_opencode_serve,
)
from .version_pin import OPENCODE_PINNED_LINUX_X64_SHA256, OPENCODE_PINNED_VERSION
from .workspace_isolation import IsolatedServeEnv, build_isolated_env

__all__ = [
    "AssistantMessageChunk",
    "DEFAULT_ALLOW_CATEGORIES",
    "DEFAULT_BASH_DENYLIST",
    "DEFAULT_DENY_CATEGORIES",
    "DEFAULT_PERMISSION_TIMEOUT_S",
    "FileChange",
    "HttpClientFactory",
    "IsolatedServeEnv",
    "OPENCODE_PINNED_LINUX_X64_SHA256",
    "OPENCODE_PINNED_VERSION",
    "OpenCodeRunResult",
    "OpenCodeRunStatus",
    "OpenCodeServeClient",
    "PermissionContext",
    "PermissionDecision",
    "PermissionRequest",
    "REQUIRES_PROJECT_ROOT_SCOPING",
    "ServeProcess",
    "ServeProcessHandle",
    "ServerConnected",
    "SessionComplete",
    "SessionError",
    "Spawner",
    "ToolCallStart",
    "UnknownEvent",
    "apply_timeout",
    "build_isolated_env",
    "consume_events",
    "decide_permission",
    "default_client_factory",
    "default_spawner",
    "parse_event",
    "reap_zombie_children",
    "run_opencode_mission",
    "shutdown_serve",
    "spawn_opencode_serve",
]
