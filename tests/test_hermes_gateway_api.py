"""GET /api/hermes-gateway/* — broker-backed command center API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)


@pytest.fixture
def mock_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


def test_hermes_gateway_snapshot(mock_gateway: None) -> None:
    res = client.get("/api/hermes-gateway/snapshot")
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "ham_hermes_gateway_snapshot"
    assert body["hermes_hub"]["gateway_mode"] == "mock"
    assert "external_runners" in body
    assert "future_adapter_placeholders" in body


def test_hermes_gateway_snapshot_refresh_query(mock_gateway: None) -> None:
    res = client.get("/api/hermes-gateway/snapshot?refresh=true")
    assert res.status_code == 200
    assert res.json()["freshness"]["inventory_cached"] is False


def test_hermes_gateway_capabilities(mock_gateway: None) -> None:
    res = client.get("/api/hermes-gateway/capabilities")
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "ham_hermes_gateway_capabilities"
    assert "hermes_agent_v0_8_0_surfaces" in body


def test_hermes_gateway_stream_route_in_openapi(mock_gateway: None) -> None:
    """Route is registered (OpenAPI may not list text/event-stream for StreamingResponse)."""
    spec = app.openapi()
    assert "/api/hermes-gateway/stream" in spec["paths"]
    assert spec["paths"]["/api/hermes-gateway/stream"]["get"]["operationId"]
