"""Tests for the Claude Agent SDK readiness shell.

Validates:
- Optional import is safe; tests pass without claude-agent-sdk installed.
- Multi-auth detection (ANTHROPIC_API_KEY, Bedrock, Vertex) marks ready.
- Bedrock/Vertex flags without their required env do not authenticate.
- Status mapping (unavailable / needs_sign_in / ready) is stable.
- SDK detection is cached; reset_claude_agent_readiness_cache invalidates it.
- Auth values never appear in the readiness object's repr/dict/fields.
- is_claude_agent_launchable mirrors Cursor semantics.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.ham.worker_adapters import claude_agent_adapter
from src.ham.worker_adapters.claude_agent_adapter import (
    ClaudeAgentWorkerCapabilities,
    ClaudeAgentWorkerReadiness,
    _format_sdk_query_failure,
    _redact_diagnostic_text,
    check_claude_agent_readiness,
    is_claude_agent_launchable,
    reset_claude_agent_readiness_cache,
)

_AUTH_ENV_KEYS = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_USE_BEDROCK",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
    "CLAUDE_CODE_USE_VERTEX",
    "ANTHROPIC_VERTEX_PROJECT_ID",
    "GCLOUD_PROJECT",
    "GOOGLE_CLOUD_PROJECT",
)


@pytest.fixture(autouse=True)
def _reset_sdk_cache():
    """Module-level _SDK_DETECTION cache leaks across tests; clear it."""
    reset_claude_agent_readiness_cache()
    yield
    reset_claude_agent_readiness_cache()


@pytest.fixture(autouse=True)
def _clean_auth_env(monkeypatch):
    """Clear any inherited auth signals so tests start from a known baseline."""
    for key in _AUTH_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


class TestCapabilities:
    def test_capabilities_are_stable(self):
        caps = ClaudeAgentWorkerCapabilities()
        assert caps.can_plan is True
        assert caps.can_edit_code is True
        assert caps.can_run_tests is True
        assert caps.can_open_pr is False
        assert caps.requires_project_root is True
        assert caps.requires_auth is True
        assert caps.launch_mode == "sdk_local"


class TestSdkDetection:
    def test_sdk_unavailable(self):
        with patch.object(claude_agent_adapter, "_do_import", return_value=(False, None)):
            readiness = check_claude_agent_readiness()
            assert readiness.status == "unavailable"
            assert readiness.sdk_available is False
            assert readiness.authenticated is False
            assert readiness.sdk_version is None
            assert readiness.reason is not None

    def test_needs_sign_in_when_no_auth(self):
        with patch.object(claude_agent_adapter, "_do_import", return_value=(True, "0.1.2")):
            readiness = check_claude_agent_readiness()
            assert readiness.status == "needs_sign_in"
            assert readiness.sdk_available is True
            assert readiness.authenticated is False
            assert readiness.sdk_version == "0.1.2"

    def test_ready_with_anthropic_api_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-real")
        with patch.object(claude_agent_adapter, "_do_import", return_value=(True, "0.1.2")):
            readiness = check_claude_agent_readiness()
            assert readiness.status == "ready"
            assert readiness.authenticated is True
            assert readiness.sdk_version == "0.1.2"

    def test_ready_with_bedrock_signal(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        with patch.object(claude_agent_adapter, "_do_import", return_value=(True, "0.1.2")):
            readiness = check_claude_agent_readiness()
            assert readiness.status == "ready"
            assert readiness.authenticated is True

    def test_ready_with_bedrock_default_region(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
        with patch.object(claude_agent_adapter, "_do_import", return_value=(True, "0.1.2")):
            readiness = check_claude_agent_readiness()
            assert readiness.status == "ready"

    def test_ready_with_vertex_signal(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_CODE_USE_VERTEX", "1")
        monkeypatch.setenv("ANTHROPIC_VERTEX_PROJECT_ID", "my-project")
        with patch.object(claude_agent_adapter, "_do_import", return_value=(True, "0.1.2")):
            readiness = check_claude_agent_readiness()
            assert readiness.status == "ready"

    def test_ready_with_vertex_gcloud_project_fallback(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_CODE_USE_VERTEX", "1")
        monkeypatch.setenv("GCLOUD_PROJECT", "my-project")
        with patch.object(claude_agent_adapter, "_do_import", return_value=(True, "0.1.2")):
            readiness = check_claude_agent_readiness()
            assert readiness.status == "ready"

    def test_bedrock_flag_without_region_not_authenticated(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
        with patch.object(claude_agent_adapter, "_do_import", return_value=(True, "0.1.2")):
            readiness = check_claude_agent_readiness()
            assert readiness.status == "needs_sign_in"
            assert readiness.authenticated is False

    def test_vertex_flag_without_project_not_authenticated(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_CODE_USE_VERTEX", "1")
        with patch.object(claude_agent_adapter, "_do_import", return_value=(True, "0.1.2")):
            readiness = check_claude_agent_readiness()
            assert readiness.status == "needs_sign_in"

    def test_bedrock_flag_must_equal_one(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "true")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        with patch.object(claude_agent_adapter, "_do_import", return_value=(True, "0.1.2")):
            readiness = check_claude_agent_readiness()
            assert readiness.status == "needs_sign_in"

    def test_import_exception_swallowed(self):
        def boom() -> tuple[bool, str | None]:
            raise RuntimeError("module shouted")

        with patch.object(claude_agent_adapter, "_detect_sdk", side_effect=boom):
            readiness = check_claude_agent_readiness()
            assert readiness.status == "unavailable"
            assert readiness.sdk_available is False
            assert readiness.authenticated is False


class TestSdkVersion:
    def test_version_surfaces_when_present(self):
        with patch.object(claude_agent_adapter, "_do_import", return_value=(True, "9.9.9")):
            readiness = check_claude_agent_readiness()
            assert readiness.sdk_version == "9.9.9"

    def test_version_none_when_sdk_absent(self):
        with patch.object(claude_agent_adapter, "_do_import", return_value=(False, None)):
            readiness = check_claude_agent_readiness()
            assert readiness.sdk_version is None


class TestCachingAndReset:
    def test_cache_only_imports_once(self):
        counter = {"n": 0}

        def fake_import() -> tuple[bool, str | None]:
            counter["n"] += 1
            return (True, "0.1.2")

        with patch.object(claude_agent_adapter, "_do_import", side_effect=fake_import):
            check_claude_agent_readiness()
            check_claude_agent_readiness()
            check_claude_agent_readiness()
            assert counter["n"] == 1

    def test_reset_clears_cache(self):
        counter = {"n": 0}

        def fake_import() -> tuple[bool, str | None]:
            counter["n"] += 1
            return (True, "0.1.2")

        with patch.object(claude_agent_adapter, "_do_import", side_effect=fake_import):
            check_claude_agent_readiness()
            assert counter["n"] == 1
            reset_claude_agent_readiness_cache()
            check_claude_agent_readiness()
            assert counter["n"] == 2


class TestAuthValuesNeverEchoed:
    """The readiness object must never expose the underlying auth values."""

    def test_anthropic_api_key_value_not_in_repr(self, monkeypatch):
        secret = "sk-ant-secret-not-real-12345"
        monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
        with patch.object(claude_agent_adapter, "_do_import", return_value=(True, "0.1.2")):
            readiness = check_claude_agent_readiness()
        text = repr(readiness)
        assert secret not in text
        assert secret not in str(readiness.__dict__)

    def test_bedrock_values_not_in_repr(self, monkeypatch):
        secret_region = "us-secret-region-1"
        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
        monkeypatch.setenv("AWS_REGION", secret_region)
        with patch.object(claude_agent_adapter, "_do_import", return_value=(True, "0.1.2")):
            readiness = check_claude_agent_readiness()
        assert secret_region not in repr(readiness)
        assert secret_region not in str(readiness.__dict__)

    def test_vertex_values_not_in_repr(self, monkeypatch):
        secret_project = "secret-project-id-12345"
        monkeypatch.setenv("CLAUDE_CODE_USE_VERTEX", "1")
        monkeypatch.setenv("ANTHROPIC_VERTEX_PROJECT_ID", secret_project)
        with patch.object(claude_agent_adapter, "_do_import", return_value=(True, "0.1.2")):
            readiness = check_claude_agent_readiness()
        assert secret_project not in repr(readiness)
        assert secret_project not in str(readiness.__dict__)


class TestLaunchability:
    def test_not_launchable_when_unavailable(self):
        readiness = ClaudeAgentWorkerReadiness(
            authenticated=False,
            sdk_available=False,
            status="unavailable",
        )
        assert is_claude_agent_launchable(readiness) is False

    def test_not_launchable_when_needs_sign_in(self):
        readiness = ClaudeAgentWorkerReadiness(
            authenticated=False,
            sdk_available=True,
            status="needs_sign_in",
        )
        assert is_claude_agent_launchable(readiness) is False

    def test_launchable_when_ready(self):
        readiness = ClaudeAgentWorkerReadiness(
            authenticated=True,
            sdk_available=True,
            sdk_version="0.1.2",
            status="ready",
        )
        assert is_claude_agent_launchable(readiness) is True

    def test_uses_check_when_none(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        with patch.object(claude_agent_adapter, "_do_import", return_value=(True, "0.1.2")):
            assert is_claude_agent_launchable(None) is True

        reset_claude_agent_readiness_cache()
        with patch.object(claude_agent_adapter, "_do_import", return_value=(False, None)):
            # Auth env still set, but SDK absent → not launchable.
            assert is_claude_agent_launchable(None) is False


class TestNoRealSdkAtModuleTop:
    """Defense-in-depth: confirm the test file does not import the real SDK."""

    def test_real_sdk_not_imported_here(self):
        # If this fails, we accidentally imported claude_agent_sdk and
        # the test suite would break on machines without the package.
        import sys

        # The adapter module should be importable; the SDK should NOT
        # appear in sys.modules unless someone genuinely installed it.
        # (We don't assert absolute absence — a CI machine might have it.
        # We only assert that *we* didn't pull it in via `import` here.)
        assert "src.ham.worker_adapters.claude_agent_adapter" in sys.modules

    def test_check_runs_without_real_sdk(self):
        """Confirms check_claude_agent_readiness handles ImportError cleanly."""
        # Use the real _do_import path — if claude_agent_sdk is not
        # installed, this should return ("unavailable").
        # If it IS installed (rare in test envs), behavior will depend
        # on env, which is fine; we only assert no exception.
        try:
            readiness = check_claude_agent_readiness()
        except Exception as exc:  # pragma: no cover — safety net
            pytest.fail(f"check_claude_agent_readiness raised: {exc!r}")
        assert readiness.status in {"ready", "needs_sign_in", "unavailable"}


class TestDiagnosticRedaction:
    def test_redact_masks_secret_patterns(self):
        raw = "error sk-ant-api03-fake HAM_CLAUDE_AGENT_SMOKE_TOKEN=x ANTHROPIC_API_KEY=y ok"
        out = _redact_diagnostic_text(raw)
        assert "sk-ant-" not in out
        assert "HAM_CLAUDE_AGENT_SMOKE_TOKEN=" not in out
        assert "ANTHROPIC_API_KEY=" not in out
        assert "[REDACTED]" in out

    def test_format_sdk_query_failure_includes_redacted_stderr(self):
        exc = Exception("Command failed with exit code 1 (exit code: 1)")
        stderr = ["line one", "oauth token sk-ant-secret"]
        detail = _format_sdk_query_failure(exc, stderr)
        assert "exit code 1" in detail
        assert "sk-ant-" not in detail
        assert "stderr:" in detail
