"""Tests for gated POST /api/workspace/tools/claude_agent_sdk/smoke."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.worker_adapters.claude_agent_adapter import (
    ClaudeAgentSmokeResult,
    claude_agent_smoke_feature_enabled,
)

client = TestClient(app)


@pytest.fixture
def clear_smoke_env(monkeypatch):
    monkeypatch.delenv("HAM_CLAUDE_AGENT_SMOKE_ENABLED", raising=False)
    monkeypatch.delenv("HAM_CLAUDE_AGENT_SMOKE_TOKEN", raising=False)
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
    yield


TOK32 = "x" * 32


class TestSmokeEndpointGating:
    """Feature flag, arming, and auth."""

    def test_smoke_feature_env_not_implicitly_enabled(self, monkeypatch):
        """Runtime SDK dependency does not imply HAM_CLAUDE_AGENT_SMOKE_ENABLED — ops must opt in."""
        monkeypatch.delenv("HAM_CLAUDE_AGENT_SMOKE_ENABLED", raising=False)
        assert claude_agent_smoke_feature_enabled() is False

    def test_disabled_by_default_returns_404(self, clear_smoke_env):
        r = client.post("/api/workspace/tools/claude_agent_sdk/smoke")
        assert r.status_code == 404

    def test_enabled_unarmed_returns_404(self, monkeypatch):
        monkeypatch.setenv("HAM_CLAUDE_AGENT_SMOKE_ENABLED", "1")
        monkeypatch.delenv("HAM_CLAUDE_AGENT_SMOKE_TOKEN", raising=False)
        monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
        monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
        r = client.post("/api/workspace/tools/claude_agent_sdk/smoke")
        assert r.status_code == 404
        assert "not configured" in r.json()["detail"].lower()

    def test_armed_without_token_returns_403(self, monkeypatch):
        monkeypatch.setenv("HAM_CLAUDE_AGENT_SMOKE_ENABLED", "1")
        monkeypatch.setenv("HAM_CLAUDE_AGENT_SMOKE_TOKEN", TOK32)
        monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
        monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
        r = client.post("/api/workspace/tools/claude_agent_sdk/smoke")
        assert r.status_code == 403

    def test_armed_wrong_token_returns_403(self, monkeypatch):
        monkeypatch.setenv("HAM_CLAUDE_AGENT_SMOKE_ENABLED", "1")
        monkeypatch.setenv("HAM_CLAUDE_AGENT_SMOKE_TOKEN", TOK32)
        monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
        monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
        r = client.post(
            "/api/workspace/tools/claude_agent_sdk/smoke",
            headers={"X-HAM-SMOKE-TOKEN": "y" * 32},
        )
        assert r.status_code == 403

    def test_authorized_readiness_error_no_leak(self, monkeypatch):
        monkeypatch.setenv("HAM_CLAUDE_AGENT_SMOKE_ENABLED", "1")
        monkeypatch.setenv("HAM_CLAUDE_AGENT_SMOKE_TOKEN", TOK32)
        monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
        monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-absolute-ultra-secret-key-999")

        fail = ClaudeAgentSmokeResult(
            status="error",
            provider="anthropic_direct",
            sdk_available=False,
            authenticated=False,
            smoke_ok=False,
            response_text="",
            blocker="Claude Agent SDK is not ready on this server.",
        )
        with patch(
            "src.api.workspace_tools.run_claude_agent_sdk_smoke",
            new_callable=AsyncMock,
            return_value=fail,
        ):
            r = client.post(
                "/api/workspace/tools/claude_agent_sdk/smoke",
                headers={"X-HAM-SMOKE-TOKEN": TOK32},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "error"
        assert body["smoke_ok"] is False
        raw = r.text
        assert "sk-ant-absolute-ultra-secret-key-999" not in raw
        assert "ANTHROPIC_API_KEY" not in raw

    def test_mock_smoke_success_returns_ok(self, monkeypatch):
        monkeypatch.setenv("HAM_CLAUDE_AGENT_SMOKE_ENABLED", "1")
        monkeypatch.setenv("HAM_CLAUDE_AGENT_SMOKE_TOKEN", TOK32)
        monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
        monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)

        ok = ClaudeAgentSmokeResult(
            status="ok",
            provider="anthropic_direct",
            sdk_available=True,
            authenticated=True,
            smoke_ok=True,
            response_text="HAM_CLAUDE_SMOKE_OK",
            blocker=None,
        )
        with patch(
            "src.api.workspace_tools.run_claude_agent_sdk_smoke",
            new_callable=AsyncMock,
            return_value=ok,
        ):
            r = client.post(
                "/api/workspace/tools/claude_agent_sdk/smoke",
                headers={"X-HAM-SMOKE-TOKEN": TOK32},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["smoke_ok"] is True
        assert body["response_text"] == "HAM_CLAUDE_SMOKE_OK"


class TestClerkSmokePath:
    def test_clerk_mode_without_actor_returns_401(self, monkeypatch):
        monkeypatch.setenv("HAM_CLAUDE_AGENT_SMOKE_ENABLED", "1")
        monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "1")
        monkeypatch.delenv("HAM_CLAUDE_AGENT_SMOKE_TOKEN", raising=False)

        r = client.post("/api/workspace/tools/claude_agent_sdk/smoke")
        assert r.status_code == 401
