"""Unit tests for the HAM OpenCode runner package.

These tests exercise the runner without ever invoking the OpenCode binary.
``subprocess.Popen`` is monkeypatched globally to refuse to run; the
runner is driven via injected ``spawner`` / ``http_client_factory`` /
``event_stream_factory`` seams.

Canary strings are obvious fakes:

- ``OPENROUTER_API_KEY`` is set to ``opencode-test-canary-not-a-real-key``.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.ham.opencode_runner import (
    PermissionContext,
    apply_timeout,
    build_isolated_env,
    consume_events,
    decide_permission,
    parse_event,
    run_opencode_mission,
)
from src.ham.opencode_runner.event_consumer import (
    AssistantMessageChunk,
    FileChange,
    PermissionRequest,
    ServerConnected,
    SessionComplete,
    SessionError,
    UnknownEvent,
)
from src.ham.opencode_runner.server_process import ServeProcess

_AUTH_CANARY = "opencode-test-canary-not-a-real-key"


@pytest.fixture(autouse=True)
def _default_opencode_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin a fake default model so the runner's provider-not-configured gate
    does not fail closed in tests that don't exercise the gate directly.

    Tests that want to exercise the gate can ``monkeypatch.delenv`` this name
    inside their own bodies.
    """
    monkeypatch.setenv("HAM_OPENCODE_DEFAULT_MODEL", "opencode-test-fake/model")


# ---------------------------------------------------------------------------
# Permission broker
# ---------------------------------------------------------------------------


def test_permission_broker_denies_bash_by_default(tmp_path: Path) -> None:
    ctx = PermissionContext(category="bash", project_root=tmp_path, bash_command="ls")
    decision, reason = decide_permission(ctx)
    assert decision == "deny"
    assert "bash" in reason


def test_permission_broker_denies_bash_denylist_match(tmp_path: Path) -> None:
    ctx = PermissionContext(category="bash", project_root=tmp_path, bash_command="rm -rf /")
    decision, reason = decide_permission(ctx)
    assert decision == "deny"
    assert "denylist" in reason


def test_permission_broker_denies_external_directory_by_default(tmp_path: Path) -> None:
    ctx = PermissionContext(category="external_directory", project_root=tmp_path)
    decision, _ = decide_permission(ctx)
    assert decision == "deny"


def test_permission_broker_allows_read_glob_grep(tmp_path: Path) -> None:
    for category in ("read", "glob", "grep", "list", "lsp", "todowrite"):
        ctx = PermissionContext(category=category, project_root=tmp_path)
        decision, _ = decide_permission(ctx)
        assert decision == "allow", category


def test_permission_broker_denies_edit_outside_project_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "elsewhere" / "secret.txt"
    ctx = PermissionContext(category="edit", project_root=tmp_path, target_path=str(outside))
    decision, reason = decide_permission(ctx)
    assert decision == "deny"
    assert "outside" in reason


def test_permission_broker_allows_edit_inside_project_root(tmp_path: Path) -> None:
    inside = tmp_path / "src" / "main.py"
    inside.parent.mkdir(parents=True, exist_ok=True)
    inside.write_text("x")
    ctx = PermissionContext(category="edit", project_root=tmp_path, target_path=str(inside))
    decision, _ = decide_permission(ctx)
    assert decision == "allow"


def test_permission_broker_denies_unknown_category(tmp_path: Path) -> None:
    ctx = PermissionContext(category="unmapped", project_root=tmp_path)
    decision, reason = decide_permission(ctx)
    assert decision == "deny"
    assert reason == "unknown_category"


def test_permission_broker_times_out_to_deny_after_30s() -> None:
    now = 1000.0
    res = apply_timeout(requested_at=now - 31.0, now=now, timeout_s=30.0)
    assert res == ("deny", "permission_timeout")


def test_permission_broker_within_deadline_returns_none() -> None:
    now = 1000.0
    res = apply_timeout(requested_at=now - 5.0, now=now, timeout_s=30.0)
    assert res is None


# ---------------------------------------------------------------------------
# Event consumer
# ---------------------------------------------------------------------------


