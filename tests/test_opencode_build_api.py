"""Gated OpenCode build router — POST /api/opencode/build/(preview|launch).

These tests lock the safety contract for the OpenCode Mission 2 build router:

- Every gate fails closed.
- The mission runner ``run_opencode_mission`` is mocked; no real
  ``opencode serve``, no model network, no subprocess.
- Response bodies never echo canary secret values.

All canary strings are obvious fakes (``opencode-test-canary-not-a-real-key``,
``test-token-canary``).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api import opencode_build as build_api
from src.api.clerk_gate import get_ham_clerk_actor
from src.api.server import app, fastapi_app
from src.ham.clerk_auth import HamActor
from src.ham.managed_workspace.provisioning import ManagedWorkspaceSetupError
from src.ham.opencode_runner.result import OpenCodeRunResult
from src.ham.worker_adapters.opencode_adapter import (
    OpenCodeStatus,
)

_EXEC_TOKEN_CANARY = "test-token-canary"  # noqa: S105
_AUTH_CANARY = "opencode-test-canary-not-a-real-key"


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
    """Strip env vars; default posture is fully disabled."""
    for name in (
        "HAM_OPENCODE_ENABLED",
        "HAM_OPENCODE_EXECUTION_ENABLED",
        "HAM_OPENCODE_EXEC_TOKEN",
        "HAM_OPENCODE_ALLOW_DELETIONS",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
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
    project_id: str = "project.opencode-abc123",
    output_target: str = "managed_workspace",
    workspace_id: str | None = "ws_opencode",
    build_lane_enabled: bool = True,
    name: str = "p_opencode",
) -> Any:
    return SimpleNamespace(
        id=project_id,
        name=name,
        output_target=output_target,
        workspace_id=workspace_id,
        build_lane_enabled=build_lane_enabled,
        root="/tmp/p_opencode",
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


def _patch_gates(
    *,
    rec: Any | None = None,
    approver_ok: bool = True,
    readiness: Any | None = None,
) -> list[Any]:
    patches: list[Any] = []
    if rec is None:
        rec = _project_rec()

    patches.append(patch.object(build_api, "_require_build_lane_project", lambda pid: rec))
    if approver_ok:
        patches.append(
            patch.object(
                build_api,
                "_require_build_approver",
                lambda actor, rec, store: None,
            )
        )
    patches.append(
        patch.object(
            build_api,
            "check_opencode_readiness",
            lambda actor: readiness or _readiness(),
        )
    )
    for p in patches:
        p.start()
    return patches


def _stop(patches: list[Any]) -> None:
    for p in reversed(patches):
        p.stop()


def _preview_digest(project_id: str, user_prompt: str, model: str | None = None) -> str:
    return build_api.compute_opencode_proposal_digest(
        project_id=project_id, user_prompt=user_prompt, model=model
    )


def _bearer() -> dict[str, str]:
    return {"Authorization": f"Bearer {_EXEC_TOKEN_CANARY}"}


# ---------------------------------------------------------------------------
# Preview tests
# ---------------------------------------------------------------------------


def test_preview_returns_503_when_execution_disabled(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    res = _client(actor).post(
        "/api/opencode/build/preview",
        json={"project_id": "p", "user_prompt": "tidy README"},
    )
    assert res.status_code == 503
    assert res.json()["detail"]["error"]["code"] == "OPENCODE_EXECUTION_DISABLED"


def test_preview_returns_503_when_provider_disabled(
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    res = _client(actor).post(
        "/api/opencode/build/preview",
        json={"project_id": "p", "user_prompt": "tidy README"},
    )
    assert res.status_code == 503
    assert res.json()["detail"]["error"]["code"] == "OPENCODE_DISABLED"


def test_preview_returns_503_when_readiness_not_configured(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    patches = _patch_gates(readiness=_readiness(status=OpenCodeStatus.CLI_MISSING))
    try:
        res = _client(actor).post(
            "/api/opencode/build/preview",
            json={"project_id": "p", "user_prompt": "tidy README"},
        )
    finally:
        _stop(patches)
    assert res.status_code == 503
    assert res.json()["detail"]["error"]["code"] == "OPENCODE_PROVIDER_NOT_CONFIGURED"


def test_preview_returns_proposal_digest_when_gates_pass(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    patches = _patch_gates()
    try:
        res = _client(actor).post(
            "/api/opencode/build/preview",
            json={"project_id": "p", "user_prompt": "tidy README"},
        )
    finally:
        _stop(patches)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "opencode_build_preview"
    assert isinstance(body["proposal_digest"], str) and len(body["proposal_digest"]) == 64
    assert body["base_revision"] == build_api.OPENCODE_REGISTRY_REVISION
    assert body["output_target"] == "managed_workspace"
    assert body["will_open_pull_request"] is False


def test_preview_does_not_spawn_opencode_serve(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")

    def explode(*a: Any, **k: Any) -> Any:
        raise AssertionError("subprocess.Popen called from preview")

    monkeypatch.setattr("subprocess.Popen", explode)
    monkeypatch.setattr("subprocess.run", explode)
    patches = _patch_gates()
    try:
        res = _client(actor).post(
            "/api/opencode/build/preview",
            json={"project_id": "p", "user_prompt": "tidy README"},
        )
    finally:
        _stop(patches)
    assert res.status_code == 200, res.text


def test_preview_does_not_make_model_api_call(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")

    def explode(*a: Any, **k: Any) -> Any:
        raise AssertionError("run_opencode_mission called from preview")

    monkeypatch.setattr(build_api, "run_opencode_mission", explode)
    patches = _patch_gates()
    try:
        res = _client(actor).post(
            "/api/opencode/build/preview",
            json={"project_id": "p", "user_prompt": "tidy README"},
        )
    finally:
        _stop(patches)
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# Launch — gating
# ---------------------------------------------------------------------------


def test_launch_returns_503_when_execution_disabled(
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    # Mission 1 back-compat: returns 503 with reason "opencode:not_implemented".
    res = _client(actor).post(
        "/api/opencode/build/launch",
        json={
            "project_id": "p",
            "user_prompt": "tidy",
            "proposal_digest": "0" * 64,
            "base_revision": build_api.OPENCODE_REGISTRY_REVISION,
            "confirmed": True,
        },
    )
    assert res.status_code == 503
    assert res.json()["detail"]["reason"] == "opencode:not_implemented"


def test_launch_rejects_missing_exec_token(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy README")
    try:
        # No Authorization header.
        res = _client(actor).post(
            "/api/opencode/build/launch",
            json={
                "project_id": rec.id,
                "user_prompt": "tidy README",
                "proposal_digest": digest,
                "base_revision": build_api.OPENCODE_REGISTRY_REVISION,
                "confirmed": True,
            },
        )
    finally:
        _stop(patches)
    assert res.status_code == 503
    assert res.json()["detail"]["error"]["code"] == "OPENCODE_LANE_UNCONFIGURED"


def test_launch_rejects_digest_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    try:
        res = _client(actor).post(
            "/api/opencode/build/launch",
            json={
                "project_id": rec.id,
                "user_prompt": "tidy README",
                "proposal_digest": "0" * 64,
                "base_revision": build_api.OPENCODE_REGISTRY_REVISION,
                "confirmed": True,
            },
        )
    finally:
        _stop(patches)
    assert res.status_code == 409
    assert res.json()["detail"]["error"]["code"] == "OPENCODE_LAUNCH_PREVIEW_STALE"


def test_launch_rejects_when_readiness_not_configured(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    rec = _project_rec()
    patches = _patch_gates(rec=rec, readiness=_readiness(status=OpenCodeStatus.CLI_MISSING))
    digest = _preview_digest(rec.id, "tidy")
    try:
        res = _client(actor).post(
            "/api/opencode/build/launch",
            json={
                "project_id": rec.id,
                "user_prompt": "tidy",
                "proposal_digest": digest,
                "base_revision": build_api.OPENCODE_REGISTRY_REVISION,
                "confirmed": True,
            },
        )
    finally:
        _stop(patches)
    assert res.status_code == 503
    assert res.json()["detail"]["error"]["code"] == "OPENCODE_PROVIDER_NOT_CONFIGURED"


def test_launch_requires_confirmed(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    res = _client(actor).post(
        "/api/opencode/build/launch",
        json={
            "project_id": "p",
            "user_prompt": "tidy",
            "proposal_digest": "0" * 64,
            "base_revision": build_api.OPENCODE_REGISTRY_REVISION,
            "confirmed": False,
        },
    )
    assert res.status_code == 422
    assert res.json()["detail"]["error"]["code"] == "OPENCODE_LAUNCH_REQUIRES_CONFIRMATION"


# ---------------------------------------------------------------------------
# Launch — workspace setup
# ---------------------------------------------------------------------------


def _raises_setup_error(**_kwargs: Any) -> None:
    raise ManagedWorkspaceSetupError(
        reason="read_only_filesystem",
        detail="managed_root_read_only",
    )


def test_launch_persists_workspace_setup_failed(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy")

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
                "/api/opencode/build/launch",
                json={
                    "project_id": rec.id,
                    "user_prompt": "tidy",
                    "proposal_digest": digest,
                    "base_revision": build_api.OPENCODE_REGISTRY_REVISION,
                    "confirmed": True,
                },
                headers=_bearer(),
            )
    finally:
        _stop(patches)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is False
    assert body["control_plane_status"] == "failed"
    assert body["output_ref"] is None
    assert len(saved) == 1
    cp_run = saved[0]
    assert cp_run.provider == "opencode_cli"
    assert cp_run.status == "failed"
    assert cp_run.status_reason == "opencode:workspace_setup_failed"


def test_launch_does_not_call_runner_when_workspace_setup_fails(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy")

    runner_mock = MagicMock()
    snapshot_mock = MagicMock()
    fake_store = SimpleNamespace(save=lambda *a, **k: None)

    try:
        with (
            patch.object(build_api, "ensure_managed_working_tree", _raises_setup_error),
            patch.object(build_api, "run_opencode_mission", runner_mock),
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
                headers=_bearer(),
            )
    finally:
        _stop(patches)
    assert res.status_code == 200
    runner_mock.assert_not_called()
    snapshot_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Launch — runner orchestration (mocked)
# ---------------------------------------------------------------------------


def test_launch_emits_snapshot_on_non_delete_change(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy")

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

    def fake_runner(**kwargs: Any) -> OpenCodeRunResult:
        return OpenCodeRunResult(
            status="success",
            changed_paths=("README.md",),
            assistant_summary="ok.",
            duration_seconds=0.05,
        )

    saved: list[Any] = []
    fake_store = SimpleNamespace(
        save=lambda r, **k: saved.append(r),
    )

    try:
        with (
            patch.object(build_api, "run_opencode_mission", fake_runner),
            patch.object(build_api, "compute_deleted_paths_against_parent", lambda common: ()),
            patch.object(build_api, "emit_managed_workspace_snapshot", lambda c: fake_snap),
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
                headers=_bearer(),
            )
    finally:
        _stop(patches)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["control_plane_status"] == "succeeded"
    assert body["output_ref"]["snapshot_id"] == "snap_abc"
    assert saved[0].status_reason == "opencode:snapshot_emitted"


def test_launch_persists_output_requires_review_on_deletion(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy")

    def fake_runner(**kwargs: Any) -> OpenCodeRunResult:
        return OpenCodeRunResult(status="success", assistant_summary="ok.", duration_seconds=0.1)

    snapshot_mock = MagicMock()
    saved: list[Any] = []
    fake_store = SimpleNamespace(save=lambda r, **k: saved.append(r))

    try:
        with (
            patch.object(build_api, "run_opencode_mission", fake_runner),
            patch.object(
                build_api,
                "compute_deleted_paths_against_parent",
                lambda common: ("README.md",),
            ),
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
                headers=_bearer(),
            )
    finally:
        _stop(patches)
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert "OpenCode proposed deleting files" in (body["summary"] or "")
    assert "output_requires_review" in (body["error_summary"] or "")
    assert "README.md" in (body["error_summary"] or "")
    snapshot_mock.assert_not_called()
    assert len(saved) == 1
    assert saved[0].status_reason == "opencode:output_requires_review"


def test_launch_allow_deletions_env_lets_emit_proceed(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    monkeypatch.setenv("HAM_OPENCODE_ALLOW_DELETIONS", "1")
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy")

    fake_snap = SimpleNamespace(
        build_outcome="succeeded",
        target_ref={"snapshot_id": "snap_ok"},
        error_summary=None,
    )
    snapshot_mock = MagicMock(return_value=fake_snap)

    def fake_runner(**kwargs: Any) -> OpenCodeRunResult:
        return OpenCodeRunResult(status="success", assistant_summary="ok.")

    fake_store = SimpleNamespace(save=lambda *a, **k: None)

    try:
        with (
            patch.object(build_api, "run_opencode_mission", fake_runner),
            patch.object(
                build_api,
                "compute_deleted_paths_against_parent",
                lambda common: ("README.md",),
            ),
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
                headers=_bearer(),
            )
    finally:
        _stop(patches)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    snapshot_mock.assert_called_once()


def test_launch_persists_nothing_to_change_when_runner_empty(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy")

    def fake_runner(**kwargs: Any) -> OpenCodeRunResult:
        return OpenCodeRunResult(status="success", assistant_summary="nothing.")

    fake_snap = SimpleNamespace(
        build_outcome="nothing_to_change", target_ref={}, error_summary=None
    )
    saved: list[Any] = []
    fake_store = SimpleNamespace(save=lambda r, **k: saved.append(r))

    try:
        with (
            patch.object(build_api, "run_opencode_mission", fake_runner),
            patch.object(build_api, "compute_deleted_paths_against_parent", lambda common: ()),
            patch.object(build_api, "emit_managed_workspace_snapshot", lambda c: fake_snap),
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
                headers=_bearer(),
            )
    finally:
        _stop(patches)
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert saved[0].status_reason == "opencode:nothing_to_change"


def test_launch_writes_control_plane_run_with_expected_fields(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy")

    fake_snap = SimpleNamespace(
        build_outcome="succeeded",
        target_ref={"snapshot_id": "snap_z"},
        error_summary=None,
    )

    def fake_runner(**kwargs: Any) -> OpenCodeRunResult:
        return OpenCodeRunResult(status="success", assistant_summary="ok.")

    saved: list[Any] = []
    fake_store = SimpleNamespace(save=lambda r, **k: saved.append(r))

    try:
        with (
            patch.object(build_api, "run_opencode_mission", fake_runner),
            patch.object(build_api, "compute_deleted_paths_against_parent", lambda common: ()),
            patch.object(build_api, "emit_managed_workspace_snapshot", lambda c: fake_snap),
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
                headers=_bearer(),
            )
    finally:
        _stop(patches)
    assert res.status_code == 200
    assert len(saved) == 1
    cp = saved[0]
    assert cp.provider == "opencode_cli"
    assert cp.action_kind == "launch"
    assert cp.output_target == "managed_workspace"
    assert cp.base_revision == build_api.OPENCODE_REGISTRY_REVISION
    assert cp.audit_ref is None
    assert cp.pr_url is None


# ---------------------------------------------------------------------------
# Safety / no leakage
# ---------------------------------------------------------------------------


def test_no_secret_in_response_body_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    res = _client(actor).post(
        "/api/opencode/build/launch",
        json={
            "project_id": "p",
            "user_prompt": "tidy",
            "proposal_digest": "0" * 64,
            "base_revision": build_api.OPENCODE_REGISTRY_REVISION,
            "confirmed": True,
        },
        headers=_bearer(),
    )
    blob = res.text
    assert _AUTH_CANARY not in blob
    assert _EXEC_TOKEN_CANARY not in blob


def test_no_secret_in_control_plane_error_summary(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy")

    def fake_runner(**kwargs: Any) -> OpenCodeRunResult:
        return OpenCodeRunResult(
            status="success",
            assistant_summary="ok.",
        )

    saved: list[Any] = []
    fake_store = SimpleNamespace(save=lambda r, **k: saved.append(r))

    try:
        with (
            patch.object(build_api, "run_opencode_mission", fake_runner),
            patch.object(
                build_api,
                "compute_deleted_paths_against_parent",
                lambda common: ("X",),
            ),
            patch.object(build_api, "emit_managed_workspace_snapshot", MagicMock()),
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
                headers=_bearer(),
            )
    finally:
        _stop(patches)
    assert res.status_code == 200
    blob = res.text
    assert _AUTH_CANARY not in blob
    assert _EXEC_TOKEN_CANARY not in blob
    if saved:
        persisted = f"{saved[0].summary or ''} {saved[0].error_summary or ''}"
        assert _AUTH_CANARY not in persisted
        assert _EXEC_TOKEN_CANARY not in persisted


def test_launch_does_not_open_pr_or_set_pr_fields(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy")

    fake_snap = SimpleNamespace(
        build_outcome="succeeded", target_ref={"snapshot_id": "x"}, error_summary=None
    )

    def fake_runner(**kwargs: Any) -> OpenCodeRunResult:
        return OpenCodeRunResult(status="success", assistant_summary="ok.")

    saved: list[Any] = []
    fake_store = SimpleNamespace(save=lambda r, **k: saved.append(r))

    try:
        with (
            patch.object(build_api, "run_opencode_mission", fake_runner),
            patch.object(build_api, "compute_deleted_paths_against_parent", lambda common: ()),
            patch.object(build_api, "emit_managed_workspace_snapshot", lambda c: fake_snap),
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
                headers=_bearer(),
            )
    finally:
        _stop(patches)
    assert res.status_code == 200
    body = res.json()
    assert body["will_open_pull_request"] is False
    cp = saved[0]
    assert cp.pr_url is None
    assert cp.pr_branch is None


# ---------------------------------------------------------------------------
# Runner is never spawned via subprocess during launch
# ---------------------------------------------------------------------------


def test_launch_does_not_invoke_subprocess_popen(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", _EXEC_TOKEN_CANARY)
    rec = _project_rec()
    patches = _patch_gates(rec=rec)
    digest = _preview_digest(rec.id, "tidy")

    def explode(*a: Any, **k: Any) -> Any:
        raise AssertionError("subprocess.Popen called by launch path")

    monkeypatch.setattr("subprocess.Popen", explode)

    def fake_runner(**kwargs: Any) -> OpenCodeRunResult:
        return OpenCodeRunResult(status="success", assistant_summary="ok.")

    fake_snap = SimpleNamespace(
        build_outcome="succeeded", target_ref={"snapshot_id": "x"}, error_summary=None
    )
    fake_store = SimpleNamespace(save=lambda *a, **k: None)

    try:
        with (
            patch.object(build_api, "run_opencode_mission", fake_runner),
            patch.object(build_api, "compute_deleted_paths_against_parent", lambda common: ()),
            patch.object(build_api, "emit_managed_workspace_snapshot", lambda c: fake_snap),
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
                headers=_bearer(),
            )
    finally:
        _stop(patches)
    assert res.status_code == 200
