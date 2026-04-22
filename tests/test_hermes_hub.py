"""Read-only GET /api/hermes-hub aggregates gateway + Hermes skills capabilities."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)


@pytest.fixture
def mock_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


def test_hermes_hub_snapshot_shape(mock_gateway, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    res = client.get("/api/hermes-hub")
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "ham_hermes_control_plane_snapshot"
    assert body["gateway_mode"] == "mock"
    assert body.get("dashboard_chat_ready") is True
    assert body.get("http_chat_ready") is False
    assert "dashboard_chat" in body
    assert body["dashboard_chat"]["active_upstream"] == "mock"
    assert body["skills_capabilities"]["kind"] == "hermes_skills_capabilities"
    assert "mode" in body["skills_capabilities"]
    assert "scope_notes" in body
    assert isinstance(body["scope_notes"]["in_ham_today"], list)
    assert isinstance(body["scope_notes"]["not_in_ham_yet"], list)


def test_hermes_hub_openrouter_summary(mock_gateway, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    res = client.get("/api/hermes-hub")
    assert res.status_code == 200
    body = res.json()
    assert body["gateway_mode"] == "openrouter"
    assert body["openrouter_chat_ready"] is True
    assert body.get("dashboard_chat_ready") is True
    assert body["dashboard_chat"]["active_upstream"] == "openrouter"


def test_hermes_hub_http_upstream_label(mock_gateway, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:8642")
    res = client.get("/api/hermes-hub")
    assert res.status_code == 200
    body = res.json()
    assert body["gateway_mode"] == "http"
    assert body.get("http_chat_ready") is True
    assert body.get("dashboard_chat_ready") is True
    assert body["dashboard_chat"]["active_upstream"] == "hermes_http"
