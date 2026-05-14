"""OpenCode hardening regression tests — no-completion + provider gate + log redaction.

These tests pin the contract added by the "persist OpenCode no-completion
failures" hardening pass:

- The runner returns ``status="session_no_completion"`` when the SSE stream
  ends without a recognised completion envelope.
- The runner returns ``status="provider_not_configured"`` when no explicit
  backend-resolved model is configured (no ``model`` arg and no
  ``HAM_OPENCODE_DEFAULT_MODEL`` env value).
- The runner emits a WARNING on missing completion that carries only the
  safe ``log_context`` fields plus elapsed_ms / event_count / last_event_type.
- The runner never echoes a canary provider value into a log line.
- ``opencode_build._status_from_run`` maps the new statuses onto the
  ``opencode:session_no_completion`` / ``opencode:provider_not_configured``
  ``ControlPlaneRun.status_reason`` values.
- The ``GET /api/control-plane-runs`` read API resolves its store through
  :func:`get_control_plane_run_store` (the same factory the write paths use)
  so a no-completion failure persisted in the configured backend is visible
  to operator reads on the same deployment.

All tests work entirely off mocked seams; no live OpenCode is invoked.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api import control_plane_runs as cpr_api
from src.api import opencode_build as build_api
from src.api.clerk_gate import get_ham_clerk_actor
from src.api.server import app, fastapi_app
from src.ham.clerk_auth import HamActor
from src.ham.opencode_runner import run_opencode_mission
from src.ham.opencode_runner.result import OpenCodeRunResult
from src.ham.opencode_runner.runner import (
    OPENCODE_DEFAULT_MODEL_ENV,
    _resolve_model_decision,
)
from src.ham.worker_adapters.opencode_adapter import OpenCodeStatus
from src.persistence.control_plane_run import (
    ControlPlaneRun,
    ControlPlaneRunStore,
    set_control_plane_run_store_for_tests,
    utc_now_iso,
)

_AUTH_CANARY = "opencode-test-canary-not-a-real-key"
_EXEC_TOKEN_CANARY = "test-token-canary"  # noqa: S105


# ---------------------------------------------------------------------------
# Shared helpers (lifted from the existing OpenCode test files to keep this
# module self-contained without coupling to internal fixtures).
# ---------------------------------------------------------------------------


class _FakeHandle:
    def __init__(self) -> None:
        self.pid = 11111
        self._poll_value: int | None = None

    def poll(self) -> int | None:
        return self._poll_value

    def terminate(self) -> None:
        self._poll_value = 0

    def kill(self) -> None:
        self._poll_value = 0

    def wait(self, timeout: float | None = None) -> int:  # noqa: ARG002
        return 0


def _mock_spawner(handle: _FakeHandle) -> Any:
    def spawn(*, argv, env, cwd):  # noqa: ARG001
        return handle

    return spawn


def _http_factory(handler):
    def factory(*, base_url, auth):  # noqa: ARG001
        transport = httpx.MockTransport(handler)
        return httpx.Client(base_url=base_url, auth=auth, transport=transport, timeout=5.0)

    return factory


def _basic_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/global/health":
        return httpx.Response(200, json={"healthy": True})
    if path == "/session" and request.method == "POST":
        return httpx.Response(200, json={"id": "sess_hd"})
    if path.startswith("/auth/") and request.method == "PUT":
        return httpx.Response(200, json=True)
    if path.endswith("/prompt_async"):
        return httpx.Response(204)
    if path.endswith("/abort") or path == "/instance/dispose":
        return httpx.Response(200, json=True)
    return httpx.Response(404)


@pytest.fixture
def actor() -> HamActor:
    return HamActor(
        user_id="user_owner",
        org_id="org_managed",
        session_id="sess_h",
        email="owner@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


@pytest.fixture
def cleanup_overrides() -> Any:
    yield
    fastapi_app.dependency_overrides.clear()


def _project_rec(
    *,
    project_id: str = "project.opencode-hd",
    output_target: str = "managed_workspace",
    workspace_id: str | None = "ws_hd",
) -> Any:
    return SimpleNamespace(
        id=project_id,
        name="p_hd",
        output_target=output_target,
        workspace_id=workspace_id,
        build_lane_enabled=True,
        root="/tmp/p_hd",
    )


def _readiness(status: OpenCodeStatus = OpenCodeStatus.CONFIGURED) -> Any:
    return SimpleNamespace(
        status=status,
        enabled=True,
        cli_present=True,
        auth_hints={"OPENROUTER_API_KEY": True},
        integration_modes={"serve": True, "acp": True, "cli": True},
        reason=None,
    )


def _patch_build_gates(rec: Any) -> list[Any]:
    patches = [
        patch.object(build_api, "_require_build_lane_project", lambda pid: rec),
        patch.object(build_api, "_require_build_approver", lambda actor, rec, store: None),
        patch.object(build_api, "check_opencode_readiness", lambda actor: _readiness()),
    ]
    for p in patches:
        p.start()
    return patches


def _stop(patches: list[Any]) -> None:
    for p in reversed(patches):
        p.stop()


def _client(actor: HamActor | None = None) -> TestClient:
    if actor is not None:
        fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: actor
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Runner — provider-not-configured gate before spawning
# ---------------------------------------------------------------------------


def test_resolve_model_decision_caller_takes_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENCODE_DEFAULT_MODEL_ENV, "env-model")
    resolved, source = _resolve_model_decision("caller-model")
    assert resolved == "caller-model"
    assert source == "caller"


def test_resolve_model_decision_env_used_when_caller_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENCODE_DEFAULT_MODEL_ENV, "env-model")
    resolved, source = _resolve_model_decision(None)
    assert resolved == "env-model"
    assert source == "env"


def test_resolve_model_decision_unset_when_neither_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(OPENCODE_DEFAULT_MODEL_ENV, raising=False)
    resolved, source = _resolve_model_decision(None)
    assert resolved is None
    assert source == "unset"


def test_runner_fails_provider_not_configured_before_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no model is set, the runner returns ``provider_not_configured``
    BEFORE touching the spawner / HTTP client / SSE seams."""
    monkeypatch.delenv(OPENCODE_DEFAULT_MODEL_ENV, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)

    def explode_spawner(**_kwargs: Any) -> Any:
        raise AssertionError("spawner must NOT be invoked when model is unset")

    def explode_http(**_kwargs: Any) -> Any:
        raise AssertionError("http client must NOT be opened when model is unset")

    def explode_stream(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("event stream must NOT be created when model is unset")

    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=explode_spawner,
        http_client_factory=explode_http,
        event_stream_factory=explode_stream,
    )
    assert result.status == "provider_not_configured"
    assert result.error_kind == "provider_not_configured"
    assert result.error_summary is not None
    assert (
        "model/provider" in result.error_summary.lower()
        or "provider" in result.error_summary.lower()
    )


