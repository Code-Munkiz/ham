"""
Tests for ``GET /api/coding/readiness``.

The endpoint is read-only and Clerk-gated. These tests lock:

- 401 when Clerk is required and no actor is supplied.
- 200 + stable JSON shape with ``kind: coding_readiness``.
- Non-operators receive ``available`` + ``blockers`` only; no ``operator_signals``.
- Operators receive ``operator_signals`` (coarse labels only).
- Response body never echoes secret values, internal workflow ids, env-name
  strings, or runner URLs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.server import app, fastapi_app
from src.ham.clerk_auth import HamActor
from src.persistence.project_store import (
    ProjectStore,
    set_project_store_for_tests,
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "HAM_DROID_RUNNER_URL",
        "HAM_DROID_RUNNER_TOKEN",
        "HAM_DROID_EXEC_TOKEN",
        "CURSOR_API_KEY",
        "HAM_CURSOR_CREDENTIALS_FILE",
        "ANTHROPIC_API_KEY",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ProjectStore:
    monkeypatch.setenv("HAM_CURSOR_CREDENTIALS_FILE", str(tmp_path / "cursor_creds.json"))
    store = ProjectStore(store_path=tmp_path / "projects.json")
    set_project_store_for_tests(store)
    yield store
    set_project_store_for_tests(None)


@pytest.fixture
def cleanup_overrides() -> Any:
    yield
    fastapi_app.dependency_overrides.clear()


def _client(actor: HamActor | None) -> TestClient:
    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: actor
    return TestClient(app)


@pytest.fixture
def operator_actor() -> HamActor:
    return HamActor(
        user_id="user_op",
        org_id=None,
        session_id="sess_o",
        email="operator@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


@pytest.fixture
def normie_actor() -> HamActor:
    return HamActor(
        user_id="user_normie",
        org_id=None,
        session_id="sess_n",
        email="normie@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


_FORBIDDEN_TOKENS = (
    "safe_edit_low",
    "low_edit",
    "--auto low",
    "ham_droid_exec_token",
    "ham_droid_runner_url",
    "ham_droid_runner_token",
    "anthropic_api_key",
    "cursor_api_key",
    "argv",
    "http://",
    "https://",
)


def _assert_no_secret_leakage(text: str) -> None:
    lower = text.lower()
    for forbidden in _FORBIDDEN_TOKENS:
        assert forbidden not in lower, f"response leaks {forbidden!r}: {lower}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_readiness_requires_clerk_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch, isolated_store: ProjectStore
) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "1")
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
    fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)
    res = TestClient(app).get("/api/coding/readiness")
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"


def test_readiness_returns_stable_envelope_with_no_project(
    isolated_store: ProjectStore, normie_actor: HamActor, cleanup_overrides: None
) -> None:
    res = _client(normie_actor).get("/api/coding/readiness")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "coding_readiness"
    # is_operator follows actor_is_workspace_operator semantics: Clerk auth
    # disabled (default test posture) treats the caller as operator. The
    # operator-vs-normie path is locked by the dedicated tests below.
    assert isinstance(body["is_operator"], bool)
    assert isinstance(body["providers"], list) and len(body["providers"]) == 7
    kinds = {p["provider"] for p in body["providers"]}
    assert kinds == {
        "no_agent",
        "factory_droid_audit",
        "factory_droid_build",
        "cursor_cloud",
        "claude_code",
        "claude_agent",
        "opencode_cli",
    }
    assert body["project"]["found"] is False
    assert body["project"]["project_id"] is None


def test_readiness_unknown_project_returns_found_false(
    isolated_store: ProjectStore, normie_actor: HamActor, cleanup_overrides: None
) -> None:
    res = _client(normie_actor).get(
        "/api/coding/readiness", params={"project_id": "project.unknown"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["project"]["found"] is False
    assert body["project"]["project_id"] == "project.unknown"


def test_readiness_includes_project_flags_when_project_exists(
    isolated_store: ProjectStore,
    tmp_path: Path,
    normie_actor: HamActor,
    cleanup_overrides: None,
) -> None:
    rec = isolated_store.make_record(name="demo", root=str(tmp_path))
    rec = rec.model_copy(update={"build_lane_enabled": True, "github_repo": "Code-Munkiz/ham"})
    isolated_store.register(rec)
    res = _client(normie_actor).get("/api/coding/readiness", params={"project_id": rec.id})
    assert res.status_code == 200
    body = res.json()
    assert body["project"]["found"] is True
    assert body["project"]["project_id"] == rec.id
    assert body["project"]["build_lane_enabled"] is True
    assert body["project"]["has_github_repo"] is True
    # The github_repo string itself is never echoed in the response.
    assert "Code-Munkiz/ham" not in res.text


def test_non_operator_response_omits_operator_signals(
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_overrides: None,
) -> None:
    # Enforce Clerk + an operator allowlist that excludes the normie so the
    # workspace-operator gate evaluates strictly. Without these, the local
    # dev fallback treats every caller as operator (matches PR #237 semantics).
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HAM_WORKSPACE_OPERATOR_EMAILS", "operator@example.test")
    res = _client(normie_actor).get("/api/coding/readiness")
    assert res.status_code == 200
    body = res.json()
    assert body["is_operator"] is False
    for entry in body["providers"]:
        assert "operator_signals" not in entry


def test_operator_response_includes_operator_signals(
    isolated_store: ProjectStore,
    operator_actor: HamActor,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HAM_WORKSPACE_OPERATOR_EMAILS", "operator@example.test")
    res = _client(operator_actor).get("/api/coding/readiness")
    assert res.status_code == 200
    body = res.json()
    assert body["is_operator"] is True
    audit = next(p for p in body["providers"] if p["provider"] == "factory_droid_audit")
    assert "operator_signals" in audit
    # Coarse labels only; never URLs or env values.
    for sig in audit["operator_signals"]:
        assert "://" not in sig
        assert "test-only-not-deployed" not in sig.lower()


def test_response_body_never_leaks_secrets(
    isolated_store: ProjectStore,
    operator_actor: HamActor,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HAM_WORKSPACE_OPERATOR_EMAILS", "operator@example.test")
    monkeypatch.setenv("HAM_DROID_RUNNER_URL", "https://runner.example/private")
    monkeypatch.setenv("HAM_DROID_RUNNER_TOKEN", "test-only-not-deployed-runner-token")
    monkeypatch.setenv("HAM_DROID_EXEC_TOKEN", "test-only-not-deployed")
    monkeypatch.setenv("CURSOR_API_KEY", "cur_" + "z" * 40)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-only")
    res = _client(operator_actor).get("/api/coding/readiness")
    assert res.status_code == 200
    _assert_no_secret_leakage(res.text)
    # Specific value checks for defence-in-depth.
    blob = res.text.lower()
    assert "test-only-not-deployed" not in blob
    assert "sk-ant-test-only" not in blob
    assert "cur_" + "z" * 40 not in blob
    assert "runner.example/private" not in blob


def test_response_body_does_not_expose_internal_workflow_ids(
    isolated_store: ProjectStore, normie_actor: HamActor, cleanup_overrides: None
) -> None:
    """Lock: chat-first surfaces never expose 'safe_edit_low' / 'readonly_repo_audit'."""
    res = _client(normie_actor).get("/api/coding/readiness")
    assert res.status_code == 200
    blob = res.text.lower()
    assert "safe_edit_low" not in blob
    assert "readonly_repo_audit" not in blob


def test_readiness_api_includes_opencode_provider_entry_when_available(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    cleanup_overrides: None,
) -> None:
    """Env gates on + CLI present + auth set → opencode_cli entry is available."""
    from src.ham.worker_adapters import opencode_adapter as _opencode_adapter

    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-opencode-canary")
    monkeypatch.setattr(
        _opencode_adapter.shutil,
        "which",
        lambda name: "/usr/local/bin/opencode" if name == "opencode" else None,
    )
    _opencode_adapter.reset_opencode_readiness_cache()
    res = _client(normie_actor).get("/api/coding/readiness")
    assert res.status_code == 200, res.text
    body = res.json()
    oc = next(p for p in body["providers"] if p["provider"] == "opencode_cli")
    assert oc["available"] is True
    assert oc["blockers"] == []
    # Secret value canary never leaks into the response body.
    assert "test-opencode-canary" not in res.text


def test_readiness_api_opencode_blockers_normie_safe(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    cleanup_overrides: None,
) -> None:
    """Lock: opencode_cli blocker copy never names env vars or runner internals."""
    monkeypatch.delenv("HAM_OPENCODE_ENABLED", raising=False)
    monkeypatch.delenv("HAM_OPENCODE_EXECUTION_ENABLED", raising=False)
    res = _client(normie_actor).get("/api/coding/readiness")
    assert res.status_code == 200
    body = res.json()
    oc = next(p for p in body["providers"] if p["provider"] == "opencode_cli")
    for blocker in oc["blockers"]:
        for forbidden in (
            "HAM_OPENCODE_ENABLED",
            "HAM_OPENCODE_EXECUTION_ENABLED",
            "OPENROUTER_API_KEY",
            "ANTHROPIC_API_KEY",
            "/usr/",
            "http://",
            "https://",
            "subprocess",
        ):
            assert forbidden not in blocker, (forbidden, blocker)


def test_no_launch_endpoint_under_coding_namespace() -> None:
    """Lock: there is no launch / dispatch / execute route under /api/coding.

    Phase 2A adds POST /api/coding/conductor/preview, so POST is allowed —
    but only on /preview paths. Negative locks ensure no route matches
    ``/launch``, ``/dispatch``, or ``/execute`` under the coding namespace.
    """
    routes = {
        (r.path, tuple(sorted(r.methods or ())))
        for r in fastapi_app.routes
        if hasattr(r, "path") and "/api/coding" in getattr(r, "path", "")
    }
    paths = {p for p, _ in routes}
    assert "/api/coding/readiness" in paths
    for p, methods in routes:
        assert "/launch" not in p, f"unexpected launch route: {p}"
        assert "/dispatch" not in p, f"unexpected dispatch route: {p}"
        assert "/execute" not in p, f"unexpected execute route: {p}"
        # Methods stay restricted to safe HTTP verbs — no PUT / DELETE / PATCH.
        for m in methods:
            assert m in ("GET", "POST", "HEAD"), f"unexpected method {m} on {p}"
