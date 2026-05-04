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

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.server import fastapi_app
from src.ham.clerk_auth import HamActor

# ``server.app`` is the PNA middleware wrapper; use the FastAPI instance for routes + overrides.
client = TestClient(fastapi_app)

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
        required_fields = {"id", "label", "category", "status", "connection", "enabled", "source", "connect_kind"}
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

    def test_connection_values_are_valid(self):
        valid_conn = {"on", "off", "error"}
        data = _get_tools()
        for tool in data["tools"]:
            assert tool["connection"] in valid_conn, (
                f"{tool['id']} has invalid connection: {tool['connection']}"
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

    def test_connect_openrouter_ok_when_validation_passes(self, tmp_path, monkeypatch):
        cred_path = tmp_path / "wtc.json"
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(cred_path))
        plausible = "sk-or-" + "v" * 30
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            with patch(
                "src.api.workspace_tools.validate_openrouter_api_key",
                return_value=True,
            ):
                r = client.post("/api/workspace/tools/openrouter/connect", json={"api_key": plausible})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["status"] == "on"
        assert body.get("credential_preview")
        assert plausible not in str(body)

    def test_connect_openrouter_invalid_key_returns_400(self, tmp_path, monkeypatch):
        cred_path = tmp_path / "wtc.json"
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(cred_path))
        plausible = "sk-or-" + "v" * 30
        with patch(
            "src.api.workspace_tools.validate_openrouter_api_key",
            return_value=False,
        ):
            r = client.post("/api/workspace/tools/openrouter/connect", json={"api_key": plausible})
        assert r.status_code == 400
        body = r.json()
        assert body["ok"] is False
        assert body["status"] == "off"
        assert body["error_code"] == "INVALID_KEY"
        assert plausible not in str(body)

    def test_connect_github_ok_and_invalid(self, tmp_path, monkeypatch):
        cred_path = tmp_path / "wtc.json"
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(cred_path))
        tok = "ghp_" + "x" * 36
        with patch("src.api.workspace_tools.validate_github_token", return_value=True):
            r = client.post("/api/workspace/tools/github/connect", json={"access_token": tok})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert tok not in str(body)

        with patch("src.api.workspace_tools.validate_github_token", return_value=False):
            r2 = client.post("/api/workspace/tools/github/connect", json={"access_token": tok})
        assert r2.status_code == 400
        assert r2.json()["error_code"] == "INVALID_KEY"

    def test_connect_claude_agent_sdk_ok_and_invalid(self, tmp_path, monkeypatch):
        cred_path = tmp_path / "wtc.json"
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(cred_path))
        from src.ham.worker_adapters.claude_agent_adapter import (
            ClaudeAgentWorkerCapabilities,
            ClaudeAgentWorkerReadiness,
        )

        key = "sk-ant-api03-fake-not-real-" + "a" * 20
        ready_sdk = ClaudeAgentWorkerReadiness(
            authenticated=False,
            sdk_available=True,
            sdk_version="0.1.2",
            status="needs_sign_in",
            capabilities=ClaudeAgentWorkerCapabilities(),
        )
        with patch(
            "src.api.workspace_tools.check_claude_agent_readiness",
            return_value=ready_sdk,
        ):
            with patch(
                "src.api.workspace_tools.validate_anthropic_api_key",
                return_value=True,
            ):
                r = client.post(
                    "/api/workspace/tools/claude_agent_sdk/connect",
                    json={"api_key": key},
                )
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert key not in r.text

        with patch(
            "src.api.workspace_tools.check_claude_agent_readiness",
            return_value=ready_sdk,
        ):
            with patch(
                "src.api.workspace_tools.validate_anthropic_api_key",
                return_value=False,
            ):
                r2 = client.post(
                    "/api/workspace/tools/claude_agent_sdk/connect",
                    json={"api_key": key},
                )
        assert r2.status_code == 400
        assert r2.json()["error_code"] == "INVALID_KEY"

    def test_connect_claude_secret_write_through_on_cloud_when_flag_on(self, tmp_path, monkeypatch):
        cred_path = tmp_path / "wtc.json"
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(cred_path))
        monkeypatch.setenv("K_SERVICE", "ham-api")
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-proj-123")
        monkeypatch.setenv("HAM_CONNECTED_TOOLS_SECRET_MANAGER_WRITE_THROUGH", "1")
        from src.ham.worker_adapters.claude_agent_adapter import (
            ClaudeAgentWorkerCapabilities,
            ClaudeAgentWorkerReadiness,
        )

        key = "sk-ant-api03-" + "a" * 32
        ready_sdk = ClaudeAgentWorkerReadiness(
            authenticated=False,
            sdk_available=True,
            sdk_version="0.1.2",
            status="needs_sign_in",
            capabilities=ClaudeAgentWorkerCapabilities(),
        )
        mock_pub = MagicMock()
        mock_roll = MagicMock()
        with patch(
            "src.api.workspace_tools.check_claude_agent_readiness",
            return_value=ready_sdk,
        ):
            with patch(
                "src.api.workspace_tools.validate_anthropic_api_key",
                return_value=True,
            ):
                with patch(
                    "src.api.workspace_tools.publish_anthropic_api_key_to_secret_manager",
                    mock_pub,
                ):
                    with patch(
                        "src.api.workspace_tools.try_rollout_cloud_run_service_for_new_secrets",
                        mock_roll,
                    ):
                        r = client.post(
                            "/api/workspace/tools/claude_agent_sdk/connect",
                            json={"api_key": key},
                        )
        assert r.status_code == 200
        mock_pub.assert_called_once()
        mock_roll.assert_called_once()
        assert key not in r.text
        data = json.loads(cred_path.read_text(encoding="utf-8"))
        assert data.get("anthropic_api_key") == key

    def test_connect_claude_secret_write_through_not_used_locally_even_if_flag_on(
        self, tmp_path, monkeypatch
    ):
        cred_path = tmp_path / "wtc.json"
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(cred_path))
        monkeypatch.delenv("K_SERVICE", raising=False)
        monkeypatch.setenv("HAM_CONNECTED_TOOLS_SECRET_MANAGER_WRITE_THROUGH", "1")
        from src.ham.worker_adapters.claude_agent_adapter import (
            ClaudeAgentWorkerCapabilities,
            ClaudeAgentWorkerReadiness,
        )

        key = "sk-ant-api03-" + "b" * 32
        ready_sdk = ClaudeAgentWorkerReadiness(
            authenticated=False,
            sdk_available=True,
            sdk_version="0.1.2",
            status="needs_sign_in",
            capabilities=ClaudeAgentWorkerCapabilities(),
        )
        mock_pub = MagicMock()
        with patch(
            "src.api.workspace_tools.check_claude_agent_readiness",
            return_value=ready_sdk,
        ):
            with patch(
                "src.api.workspace_tools.validate_anthropic_api_key",
                return_value=True,
            ):
                with patch(
                    "src.api.workspace_tools.publish_anthropic_api_key_to_secret_manager",
                    mock_pub,
                ):
                    r = client.post(
                        "/api/workspace/tools/claude_agent_sdk/connect",
                        json={"api_key": key},
                    )
        assert r.status_code == 200
        mock_pub.assert_not_called()

    def test_connect_claude_secret_write_through_failure_does_not_persist_key(
        self, tmp_path, monkeypatch
    ):
        cred_path = tmp_path / "wtc.json"
        cred_path.write_text(
            '{"anthropic_api_key": "sk-ant-prior-only-not-returned"}\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(cred_path))
        monkeypatch.setenv("K_SERVICE", "ham-api")
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "p")
        monkeypatch.setenv("HAM_CONNECTED_TOOLS_SECRET_MANAGER_WRITE_THROUGH", "1")
        from src.ham.worker_adapters.claude_agent_adapter import (
            ClaudeAgentWorkerCapabilities,
            ClaudeAgentWorkerReadiness,
        )

        new_key = "sk-ant-api03-" + "c" * 32
        ready_sdk = ClaudeAgentWorkerReadiness(
            authenticated=False,
            sdk_available=True,
            sdk_version="0.1.2",
            status="needs_sign_in",
            capabilities=ClaudeAgentWorkerCapabilities(),
        )

        def boom(_k: str) -> None:
            raise RuntimeError("sm failed")

        with patch(
            "src.api.workspace_tools.check_claude_agent_readiness",
            return_value=ready_sdk,
        ):
            with patch(
                "src.api.workspace_tools.validate_anthropic_api_key",
                return_value=True,
            ):
                with patch(
                    "src.api.workspace_tools.publish_anthropic_api_key_to_secret_manager",
                    side_effect=boom,
                ):
                    r = client.post(
                        "/api/workspace/tools/claude_agent_sdk/connect",
                        json={"api_key": new_key},
                    )
        assert r.status_code == 503
        body = r.json()
        assert body["error_code"] == "DURABLE_STORE_FAILED"
        assert new_key not in json.dumps(body)
        data = json.loads(cred_path.read_text(encoding="utf-8"))
        assert data.get("anthropic_api_key") == "sk-ant-prior-only-not-returned"

    def test_connect_claude_invalid_skips_secret_publish(self, tmp_path, monkeypatch):
        cred_path = tmp_path / "wtc.json"
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(cred_path))
        monkeypatch.setenv("K_SERVICE", "ham-api")
        monkeypatch.setenv("HAM_CONNECTED_TOOLS_SECRET_MANAGER_WRITE_THROUGH", "1")
        from src.ham.worker_adapters.claude_agent_adapter import (
            ClaudeAgentWorkerCapabilities,
            ClaudeAgentWorkerReadiness,
        )

        key = "sk-ant-api03-" + "d" * 32
        ready_sdk = ClaudeAgentWorkerReadiness(
            authenticated=False,
            sdk_available=True,
            sdk_version="0.1.2",
            status="needs_sign_in",
            capabilities=ClaudeAgentWorkerCapabilities(),
        )
        mock_pub = MagicMock()
        with patch(
            "src.api.workspace_tools.check_claude_agent_readiness",
            return_value=ready_sdk,
        ):
            with patch(
                "src.api.workspace_tools.validate_anthropic_api_key",
                return_value=False,
            ):
                with patch(
                    "src.api.workspace_tools.publish_anthropic_api_key_to_secret_manager",
                    mock_pub,
                ):
                    r = client.post(
                        "/api/workspace/tools/claude_agent_sdk/connect",
                        json={"api_key": key},
                    )
        assert r.status_code == 400
        mock_pub.assert_not_called()

    def test_connect_claude_agent_sdk_requires_sdk(self, monkeypatch):
        from src.ham.worker_adapters.claude_agent_adapter import (
            ClaudeAgentWorkerCapabilities,
            ClaudeAgentWorkerReadiness,
        )

        no_sdk = ClaudeAgentWorkerReadiness(
            authenticated=False,
            sdk_available=False,
            sdk_version=None,
            status="unavailable",
            capabilities=ClaudeAgentWorkerCapabilities(),
        )
        with patch(
            "src.api.workspace_tools.check_claude_agent_readiness",
            return_value=no_sdk,
        ):
            r = client.post(
                "/api/workspace/tools/claude_agent_sdk/connect",
                json={"api_key": "sk-ant-" + "a" * 40},
            )
        assert r.status_code == 400
        assert r.json()["error_code"] == "SETUP_REQUIRED"

    def test_disconnect_openrouter_clears_store(self, tmp_path, monkeypatch):
        cred_path = tmp_path / "wtc.json"
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(cred_path))
        cred_path.write_text(
            '{"openrouter_api_key": "sk-or-secret-not-in-response"}\n',
            encoding="utf-8",
        )
        r = client.post("/api/workspace/tools/openrouter/disconnect")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "sk-or-secret" not in str(body)

    def test_cursor_connect_and_disconnect_roundtrip(self, tmp_path):
        cred_file = tmp_path / "cursor_credentials.json"
        env = {
            "HAM_CURSOR_CREDENTIALS_FILE": str(cred_file),
            "CURSOR_API_KEY": "",
        }
        with patch.dict(os.environ, env):
            plausible = "cur_" + "a" * 40
            with patch(
                "src.api.workspace_tools.validate_cursor_api_key",
                return_value=True,
            ):
                r = client.post("/api/workspace/tools/cursor/connect", json={"api_key": plausible})
            assert r.status_code == 200
            body = r.json()
            assert body["ok"] is True
            assert plausible not in str(body)
            assert body.get("credential_preview")

            tools = client.get("/api/workspace/tools").json()["tools"]
            cur = next(t for t in tools if t["id"] == "cursor")
            assert cur["status"] == "ready"
            assert cur.get("credential_preview")

            r2 = client.post("/api/workspace/tools/cursor/disconnect")
            assert r2.status_code == 200
            assert r2.json()["ok"] is True

            tools2 = client.get("/api/workspace/tools").json()["tools"]
            cur2 = next(t for t in tools2 if t["id"] == "cursor")
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
        assert tool["safe_actions"] == ["check_status", "connect", "disconnect"]
        assert "plan" in tool["capabilities"]
        assert "edit_code" in tool["capabilities"]
        assert "version" in tool
        assert "connection" in tool
        assert tool["connection"] in ("on", "off", "error")

    def test_status_is_valid(self):
        valid = {"ready", "needs_sign_in", "not_found", "off", "error", "unknown"}
        assert self._claude_entry()["status"] in valid

    def test_safe_actions_include_connect(self):
        assert "connect" in self._claude_entry()["safe_actions"]
        assert "check_status" in self._claude_entry()["safe_actions"]

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
            assert "Install Claude Agent" in tool["setup_hint"]
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
            assert "Paste your Anthropic API key" in tool["setup_hint"]
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
            assert tool["setup_hint"] == "Claude Agent is connected."
            assert tool["version"] == "0.1.2"

    def test_setup_hint_for_error(self):
        with patch(
            "src.api.workspace_tools.check_claude_agent_readiness",
            side_effect=RuntimeError("boom"),
        ):
            tool = self._claude_entry()
            assert tool["status"] == "error"
            assert "something went wrong" in tool["setup_hint"].lower()
            assert tool["version"] is None

    def test_disconnect_clears_stored_key(self, tmp_path, monkeypatch):
        cred_path = tmp_path / "wtc.json"
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(cred_path))
        cred_path.write_text(
            '{"anthropic_api_key": "sk-ant-secret-not-in-body"}\n',
            encoding="utf-8",
        )
        r = client.post("/api/workspace/tools/claude_agent_sdk/disconnect")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "sk-ant-secret-not-in-body" not in str(body)

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