def test_event_consumer_parses_known_events() -> None:
    raw = [
        {"type": "server.connected"},
        {"type": "message.part.updated", "part": {"text": "hello"}},
        {"type": "file.changed", "path": "src/a.py", "deleted": False},
        {
            "type": "session.permission.requested",
            "sessionID": "s",
            "permissionID": "p",
            "category": "edit",
        },
        {"type": "session.idle", "sessionID": "s"},
    ]
    parsed = list(consume_events(raw))
    assert isinstance(parsed[0], ServerConnected)
    assert isinstance(parsed[1], AssistantMessageChunk)
    assert isinstance(parsed[2], FileChange)
    assert isinstance(parsed[3], PermissionRequest)
    assert isinstance(parsed[4], SessionComplete)


def test_event_consumer_tolerates_unknown_types() -> None:
    raw = [{"type": "xyz.weird", "payload": 1}]
    parsed = list(consume_events(raw))
    assert isinstance(parsed[0], UnknownEvent)


def test_event_consumer_tolerates_extra_fields() -> None:
    raw = {"type": "session.idle", "sessionID": "s", "extra": {"future": True}}
    ev = parse_event(raw)
    assert isinstance(ev, SessionComplete)
    # extra='allow' on the model preserves the extra value.
    assert getattr(ev, "extra", None) == {"future": True}


def test_event_consumer_handles_session_error() -> None:
    ev = parse_event({"type": "session.error", "message": "boom"})
    assert isinstance(ev, SessionError)
    assert ev.message == "boom"


# ---------------------------------------------------------------------------
# Global SSE session filtering
# ---------------------------------------------------------------------------


def test_filter_events_for_session_skips_foreign_session_payloads() -> None:
    from src.ham.opencode_runner.event_consumer import filter_events_for_session

    sid = "sess_target"
    stream = [
        {"type": "server.connected"},
        {"type": "message.part.updated", "sessionID": "other", "part": {"text": "x"}},
        {"type": "message.part.updated", "sessionID": sid, "part": {"text": "ok"}},
        {"type": "session.idle", "sessionID": "other"},
        {"type": "session.idle", "sessionID": sid},
    ]
    out = list(filter_events_for_session(iter(stream), sid))
    texts = []
    for e in out:
        if e["type"] == "message.part.updated":
            texts.append(((e["part"] or {}).get("text") or "").strip())
    assert texts == ["ok"]
    idle_ids = [e.get("sessionID") for e in out if e["type"] == "session.idle"]
    assert idle_ids == [sid]


