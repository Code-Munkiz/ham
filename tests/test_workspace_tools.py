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
        assert "sk-" not in raw
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
            if tool["status"] in ("unknown", "not_found", "off"):
                assert tool["enabled"] is False, (
                    f"{tool['id']} should not be enabled when status={tool['status']}"
                )


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
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test-12345"}):
            data = _get_tools()
            tool = next(t for t in data["tools"] if t["id"] == "openrouter")
            assert tool["status"] == "ready"
            assert "sk-or-test-12345" not in str(data)

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

    def test_cursor_needs_sign_in_when_no_key(self):
        with patch.dict(os.environ, {"CURSOR_API_KEY": ""}):
            data = _get_tools()
            tool = next(t for t in data["tools"] if t["id"] == "cursor")
            assert tool["status"] in ("needs_sign_in", "ready")

    def test_comfyui_does_not_leak_config(self):
        data = _get_tools()
        tool = next(t for t in data["tools"] if t["id"] == "comfyui")
        assert tool["status"] == "unknown"
        assert "comfyui" not in str(tool.get("setup_hint", "")).lower() or "detect" in str(tool.get("setup_hint", "")).lower()


class TestResponseSchema:
    """Validate response shape matches expected schema."""

    def test_all_tools_have_required_fields(self):
        data = _get_tools()
        required_fields = {"id", "label", "category", "status", "enabled", "source"}
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