class TestClaudeAgentSdkMissionRoute:
    """POST /api/workspace/tools/claude_agent_sdk/mission — Clerk + credential gate."""

    def _actor(self) -> HamActor:
        return HamActor(
            user_id="user_mission_test",
            org_id=None,
            session_id="sess_mission",
            email="mission-test@example.com",
            permissions=frozenset(),
            org_role=None,
            raw_permission_claim=None,
        )

    def test_mission_401_without_clerk_when_auth_required(self, monkeypatch):
        monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "1")
        monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        async def _no_actor() -> None:
            return None

        fastapi_app.dependency_overrides[get_ham_clerk_actor] = _no_actor
        try:
            r = client.post("/api/workspace/tools/claude_agent_sdk/mission")
        finally:
            fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)

        assert r.status_code == 401
        body = r.json()
        assert body["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"

    def test_mission_smoke_token_does_not_bypass_clerk(self, monkeypatch):
        monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "1")
        monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
        monkeypatch.setenv("HAM_CLAUDE_AGENT_SMOKE_ENABLED", "1")
        monkeypatch.setenv("HAM_CLAUDE_AGENT_SMOKE_TOKEN", "x" * 32)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        async def _no_actor() -> None:
            return None

        fastapi_app.dependency_overrides[get_ham_clerk_actor] = _no_actor
        try:
            r = client.post(
                "/api/workspace/tools/claude_agent_sdk/mission",
                headers={"X-HAM-SMOKE-TOKEN": "x" * 32},
            )
        finally:
            fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)

        assert r.status_code == 401

    def test_mission_400_connect_required_with_session_no_key(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "1")
        monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(tmp_path / "empty.json"))
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        cred = tmp_path / "empty.json"
        cred.write_text("{}\n", encoding="utf-8")

        async def _actor_dep() -> HamActor:
            return self._actor()

        fastapi_app.dependency_overrides[get_ham_clerk_actor] = _actor_dep
        try:
            r = client.post("/api/workspace/tools/claude_agent_sdk/mission")
        finally:
            fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)

        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "CONNECT_CLAUDE_AGENT_REQUIRED"
        assert "Connect Claude Agent first" in r.json()["detail"]["message"]

    def test_mission_200_calls_adapter_when_authed_and_key_present(
        self, tmp_path, monkeypatch
    ):
        from src.ham.worker_adapters.claude_agent_adapter import ClaudeAgentMissionResult

        monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "1")
        monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
        monkeypatch.setenv(
            "HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(tmp_path / "wtc.json")
        )
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        cred = tmp_path / "wtc.json"
        cred.write_text(
            '{"anthropic_api_key": "sk-ant-api03-connect-tools-test-not-real"}\n',
            encoding="utf-8",
        )

        fake = ClaudeAgentMissionResult(
            ok=True,
            mission_ok=True,
            worker="claude_agent_sdk",
            mission_type="non_mutating_review",
            result_text='{"mission_status":"ok"}',
            parsed_result={"mission_status": "ok", "worker": "claude_agent_sdk"},
            duration_ms=12,
            safety_mode="plan",
            blocker=None,
        )

        async def _actor_dep() -> HamActor:
            return self._actor()

        fastapi_app.dependency_overrides[get_ham_clerk_actor] = _actor_dep
        try:
            with patch(
                "src.api.workspace_tools.run_claude_agent_sdk_mission",
                new=AsyncMock(return_value=fake),
            ):
                r = client.post("/api/workspace/tools/claude_agent_sdk/mission")
        finally:
            fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)

        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["mission_ok"] is True
        assert body["worker"] == "claude_agent_sdk"
        assert "sk-ant-api03" not in str(body)


class TestClaudeCodeEntryRegression:
    """Regression: the existing claude_code (local CLI) entry must not change."""

    def test_claude_code_id_label_source_unchanged(self):
        data = _get_tools()
        cc = next(t for t in data["tools"] if t["id"] == "claude_code")
        assert cc["label"] == "Claude Code"
        assert cc["connect_kind"] == "local_scan"
        assert cc["safe_actions"] == ["check_status"]
        assert cc["source"] in ("this_computer", "unknown")

    def test_claude_code_has_no_version(self):
        data = _get_tools()
        cc = next(t for t in data["tools"] if t["id"] == "claude_code")
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
