"""Tests for workspace tool/worker discovery endpoint (GET /api/workspace/tools).

Validates:
- All expected tools are present by id
- Response contains no secrets/env dumps
- Cloud mode does not claim local scan
- AI Studio and Antigravity are included
- Toggle/default enabled states are stable
- OpenRouter/Cursor/ComfyUI statuses do not leak credentials
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)

EXPECTED_TOOL_IDS = [
    "openrouter",
    "cursor",
    "factory_droid",
    "claude_code",
    "claude_agent_sdk",
    "openclaw",
    "ai_studio",
    "antigravity",
    "github",
    "git",
    "node",
    "python",
    "docker",
    "vercel",
    "google_cloud",
    "comfyui",
]


def _get_tools() -> dict:
    resp = client.get("/api/workspace/tools")
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture(autouse=True)
def _reset_claude_agent_sdk_cache():
    """Module-level _SDK_DETECTION cache leaks across tests; clear it."""
    from src.ham.worker_adapters.claude_agent_adapter import (
        reset_claude_agent_readiness_cache,
    )

    reset_claude_agent_readiness_cache()
    yield
    reset_claude_agent_readiness_cache()


class TestToolDiscoveryEndpoint:
    """Core endpoint behavior."""

    def test_returns_all_expected_tools(self):
        data = _get_tools()
        ids = [t["id"] for t in data["tools"]]
        for expected_id in EXPECTED_TOOL_IDS:
            assert expected_id in ids, f"Missing tool: {expected_id}"

    def test_response_has_no_secrets(self):
        data = _get_tools()
        raw = str(data)
        assert "OPENROUTER_API_KEY" not in raw
        assert "CURSOR_API_KEY" not in raw
        assert "HAM_DROID_EXEC_TOKEN" not in raw
        assert "GITHUB_TOKEN" not in raw
        assert "GH_TOKEN" not in raw
        # Masked previews may begin with sk-or…; never leak raw env-style blobs.
        assert "Bearer " not in raw

    def test_response_has_no_env_dump(self):
        data = _get_tools()
        raw = str(data)
        assert "PATH=" not in raw
        assert "HOME=" not in raw
        assert "PYTHONPATH" not in raw

    def test_ai_studio_included(self):
        data = _get_tools()
        ids = [t["id"] for t in data["tools"]]
        assert "ai_studio" in ids
        ai_studio = next(t for t in data["tools"] if t["id"] == "ai_studio")
        assert ai_studio["label"] == "AI Studio"
        assert ai_studio["status"] == "unknown"
        assert ai_studio["enabled"] is False

    def test_antigravity_included(self):
        data = _get_tools()
        ids = [t["id"] for t in data["tools"]]
        assert "antigravity" in ids
        antigravity = next(t for t in data["tools"] if t["id"] == "antigravity")
        assert antigravity["label"] == "Antigravity"
        assert antigravity["status"] == "unknown"
        assert antigravity["enabled"] is False

    def test_toggle_defaults_are_stable(self):
        data = _get_tools()
        for tool in data["tools"]:
            assert isinstance(tool["enabled"], bool)
            if tool["status"] in ("unknown", "not_found", "off", "needs_sign_in"):
                assert tool["enabled"] is False, (
                    f"{tool['id']} should not be enabled when status={tool['status']}"
                )
            if tool["status"] == "ready":
                assert tool["enabled"] is True


class TestCloudModeSafety:
    """Ensure cloud mode doesn't claim local scanning."""

    def test_cloud_mode_scan_not_available(self):
        with patch.dict(os.environ, {"K_SERVICE": "ham-api"}):
            data = _get_tools()
            assert data["scan_available"] is False
            assert data["scan_hint"] is not None

    def test_cloud_mode_local_tools_are_unknown(self):
        with patch.dict(os.environ, {"K_SERVICE": "ham-api"}):
            data = _get_tools()
            local_tool_ids = ["git", "node", "python", "docker", "claude_code", "openclaw"]
            for tool in data["tools"]:
                if tool["id"] in local_tool_ids:
                    assert tool["status"] in ("unknown", "not_found"), (
                        f"{tool['id']} should not claim ready in cloud mode"
                    )

    def test_non_cloud_mode_scan_available(self):
        env = {k: "" for k in ("K_SERVICE", "CLOUD_RUN_JOB", "GAE_APPLICATION")}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("K_SERVICE", None)
            os.environ.pop("CLOUD_RUN_JOB", None)
            os.environ.pop("GAE_APPLICATION", None)
            data = _get_tools()
            assert data["scan_available"] is True


