"""Tests for Cursor worker adapter readiness shell.

Validates:
- Cursor worker status appears in tool discovery
- Cursor off/disabled is not launchable
- Missing auth returns needs_sign_in
- Launch method is mock-only (readiness check only)
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.ham.worker_adapters.cursor_adapter import (
    CursorWorkerCapabilities,
    CursorWorkerReadiness,
    check_cursor_readiness,
    is_cursor_launchable,
)


class TestCursorWorkerCapabilities:
    """Capabilities are declared correctly."""

    def test_capabilities_are_stable(self):
        caps = CursorWorkerCapabilities()
        assert caps.can_plan is True
        assert caps.can_edit_code is True
        assert caps.can_run_tests is True
        assert caps.can_open_pr is True
        assert caps.requires_project_root is True
        assert caps.requires_auth is True
        assert caps.launch_mode == "cloud_agent"


class TestCursorWorkerReadiness:
    """Readiness detection without real API calls."""

    def test_needs_sign_in_when_no_key(self):
        with patch.dict(os.environ, {"CURSOR_API_KEY": ""}):
            with patch(
                "src.ham.worker_adapters.cursor_adapter.get_effective_cursor_api_key",
                return_value=None,
            ):
                readiness = check_cursor_readiness()
                assert readiness.status == "needs_sign_in"
                assert readiness.authenticated is False
                assert readiness.reason is not None

    def test_ready_when_key_present(self):
        with patch(
            "src.ham.worker_adapters.cursor_adapter.get_effective_cursor_api_key",
            return_value="cur_test_key",
        ):
            readiness = check_cursor_readiness()
            assert readiness.status == "ready"
            assert readiness.authenticated is True
            assert readiness.reason is None

    def test_ready_includes_capabilities(self):
        with patch(
            "src.ham.worker_adapters.cursor_adapter.get_effective_cursor_api_key",
            return_value="cur_test_key",
        ):
            readiness = check_cursor_readiness()
            assert readiness.capabilities.can_plan is True
            assert readiness.capabilities.can_edit_code is True

    def test_handles_credential_exception_gracefully(self):
        with patch(
            "src.ham.worker_adapters.cursor_adapter.get_effective_cursor_api_key",
            side_effect=RuntimeError("file not found"),
        ):
            readiness = check_cursor_readiness()
            assert readiness.status == "needs_sign_in"
            assert readiness.authenticated is False


class TestCursorLaunchability:
    """Launch gate is readiness-only in MVP."""

    def test_not_launchable_when_no_auth(self):
        readiness = CursorWorkerReadiness(
            authenticated=False,
            status="needs_sign_in",
        )
        assert is_cursor_launchable(readiness) is False

    def test_launchable_when_authenticated(self):
        readiness = CursorWorkerReadiness(
            authenticated=True,
            status="ready",
        )
        assert is_cursor_launchable(readiness) is True

    def test_not_launchable_when_unavailable(self):
        readiness = CursorWorkerReadiness(
            authenticated=False,
            status="unavailable",
        )
        assert is_cursor_launchable(readiness) is False

    def test_launchable_uses_check_when_none(self):
        with patch(
            "src.ham.worker_adapters.cursor_adapter.get_effective_cursor_api_key",
            return_value="key",
        ):
            assert is_cursor_launchable(None) is True

        with patch(
            "src.ham.worker_adapters.cursor_adapter.get_effective_cursor_api_key",
            return_value=None,
        ):
            assert is_cursor_launchable(None) is False


class TestToolDiscoveryIntegration:
    """Cursor appears correctly in workspace/tools endpoint."""

    def test_cursor_appears_in_tools_list(self):
        from fastapi.testclient import TestClient
        from src.api.server import app

        client = TestClient(app)
        resp = client.get("/api/workspace/tools")
        assert resp.status_code == 200
        tools = resp.json()["tools"]
        cursor_tools = [t for t in tools if t["id"] == "cursor"]
        assert len(cursor_tools) == 1
        cursor = cursor_tools[0]
        assert cursor["label"] == "Cursor"
        assert cursor["status"] in ("ready", "needs_sign_in", "unknown")
        assert "plan" in cursor["capabilities"]
        assert "edit_code" in cursor["capabilities"]
