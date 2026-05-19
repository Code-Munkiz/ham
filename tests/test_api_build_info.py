"""Tests for `/api/status` build sub-object and `/api/build-info` route.

Locks the backward-compatible shape of `/api/status` (used by the frontend
managed-build smoke preflight) and the sanitization rules applied to env-driven
build metadata in `src.api.server._build_info`.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.server import app

_BUILD_ENV_NAMES = (
    "HAM_BUILD_SHA",
    "GIT_SHA",
    "HAM_BUILD_TIME",
    "BUILD_TIME",
    "HAM_SERVICE_VERSION",
    "K_REVISION",
    "HAM_DEPLOYED_REVISION",
)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def clean_build_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _BUILD_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_api_status_preserves_backward_compatible_shape(
    client: TestClient, clean_build_env: None
) -> None:
    res = client.get("/api/status")
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body.get("version"), str)
    run_count = body.get("run_count")
    assert isinstance(run_count, int) and run_count >= 0
    caps = body.get("capabilities")
    assert isinstance(caps, dict)
    assert caps.get("project_agent_profiles_read") is True
    build = body.get("build")
    assert isinstance(build, dict)


def test_api_status_build_object_has_all_keys(
    client: TestClient, clean_build_env: None
) -> None:
    res = client.get("/api/status")
    assert res.status_code == 200, res.text
    build = res.json().get("build") or {}
    assert set(build.keys()) == {
        "git_sha",
        "build_time",
        "service_version",
        "deployed_revision",
    }


def test_api_build_info_endpoint_returns_same_object(
    client: TestClient, clean_build_env: None
) -> None:
    status_res = client.get("/api/status")
    build_res = client.get("/api/build-info")
    assert status_res.status_code == 200, status_res.text
    assert build_res.status_code == 200, build_res.text
    assert build_res.json() == status_res.json().get("build")


def test_build_info_defaults_when_env_unset(
    client: TestClient, clean_build_env: None
) -> None:
    res = client.get("/api/build-info")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body == {
        "git_sha": None,
        "build_time": None,
        "service_version": "0.1.0",
        "deployed_revision": None,
    }


def test_build_info_reads_safe_env_values(
    client: TestClient, clean_build_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_BUILD_SHA", "abc1234")
    monkeypatch.setenv("HAM_BUILD_TIME", "2026-05-19T12:00:00Z")
    monkeypatch.setenv("HAM_SERVICE_VERSION", "0.2.0")
    monkeypatch.setenv("K_REVISION", "ham-api-0001-abc")
    res = client.get("/api/build-info")
    assert res.status_code == 200, res.text
    assert res.json() == {
        "git_sha": "abc1234",
        "build_time": "2026-05-19T12:00:00Z",
        "service_version": "0.2.0",
        "deployed_revision": "ham-api-0001-abc",
    }


def test_build_info_sanitizes_long_values(
    client: TestClient, clean_build_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_BUILD_SHA", "a" * 200)
    res = client.get("/api/build-info")
    assert res.status_code == 200, res.text
    assert res.json().get("git_sha") is None


def test_build_info_sanitizes_invalid_characters(
    client: TestClient, clean_build_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_BUILD_SHA", "abc$ defg")
    res = client.get("/api/build-info")
    assert res.status_code == 200, res.text
    assert res.json().get("git_sha") is None


def test_build_info_prefers_ham_prefixed_env(
    client: TestClient, clean_build_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_BUILD_SHA", "aaaaaaa")
    monkeypatch.setenv("GIT_SHA", "bbbbbbb")
    res = client.get("/api/build-info")
    assert res.status_code == 200, res.text
    assert res.json().get("git_sha") == "aaaaaaa"


def test_build_info_falls_back_to_unprefixed_env(
    client: TestClient, clean_build_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_SHA", "ccccccc")
    res = client.get("/api/build-info")
    assert res.status_code == 200, res.text
    assert res.json().get("git_sha") == "ccccccc"


def test_build_info_response_does_not_leak_internal_tokens(
    client: TestClient, clean_build_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_BUILD_SHA", "abc1234")
    forbidden = (
        "HERMES_GATEWAY",
        "HAM_DROID_EXEC_TOKEN",
        "HAM_RUN_LAUNCH_TOKEN",
        "HAM_CURSOR_AGENT_LAUNCH_TOKEN",
        "HAM_SETTINGS_WRITE_TOKEN",
        "HAM_SKILLS_WRITE_TOKEN",
        "HAM_CAPABILITY_LIBRARY_WRITE_TOKEN",
        "HAM_CLAUDE_AGENT_SMOKE_TOKEN",
        "OPENROUTER_API_KEY",
        "CLERK",
        "proposal_digest",
        "base_revision",
        ".ham/runs",
        "operator.phase",
        "ControlPlaneRun",
        "cursor_cloud",
        "opencode_cli",
        "claude_code",
        "factory_droid_audit",
        "factory_droid_build",
    )
    for path in ("/api/status", "/api/build-info"):
        res = client.get(path)
        assert res.status_code == 200, res.text
        text = res.text
        for needle in forbidden:
            assert needle not in text, f"{path} leaked {needle!r}"


def test_build_info_helper_ignores_secret_named_env_vars(
    client: TestClient, clean_build_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_BUILD_TOKEN", "should-not-leak")
    for path in ("/api/status", "/api/build-info"):
        res = client.get(path)
        assert res.status_code == 200, res.text
        text = res.text
        assert "should-not-leak" not in text
        assert "HAM_BUILD_TOKEN" not in text
