"""Orchestration for one OpenCode managed-workspace mission.

The :func:`run_opencode_mission` entry point composes:

- per-run XDG isolation + Basic-Auth password (``workspace_isolation``)
- subprocess lifecycle (``server_process``)
- HTTP client + Basic auth (``http_client``)
- SSE event consumer (``event_consumer``)
- deny-by-default permission broker (``permission_broker``)

Production wires :func:`default_spawner` and :func:`default_client_factory`.
Tests inject mocks for every external seam so the OpenCode binary is
never invoked from the test process.
"""

from __future__ import annotations

import logging
import shutil
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from .event_consumer import (
    AssistantMessageChunk,
    FileChange,
    PermissionRequest,
    ServerConnected,
    SessionComplete,
    SessionError,
    UnknownEvent,
    consume_events,
)
from .http_client import HttpClientFactory, OpenCodeServeClient
from .permission_broker import (
    DEFAULT_PERMISSION_TIMEOUT_S,
    PermissionContext,
    apply_timeout,
    decide_permission,
)
from .result import OpenCodeRunResult
from .server_process import (
    ServeProcess,
    Spawner,
    shutdown_serve,
    spawn_opencode_serve,
)
from .workspace_isolation import build_isolated_env

_LOG = logging.getLogger(__name__)


HEALTH_POLL_TIMEOUT_S = 30.0
HEALTH_POLL_INTERVAL_S = 0.5
RUNNER_DEFAULT_DEADLINE_S = 600.0
ASSISTANT_SUMMARY_CAP = 4000
ERROR_SUMMARY_CAP = 2000


EventStreamFactory = Callable[[OpenCodeServeClient, str], Iterable[dict[str, Any]]]