def test_runner_provider_not_configured_does_not_log_caller_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv(OPENCODE_DEFAULT_MODEL_ENV, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    caplog.set_level(logging.DEBUG, logger="src.ham.opencode_runner.runner")
    run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
    )
    blob = "\n".join(rec.getMessage() for rec in caplog.records)
    assert _AUTH_CANARY not in blob


def test_runner_proceeds_when_env_default_model_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    monkeypatch.setenv(OPENCODE_DEFAULT_MODEL_ENV, "openrouter/fake")
    events = [
        {"type": "server.connected"},
        {"type": "session.idle"},
    ]
    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner(_FakeHandle()),
        http_client_factory=_http_factory(_basic_handler),
        event_stream_factory=lambda _c, _s: iter(events),
    )
    assert result.status == "success"


# ---------------------------------------------------------------------------
# 2. Runner — session_no_completion (SSE ended without session.idle)
# ---------------------------------------------------------------------------


def test_runner_returns_session_no_completion_when_stream_ends_without_idle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    monkeypatch.setenv(OPENCODE_DEFAULT_MODEL_ENV, "openrouter/fake")
    # SSE stream ends without ``session.idle`` and without ``session.error``.
    events = [
        {"type": "server.connected"},
        {"type": "message.part.updated", "part": {"text": "thinking..."}},
        {"type": "file.changed", "path": "src/x.py"},
    ]
    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner(_FakeHandle()),
        http_client_factory=_http_factory(_basic_handler),
        event_stream_factory=lambda _c, _s: iter(events),
    )
    assert result.status == "session_no_completion"
    assert result.error_kind == "session_no_completion"
    assert result.error_summary is not None
    assert "completion" in result.error_summary.lower()
    # Even though the run did not complete, intermediate observations are kept.
    assert result.changed_paths == ("src/x.py",)


