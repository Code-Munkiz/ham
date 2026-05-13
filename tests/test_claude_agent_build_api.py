"""Gated Claude Agent build router — POST /api/claude-agent/build/(preview|launch).

These tests lock the safety contract for the Claude Agent build router:

- Every gate (Clerk session, enable env, project lookup, managed-workspace
  target, build approver, SDK install presence, Anthropic auth presence,
  digest verify, exec token) fails closed without invoking the runner.
- The mission runner ``run_claude_agent_mission`` is mocked; no real
  ``claude-agent-sdk`` call, no Anthropic network, no subprocess.
- Response bodies never echo fake canary secret values.

All Anthropic / token canary strings are obviously fake (``test-token-canary``,
``claude-agent-test-canary-not-a-real-key``).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api import claude_agent_build as build_api
from src.api.clerk_gate import get_ham_clerk_actor
from src.api.server import app, fastapi_app
from src.ham.claude_agent_runner.types import ClaudeAgentRunResult
from src.ham.clerk_auth import HamActor
from src.ham.managed_workspace.provisioning import ManagedWorkspaceSetupError


_EXEC_TOKEN_CANARY = "test-token-canary"  # noqa: S105


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cleanup_overrides() -> Any:
    yield
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def actor() -> HamActor:
    return HamActor(
        user_id="user_owner",
        org_id="org_managed",
        session_id="sess_o",
        email="owner@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Strip env vars; default posture is disabled / no token."""
    for name in (
        "CLAUDE_AGENT_ENABLED",
        "HAM_CLAUDE_AGENT_EXEC_TOKEN",
        "ANTHROPIC_API_KEY",
        "HAM_CLERK_REQUIRE_AUTH",
        "HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HAM_MANAGED_WORKSPACE_ROOT", str(tmp_path / "ham-workspaces"))


def _client(actor: HamActor | None = None) -> TestClient:
    if actor is not None:
        fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: actor
    return TestClient(app)


def _project_rec(
    *,
    project_id: str = "project.claude-abc123",
    output_target: str = "managed_workspace",
    workspace_id: str | None = "ws_claude",
    build_lane_enabled: bool = True,
    name: str = "p_claude",
) -> Any:
    return SimpleNamespace(
        id=project_id,
        name=name,
        output_target=output_target,
        workspace_id=workspace_id,
        build_lane_enabled=build_lane_enabled,
        root="/tmp/p_claude",
    )


def _readiness(sdk_available: bool = True, authenticated: bool = True) -> Any:
    return SimpleNamespace(
        sdk_available=sdk_available,
        authenticated=authenticated,
        sdk_version="0.1.0",
        status="ready" if (sdk_available and authenticated) else "unavailable",
    )


def _patch_gates(
    *,
    rec: Any | None = None,
    approver_ok: bool = True,
    sdk_available: bool = True,
    auth_ok: bool = True,
) -> list[Any]:
    """Return a list of started patches caller MUST stop()."""
    patches: list[Any] = []

    if rec is None:
        rec = _project_rec()

    p1 = patch.object(build_api, "_require_build_lane_project", lambda pid: rec)
    patches.append(p1)

    if approver_ok:
        p2 = patch.object(build_api, "_require_build_approver", lambda actor, rec, store: None)
        patches.append(p2)

    p3 = patch.object(
        build_api,
        "check_claude_agent_readiness",
        lambda actor: _readiness(sdk_available=sdk_available, authenticated=True),
    )
    patches.append(p3)

    p4 = patch.object(
        build_api,
        "claude_agent_mission_auth_configured",
        lambda actor: auth_ok,
    )
    patches.append(p4)

    for p in patches:
        p.start()
    return patches


def _stop(patches: list[Any]) -> None:
    for p in reversed(patches):
        p.stop()


# ---------------------------------------------------------------------------
# Preview tests
# ---------------------------------------------------------------------------


def test_preview_requires_clerk_session(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "1")
    fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)
    res = TestClient(app).post(
        "/api/claude-agent/build/preview",
        json={"project_id": "p", "user_prompt": "tidy README"},
    )
    assert res.status_code == 401