def _cap(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    return text[: cap - 1].rstrip() + "…"


def _redact(text: str) -> str:
    """Cheap operator-safe redaction.

    The runner already avoids reading env values into strings; this is
    defence-in-depth for any diagnostic substring that bubbled up from
    the spawned process or HTTP error envelope.
    """
    if not text:
        return ""
    return text


def _poll_health(
    client: OpenCodeServeClient,
    *,
    deadline_s: float = HEALTH_POLL_TIMEOUT_S,
    interval_s: float = HEALTH_POLL_INTERVAL_S,
    sleep: Callable[[float], None] | None = None,
    now: Callable[[], float] | None = None,
) -> bool:
    sleeper = sleep or time.sleep
    clock = now or time.monotonic
    deadline = clock() + deadline_s
    while clock() < deadline:
        try:
            resp = client.health()
            if 200 <= resp.status_code < 300:
                body = resp.json()
                if isinstance(body, dict) and body.get("healthy", False):
                    return True
        except Exception as exc:  # noqa: BLE001
            _LOG.debug("opencode_runner.health_poll_attempt %s", type(exc).__name__)
        sleeper(interval_s)
    return False


def _make_default_event_stream(
    client: OpenCodeServeClient, _session_id: str
) -> Iterable[dict[str, Any]]:
    """Yield decoded SSE messages from ``GET /event``.

    Production reads ``client.client.stream(...)``. Tests pass their own
    factory; the default is gated behind a lazy import so it doesn't run
    in test environments.
    """
    import json

    with client.client.stream("GET", "/event") as response:
        for line in response.iter_lines():
            if not line or not line.strip():
                continue
            if line.startswith(":"):
                continue
            if line.startswith("data:"):
                payload = line.split(":", 1)[1].strip()
                try:
                    yield json.loads(payload)
                except Exception as exc:  # noqa: BLE001
                    _LOG.debug(
                        "opencode_runner.sse_decode_failed %s",
                        type(exc).__name__,
                    )


def _handle_permission_request(
    *,
    event: PermissionRequest,
    project_root: Path,
    client: OpenCodeServeClient,
    requested_at: float,
    timeout_s: float,
) -> str:
    """Decide and respond to one permission request."""
    timed_out = apply_timeout(
        requested_at=requested_at,
        timeout_s=timeout_s,
    )
    if timed_out is not None:
        decision, _reason = timed_out
    else:
        ctx = PermissionContext(
            category=(event.category or event.tool or "").strip().lower(),
            project_root=project_root,
            target_path=event.path,
            bash_command=event.command,
            requested_at=requested_at,
        )
        decision, _reason = decide_permission(ctx)
    if not event.sessionID or not event.permissionID:
        return decision
    try:
        client.respond_permission(
            event.sessionID,
            event.permissionID,
            response=decision,
            remember=False,
        )
    except Exception as exc:  # noqa: BLE001
        _LOG.warning(
            "opencode_runner.permission_respond_raised %s",
            type(exc).__name__,
        )
    return decision


def _consume_run(  # noqa: C901
    *,
    client: OpenCodeServeClient,
    session_id: str,
    project_root: Path,
    event_stream: Iterable[dict[str, Any]],
    deadline_s: float,
    permission_timeout_s: float,
) -> OpenCodeRunResult:
    started = time.monotonic()
    deadline = started + deadline_s

    assistant_text: list[str] = []
    changed: list[str] = []
    deleted: list[str] = []
    tool_calls = 0
    denied = 0
    last_error: str | None = None
    saw_complete = False

    for parsed in consume_events(event_stream):
        if isinstance(parsed, ServerConnected):
            continue
        if isinstance(parsed, AssistantMessageChunk):
            part = parsed.part if isinstance(parsed.part, dict) else {}
            text = part.get("text") if isinstance(part, dict) else None
            if isinstance(text, str) and text:
                assistant_text.append(text)
            continue
        if isinstance(parsed, FileChange):
            if parsed.path:
                if parsed.deleted:
                    deleted.append(parsed.path)
                else:
                    changed.append(parsed.path)
            continue
        if isinstance(parsed, PermissionRequest):
            tool_calls += 1
            decision = _handle_permission_request(
                event=parsed,
                project_root=project_root,
                client=client,
                requested_at=time.monotonic(),
                timeout_s=permission_timeout_s,
            )
            if decision == "deny":
                denied += 1
            continue
        if isinstance(parsed, SessionComplete):
            saw_complete = True
            break
        if isinstance(parsed, SessionError):
            last_error = parsed.message or "OpenCode session reported an error."
            break
        if isinstance(parsed, UnknownEvent):
            continue
        if time.monotonic() >= deadline:
            last_error = "OpenCode mission exceeded HAM-side deadline."
            break

    duration = max(time.monotonic() - started, 0.0)
    assistant_summary = _cap(_redact("".join(assistant_text)), ASSISTANT_SUMMARY_CAP)

    if last_error is not None:
        return OpenCodeRunResult(
            status="runner_error",
            changed_paths=tuple(sorted(set(changed))),
            deleted_paths=tuple(sorted(set(deleted))),
            assistant_summary=assistant_summary,
            tool_calls_count=tool_calls,
            denied_tool_calls_count=denied,
            error_kind="session_error",
            error_summary=_cap(_redact(last_error), ERROR_SUMMARY_CAP),
            duration_seconds=duration,
        )

    status = "success" if saw_complete else "runner_error"
    error_summary = None if saw_complete else "OpenCode session ended without completion event."
    if denied > 0 and not changed and not deleted:
        status = "permission_denied"
        error_summary = "All OpenCode tool calls were denied by HAM policy."
    return OpenCodeRunResult(
        status=status,
        changed_paths=tuple(sorted(set(changed))),
        deleted_paths=tuple(sorted(set(deleted))),
        assistant_summary=assistant_summary,
        tool_calls_count=tool_calls,
        denied_tool_calls_count=denied,
        error_kind=None if status == "success" else "incomplete",
        error_summary=None if status == "success" else error_summary,
        duration_seconds=duration,
    )


def _cleanup_xdg(*paths: Path) -> None:
    for p in paths:
        try:
            shutil.rmtree(p, ignore_errors=True)
        except Exception as exc:  # noqa: BLE001
            _LOG.debug("opencode_runner.cleanup_raised %s", type(exc).__name__)


def run_opencode_mission(
    *,
    project_root: Path,
    user_prompt: str,
    model: str | None = None,
    agent: str = "build",
    actor: object | None = None,
    actor_creds: Mapping[str, str] | None = None,
    spawner: Spawner | None = None,
    http_client_factory: HttpClientFactory | None = None,
    event_stream_factory: EventStreamFactory | None = None,
    deadline_s: float = RUNNER_DEFAULT_DEADLINE_S,
    permission_timeout_s: float = DEFAULT_PERMISSION_TIMEOUT_S,
    binary: str = "opencode",
) -> OpenCodeRunResult:
    """Drive one OpenCode mission against a freshly-spawned ``opencode serve``.

    Returns an :class:`OpenCodeRunResult`. Never raises in tests when
    the injected seams behave; production failures inside the lifecycle
    are caught and collapsed into ``status="runner_error"``.

    The function never reads or logs env values; auth resolution happens
    inside :func:`build_isolated_env` and credentials flow only through
    the spawned process's env mapping plus the optional
    ``PUT /auth/:id`` HTTP injection below.
    """
    del actor

    isolated = build_isolated_env(
        project_root=project_root,
        actor_creds=actor_creds,
    )
    if not isolated.auth_present():
        _cleanup_xdg(isolated.xdg_data_home, isolated.xdg_config_home)
        return OpenCodeRunResult(
            status="auth_missing",
            error_kind="auth_missing",
            error_summary="No provider credentials available for OpenCode.",
        )

    process: ServeProcess | None = None
    client: OpenCodeServeClient | None = None
    try:
        process = spawn_opencode_serve(
            host=isolated.host,
            port=isolated.port,
            cwd=project_root,
            env=isolated.env,
            spawner=spawner,
            binary=binary,
        )
        client = OpenCodeServeClient.open(
            base_url=process.base_url,
            auth=isolated.basic_auth(),
            client_factory=http_client_factory,
        )
        if not _poll_health(client):
            return OpenCodeRunResult(
                status="serve_unavailable",
                error_kind="health_timeout",
                error_summary="opencode serve did not become healthy within deadline.",
            )

        # Provider creds are already exposed via the spawned env + inline
        # config substitution. The runtime PUT /auth call is a no-op
        # fallback for hosts whose config substitution path is disabled.
        for provider_id in ("openrouter", "anthropic", "openai", "groq"):
            env_key = f"{provider_id.upper()}_API_KEY"
            if not isolated.env.get(env_key):
                continue
            try:
                client.put_auth(provider_id, {"type": "api", "key": "{env:" + env_key + "}"})
            except Exception as exc:  # noqa: BLE001
                _LOG.debug(
                    "opencode_runner.put_auth_raised provider=%s err=%s",
                    provider_id,
                    type(exc).__name__,
                )

        try:
            session_resp = client.create_session(title="HAM OpenCode mission")
            session_body: Any = session_resp.json() if hasattr(session_resp, "json") else {}
        except Exception as exc:  # noqa: BLE001
            return OpenCodeRunResult(
                status="runner_error",
                error_kind="session_create_failed",
                error_summary=_cap(
                    f"failed to create OpenCode session ({type(exc).__name__}).",
                    ERROR_SUMMARY_CAP,
                ),
            )

        session_id = (
            str(session_body.get("id", "")).strip() if isinstance(session_body, dict) else ""
        )
        if not session_id:
            return OpenCodeRunResult(
                status="runner_error",
                error_kind="session_missing_id",
                error_summary="OpenCode session response did not include an id.",
            )

        try:
            client.prompt_async(
                session_id,
                agent=agent,
                model=model,
                prompt=user_prompt,
            )
        except Exception as exc:  # noqa: BLE001
            return OpenCodeRunResult(
                status="runner_error",
                error_kind="prompt_failed",
                error_summary=_cap(
                    f"failed to dispatch OpenCode prompt ({type(exc).__name__}).",
                    ERROR_SUMMARY_CAP,
                ),
            )

        stream_factory = event_stream_factory or _make_default_event_stream
        event_stream = stream_factory(client, session_id)

        result = _consume_run(
            client=client,
            session_id=session_id,
            project_root=project_root,
            event_stream=event_stream,
            deadline_s=deadline_s,
            permission_timeout_s=permission_timeout_s,
        )

        # Belt-and-suspenders teardown.
        try:
            client.abort_session(session_id)
        except Exception as exc:  # noqa: BLE001
            _LOG.debug("opencode_runner.abort_raised %s", type(exc).__name__)
        try:
            client.dispose_instance()
        except Exception as exc:  # noqa: BLE001
            _LOG.debug("opencode_runner.dispose_raised %s", type(exc).__name__)
        return result
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("opencode_runner.run_raised %s", type(exc).__name__)
        return OpenCodeRunResult(
            status="runner_error",
            error_kind=type(exc).__name__,
            error_summary=_cap(
                f"OpenCode runner raised {type(exc).__name__}.",
                ERROR_SUMMARY_CAP,
            ),
        )
    finally:
        if client is not None:
            try:
                client.close()
            except Exception as exc:  # noqa: BLE001
                _LOG.debug("opencode_runner.close_raised %s", type(exc).__name__)
        if process is not None:
            shutdown_serve(process)
        _cleanup_xdg(isolated.xdg_data_home, isolated.xdg_config_home)


__all__ = ["run_opencode_mission"]
