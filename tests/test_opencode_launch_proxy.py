"""Tests for the chat-side OpenCode launch proxy.

Routes under test:

- ``POST /api/opencode/build/launch_proxy`` (this module).

The proxy must:

- Run the same gate stack as the operator route, plus a stricter request
  shape (``extra="forbid"``).
- Read ``HAM_OPENCODE_EXEC_TOKEN`` only from the process environment.
- Never reflect the token value to the response body, response headers,
  or any log line.
- Persist a ``ControlPlaneRun`` with ``provider="opencode_cli"`` on
  success.

All canary tokens used here are obvious fakes (``test-token-canary-<hex>``
and ``opencode-test-canary-not-a-real-key``).
"""

from __future__ import annotations

import logging
import secrets
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api import opencode_build as build_api
from src.api import opencode_launch_proxy as proxy_api
from src.api.clerk_gate import get_ham_clerk_actor
from src.api.server import app, fastapi_app
from src.ham.clerk_auth import HamActor
from src.ham.opencode_runner.result import OpenCodeRunResult
from src.ham.worker_adapters.opencode_adapter import OpenCodeStatus

_AUTH_CANARY = "opencode-test-canary-not-a-real-key"


def _new_token() -> str:
    return "test-token-canary-" + secrets.token_hex(16)


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
    project_id: str = "project.opencode-proxy-abc123",
    output_target: str = "managed_workspace",
    workspace_id: str | None = "ws_proxy",
    build_lane_enabled: bool = True,
    name: str = "p_opencode_proxy",
) -> Any:
    return SimpleNamespace(
        id=project_id,
        name=name,
        output_target=output_target,
        workspace_id=workspace_id,
        build_lane_enabled=build_lane_enabled,
        root="/tmp/p_opencode_proxy",
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


def _patch_proxy_gates(
    *,
    rec: Any | None = None,
    approver_ok: bool = True,
    readiness: Any | None = None,
) -> list[Any]:
    patches: list[Any] = []
    if rec is None:
        rec = _project_rec()
    fake_store = SimpleNamespace(get_project=lambda _pid: rec)
    patches.append(patch.object(proxy_api, "get_project_store", lambda: fake_store))
    if approver_ok:
        patches.append(
            patch.object(
                proxy_api,
                "_require_build_approver",
                lambda actor, rec, store: None,
            )
        )
    patches.append(
        patch.object(
            proxy_api,
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


def _good_body(
    rec: Any,
    *,
    user_prompt: str = "tidy README",
    model: str | None = None,
    confirmed: bool = True,
) -> dict[str, Any]:
    return {
        "project_id": rec.id,
        "user_prompt": user_prompt,
        "model": model,
        "proposal_digest": _preview_digest(rec.id, user_prompt, model),
        "base_revision": build_api.OPENCODE_REGISTRY_REVISION,
        "confirmed": confirmed,
    }


# ---------------------------------------------------------------------------
# Gate-stack tests (fail-closed matrix)
# ---------------------------------------------------------------------------


def test_proxy_requires_clerk(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "1")
    res = _client().post(
        "/api/opencode/build/launch_proxy",
        json={
            "project_id": "p",
            "user_prompt": "tidy",
            "proposal_digest": "0" * 64,
            "base_revision": build_api.OPENCODE_REGISTRY_REVISION,
            "confirmed": True,
        },
    )
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"


def test_proxy_requires_confirmed_true(
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    res = _client(actor).post(
        "/api/opencode/build/launch_proxy",
        json={
            "project_id": "p",
            "user_prompt": "tidy",
            "proposal_digest": "0" * 64,
            "base_revision": build_api.OPENCODE_REGISTRY_REVISION,
            "confirmed": False,
        },
    )
    assert res.status_code == 400
    assert res.json()["detail"]["error"]["code"] == "NOT_APPROVED"


def test_proxy_requires_opencode_enabled(
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    res = _client(actor).post(
        "/api/opencode/build/launch_proxy",
        json={
            "project_id": "p",
            "user_prompt": "tidy",
            "proposal_digest": "0" * 64,
            "base_revision": build_api.OPENCODE_REGISTRY_REVISION,
            "confirmed": True,
        },
    )
    assert res.status_code == 503
    assert res.json()["detail"]["error"]["code"] == "OPENCODE_DISABLED"


def test_proxy_requires_execution_enabled(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    res = _client(actor).post(
        "/api/opencode/build/launch_proxy",
        json={
            "project_id": "p",
            "user_prompt": "tidy",
            "proposal_digest": "0" * 64,
            "base_revision": build_api.OPENCODE_REGISTRY_REVISION,
            "confirmed": True,
        },
    )
    assert res.status_code == 503
    assert res.json()["detail"]["error"]["code"] == "OPENCODE_EXECUTION_DISABLED"


def test_proxy_requires_project_found(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")

    fake_store = SimpleNamespace(get_project=lambda _pid: None)
    with patch.object(proxy_api, "get_project_store", lambda: fake_store):
        res = _client(actor).post(
            "/api/opencode/build/launch_proxy",
            json={
                "project_id": "missing",
                "user_prompt": "tidy",
                "proposal_digest": "0" * 64,
                "base_revision": build_api.OPENCODE_REGISTRY_REVISION,
                "confirmed": True,
            },
        )
    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "PROJECT_NOT_FOUND"


def test_proxy_requires_managed_workspace_output_target(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    rec = _project_rec(output_target="github_pr", workspace_id=None)
    fake_store = SimpleNamespace(get_project=lambda _pid: rec)
    with patch.object(proxy_api, "get_project_store", lambda: fake_store):
        res = _client(actor).post(
            "/api/opencode/build/launch_proxy",
            json=_good_body(rec),
        )
    assert res.status_code == 409
    assert res.json()["detail"]["error"]["code"] == "OUTPUT_TARGET_REQUIRED_MANAGED_WORKSPACE"


def test_proxy_requires_build_approver(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    rec = _project_rec()

    def _denied(_actor: Any, _rec: Any, _store: Any) -> None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "HAM_PERMISSION_DENIED",
                    "message": "Only a workspace owner or admin can approve a managed build.",
                }
            },
        )

    patches = _patch_proxy_gates(rec=rec, approver_ok=False)
    try:
        with patch.object(proxy_api, "_require_build_approver", _denied):
            res = _client(actor).post(
                "/api/opencode/build/launch_proxy",
                json=_good_body(rec),
            )
    finally:
        _stop(patches)
    assert res.status_code == 403
    assert res.json()["detail"]["error"]["code"] == "HAM_PERMISSION_DENIED"


def test_proxy_requires_readiness_configured(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    rec = _project_rec()
    patches = _patch_proxy_gates(
        rec=rec,
        readiness=_readiness(status=OpenCodeStatus.CLI_MISSING),
    )
    try:
        res = _client(actor).post(
            "/api/opencode/build/launch_proxy",
            json=_good_body(rec),
        )
    finally:
        _stop(patches)
    assert res.status_code == 503
    assert res.json()["detail"]["error"]["code"] == "OPENCODE_LANE_UNCONFIGURED"


def test_proxy_rejects_digest_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    rec = _project_rec()
    patches = _patch_proxy_gates(rec=rec)
    body = _good_body(rec)
    body["proposal_digest"] = "0" * 64
    try:
        res = _client(actor).post("/api/opencode/build/launch_proxy", json=body)
    finally:
        _stop(patches)
    assert res.status_code == 409
    assert res.json()["detail"]["error"]["code"] == "OPENCODE_LAUNCH_PREVIEW_STALE"


def test_proxy_rejects_missing_env_token(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    # Note: HAM_OPENCODE_EXEC_TOKEN is intentionally unset.
    rec = _project_rec()
    patches = _patch_proxy_gates(rec=rec)
    try:
        res = _client(actor).post(
            "/api/opencode/build/launch_proxy",
            json=_good_body(rec),
        )
    finally:
        _stop(patches)
    assert res.status_code == 503
    assert res.json()["detail"]["error"]["code"] == "OPENCODE_LANE_UNCONFIGURED"


# ---------------------------------------------------------------------------
# Happy path: snapshot emit
# ---------------------------------------------------------------------------


def test_proxy_succeeds_and_emits_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    token = _new_token()
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", token)
    rec = _project_rec()
    patches = _patch_proxy_gates(rec=rec)

    fake_snap = SimpleNamespace(
        build_outcome="succeeded",
        target_ref={
            "snapshot_id": "snap_proxy_abc",
            "preview_url": "https://snapshots.example.test/proxy/abc",
            "changed_paths_count": 2,
            "neutral_outcome": "snapshot_published",
        },
        error_summary=None,
    )

    def fake_runner(**kwargs: Any) -> OpenCodeRunResult:
        return OpenCodeRunResult(
            status="success",
            changed_paths=("README.md", "docs/notes.md"),
            assistant_summary="proxy ok.",
            duration_seconds=0.05,
        )

    saved: list[Any] = []
    fake_store = SimpleNamespace(save=lambda r, **k: saved.append(r))

    try:
        with (
            patch.object(build_api, "run_opencode_mission", fake_runner),
            patch.object(build_api, "compute_deleted_paths_against_parent", lambda _c: ()),
            patch.object(build_api, "emit_managed_workspace_snapshot", lambda _c: fake_snap),
            patch.object(build_api, "get_control_plane_run_store", lambda: fake_store),
        ):
            res = _client(actor).post(
                "/api/opencode/build/launch_proxy",
                json=_good_body(rec),
            )
    finally:
        _stop(patches)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "opencode_build_launch"
    assert body["ok"] is True
    assert body["control_plane_status"] == "succeeded"
    assert body["output_ref"]["snapshot_id"] == "snap_proxy_abc"
    assert body["output_ref"]["changed_paths_count"] == 2
    assert body["will_open_pull_request"] is False
    assert saved
    assert saved[0].status_reason == "opencode:snapshot_emitted"


def test_proxy_succeeds_nothing_to_change(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    token = _new_token()
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", token)
    rec = _project_rec()
    patches = _patch_proxy_gates(rec=rec)

    fake_snap = SimpleNamespace(
        build_outcome="nothing_to_change",
        target_ref={},
        error_summary=None,
    )

    def fake_runner(**kwargs: Any) -> OpenCodeRunResult:
        return OpenCodeRunResult(status="success", assistant_summary="nothing.")

    saved: list[Any] = []
    fake_store = SimpleNamespace(save=lambda r, **k: saved.append(r))

    try:
        with (
            patch.object(build_api, "run_opencode_mission", fake_runner),
            patch.object(build_api, "compute_deleted_paths_against_parent", lambda _c: ()),
            patch.object(build_api, "emit_managed_workspace_snapshot", lambda _c: fake_snap),
            patch.object(build_api, "get_control_plane_run_store", lambda: fake_store),
        ):
            res = _client(actor).post(
                "/api/opencode/build/launch_proxy",
                json=_good_body(rec),
            )
    finally:
        _stop(patches)
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert saved[0].status_reason == "opencode:nothing_to_change"


def test_proxy_safe_blocks_output_requires_review(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    """Deletion guard (Mission 3.1) must fire through the proxy too."""
    token = _new_token()
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", token)
    rec = _project_rec()
    patches = _patch_proxy_gates(rec=rec)

    def fake_runner(**kwargs: Any) -> OpenCodeRunResult:
        return OpenCodeRunResult(status="success", assistant_summary="ok.")

    snapshot_mock = MagicMock()
    saved: list[Any] = []
    fake_store = SimpleNamespace(save=lambda r, **k: saved.append(r))

    try:
        with (
            patch.object(build_api, "run_opencode_mission", fake_runner),
            patch.object(
                build_api,
                "compute_deleted_paths_against_parent",
                lambda _c: ("README.md",),
            ),
            patch.object(build_api, "emit_managed_workspace_snapshot", snapshot_mock),
            patch.object(build_api, "get_control_plane_run_store", lambda: fake_store),
        ):
            res = _client(actor).post(
                "/api/opencode/build/launch_proxy",
                json=_good_body(rec),
            )
    finally:
        _stop(patches)
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert body["output_ref"] is None
    assert "output_requires_review" in (body["error_summary"] or "")
    snapshot_mock.assert_not_called()
    assert saved[0].status_reason == "opencode:output_requires_review"


def test_proxy_deletion_guard_blocks_when_allow_deletions_false(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    """Mission 3.1 invariant: when HAM_OPENCODE_ALLOW_DELETIONS is not
    truthy, a deletion proposal must NOT result in a snapshot emit.

    Mirrors ``test_opencode_build_api.test_launch_persists_output_requires_review_on_deletion``
    but via the proxy path."""
    token = _new_token()
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", token)
    monkeypatch.delenv("HAM_OPENCODE_ALLOW_DELETIONS", raising=False)

    rec = _project_rec()
    patches = _patch_proxy_gates(rec=rec)

    def fake_runner(**kwargs: Any) -> OpenCodeRunResult:
        return OpenCodeRunResult(status="success", assistant_summary="ok.")

    snapshot_mock = MagicMock()
    saved: list[Any] = []
    fake_store = SimpleNamespace(save=lambda r, **k: saved.append(r))

    try:
        with (
            patch.object(build_api, "run_opencode_mission", fake_runner),
            patch.object(
                build_api,
                "compute_deleted_paths_against_parent",
                lambda _c: ("a.py", "b.py"),
            ),
            patch.object(build_api, "emit_managed_workspace_snapshot", snapshot_mock),
            patch.object(build_api, "get_control_plane_run_store", lambda: fake_store),
        ):
            res = _client(actor).post(
                "/api/opencode/build/launch_proxy",
                json=_good_body(rec),
            )
    finally:
        _stop(patches)
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert body["control_plane_status"] == "failed"
    snapshot_mock.assert_not_called()
    cp = saved[0]
    assert cp.status_reason == "opencode:output_requires_review"
    assert cp.output_ref is None


# ---------------------------------------------------------------------------
# Token-leak invariants
# ---------------------------------------------------------------------------


def test_proxy_response_does_not_leak_token(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    token = _new_token()
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", token)
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    rec = _project_rec()
    patches = _patch_proxy_gates(rec=rec)

    fake_snap = SimpleNamespace(
        build_outcome="succeeded",
        target_ref={"snapshot_id": "snap_x"},
        error_summary=None,
    )

    def fake_runner(**kwargs: Any) -> OpenCodeRunResult:
        return OpenCodeRunResult(status="success", assistant_summary="ok.")

    fake_store = SimpleNamespace(save=lambda *a, **k: None)

    caplog.set_level(logging.DEBUG)
    try:
        with (
            patch.object(build_api, "run_opencode_mission", fake_runner),
            patch.object(build_api, "compute_deleted_paths_against_parent", lambda _c: ()),
            patch.object(build_api, "emit_managed_workspace_snapshot", lambda _c: fake_snap),
            patch.object(build_api, "get_control_plane_run_store", lambda: fake_store),
        ):
            res = _client(actor).post(
                "/api/opencode/build/launch_proxy",
                json=_good_body(rec),
            )
    finally:
        _stop(patches)
    assert res.status_code == 200
    blob = res.text
    assert token not in blob
    assert _AUTH_CANARY not in blob
    for v in res.headers.values():
        assert token not in v
    assert token not in caplog.text


def test_proxy_does_not_accept_token_from_body(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    for extra_field in ("exec_token", "token", "authorization"):
        res = _client(actor).post(
            "/api/opencode/build/launch_proxy",
            json={
                "project_id": "p",
                "user_prompt": "tidy",
                "proposal_digest": "0" * 64,
                "base_revision": build_api.OPENCODE_REGISTRY_REVISION,
                "confirmed": True,
                extra_field: _new_token(),
            },
        )
        assert res.status_code == 422, (extra_field, res.text)


def test_proxy_does_not_accept_token_from_header(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    """Authorization header is not consulted for the OpenCode exec token.

    Even when a token is sent over the wire, the proxy reads only from
    process env, so an unset env still yields 503."""
    header_token = _new_token()
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    # HAM_OPENCODE_EXEC_TOKEN intentionally unset.
    rec = _project_rec()
    patches = _patch_proxy_gates(rec=rec)
    try:
        res = _client(actor).post(
            "/api/opencode/build/launch_proxy",
            json=_good_body(rec),
            headers={"Authorization": f"Bearer {header_token}"},
        )
    finally:
        _stop(patches)
    assert res.status_code == 503
    assert res.json()["detail"]["error"]["code"] == "OPENCODE_LANE_UNCONFIGURED"
    assert header_token not in res.text


def test_proxy_persists_control_plane_run(
    monkeypatch: pytest.MonkeyPatch,
    isolated_env: None,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    token = _new_token()
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", token)
    rec = _project_rec()
    patches = _patch_proxy_gates(rec=rec)

    fake_snap = SimpleNamespace(
        build_outcome="succeeded",
        target_ref={"snapshot_id": "snap_persist"},
        error_summary=None,
    )

    def fake_runner(**kwargs: Any) -> OpenCodeRunResult:
        return OpenCodeRunResult(status="success", assistant_summary="ok.")

    saved: list[Any] = []
    fake_store = SimpleNamespace(save=lambda r, **k: saved.append(r))

    try:
        with (
            patch.object(build_api, "run_opencode_mission", fake_runner),
            patch.object(build_api, "compute_deleted_paths_against_parent", lambda _c: ()),
            patch.object(build_api, "emit_managed_workspace_snapshot", lambda _c: fake_snap),
            patch.object(build_api, "get_control_plane_run_store", lambda: fake_store),
        ):
            res = _client(actor).post(
                "/api/opencode/build/launch_proxy",
                json=_good_body(rec),
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
    assert cp.pr_url is None