def test_preview_returns_503_when_claude_agent_disabled(
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    # CLAUDE_AGENT_ENABLED unset by fixture.
    res = _client(actor).post(
        "/api/claude-agent/build/preview",
        json={"project_id": "p1", "user_prompt": "tidy README"},
    )
    assert res.status_code == 503
    assert res.json()["detail"]["error"]["code"] == "CLAUDE_AGENT_DISABLED"


def test_preview_returns_422_when_project_missing_managed_workspace_output_target(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    rec = _project_rec(output_target="github_pr")
    patches = _patch_gates(rec=rec)
    try:
        res = _client(actor).post(
            "/api/claude-agent/build/preview",
            json={"project_id": rec.id, "user_prompt": "tidy README"},
        )
    finally:
        _stop(patches)
    assert res.status_code == 422
    assert res.json()["detail"]["error"]["code"] == "CLAUDE_AGENT_REQUIRES_MANAGED_WORKSPACE"


def test_preview_returns_503_when_sdk_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    patches = _patch_gates(sdk_available=False)
    try:
        res = _client(actor).post(
            "/api/claude-agent/build/preview",
            json={"project_id": "p", "user_prompt": "tidy README"},
        )
    finally:
        _stop(patches)
    assert res.status_code == 503
    assert res.json()["detail"]["error"]["code"] == "CLAUDE_AGENT_SDK_UNAVAILABLE"


def test_preview_returns_503_when_auth_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    patches = _patch_gates(auth_ok=False)
    try:
        res = _client(actor).post(
            "/api/claude-agent/build/preview",
            json={"project_id": "p", "user_prompt": "tidy README"},
        )
    finally:
        _stop(patches)
    assert res.status_code == 503
    assert res.json()["detail"]["error"]["code"] == "CLAUDE_AGENT_AUTH_UNAVAILABLE"


def test_preview_returns_200_with_digest_and_base_revision_when_gates_pass(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    patches = _patch_gates()
    try:
        res = _client(actor).post(
            "/api/claude-agent/build/preview",
            json={"project_id": "p", "user_prompt": "tidy README"},
        )
    finally:
        _stop(patches)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "claude_agent_build_preview"
    assert isinstance(body["proposal_digest"], str) and len(body["proposal_digest"]) == 64
    assert body["base_revision"] == build_api.CLAUDE_AGENT_REGISTRY_REVISION
    assert body["output_target"] == "managed_workspace"
    assert body["will_open_pull_request"] is False


# ---------------------------------------------------------------------------
# Launch tests
# ---------------------------------------------------------------------------


def _preview_digest(project_id: str, user_prompt: str) -> str:
    return build_api.compute_claude_agent_proposal_digest(
        project_id=project_id, user_prompt=user_prompt
    )


def test_launch_requires_confirmed_true(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    res = _client(actor).post(
        "/api/claude-agent/build/launch",
        json={
            "project_id": "p",
            "user_prompt": "tidy README",
            "proposal_digest": "0" * 64,
            "base_revision": build_api.CLAUDE_AGENT_REGISTRY_REVISION,
            "confirmed": False,
        },
    )
    assert res.status_code == 422
    assert res.json()["detail"]["error"]["code"] == "CLAUDE_AGENT_LAUNCH_REQUIRES_CONFIRMATION"


def test_launch_returns_503_when_disabled(
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    res = _client(actor).post(
        "/api/claude-agent/build/launch",
        json={
            "project_id": "p",
            "user_prompt": "tidy README",
            "proposal_digest": "0" * 64,
            "base_revision": build_api.CLAUDE_AGENT_REGISTRY_REVISION,
            "confirmed": True,
        },
    )
    assert res.status_code == 503
    assert res.json()["detail"]["error"]["code"] == "CLAUDE_AGENT_DISABLED"


def test_launch_returns_422_when_output_target_is_github_pr(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    rec = _project_rec(output_target="github_pr")
    patches = _patch_gates(rec=rec)
    try:
        res = _client(actor).post(
            "/api/claude-agent/build/launch",
            json={
                "project_id": rec.id,
                "user_prompt": "tidy README",
                "proposal_digest": "0" * 64,
                "base_revision": build_api.CLAUDE_AGENT_REGISTRY_REVISION,
                "confirmed": True,
            },
        )
    finally:
        _stop(patches)
    assert res.status_code == 422
    assert res.json()["detail"]["error"]["code"] == "CLAUDE_AGENT_REQUIRES_MANAGED_WORKSPACE"


def test_launch_returns_409_when_digest_or_base_revision_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    try:
        res = _client(actor).post(
            "/api/claude-agent/build/launch",
            json={
                "project_id": rec.id,
                "user_prompt": "tidy README",
                "proposal_digest": "0" * 64,
                "base_revision": build_api.CLAUDE_AGENT_REGISTRY_REVISION,
                "confirmed": True,
            },
        )
    finally:
        _stop(patches)
    assert res.status_code == 409
    assert res.json()["detail"]["error"]["code"] == "CLAUDE_AGENT_LAUNCH_PREVIEW_STALE"


def test_launch_returns_503_when_exec_token_missing(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    # HAM_CLAUDE_AGENT_EXEC_TOKEN is unset by isolated_env.
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy README")
    try:
        res = _client(actor).post(
            "/api/claude-agent/build/launch",
            json={
                "project_id": rec.id,
                "user_prompt": "tidy README",
                "proposal_digest": digest,
                "base_revision": build_api.CLAUDE_AGENT_REGISTRY_REVISION,
                "confirmed": True,
            },
        )
    finally:
        _stop(patches)
    assert res.status_code == 503
    assert res.json()["detail"]["error"]["code"] == "CLAUDE_AGENT_LANE_UNCONFIGURED"


def test_launch_returns_success_shape_when_runner_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    monkeypatch.setenv("HAM_CLAUDE_AGENT_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy README")

    async def _fake_run(**_kwargs: Any) -> ClaudeAgentRunResult:
        return ClaudeAgentRunResult(
            status="success",
            changed_paths=("/tmp/a.txt",),
            assistant_summary="finished tidying.",
            tool_calls_count=1,
            denied_tool_calls_count=0,
            duration_seconds=0.1,
            sdk_version="0.1.0",
        )

    fake_snap = SimpleNamespace(
        build_outcome="succeeded",
        target_ref={
            "snapshot_id": "snap_abc",
            "preview_url": "https://snapshots.example.test/p/abc",
            "changed_paths_count": 1,
            "neutral_outcome": "snapshot_published",
        },
        error_summary=None,
    )
    saved: list[Any] = []

    def _fake_save(run: Any, *, project_root_for_mirror: str | None = None) -> None:
        saved.append(run)

    fake_store = SimpleNamespace(save=_fake_save)

    try:
        with (
            patch.object(build_api, "run_claude_agent_mission", _fake_run),
            patch.object(build_api, "emit_managed_workspace_snapshot", lambda common: fake_snap),
            patch.object(build_api, "get_control_plane_run_store", lambda: fake_store),
        ):
            res = _client(actor).post(
                "/api/claude-agent/build/launch",
                json={
                    "project_id": rec.id,
                    "user_prompt": "tidy README",
                    "proposal_digest": digest,
                    "base_revision": build_api.CLAUDE_AGENT_REGISTRY_REVISION,
                    "confirmed": True,
                },
            )
    finally:
        _stop(patches)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "claude_agent_build_launch"
    assert body["ok"] is True
    assert body["control_plane_status"] == "succeeded"
    assert isinstance(body["ham_run_id"], str) and body["ham_run_id"]
    assert body["output_target"] == "managed_workspace"
    output_ref = body["output_ref"]
    assert output_ref["snapshot_id"] == "snap_abc"
    assert output_ref["preview_url"].startswith("https://")
    assert output_ref["changed_paths_count"] == 1
    assert output_ref["neutral_outcome"] == "snapshot_published"


def test_launch_persists_control_plane_run_on_success(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    monkeypatch.setenv("HAM_CLAUDE_AGENT_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy README")

    async def _fake_run(**_kwargs: Any) -> ClaudeAgentRunResult:
        return ClaudeAgentRunResult(
            status="success",
            assistant_summary="ok.",
            duration_seconds=0.1,
        )

    fake_snap = SimpleNamespace(
        build_outcome="succeeded",
        target_ref={"snapshot_id": "snap_ok"},
        error_summary=None,
    )
    saved: list[Any] = []

    def _fake_save(run: Any, *, project_root_for_mirror: str | None = None) -> None:
        saved.append(run)

    fake_store = SimpleNamespace(save=_fake_save)

    try:
        with (
            patch.object(build_api, "run_claude_agent_mission", _fake_run),
            patch.object(build_api, "emit_managed_workspace_snapshot", lambda common: fake_snap),
            patch.object(build_api, "get_control_plane_run_store", lambda: fake_store),
        ):
            res = _client(actor).post(
                "/api/claude-agent/build/launch",
                json={
                    "project_id": rec.id,
                    "user_prompt": "tidy README",
                    "proposal_digest": digest,
                    "base_revision": build_api.CLAUDE_AGENT_REGISTRY_REVISION,
                    "confirmed": True,
                },
            )
    finally:
        _stop(patches)
    assert res.status_code == 200, res.text
    assert len(saved) == 1
    cp_run = saved[0]
    assert cp_run.provider == "claude_agent"
    assert cp_run.status == "succeeded"


def test_launch_persists_control_plane_run_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    monkeypatch.setenv("HAM_CLAUDE_AGENT_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy README")

    async def _fake_run(**_kwargs: Any) -> ClaudeAgentRunResult:
        return ClaudeAgentRunResult(
            status="sdk_error",
            error_kind="RuntimeError",
            error_summary="boom: nothing leaked here.",
            duration_seconds=0.05,
        )

    saved: list[Any] = []

    def _fake_save(run: Any, *, project_root_for_mirror: str | None = None) -> None:
        saved.append(run)

    fake_store = SimpleNamespace(save=_fake_save)

    try:
        with (
            patch.object(build_api, "run_claude_agent_mission", _fake_run),
            patch.object(build_api, "get_control_plane_run_store", lambda: fake_store),
        ):
            res = _client(actor).post(
                "/api/claude-agent/build/launch",
                json={
                    "project_id": rec.id,
                    "user_prompt": "tidy README",
                    "proposal_digest": digest,
                    "base_revision": build_api.CLAUDE_AGENT_REGISTRY_REVISION,
                    "confirmed": True,
                },
            )
    finally:
        _stop(patches)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is False
    assert body["control_plane_status"] == "failed"
    assert isinstance(body["error_summary"], str) and body["error_summary"]
    assert len(saved) == 1
    cp_run = saved[0]
    assert cp_run.provider == "claude_agent"
    assert cp_run.status == "failed"


def test_launch_does_not_leak_secret_values(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    anthropic_canary = "claude-agent-test-canary-not-a-real-key"
    monkeypatch.setenv("ANTHROPIC_API_KEY", anthropic_canary)
    monkeypatch.setenv("HAM_CLAUDE_AGENT_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    # CLAUDE_AGENT_ENABLED stays unset → first gate fails.
    res = _client(actor).post(
        "/api/claude-agent/build/launch",
        json={
            "project_id": "p",
            "user_prompt": "tidy README",
            "proposal_digest": "0" * 64,
            "base_revision": build_api.CLAUDE_AGENT_REGISTRY_REVISION,
            "confirmed": True,
        },
    )
    blob = res.text
    assert anthropic_canary not in blob
    assert _EXEC_TOKEN_CANARY not in blob


# ---------------------------------------------------------------------------
# Workspace-provisioning failure tests (Mission 2.x)
# ---------------------------------------------------------------------------


def _raises_setup_error(**_kwargs: Any) -> None:
    raise ManagedWorkspaceSetupError(
        reason="read_only_filesystem",
        detail="managed_root_read_only",
    )


def test_launch_returns_workspace_setup_failed_when_provisioning_raises(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    monkeypatch.setenv("HAM_CLAUDE_AGENT_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy README")

    saved: list[Any] = []

    def _fake_save(run: Any, *, project_root_for_mirror: str | None = None) -> None:
        saved.append(run)

    fake_store = SimpleNamespace(save=_fake_save)

    try:
        with (
            patch.object(build_api, "ensure_managed_working_tree", _raises_setup_error),
            patch.object(build_api, "get_control_plane_run_store", lambda: fake_store),
        ):
            res = _client(actor).post(
                "/api/claude-agent/build/launch",
                json={
                    "project_id": rec.id,
                    "user_prompt": "tidy README",
                    "proposal_digest": digest,
                    "base_revision": build_api.CLAUDE_AGENT_REGISTRY_REVISION,
                    "confirmed": True,
                },
            )
    finally:
        _stop(patches)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is False
    assert body["control_plane_status"] == "failed"
    error_summary = body["error_summary"]
    assert isinstance(error_summary, str) and error_summary
    assert "/" not in error_summary
    assert "/srv/" not in error_summary
    assert "HAM_" not in error_summary
    assert body["output_ref"] is None
    assert len(saved) == 1
    cp_run = saved[0]
    assert cp_run.provider == "claude_agent"
    assert cp_run.status == "failed"
    assert cp_run.status_reason == "claude_agent:workspace_setup_failed"


def test_launch_does_not_call_runner_when_provisioning_fails(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    monkeypatch.setenv("HAM_CLAUDE_AGENT_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy README")

    mock_runner = MagicMock()
    fake_store = SimpleNamespace(save=lambda *a, **k: None)
    snapshot_mock = MagicMock()

    try:
        with (
            patch.object(build_api, "ensure_managed_working_tree", _raises_setup_error),
            patch.object(build_api, "run_claude_agent_mission", mock_runner),
            patch.object(build_api, "emit_managed_workspace_snapshot", snapshot_mock),
            patch.object(build_api, "get_control_plane_run_store", lambda: fake_store),
        ):
            res = _client(actor).post(
                "/api/claude-agent/build/launch",
                json={
                    "project_id": rec.id,
                    "user_prompt": "tidy README",
                    "proposal_digest": digest,
                    "base_revision": build_api.CLAUDE_AGENT_REGISTRY_REVISION,
                    "confirmed": True,
                },
            )
    finally:
        _stop(patches)
    assert res.status_code == 200, res.text
    mock_runner.assert_not_called()
    snapshot_mock.assert_not_called()


def test_launch_calls_runner_only_after_working_tree_exists(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    monkeypatch.setenv("HAM_CLAUDE_AGENT_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    monkeypatch.setenv("HAM_MANAGED_WORKSPACE_ROOT", str(tmp_path / "ham-workspaces"))
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy README")

    cwd_was_dir: list[bool] = []

    async def _fake_run(**kwargs: Any) -> ClaudeAgentRunResult:
        project_root = kwargs["project_root"]
        cwd_was_dir.append(Path(project_root).is_dir())
        return ClaudeAgentRunResult(
            status="success",
            assistant_summary="ok.",
            duration_seconds=0.1,
        )

    fake_snap = SimpleNamespace(
        build_outcome="succeeded",
        target_ref={"snapshot_id": "snap_ok"},
        error_summary=None,
    )
    fake_store = SimpleNamespace(save=lambda *a, **k: None)

    try:
        with (
            patch.object(build_api, "run_claude_agent_mission", _fake_run),
            patch.object(build_api, "emit_managed_workspace_snapshot", lambda common: fake_snap),
            patch.object(build_api, "get_control_plane_run_store", lambda: fake_store),
        ):
            res = _client(actor).post(
                "/api/claude-agent/build/launch",
                json={
                    "project_id": rec.id,
                    "user_prompt": "tidy README",
                    "proposal_digest": digest,
                    "base_revision": build_api.CLAUDE_AGENT_REGISTRY_REVISION,
                    "confirmed": True,
                },
            )
    finally:
        _stop(patches)
    assert res.status_code == 200, res.text
    assert cwd_was_dir == [True]


def test_launch_workspace_setup_failed_does_not_emit_snapshot_or_pr(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    monkeypatch.setenv("HAM_CLAUDE_AGENT_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy README")

    snapshot_mock = MagicMock()
    fake_store = SimpleNamespace(save=lambda *a, **k: None)

    try:
        with (
            patch.object(build_api, "ensure_managed_working_tree", _raises_setup_error),
            patch.object(build_api, "emit_managed_workspace_snapshot", snapshot_mock),
            patch.object(build_api, "get_control_plane_run_store", lambda: fake_store),
        ):
            res = _client(actor).post(
                "/api/claude-agent/build/launch",
                json={
                    "project_id": rec.id,
                    "user_prompt": "tidy README",
                    "proposal_digest": digest,
                    "base_revision": build_api.CLAUDE_AGENT_REGISTRY_REVISION,
                    "confirmed": True,
                },
            )
    finally:
        _stop(patches)
    assert res.status_code == 200, res.text
    snapshot_mock.assert_not_called()
    body = res.json()
    assert "snapshot_id" not in (body.get("output_ref") or {})
    assert "preview_url" not in (body.get("output_ref") or {})
    assert body["will_open_pull_request"] is False
