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

import json
import logging
import os
import queue
import shutil
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
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
    filter_events_for_session,
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

# Backend-only default model selector. Read by the runner before spawning so
# HAM can fail closed with ``provider_not_configured`` if neither an explicit
# ``model`` argument nor this env was set. Never exposed to the browser; the
# value is read but only its presence is logged.
OPENCODE_DEFAULT_MODEL_ENV = "HAM_OPENCODE_DEFAULT_MODEL"


def _safe_log_fields(
    log_context: Mapping[str, Any] | None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose a redacted, JSON-safe dict for lifecycle logs.

    Only string/bool/int/None values are forwarded; everything else is
    coerced via ``type(value).__name__`` so secrets that may have been
    threaded by accident never reach the log surface as values.
    """
    fields: dict[str, Any] = {}
    for source in (log_context, extra):
        if not source:
            continue
        for key, value in source.items():
            if value is None or isinstance(value, (bool, int, str)):
                fields[str(key)] = value
            else:
                fields[str(key)] = type(value).__name__
    return fields


def _resolve_model_decision(
    model: str | None,
) -> tuple[str | None, str]:
    """Return ``(resolved_model_or_None, decision_source)``.

    The resolved model is ``None`` only when no explicit choice was made.
    ``decision_source`` is one of ``"caller"``, ``"env"``, or ``"unset"`` and
    is safe to log (it never contains the model id itself).
    """
    if model and str(model).strip():
        return str(model).strip(), "caller"
    env_value = (os.environ.get(OPENCODE_DEFAULT_MODEL_ENV) or "").strip()
    if env_value:
        return env_value, "env"
    return None, "unset"


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


# OpenCode ``opencode serve`` exposes a global subscription at this path per
# upstream mintdocs + server tables; legacy ``GET /event`` terminates after
# one ``server.connected`` frame and does not deliver session lifecycle events.
GLOBAL_SSE_EVENT_PATH = "/global/event"


def _decode_sse_data_line(line: str) -> dict[str, Any] | None:
    if not line or not line.strip():
        return None
    if line.startswith(":"):
        return None
    if line.startswith("data:"):
        payload = line.split(":", 1)[1].strip()
        try:
            decoded_any: Any = json.loads(payload)
        except json.JSONDecodeError:
            _LOG.debug("opencode_runner.sse_decode_failed JSONDecodeError")
            return None
        if isinstance(decoded_any, dict):
            return decoded_any
        return None
    return None


def _timed_sse_queue_iterator(
    q: queue.Queue[dict[str, Any] | None],
    *,
    deadline_s: float,
) -> Iterator[dict[str, Any]]:
    """Drain ``q`` until a ``None`` sentinel, timeout, or ``deadline_s`` elapses."""

    deadline_abs = time.monotonic() + deadline_s
    while True:
        remaining = deadline_abs - time.monotonic()
        if remaining <= 0:
            break
        timeout_s = max(min(remaining, 1.0), 1e-6)
        try:
            item = q.get(timeout=timeout_s)
        except queue.Empty:
            continue
        if item is None:
            break
        yield item


def _sse_reader_worker(
    stream_client: OpenCodeServeClient,
    q: queue.Queue[dict[str, Any] | None],
    errors: list[BaseException],
) -> None:
    """Background pump: subscribe to ``GET /global/event`` and enqueue payloads."""

    try:
        with stream_client.client.stream(
            "GET",
            GLOBAL_SSE_EVENT_PATH,
            headers={"Accept": "text/event-stream"},
        ) as response:
            response.raise_for_status()
            for line_raw in response.iter_lines():
                if line_raw is None:
                    continue
                line_str = (
                    line_raw.decode("utf-8", errors="replace")
                    if isinstance(line_raw, (bytes, bytearray))
                    else str(line_raw)
                )
                decoded = _decode_sse_data_line(line_str)
                if decoded is None:
                    continue
                q.put(decoded)
    except Exception as exc:  # noqa: BLE001
        errors.append(exc)
        _LOG.debug("opencode_runner.global_sse_reader_raised %s", type(exc).__name__)
    finally:
        q.put(None)


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
    log_context: Mapping[str, Any] | None = None,
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
    event_count = 0
    last_event_type: str | None = None

    _LOG.info(
        "opencode_runner.sse_stream_started %s",
        _safe_log_fields(log_context, {"session_id": session_id}),
    )

    for parsed in consume_events(event_stream):
        event_count += 1
        last_event_type = type(parsed).__name__
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
            _LOG.info(
                "opencode_runner.permission_request_received %s",
                _safe_log_fields(
                    log_context,
                    {
                        "category": (parsed.category or "")[:64],
                        "tool": (parsed.tool or "")[:64],
                    },
                ),
            )
            decision = _handle_permission_request(
                event=parsed,
                project_root=project_root,
                client=client,
                requested_at=time.monotonic(),
                timeout_s=permission_timeout_s,
            )
            _LOG.info(
                "opencode_runner.permission_request_decided %s",
                _safe_log_fields(log_context, {"decision": decision}),
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
    elapsed_ms = int(duration * 1000)
    assistant_summary = _cap(_redact("".join(assistant_text)), ASSISTANT_SUMMARY_CAP)

    base_log_fields = _safe_log_fields(
        log_context,
        {
            "event_count": event_count,
            "last_event_type": last_event_type or "none",
            "elapsed_ms": elapsed_ms,
            "tool_calls": tool_calls,
            "denied_tool_calls": denied,
            "changed_count": len(set(changed)),
            "deleted_count": len(set(deleted)),
        },
    )

    if last_error is not None:
        _LOG.info(
            "opencode_runner.sse_stream_ended status=session_error %s",
            base_log_fields,
        )
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

    if saw_complete:
        _LOG.info(
            "opencode_runner.completion_envelope_received %s",
            base_log_fields,
        )
        return OpenCodeRunResult(
            status="success",
            changed_paths=tuple(sorted(set(changed))),
            deleted_paths=tuple(sorted(set(deleted))),
            assistant_summary=assistant_summary,
            tool_calls_count=tool_calls,
            denied_tool_calls_count=denied,
            error_kind=None,
            error_summary=None,
            duration_seconds=duration,
        )

    # No completion envelope. Decide whether HAM saw all-denied tool calls
    # (operator policy is the cause) or a true protocol-level no-completion
    # (subprocess / SSE dropped without emitting ``session.idle``).
    if denied > 0 and not changed and not deleted:
        _LOG.info(
            "opencode_runner.sse_stream_ended status=permission_denied %s",
            base_log_fields,
        )
        return OpenCodeRunResult(
            status="permission_denied",
            changed_paths=(),
            deleted_paths=(),
            assistant_summary=assistant_summary,
            tool_calls_count=tool_calls,
            denied_tool_calls_count=denied,
            error_kind="permission_denied",
            error_summary="All OpenCode tool calls were denied by HAM policy.",
            duration_seconds=duration,
        )

    _LOG.warning(
        "opencode_runner.completion_envelope_missing %s",
        base_log_fields,
    )
    return OpenCodeRunResult(
        status="session_no_completion",
        changed_paths=tuple(sorted(set(changed))),
        deleted_paths=tuple(sorted(set(deleted))),
        assistant_summary=assistant_summary,
        tool_calls_count=tool_calls,
        denied_tool_calls_count=denied,
        error_kind="session_no_completion",
        error_summary="OpenCode session ended without a completion envelope.",
        duration_seconds=duration,
    )


def _cleanup_xdg(*paths: Path) -> None:
    for p in paths:
        try:
            shutil.rmtree(p, ignore_errors=True)
        except Exception as exc:  # noqa: BLE001
            _LOG.debug("opencode_runner.cleanup_raised %s", type(exc).__name__)


def run_opencode_mission(  # noqa: C901
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
    log_context: Mapping[str, Any] | None = None,
) -> OpenCodeRunResult:
    """Drive one OpenCode mission against a freshly-spawned ``opencode serve``.

    Returns an :class:`OpenCodeRunResult`. Never raises in tests when
    the injected seams behave; production failures inside the lifecycle
    are caught and collapsed into ``status="runner_error"``.

    The function never reads or logs env values; auth resolution happens
    inside :func:`build_isolated_env` and credentials flow only through
    the spawned process's env mapping plus the optional
    ``PUT /auth/:id`` HTTP injection below.

    ``log_context`` carries pre-redacted safe identifiers (``ham_run_id``,
    ``provider``, ``project_id``, ``workspace_id``, ``route``,
    ``proposal_digest``) so lifecycle log lines (INFO + the no-completion
    WARNING) can be correlated to a control-plane row without re-deriving
    the values inside the runner.
    """
    del actor

    resolved_model, model_source = _resolve_model_decision(model)
    if resolved_model is None:
        _LOG.warning(
            "opencode_runner.provider_not_configured %s",
            _safe_log_fields(log_context, {"reason": "model_unset"}),
        )
        return OpenCodeRunResult(
            status="provider_not_configured",
            error_kind="provider_not_configured",
            error_summary="No explicit OpenCode model/provider was configured for this launch.",
        )

    _LOG.info(
        "opencode_runner.run_starting %s",
        _safe_log_fields(log_context, {"model_source": model_source}),
    )

    isolated = build_isolated_env(
        project_root=project_root,
        actor_creds=actor_creds,
    )
    if not isolated.auth_present():
        _LOG.warning(
            "opencode_runner.auth_missing %s",
            _safe_log_fields(log_context, None),
        )
        _cleanup_xdg(isolated.xdg_data_home, isolated.xdg_config_home)
        return OpenCodeRunResult(
            status="auth_missing",
            error_kind="auth_missing",
            error_summary="No provider credentials available for OpenCode.",
        )

    process: ServeProcess | None = None
    client: OpenCodeServeClient | None = None
    sse_thread: threading.Thread | None = None
    stream_dup_client: OpenCodeServeClient | None = None
    try:
        _LOG.info(
            "opencode_runner.serve_spawn_attempted %s",
            _safe_log_fields(log_context, None),
        )
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
            exit_code = (
                process.handle.poll()
                if process is not None and process.handle is not None
                else None
            )
            _LOG.warning(
                "opencode_runner.serve_not_ready %s",
                _safe_log_fields(log_context, {"exit_code": exit_code}),
            )
            return OpenCodeRunResult(
                status="serve_unavailable",
                error_kind="health_timeout",
                error_summary="opencode serve did not become healthy within deadline.",
            )
        _LOG.info(
            "opencode_runner.serve_ready %s",
            _safe_log_fields(log_context, None),
        )

        # Provider creds are already exposed via the spawned env + inline
        # config substitution. The runtime PUT /auth call is a no-op
        # fallback for hosts whose config substitution path is disabled.
        for provider_id in ("openrouter", "anthropic", "openai", "groq"):
            env_key = f"{provider_id.upper()}_API_KEY"
            if not isolated.env.get(env_key):
                continue
            _LOG.info(
                "opencode_runner.auth_injection_attempted %s",
                _safe_log_fields(log_context, {"provider_id": provider_id}),
            )
            try:
                client.put_auth(provider_id, {"type": "api", "key": "{env:" + env_key + "}"})
            except Exception as exc:  # noqa: BLE001
                _LOG.warning(
                    "opencode_runner.auth_injection_failed %s",
                    _safe_log_fields(
                        log_context,
                        {"provider_id": provider_id, "err": type(exc).__name__},
                    ),
                )

        _LOG.info(
            "opencode_runner.session_create_attempted %s",
            _safe_log_fields(log_context, None),
        )
        try:
            session_resp = client.create_session(title="HAM OpenCode mission")
            session_body: Any = session_resp.json() if hasattr(session_resp, "json") else {}
        except Exception as exc:  # noqa: BLE001
            _LOG.warning(
                "opencode_runner.session_create_failed %s",
                _safe_log_fields(log_context, {"err": type(exc).__name__}),
            )
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
            _LOG.warning(
                "opencode_runner.session_missing_id %s",
                _safe_log_fields(log_context, None),
            )
            return OpenCodeRunResult(
                status="runner_error",
                error_kind="session_missing_id",
                error_summary="OpenCode session response did not include an id.",
            )

        sse_reader_errors: list[BaseException] = []
        if event_stream_factory is not None:
            filtered_event_stream = filter_events_for_session(
                event_stream_factory(client, session_id),
                session_id,
            )
        else:
            stream_dup_client = OpenCodeServeClient.open(
                base_url=process.base_url,
                auth=isolated.basic_auth(),
                client_factory=http_client_factory,
            )
            sse_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
            sse_thread = threading.Thread(
                target=_sse_reader_worker,
                kwargs={
                    "stream_client": stream_dup_client,
                    "q": sse_queue,
                    "errors": sse_reader_errors,
                },
                name="ham-opencode-global-sse",
                daemon=True,
            )
            sse_thread.start()
            filtered_event_stream = filter_events_for_session(
                _timed_sse_queue_iterator(sse_queue, deadline_s=deadline_s),
                session_id,
            )

        try:
            client.prompt_async(
                session_id,
                agent=agent,
                model=resolved_model,
                prompt=user_prompt,
            )
        except Exception as exc:  # noqa: BLE001
            _LOG.warning(
                "opencode_runner.prompt_failed %s",
                _safe_log_fields(log_context, {"err": type(exc).__name__}),
            )
            return OpenCodeRunResult(
                status="runner_error",
                error_kind="prompt_failed",
                error_summary=_cap(
                    f"failed to dispatch OpenCode prompt ({type(exc).__name__}).",
                    ERROR_SUMMARY_CAP,
                ),
            )

        if sse_reader_errors:
            _LOG.warning(
                "opencode_runner.global_sse_reader_failed %s",
                _safe_log_fields(
                    log_context,
                    {"err": type(sse_reader_errors[0]).__name__},
                ),
            )

        result = _consume_run(
            client=client,
            session_id=session_id,
            project_root=project_root,
            event_stream=filtered_event_stream,
            deadline_s=deadline_s,
            permission_timeout_s=permission_timeout_s,
            log_context=log_context,
        )

        exit_code = (
            process.handle.poll() if process is not None and process.handle is not None else None
        )
        if exit_code is not None:
            _LOG.info(
                "opencode_runner.subprocess_exited %s",
                _safe_log_fields(log_context, {"exit_code": exit_code}),
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
        _LOG.warning(
            "opencode_runner.run_raised %s",
            _safe_log_fields(log_context, {"err": type(exc).__name__}),
        )
        return OpenCodeRunResult(
            status="runner_error",
            error_kind=type(exc).__name__,
            error_summary=_cap(
                f"OpenCode runner raised {type(exc).__name__}.",
                ERROR_SUMMARY_CAP,
            ),
        )
    finally:
        if stream_dup_client is not None:
            try:
                stream_dup_client.close()
            except Exception as exc:  # noqa: BLE001
                _LOG.debug("opencode_runner.sse_client_close_raised %s", type(exc).__name__)
        if sse_thread is not None and sse_thread.is_alive():
            sse_thread.join(timeout=5.0)
        if client is not None:
            try:
                client.close()
            except Exception as exc:  # noqa: BLE001
                _LOG.debug("opencode_runner.close_raised %s", type(exc).__name__)
        if process is not None:
            shutdown_serve(process)
        _cleanup_xdg(isolated.xdg_data_home, isolated.xdg_config_home)


__all__ = ["GLOBAL_SSE_EVENT_PATH", "run_opencode_mission"]