def test_runner_session_no_completion_emits_warning_with_safe_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    monkeypatch.setenv(OPENCODE_DEFAULT_MODEL_ENV, "openrouter/fake")
    caplog.set_level(logging.INFO, logger="src.ham.opencode_runner.runner")

    log_context = {
        "ham_run_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "provider": "opencode_cli",
        "route": "/api/opencode/build/launch",
        "project_id": "project.demo",
        "workspace_id": "ws_demo",
        "proposal_digest": "d" * 64,
    }
    events = [
        {"type": "server.connected"},
        {"type": "message.part.updated", "part": {"text": "hi"}},
    ]
    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner(_FakeHandle()),
        http_client_factory=_http_factory(_basic_handler),
        event_stream_factory=lambda _c, _s: iter(events),
        log_context=log_context,
    )
    assert result.status == "session_no_completion"

    warning_records = [
        rec
        for rec in caplog.records
        if rec.levelno == logging.WARNING and "completion_envelope_missing" in rec.getMessage()
    ]
    assert warning_records, "expected a WARNING log for missing completion envelope"
    blob = warning_records[0].getMessage()
    # Safe identifiers are present.
    for key in (
        "ham_run_id",
        "provider",
        "project_id",
        "workspace_id",
        "route",
        "elapsed_ms",
        "event_count",
        "last_event_type",
    ):
        assert key in blob, key
    # Secret-shaped values are not present.
    assert _AUTH_CANARY not in blob
    assert _EXEC_TOKEN_CANARY not in blob


def test_runner_session_no_completion_does_not_echo_secrets_in_any_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    monkeypatch.setenv(OPENCODE_DEFAULT_MODEL_ENV, "openrouter/fake")
    caplog.set_level(logging.DEBUG)
    events = [{"type": "server.connected"}]
    run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner(_FakeHandle()),
        http_client_factory=_http_factory(_basic_handler),
        event_stream_factory=lambda _c, _s: iter(events),
    )
    blob = "\n".join(rec.getMessage() for rec in caplog.records)
    assert _AUTH_CANARY not in blob
    assert _EXEC_TOKEN_CANARY not in blob


# ---------------------------------------------------------------------------
# 3. opencode_build._status_from_run — new status mappings
# ---------------------------------------------------------------------------


def test_status_from_run_maps_session_no_completion_to_status_reason() -> None:
    status, reason = build_api._status_from_run("session_no_completion", None)
    assert status == "failed"
    assert reason == "opencode:session_no_completion"


def test_status_from_run_maps_provider_not_configured_to_status_reason() -> None:
    status, reason = build_api._status_from_run("provider_not_configured", None)
    assert status == "failed"
    assert reason == "opencode:provider_not_configured"


# ---------------------------------------------------------------------------
# 4. End-to-end launch — no-completion persists a failed ControlPlaneRun and
#    does NOT emit a snapshot, NOT advance head, NOT create a successful row.
# ---------------------------------------------------------------------------