def test_runner_global_sse_subscribed_before_prompt_async(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production path opens ``GET /global/event`` before ``prompt_async``."""
    from src.ham.opencode_runner.runner import GLOBAL_SSE_EVENT_PATH

    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    handle = _FakeHandle()
    seq: list[tuple[str, str]] = []
    sse_body = (
        b'data: {"type":"server.connected"}\n\n'
        b'data: {"type":"session.idle","sessionID":"sess_abc"}\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        meth = request.method.upper()
        path = request.url.path
        seq.append((meth, path))
        if path == "/global/health":
            return httpx.Response(200, json={"healthy": True, "version": "test"})
        if path == "/session" and meth == "POST":
            return httpx.Response(200, json={"id": "sess_abc", "title": "t"})
        if path.startswith("/auth/") and meth == "PUT":
            return httpx.Response(200, json=True)
        if meth == "GET" and path == GLOBAL_SSE_EVENT_PATH:
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=sse_body,
            )
        if path.endswith("/prompt_async") and meth == "POST":
            return httpx.Response(204)
        if path.endswith("/abort") or path == "/instance/dispose":
            return httpx.Response(200, json=True)
        return httpx.Response(404, json={"error": path})

    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner_factory(handle),
        http_client_factory=_http_factory(handler),
        # Explicitly exercise the threaded global SSE subscriber (second client).
        event_stream_factory=None,
    )
    assert result.status == "success"
    ge_idx = next(i for i, (m, p) in enumerate(seq) if m == "GET" and p == GLOBAL_SSE_EVENT_PATH)
    pr_idx = next(
        i for i, (m, p) in enumerate(seq) if m == "POST" and p.endswith("/prompt_async")
    )
    assert ge_idx < pr_idx


def test_runner_server_connected_without_idle_session_no_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    events = [{"type": "server.connected"}]
    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner_factory(_FakeHandle()),
        http_client_factory=_http_factory(_basic_handler_factory()),
        event_stream_factory=lambda _c, _s: iter(events),
    )
    assert result.status == "session_no_completion"
    assert result.error_kind == "session_no_completion"


def test_runner_ignores_session_error_for_foreign_session_then_completes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    events = [
        {"type": "server.connected"},
        {"type": "session.error", "sessionID": "other", "message": "boom"},
        {"type": "session.idle", "sessionID": "sess_abc"},
    ]
    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner_factory(_FakeHandle()),
        http_client_factory=_http_factory(_basic_handler_factory()),
        event_stream_factory=lambda _c, _s: iter(events),
    )
    assert result.status == "success"


def test_runner_matching_session_error_is_runner_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    events = [
        {"type": "server.connected"},
        {"type": "session.error", "sessionID": "sess_abc", "message": "bad llm"},
    ]
    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner_factory(_FakeHandle()),
        http_client_factory=_http_factory(_basic_handler_factory()),
        event_stream_factory=lambda _c, _s: iter(events),
    )
    assert result.status == "runner_error"
    assert result.error_kind == "session_error"
    assert "bad llm" in (result.error_summary or "")


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------


def test_adapter_uses_per_run_xdg_data_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    iso = build_isolated_env(project_root=tmp_path)
    try:
        assert iso.xdg_data_home.exists()
        assert iso.xdg_config_home.exists()
        assert iso.env["XDG_DATA_HOME"] == str(iso.xdg_data_home)
        assert iso.env["XDG_CONFIG_HOME"] == str(iso.xdg_config_home)
    finally:
        import shutil

        shutil.rmtree(iso.xdg_data_home, ignore_errors=True)
        shutil.rmtree(iso.xdg_config_home, ignore_errors=True)


def test_adapter_does_not_use_shared_global_auth_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """XDG redirection guarantees ~/.local/share/opencode/auth.json is never touched."""
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    iso = build_isolated_env(project_root=tmp_path)
    try:
        # The XDG_DATA_HOME points to a fresh tempdir, not $HOME/.local/share.
        home = Path(iso.env.get("HOME", "/")).expanduser()
        candidate = home / ".local" / "share"
        assert not str(iso.xdg_data_home).startswith(str(candidate))
        assert _AUTH_CANARY not in iso.env["XDG_DATA_HOME"]
    finally:
        import shutil

        shutil.rmtree(iso.xdg_data_home, ignore_errors=True)
        shutil.rmtree(iso.xdg_config_home, ignore_errors=True)


def test_adapter_password_is_per_run_random(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    iso1 = build_isolated_env(project_root=tmp_path)
    iso2 = build_isolated_env(project_root=tmp_path)
    try:
        assert iso1.password != iso2.password
        assert len(iso1.password) >= 32
        assert iso1.env["OPENCODE_SERVER_PASSWORD"] == iso1.password
    finally:
        import shutil

        for x in (iso1, iso2):
            shutil.rmtree(x.xdg_data_home, ignore_errors=True)
            shutil.rmtree(x.xdg_config_home, ignore_errors=True)


def test_adapter_isolated_env_does_not_log_secret_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    caplog.set_level(logging.DEBUG)
    iso = build_isolated_env(project_root=tmp_path)
    try:
        blob = "\n".join(rec.getMessage() for rec in caplog.records)
        assert _AUTH_CANARY not in blob
        assert iso.env.get("OPENROUTER_API_KEY") == _AUTH_CANARY
    finally:
        import shutil

        shutil.rmtree(iso.xdg_data_home, ignore_errors=True)
        shutil.rmtree(iso.xdg_config_home, ignore_errors=True)


# ---------------------------------------------------------------------------
# Runner orchestration (mocked end-to-end)
# ---------------------------------------------------------------------------


class _FakeHandle:
    def __init__(self) -> None:
        self.pid = 12345
        self._terminated = False
        self._killed = False
        self._poll_value: int | None = None

    def poll(self) -> int | None:
        return self._poll_value

    def terminate(self) -> None:
        self._terminated = True
        self._poll_value = 0

    def kill(self) -> None:
        self._killed = True
        self._poll_value = 0

    def wait(self, timeout: float | None = None) -> int:  # noqa: ARG002
        return 0


def _no_spawner_assert(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
    raise AssertionError("opencode serve must NOT be spawned via subprocess in this test")


def _mock_spawner_factory(handle: _FakeHandle) -> Any:
    def spawn(*, argv, env, cwd):  # noqa: ARG001
        return handle

    return spawn


def _http_factory(handler):
    def factory(*, base_url, auth):  # noqa: ARG001
        transport = httpx.MockTransport(handler)
        return httpx.Client(base_url=base_url, auth=auth, transport=transport, timeout=5.0)

    return factory


def _basic_handler_factory(events: list[dict[str, Any]] | None = None):
    state = {"session_id": "sess_abc", "events": events or []}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/global/health":
            return httpx.Response(200, json={"healthy": True, "version": "test"})
        if path == "/session" and request.method == "POST":
            return httpx.Response(200, json={"id": state["session_id"], "title": "t"})
        if path.startswith("/auth/") and request.method == "PUT":
            return httpx.Response(200, json=True)
        if path.endswith("/prompt_async") and request.method == "POST":
            return httpx.Response(204)
        if path.endswith("/abort"):
            return httpx.Response(200, json=True)
        if path == "/instance/dispose":
            return httpx.Response(200, json=True)
        if path.startswith("/session/") and "/permissions/" in path:
            return httpx.Response(200, json=True)
        return httpx.Response(404, json={"error": path})

    return handler


def test_runner_returns_success_when_session_completes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    handle = _FakeHandle()
    spawn = _mock_spawner_factory(handle)
    handler = _basic_handler_factory()
    events = [
        {"type": "server.connected"},
        {"type": "message.part.updated", "part": {"text": "all done"}},
        {"type": "file.changed", "path": "README.md"},
        {"type": "session.idle", "sessionID": "sess_abc"},
    ]
    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=spawn,
        http_client_factory=_http_factory(handler),
        event_stream_factory=lambda _c, _s: iter(events),
    )
    assert result.status == "success"
    assert "all done" in result.assistant_summary
    assert result.changed_paths == ("README.md",)
    assert result.deleted_paths == ()


def test_runner_records_deleted_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    handle = _FakeHandle()
    handler = _basic_handler_factory()
    events = [
        {"type": "server.connected"},
        {"type": "file.changed", "path": "README.md", "deleted": True},
        {"type": "session.idle"},
    ]
    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner_factory(handle),
        http_client_factory=_http_factory(handler),
        event_stream_factory=lambda _c, _s: iter(events),
    )
    assert result.status == "success"
    assert result.deleted_paths == ("README.md",)


def test_runner_serve_unavailable_when_health_never_ok(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)

    def health_unhealthy(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"healthy": False})

    monkeypatch.setattr("src.ham.opencode_runner.runner.HEALTH_POLL_TIMEOUT_S", 0.1)
    monkeypatch.setattr("src.ham.opencode_runner.runner.HEALTH_POLL_INTERVAL_S", 0.01)

    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner_factory(_FakeHandle()),
        http_client_factory=_http_factory(health_unhealthy),
        event_stream_factory=lambda _c, _s: iter([]),
    )
    assert result.status == "serve_unavailable"


def test_runner_auth_missing_when_no_creds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for n in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setattr("subprocess.Popen", _no_spawner_assert)
    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
    )
    assert result.status == "auth_missing"


def test_runner_does_not_invoke_subprocess_popen_when_seam_injected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    monkeypatch.setattr("subprocess.Popen", _no_spawner_assert)

    handler = _basic_handler_factory()
    events = [
        {"type": "server.connected"},
        {"type": "session.idle"},
    ]
    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner_factory(_FakeHandle()),
        http_client_factory=_http_factory(handler),
        event_stream_factory=lambda _c, _s: iter(events),
    )
    # If we got here, subprocess.Popen was NOT called.
    assert result.status == "success"


def test_runner_permission_request_routed_through_broker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    permissions_seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/global/health":
            return httpx.Response(200, json={"healthy": True})
        if path == "/session" and request.method == "POST":
            return httpx.Response(200, json={"id": "s1"})
        if path.startswith("/auth/") and request.method == "PUT":
            return httpx.Response(200, json=True)
        if path.endswith("/prompt_async"):
            return httpx.Response(204)
        if "/permissions/" in path:
            permissions_seen.append({"path": path, "body": request.content.decode()})
            return httpx.Response(200, json=True)
        if path.endswith("/abort") or path == "/instance/dispose":
            return httpx.Response(200, json=True)
        return httpx.Response(404)

    events = [
        {"type": "server.connected"},
        {
            "type": "session.permission.requested",
            "sessionID": "s1",
            "permissionID": "p1",
            "category": "bash",
            "command": "ls",
        },
        {"type": "session.idle"},
    ]
    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner_factory(_FakeHandle()),
        http_client_factory=_http_factory(handler),
        event_stream_factory=lambda _c, _s: iter(events),
    )
    assert len(permissions_seen) == 1
    assert '"response":"deny"' in permissions_seen[0]["body"]
    assert result.denied_tool_calls_count == 1


def test_runner_no_secret_in_error_summary_when_runner_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)

    def spawn_explodes(**_kwargs: Any) -> Any:
        raise RuntimeError(_AUTH_CANARY)

    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=spawn_explodes,
    )
    assert result.status == "runner_error"
    assert _AUTH_CANARY not in (result.error_summary or "")
    assert _AUTH_CANARY not in result.assistant_summary


def test_runner_disposes_instance_on_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    dispose_seen: list[bool] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/instance/dispose":
            dispose_seen.append(True)
            return httpx.Response(200, json=True)
        return _basic_handler_factory()(request)

    events = [
        {"type": "server.connected"},
        {"type": "session.idle"},
    ]
    run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner_factory(_FakeHandle()),
        http_client_factory=_http_factory(handler),
        event_stream_factory=lambda _c, _s: iter(events),
    )
    assert dispose_seen == [True]


def test_runner_shutdown_calls_terminate_after_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    handle = _FakeHandle()
    events = [
        {"type": "server.connected"},
        {"type": "session.idle"},
    ]
    run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner_factory(handle),
        http_client_factory=_http_factory(_basic_handler_factory()),
        event_stream_factory=lambda _c, _s: iter(events),
    )
    assert handle._terminated is True


def test_runner_cleanup_removes_xdg_temp_dirs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    captured: dict[str, Path] = {}

    real_build = build_isolated_env

    def capturing_build(**kwargs: Any) -> Any:
        iso = real_build(**kwargs)
        captured["data"] = iso.xdg_data_home
        captured["config"] = iso.xdg_config_home
        return iso

    monkeypatch.setattr(
        "src.ham.opencode_runner.runner.build_isolated_env",
        capturing_build,
    )

    events = [{"type": "server.connected"}, {"type": "session.idle"}]
    run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner_factory(_FakeHandle()),
        http_client_factory=_http_factory(_basic_handler_factory()),
        event_stream_factory=lambda _c, _s: iter(events),
    )
    assert not captured["data"].exists()
    assert not captured["config"].exists()


# ---------------------------------------------------------------------------
# Server-process helpers
# ---------------------------------------------------------------------------


def test_shutdown_serve_terminates_then_kills_if_needed(tmp_path: Path) -> None:
    from src.ham.opencode_runner.server_process import shutdown_serve

    class _Stubborn:
        pid = 9999

        def __init__(self) -> None:
            self.terminated = False
            self.killed = False

        def poll(self) -> int | None:
            return None  # Never exits.

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

        def wait(self, timeout: float | None = None) -> int:  # noqa: ARG002
            return 0

    handle = _Stubborn()
    proc = ServeProcess(handle=handle, host="127.0.0.1", port=12345, cwd=tmp_path)
    shutdown_serve(proc, grace_period_s=0.05, kill_fn=lambda *_a, **_k: None)
    assert handle.terminated is True
    assert handle.killed is True


def test_default_spawner_is_only_subprocess_import_site() -> None:
    """The runner package must not import subprocess except in server_process."""
    from src.ham.opencode_runner import (
        event_consumer,
        http_client,
        permission_broker,
        result,
        runner,
        workspace_isolation,
    )

    for mod in (
        event_consumer,
        http_client,
        permission_broker,
        result,
        runner,
        workspace_isolation,
    ):
        assert getattr(mod, "subprocess", None) is None, mod.__name__


# ---------------------------------------------------------------------------
# Permission broker timeout integration
# ---------------------------------------------------------------------------


def test_permission_request_auto_denies_after_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.ham.opencode_runner.runner import _handle_permission_request

    class _Client:
        def respond_permission(self, *a: Any, **k: Any) -> Any:
            self.last = (a, k)
            return httpx.Response(200, json=True)

    event = PermissionRequest(
        type="session.permission.requested",
        sessionID="s",
        permissionID="p",
        category="read",
    )
    client = _Client()
    decision = _handle_permission_request(
        event=event,
        project_root=tmp_path,
        client=client,  # type: ignore[arg-type]
        requested_at=time.monotonic() - 60.0,
        timeout_s=30.0,
    )
    assert decision == "deny"
    assert client.last[1]["response"] == "deny"