class TestCredentialStatusSafety:
    """Statuses must not leak credential values."""

    def test_openrouter_ready_when_key_set(self):
        plausible_key = "sk-or-" + "a" * 30
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": plausible_key}):
            data = _get_tools()
            tool = next(t for t in data["tools"] if t["id"] == "openrouter")
            assert tool["status"] == "ready"
            assert plausible_key not in str(data)

    def test_openrouter_needs_sign_in_when_no_key(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            data = _get_tools()
            tool = next(t for t in data["tools"] if t["id"] == "openrouter")
            assert tool["status"] == "needs_sign_in"

    def test_cursor_ready_when_key_set(self):
        with patch.dict(os.environ, {"CURSOR_API_KEY": "cur_test_key_abc"}):
            data = _get_tools()
            tool = next(t for t in data["tools"] if t["id"] == "cursor")
            assert tool["status"] == "ready"
            assert "cur_test_key_abc" not in str(data)

    def test_openrouter_ready_from_catalog_flag_without_env_key(self):
        with patch("src.api.workspace_tools.build_catalog_payload", return_value={"openrouter_chat_ready": True}):
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
                data = _get_tools()
                tool = next(t for t in data["tools"] if t["id"] == "openrouter")
                assert tool["status"] == "ready"

    def test_github_ready_when_token_env_set(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_" + "x" * 36}):
            data = _get_tools()
            gh = next(t for t in data["tools"] if t["id"] == "github")
            assert gh["status"] == "ready"
            assert "ghp_" not in str(data)

    def test_comfyui_does_not_leak_config(self):
        data = _get_tools()
        tool = next(t for t in data["tools"] if t["id"] == "comfyui")
        assert tool["status"] in ("unknown", "not_found", "ready", "needs_sign_in")
        assert "HAM_COMFYUI" not in str(tool)


class TestResponseSchema:
    """Validate response shape matches expected schema."""

    def test_all_tools_have_required_fields(self):
        data = _get_tools()
        required_fields = {"id", "label", "category", "status", "enabled", "source", "connect_kind"}
        for tool in data["tools"]:
            for field in required_fields:
                assert field in tool, f"Tool {tool.get('id', '?')} missing field: {field}"

    def test_status_values_are_valid(self):
        valid_statuses = {"ready", "needs_sign_in", "not_found", "off", "error", "unknown"}
        data = _get_tools()
        for tool in data["tools"]:
            assert tool["status"] in valid_statuses, (
                f"{tool['id']} has invalid status: {tool['status']}"
            )

    def test_source_values_are_valid(self):
        valid_sources = {"cloud", "this_computer", "built_in", "unknown"}
        data = _get_tools()
        for tool in data["tools"]:
            assert tool["source"] in valid_sources, (
                f"{tool['id']} has invalid source: {tool['source']}"
            )

    def test_category_values_are_valid(self):
        valid_categories = {"coding", "cloud", "local_tool", "media", "repo", "deploy", "model"}
        data = _get_tools()
        for tool in data["tools"]:
            assert tool["category"] in valid_categories, (
                f"{tool['id']} has invalid category: {tool['category']}"
            )

    def test_connect_kind_values_are_valid(self):
        valid = {"none", "api_key", "access_token", "local_scan", "coming_soon"}
        data = _get_tools()
        for tool in data["tools"]:
            assert tool["connect_kind"] in valid


class TestConnectAndScanEndpoints:
    def test_connect_unknown_tool_404(self):
        r = client.post("/api/workspace/tools/nope_tool/connect", json={"api_key": "x"})
        assert r.status_code == 404

    def test_connect_openrouter_blocked_501(self):
        plausible = "sk-or-" + "v" * 30
        r = client.post("/api/workspace/tools/openrouter/connect", json={"api_key": plausible})
        assert r.status_code == 501
        body = r.json()
        assert "detail" in body
        assert plausible not in str(body)

    def test_cursor_connect_and_disconnect_roundtrip(self, tmp_path):
        cred_file = tmp_path / "cursor_credentials.json"
        env = {
            "HAM_CURSOR_CREDENTIALS_FILE": str(cred_file),
            "CURSOR_API_KEY": "",
        }
        with patch.dict(os.environ, env):
            plausible = "cur_" + "a" * 40
            r = client.post("/api/workspace/tools/cursor/connect", json={"api_key": plausible})
            assert r.status_code == 200
            data = r.json()
            assert plausible not in str(data)
            cur = next(t for t in data["tools"] if t["id"] == "cursor")
            assert cur["status"] == "ready"
            assert cur.get("credential_preview")

            r2 = client.post("/api/workspace/tools/cursor/disconnect")
            assert r2.status_code == 200
            data2 = r2.json()
            cur2 = next(t for t in data2["tools"] if t["id"] == "cursor")
            assert cur2["status"] == "needs_sign_in"

    def test_scan_endpoint_returns_tools(self):
        r = client.post("/api/workspace/tools/scan")
        assert r.status_code == 200
        body = r.json()
        assert "tools" in body
        assert len(body["tools"]) >= len(EXPECTED_TOOL_IDS)


class TestClaudeAgentSdkEntry:
    """Behavior of the new claude_agent_sdk Connected Tools entry."""

    def _claude_entry(self) -> dict:
        data = _get_tools()
        matches = [t for t in data["tools"] if t["id"] == "claude_agent_sdk"]
        assert len(matches) == 1, "claude_agent_sdk entry missing or duplicated"
        return matches[0]

    def test_entry_shape(self):
        tool = self._claude_entry()
        assert tool["label"] == "Claude Agent"
        assert tool["category"] == "coding"
        assert tool["source"] == "cloud"
        assert tool["connect_kind"] == "api_key"
        assert tool["safe_actions"] == ["check_status", "connect"]
        assert "plan" in tool["capabilities"]
        assert "edit_code" in tool["capabilities"]
        assert "version" in tool
        assert "service_smoke_available" in tool
        assert "service_smoke_hint" in tool

    def test_status_is_valid(self):
        valid = {"ready", "needs_sign_in", "not_found", "off", "error", "unknown"}
        assert self._claude_entry()["status"] in valid

    def test_safe_actions_include_connect_for_future_vault_ux(self):
        assert "connect" in self._claude_entry()["safe_actions"]
        assert "check_status" in self._claude_entry()["safe_actions"]

    def test_service_smoke_metadata_when_route_armed(self, monkeypatch):
        monkeypatch.setenv("HAM_CLAUDE_AGENT_SMOKE_ENABLED", "1")
        monkeypatch.setenv("HAM_CLAUDE_AGENT_SMOKE_TOKEN", "z" * 32)
        monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
        monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
        tool = self._claude_entry()
        assert tool["service_smoke_available"] is True
        assert tool["service_smoke_hint"]
        assert "HAM_CLAUDE_AGENT_SMOKE_TOKEN" not in str(tool)

    def test_setup_hint_for_not_found(self):
        from src.ham.worker_adapters.claude_agent_adapter import (
            ClaudeAgentWorkerCapabilities,
            ClaudeAgentWorkerReadiness,
        )

        readiness = ClaudeAgentWorkerReadiness(
            authenticated=False,
            sdk_available=False,
            status="unavailable",
            capabilities=ClaudeAgentWorkerCapabilities(),
        )
        with patch(
            "src.api.workspace_tools.check_claude_agent_readiness",
            return_value=readiness,
        ):
            tool = self._claude_entry()
            assert tool["status"] == "not_found"
            assert tool["setup_hint"] == "Claude isn't installed on this server yet."
            assert tool["version"] is None

    def test_setup_hint_for_needs_sign_in(self):
        from src.ham.worker_adapters.claude_agent_adapter import (
            ClaudeAgentWorkerCapabilities,
            ClaudeAgentWorkerReadiness,
        )

        readiness = ClaudeAgentWorkerReadiness(
            authenticated=False,
            sdk_available=True,
            sdk_version="0.1.2",
            status="needs_sign_in",
            capabilities=ClaudeAgentWorkerCapabilities(),
        )
        with patch(
            "src.api.workspace_tools.check_claude_agent_readiness",
            return_value=readiness,
        ):
            tool = self._claude_entry()
            assert tool["status"] == "needs_sign_in"
            assert "ANTHROPIC_API_KEY" in tool["setup_hint"]
            assert "Bedrock" in tool["setup_hint"] or "Vertex" in tool["setup_hint"]
            assert tool["version"] == "0.1.2"

    def test_setup_hint_for_ready(self):
        from src.ham.worker_adapters.claude_agent_adapter import (
            ClaudeAgentWorkerCapabilities,
            ClaudeAgentWorkerReadiness,
        )

        readiness = ClaudeAgentWorkerReadiness(
            authenticated=True,
            sdk_available=True,
            sdk_version="0.1.2",
            status="ready",
            capabilities=ClaudeAgentWorkerCapabilities(),
        )
        with patch(
            "src.api.workspace_tools.check_claude_agent_readiness",
            return_value=readiness,
        ):
            tool = self._claude_entry()
            assert tool["status"] == "ready"
            assert "full autonomous execution" in tool["setup_hint"].lower()
            assert tool["version"] == "0.1.2"

    def test_setup_hint_for_error(self):
        with patch(
            "src.api.workspace_tools.check_claude_agent_readiness",
            side_effect=RuntimeError("boom"),
        ):
            tool = self._claude_entry()
            assert tool["status"] == "error"
            assert "unexpected error" in tool["setup_hint"].lower()
            assert tool["version"] is None

    def test_connect_returns_501_secure_storage_not_ready(self):
        r = client.post(
            "/api/workspace/tools/claude_agent_sdk/connect",
            json={"api_key": "sk-ant-test-not-real"},
        )
        assert r.status_code == 501
        body = r.json()
        assert "SECURE_STORAGE_NOT_READY" in str(body).upper() or "secure" in str(body).lower()
        assert "sk-ant-test-not-real" not in str(body)

    def test_disconnect_returns_501(self):
        r = client.post("/api/workspace/tools/claude_agent_sdk/disconnect")
        assert r.status_code == 501

    def test_no_auth_values_in_response(self):
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-secret-not-real-12345",
            "ANTHROPIC_VERTEX_PROJECT_ID": "secret-vertex-project-id-99999",
        }
        with patch.dict(os.environ, env):
            data = _get_tools()
            raw = str(data)
            assert "sk-ant-secret-not-real-12345" not in raw
            assert "secret-vertex-project-id-99999" not in raw


class TestClaudeCodeEntryUnchanged:
    """Regression: the existing claude_code (local CLI) entry must not change."""

    def test_claude_code_id_label_source_unchanged(self):
        data = _get_tools()
        cc = next(t for t in data["tools"] if t["id"] == "claude_code")
        assert cc["label"] == "Claude Code"
        assert cc["connect_kind"] == "local_scan"
        assert cc["safe_actions"] == ["check_status"]
        # Source flips to "unknown" in cloud mode and "this_computer" otherwise;
        # both are fine. Just confirm it is NOT the new SDK source.
        assert cc["source"] in ("this_computer", "unknown")

    def test_claude_code_has_no_version(self):
        data = _get_tools()
        cc = next(t for t in data["tools"] if t["id"] == "claude_code")
        # The new optional field defaults to None for entries that don't set it.
        assert cc.get("version") is None


class TestVersionFieldDefaults:
    """The new optional `version` field must default to None for everything
    except the claude_agent_sdk entry (and only when it actually has one)."""

    def test_version_is_none_for_non_claude_entries(self):
        data = _get_tools()
        for tool in data["tools"]:
            if tool["id"] == "claude_agent_sdk":
                continue
            assert tool.get("version") is None, (
                f"{tool['id']} unexpectedly has version={tool.get('version')!r}"
            )


class TestScanInvalidatesClaudeCache:
    """The scan endpoint must invalidate the Claude SDK detection cache."""

    def test_scan_calls_reset_cache(self):
        with patch(
            "src.api.workspace_tools.reset_claude_agent_readiness_cache"
        ) as mock_reset:
            r = client.post("/api/workspace/tools/scan")
            assert r.status_code == 200
            assert mock_reset.called