def _setup_launch_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in (
        "HAM_OPENCODE_ENABLED",
        "HAM_OPENCODE_EXECUTION_ENABLED",
        "HAM_OPENCODE_EXEC_TOKEN",
        "HAM_OPENCODE_ALLOW_DELETIONS",
        "OPENROUTER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    monkeypatch.setenv("HAM_MANAGED_WORKSPACE_ROOT", str(tmp_path / "ham-ws"))


def _preview_digest(project_id: str, user_prompt: str) -> str:
    return build_api.compute_opencode_proposal_digest(
        project_id=project_id, user_prompt=user_prompt, model=None
    )


def test_launch_no_completion_persists_failed_run_no_snapshot_no_head(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    _setup_launch_env(monkeypatch, tmp_path)
    rec = _project_rec()
    patches = _patch_build_gates(rec)
    digest = _preview_digest(rec.id, "tidy")

    def no_completion_runner(**_kwargs: Any) -> OpenCodeRunResult:
        return OpenCodeRunResult(
            status="session_no_completion",
            assistant_summary="partial output",
            error_kind="session_no_completion",
            error_summary="OpenCode session ended without a completion envelope.",
            duration_seconds=0.1,
        )

    snapshot_mock = MagicMock()
    deleted_paths_mock = MagicMock(return_value=())
    saved: list[Any] = []
    fake_store = SimpleNamespace(save=lambda r, **k: saved.append(r))

    try:
        with (
            patch.object(build_api, "run_opencode_mission", no_completion_runner),
            patch.object(build_api, "compute_deleted_paths_against_parent", deleted_paths_mock),
            patch.object(build_api, "emit_managed_workspace_snapshot", snapshot_mock),
            patch.object(build_api, "get_control_plane_run_store", lambda: fake_store),
        ):
            res = _client(actor).post(
                "/api/opencode/build/launch",
                json={
                    "project_id": rec.id,
                    "user_prompt": "tidy",
                    "proposal_digest": digest,
                    "base_revision": build_api.OPENCODE_REGISTRY_REVISION,
                    "confirmed": True,
                },
                headers={"Authorization": f"Bearer {_EXEC_TOKEN_CANARY}"},
            )
    finally:
        _stop(patches)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is False
    assert body["control_plane_status"] == "failed"
    assert body["output_ref"] is None

    # Exactly one ControlPlaneRun row persisted, with the new status_reason.
    assert len(saved) == 1
    cp = saved[0]
    assert cp.provider == "opencode_cli"
    assert cp.action_kind == "launch"
    assert cp.status == "failed"
    assert cp.status_reason == "opencode:session_no_completion"
    assert cp.output_target == "managed_workspace"
    # No PR fields, no audit_ref leakage.
    assert cp.pr_url is None
    assert cp.pr_branch is None
    assert cp.audit_ref is None

    # No snapshot was emitted (so head.json was not advanced and no
    # successful ProjectSnapshot was created).
    snapshot_mock.assert_not_called()
    # The deletion-guard helper is also not consulted on the no-completion
    # path (because we never enter the ``run_result.status == "success"``
    # branch).
    deleted_paths_mock.assert_not_called()


def test_launch_provider_not_configured_persists_failed_run_no_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    """The runner can also return ``provider_not_configured`` after the
    gate stack; the launch core must persist a failed ControlPlaneRun
    with the right status_reason without ever emitting a snapshot."""
    _setup_launch_env(monkeypatch, tmp_path)
    rec = _project_rec()
    patches = _patch_build_gates(rec)
    digest = _preview_digest(rec.id, "tidy")

    def provider_not_configured_runner(**_kwargs: Any) -> OpenCodeRunResult:
        return OpenCodeRunResult(
            status="provider_not_configured",
            error_kind="provider_not_configured",
            error_summary="No explicit OpenCode model/provider was configured for this launch.",
        )

    snapshot_mock = MagicMock()
    saved: list[Any] = []
    fake_store = SimpleNamespace(save=lambda r, **k: saved.append(r))

    try:
        with (
            patch.object(build_api, "run_opencode_mission", provider_not_configured_runner),
            patch.object(build_api, "emit_managed_workspace_snapshot", snapshot_mock),
            patch.object(build_api, "get_control_plane_run_store", lambda: fake_store),
        ):
            res = _client(actor).post(
                "/api/opencode/build/launch",
                json={
                    "project_id": rec.id,
                    "user_prompt": "tidy",
                    "proposal_digest": digest,
                    "base_revision": build_api.OPENCODE_REGISTRY_REVISION,
                    "confirmed": True,
                },
                headers={"Authorization": f"Bearer {_EXEC_TOKEN_CANARY}"},
            )
    finally:
        _stop(patches)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is False
    assert body["control_plane_status"] == "failed"
    assert len(saved) == 1
    assert saved[0].status_reason == "opencode:provider_not_configured"
    snapshot_mock.assert_not_called()


def test_launch_no_completion_error_summary_does_not_leak_secrets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    _setup_launch_env(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    rec = _project_rec()
    patches = _patch_build_gates(rec)
    digest = _preview_digest(rec.id, "tidy")

    def no_completion_runner(**_kwargs: Any) -> OpenCodeRunResult:
        return OpenCodeRunResult(
            status="session_no_completion",
            assistant_summary="",
            error_kind="session_no_completion",
            error_summary="OpenCode session ended without a completion envelope.",
        )

    saved: list[Any] = []
    fake_store = SimpleNamespace(save=lambda r, **k: saved.append(r))

    try:
        with (
            patch.object(build_api, "run_opencode_mission", no_completion_runner),
            patch.object(build_api, "get_control_plane_run_store", lambda: fake_store),
        ):
            res = _client(actor).post(
                "/api/opencode/build/launch",
                json={
                    "project_id": rec.id,
                    "user_prompt": "tidy",
                    "proposal_digest": digest,
                    "base_revision": build_api.OPENCODE_REGISTRY_REVISION,
                    "confirmed": True,
                },
                headers={"Authorization": f"Bearer {_EXEC_TOKEN_CANARY}"},
            )
    finally:
        _stop(patches)

    blob = res.text
    assert _AUTH_CANARY not in blob
    assert _EXEC_TOKEN_CANARY not in blob
    persisted = (saved[0].error_summary or "") + " " + (saved[0].summary or "")
    assert _AUTH_CANARY not in persisted
    assert _EXEC_TOKEN_CANARY not in persisted


# ---------------------------------------------------------------------------
# 5. ControlPlaneRun store consistency — read API uses the same factory
#    the write paths use (so Firestore-backed deployments are coherent).
# ---------------------------------------------------------------------------


@pytest.fixture
def store_consistency_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, actor: HamActor
) -> TestClient:
    """Bind a shared file-backed store via the public test seam so both the
    write path (``get_control_plane_run_store``) and the read API resolve
    the same instance.
    """
    cpr_dir = tmp_path / "cpr"
    cpr_dir.mkdir()
    shared = ControlPlaneRunStore(base_dir=cpr_dir)
    set_control_plane_run_store_for_tests(shared)
    monkeypatch.setattr(cpr_api, "_store", None)

    yield_client = TestClient(app)
    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: actor
    try:
        yield yield_client
    finally:
        fastapi_app.dependency_overrides.clear()
        set_control_plane_run_store_for_tests(None)


def _register_project(client: TestClient, *, name: str, root: Path) -> str:
    res = client.post(
        "/api/projects",
        json={"name": name, "root": str(root), "description": ""},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_read_api_resolves_through_configured_backend(
    store_consistency_client: TestClient, tmp_path: Path
) -> None:
    """A write via ``get_control_plane_run_store()`` (the singleton used by
    the OpenCode / Claude Agent / Cursor write paths) must be visible to
    the read API. This pins the bug-fix: the read API used to instantiate
    its own ``ControlPlaneRunStore()`` and so missed Firestore-backed writes
    on the same deployment.
    """
    from src.persistence.control_plane_run import get_control_plane_run_store

    root = tmp_path / "r"
    root.mkdir()
    pid = _register_project(store_consistency_client, name="cps", root=root)

    now = utc_now_iso()
    rid = "deadbeef-1111-2222-3333-444444444444"
    run = ControlPlaneRun(
        ham_run_id=rid,
        provider="opencode_cli",
        action_kind="launch",
        project_id=pid,
        created_by=None,
        created_at=now,
        updated_at=now,
        committed_at=now,
        started_at=now,
        finished_at=now,
        last_observed_at=now,
        status="failed",
        status_reason="opencode:session_no_completion",
        proposal_digest="a" * 64,
        base_revision=build_api.OPENCODE_REGISTRY_REVISION,
        external_id="ext-hd",
        workflow_id=None,
        summary=None,
        error_summary="OpenCode session ended without a completion envelope.",
        last_provider_status=None,
        audit_ref=None,
        output_target="managed_workspace",
    )
    get_control_plane_run_store().save(run, project_root_for_mirror=None)

    res = store_consistency_client.get("/api/control-plane-runs", params={"project_id": pid})
    assert res.status_code == 200, res.text
    runs = res.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["ham_run_id"] == rid
    assert runs[0]["status"] == "failed"
    assert runs[0]["status_reason"] == "opencode:session_no_completion"

    res2 = store_consistency_client.get(f"/api/control-plane-runs/{rid}")
    assert res2.status_code == 200, res2.text
    assert res2.json()["run"]["status_reason"] == "opencode:session_no_completion"


# ---------------------------------------------------------------------------
# 6. Subprocess exit without envelope still maps to session_no_completion
# ---------------------------------------------------------------------------


def test_subprocess_exit_without_envelope_maps_to_session_no_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate the failure shape the operator hit live: the SSE stream is
    served from a now-exited subprocess. The runner must surface
    ``session_no_completion``, not ``runner_error``, so the launch core
    can persist the durable ``opencode:session_no_completion`` row.
    """
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    monkeypatch.setenv(OPENCODE_DEFAULT_MODEL_ENV, "openrouter/fake")

    handle = _FakeHandle()
    events = [
        {"type": "server.connected"},
        {"type": "message.part.updated", "part": {"text": "starting..."}},
        # No session.idle, no session.error — stream just ends.
    ]
    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner(handle),
        http_client_factory=_http_factory(_basic_handler),
        event_stream_factory=lambda _c, _s: iter(events),
    )
    # Even though we observed `server.connected` and an assistant chunk,
    # without an explicit completion event we mark the run as no-completion.
    assert result.status == "session_no_completion"
    assert result.error_summary is not None


# ---------------------------------------------------------------------------
# 7. SSE vocabulary tolerance regression — unknown event types must not flip
#    a real no-completion case into runner_error, and known-good streams must
#    still succeed.
# ---------------------------------------------------------------------------


def test_unknown_events_before_session_idle_still_succeed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    monkeypatch.setenv(OPENCODE_DEFAULT_MODEL_ENV, "openrouter/fake")
    events = [
        {"type": "server.connected"},
        {"type": "future.event.from.upstream", "shape": "unknown"},
        {"type": "message.part.updated", "part": {"text": "ok"}},
        {"type": "session.idle"},
    ]
    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner(_FakeHandle()),
        http_client_factory=_http_factory(_basic_handler),
        event_stream_factory=lambda _c, _s: iter(events),
    )
    assert result.status == "success"


def test_unknown_events_without_session_idle_yield_session_no_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    monkeypatch.setenv(OPENCODE_DEFAULT_MODEL_ENV, "openrouter/fake")
    events = [
        {"type": "server.connected"},
        {"type": "future.event.from.upstream", "shape": "unknown"},
    ]
    result = run_opencode_mission(
        project_root=tmp_path,
        user_prompt="tidy",
        spawner=_mock_spawner(_FakeHandle()),
        http_client_factory=_http_factory(_basic_handler),
        event_stream_factory=lambda _c, _s: iter(events),
    )
    assert result.status == "session_no_completion"
