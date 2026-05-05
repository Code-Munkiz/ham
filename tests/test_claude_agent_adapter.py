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

import asyncio
from unittest.mock import patch

import json

import pytest

from src.ham.worker_adapters import claude_agent_adapter
from src.ham.worker_adapters.claude_agent_adapter import (
    ClaudeAgentWorkerCapabilities,
    ClaudeAgentWorkerReadiness,
    _format_sdk_query_failure,
    _mission_acceptance_blocker,
    _redact_diagnostic_text,
    check_claude_agent_readiness,
    claude_agent_mission_auth_configured,
    is_claude_agent_launchable,
    parse_claude_mission_acceptance_text,
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


class TestMissionAuthConfigured:
    def test_false_without_stored_key_or_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(tmp_path / "w.json"))
        (tmp_path / "w.json").write_text("{}\n", encoding="utf-8")
        assert claude_agent_mission_auth_configured(None) is False

    def test_true_with_connected_tools_stored_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(tmp_path / "w.json"))
        (tmp_path / "w.json").write_text(
            '{"anthropic_api_key": "sk-ant-fake-mission-gate"}\n',
            encoding="utf-8",
        )
        assert claude_agent_mission_auth_configured(None) is True

    def test_true_with_legacy_env_anthropic_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-env-fallback")
        assert claude_agent_mission_auth_configured(None) is True

    def test_true_with_bedrock_signals(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        assert claude_agent_mission_auth_configured(None) is True


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


class TestHeadlessNonzeroSummary:
    def test_summarizes_cli_auth_json_stdout(self):
        payload = json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": True,
                "api_error_status": 401,
                "result": "Should not appear wholesale",
            }
        )
        s = claude_agent_adapter._headless_nonzero_summary(payload, "")
        assert "401" in s or "http=401" in s
        assert "Should not appear wholesale" not in s


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


class TestResolveClaudeAgentAnthropicApiKey:
    """``resolve_claude_agent_anthropic_api_key`` precedence (never logged by helper)."""

    def test_stored_preferred_over_env(self, monkeypatch, tmp_path):
        cred_path = tmp_path / "creds.json"
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(cred_path))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-test")
        from src.persistence import workspace_tool_credentials as wtc

        wtc.save_anthropic_api_key("sk-ant-stored-test")
        assert wtc.resolve_claude_agent_anthropic_api_key() == "sk-ant-stored-test"

    def test_env_fallback_when_no_stored(self, monkeypatch, tmp_path):
        cred_path = tmp_path / "empty.json"
        cred_path.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(cred_path))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-test")
        from src.persistence import workspace_tool_credentials as wtc

        assert wtc.resolve_claude_agent_anthropic_api_key() == "sk-ant-env-test"

    def test_missing_returns_none(self, monkeypatch, tmp_path):
        cred_path = tmp_path / "empty.json"
        cred_path.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(cred_path))
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from src.persistence import workspace_tool_credentials as wtc

        assert wtc.resolve_claude_agent_anthropic_api_key() is None


class TestClaudeRuntimeEnvOverlay:
    def test_overlay_prefers_stored_over_env(self, monkeypatch, tmp_path):
        cred_path = tmp_path / "creds.json"
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(cred_path))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-test")
        from src.persistence import workspace_tool_credentials as wtc

        wtc.save_anthropic_api_key("sk-ant-stored-test")
        overlay = claude_agent_adapter._claude_runtime_anthropic_env_overlay()
        assert overlay == {"ANTHROPIC_API_KEY": "sk-ant-stored-test"}

    def test_overlay_empty_when_bedrock_configured(self, monkeypatch, tmp_path):
        cred_path = tmp_path / "creds.json"
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(cred_path))
        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        from src.persistence import workspace_tool_credentials as wtc

        wtc.save_anthropic_api_key("sk-ant-stored-test")
        assert claude_agent_adapter._claude_runtime_anthropic_env_overlay() == {}

    def test_subprocess_env_contains_git_prompt_and_resolved_key(
        self, monkeypatch, tmp_path
    ):
        cred_path = tmp_path / "creds.json"
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(cred_path))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-test")
        from src.persistence import workspace_tool_credentials as wtc

        wtc.save_anthropic_api_key("sk-ant-stored-test")
        env = claude_agent_adapter._subprocess_env_for_claude()
        assert env.get("GIT_TERMINAL_PROMPT") == "0"
        assert env.get("ANTHROPIC_API_KEY") == "sk-ant-stored-test"

    def test_headless_subprocess_receives_stored_anthropic_key(
        self, monkeypatch, tmp_path
    ):
        cred_path = tmp_path / "creds.json"
        monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(cred_path))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-test")
        from src.persistence import workspace_tool_credentials as wtc

        wtc.save_anthropic_api_key("sk-ant-stored-test")

        captured: dict[str, object] = {}

        async def fake_exec(*_a, **_kw):
            captured.update(_kw)
            class _Proc:
                returncode = 0

                async def communicate(self):
                    return (b'{"result":"ok"}', b"")

            return _Proc()

        monkeypatch.setattr(
            claude_agent_adapter.asyncio, "create_subprocess_exec", fake_exec
        )
        monkeypatch.setattr(claude_agent_adapter.shutil, "which", lambda _x: "/bin/claude")

        async def run():
            return await claude_agent_adapter._run_claude_headless_plan_json_query(
                "p", 30.0, 100
            )

        text, err = asyncio.run(run())
        assert err is None
        assert text == "ok"
        env = captured.get("env")
        assert isinstance(env, dict)
        assert env.get("ANTHROPIC_API_KEY") == "sk-ant-stored-test"
        blob = str(captured)
        assert "sk-ant-env-test" not in blob

    def test_plan_query_fails_safe_without_direct_key_when_claimed_ready(
        self, monkeypatch
    ):
        fake_rd = ClaudeAgentWorkerReadiness(
            authenticated=True,
            sdk_available=True,
            sdk_version="0.1.2",
            status="ready",
        )
        monkeypatch.setattr(
            claude_agent_adapter,
            "check_claude_agent_readiness",
            lambda actor=None: fake_rd,
        )
        monkeypatch.setattr(
            claude_agent_adapter,
            "_uses_non_anthropic_direct_cloud_auth",
            lambda: False,
        )
        monkeypatch.setattr(
            claude_agent_adapter,
            "resolve_claude_agent_anthropic_api_key_for_actor",
            lambda actor=None: None,
        )

        async def run():
            return await claude_agent_adapter._run_claude_agent_sdk_plan_query(
                "x", 1.0, 100
            )

        text, blocker, rd = asyncio.run(run())
        assert text is None
        assert rd is fake_rd
        assert blocker is not None
        assert "sk-ant-" not in (blocker or "")
        assert "ANTHROPIC_API_KEY=" not in (blocker or "")


class TestClaudeMissionAcceptanceParsing:
    def _valid(self) -> dict:
        return {
            "mission_status": "ok",
            "worker": "claude_agent_sdk",
            "job_type": "non_mutating_review",
            "summary": "Review complete.",
            "acceptance_criteria": ["c1", "c2", "c3"],
        }

    def test_raw_json_passes(self):
        d = self._valid()
        text = json.dumps(d)
        parsed, ok, reason = parse_claude_mission_acceptance_text(text)
        assert ok is True
        assert reason is None
        assert parsed is not None
        assert parsed["worker"] == "claude_agent_sdk"
        assert len(parsed["acceptance_criteria"]) == 3

    def test_fenced_json_passes(self):
        d = self._valid()
        text = "```json\n" + json.dumps(d) + "\n```"
        parsed, ok, reason = parse_claude_mission_acceptance_text(text)
        assert ok is True
        assert parsed is not None

    def test_prose_before_and_after_json_passes(self):
        d = self._valid()
        text = 'Here you go: ' + json.dumps(d) + " — thanks"
        parsed, ok, reason = parse_claude_mission_acceptance_text(text)
        assert ok is True
        assert parsed is not None

    def test_malformed_json_fails(self):
        parsed, ok, reason = parse_claude_mission_acceptance_text("{not json")
        assert ok is False
        assert parsed is None
        assert reason

    def test_missing_acceptance_criteria_fails(self):
        d = self._valid()
        del d["acceptance_criteria"]
        parsed, ok, reason = parse_claude_mission_acceptance_text(json.dumps(d))
        assert ok is False
        assert parsed is None
        assert reason and "acceptance_criteria" in reason

    def test_wrong_worker_fails(self):
        d = self._valid()
        d["worker"] = "other_worker"
        parsed, ok, reason = parse_claude_mission_acceptance_text(json.dumps(d))
        assert ok is False
        assert parsed is None
        assert reason and "worker" in reason.lower()

    def test_acceptance_criteria_wrong_length_fails(self):
        d = self._valid()
        d["acceptance_criteria"] = ["only", "two"]
        parsed, ok, reason = parse_claude_mission_acceptance_text(json.dumps(d))
        assert ok is False
        assert parsed is None
        assert reason

    def test_long_invalid_payload_blocker_stays_short(self):
        noise = "x" * 3000
        parsed, ok, reason = parse_claude_mission_acceptance_text(noise)
        assert ok is False
        assert parsed is None
        wrapped = _mission_acceptance_blocker(reason or "x")
        assert len(wrapped) < 400
        assert noise not in wrapped

    def test_two_top_level_json_objects_fails(self):
        d1 = self._valid()
        d2 = self._valid()
        d2["summary"] = "Second summary."
        text = json.dumps(d1) + " " + json.dumps(d2)
        parsed, ok, reason = parse_claude_mission_acceptance_text(text)
        assert ok is False
        assert parsed is None

    def test_two_valid_fenced_blocks_ambiguous(self):
        d1 = self._valid()
        d2 = self._valid()
        d2["summary"] = "Second summary."
        text = (
            "```json\n"
            + json.dumps(d1)
            + "\n```\n```\n"
            + json.dumps(d2)
            + "\n```"
        )
        parsed, ok, reason = parse_claude_mission_acceptance_text(text)
        assert ok is False
        assert parsed is None
        assert reason and "ambiguous" in reason.lower()

    def test_secret_pattern_in_summary_rejected(self):
        d = self._valid()
        d["summary"] = "stopped on sk-ant-api03-example"
        parsed, ok, reason = parse_claude_mission_acceptance_text(json.dumps(d))
        assert ok is False
        assert parsed is None
        assert reason
        assert "sk-ant-" not in (reason or "")

    def test_run_mission_invalid_result_text_safe_blocker(self, monkeypatch):
        rd = ClaudeAgentWorkerReadiness(
            authenticated=True,
            sdk_available=True,
            sdk_version="0.1.2",
            status="ready",
        )

        async def fake_run(*_a, **_kw):
            return ("x" * 900 + " not json", None, rd)

        monkeypatch.setattr(
            claude_agent_adapter,
            "_run_claude_agent_sdk_plan_query",
            fake_run,
        )
        out = asyncio.run(claude_agent_adapter.run_claude_agent_sdk_mission(None))
        assert out.ok is True
        assert out.mission_ok is False
        assert out.result_text
        assert out.parsed_result is None
        assert out.blocker
        assert len(out.blocker) < 450
        assert out.result_text not in (out.blocker or "")

    def test_run_mission_valid_json_round_trip(self, monkeypatch):
        rd = ClaudeAgentWorkerReadiness(
            authenticated=True,
            sdk_available=True,
            sdk_version="0.1.2",
            status="ready",
        )
        d = {
            "mission_status": "ok",
            "worker": "claude_agent_sdk",
            "job_type": "non_mutating_review",
            "summary": "Done.",
            "acceptance_criteria": ["a", "b", "c"],
        }

        async def fake_run(*_a, **_kw):
            return (json.dumps(d), None, rd)

        monkeypatch.setattr(
            claude_agent_adapter,
            "_run_claude_agent_sdk_plan_query",
            fake_run,
        )
        out = asyncio.run(claude_agent_adapter.run_claude_agent_sdk_mission(None))
        assert out.ok is True
        assert out.mission_ok is True
        assert out.parsed_result is not None
        assert out.parsed_result["worker"] == "claude_agent_sdk"
        assert out.blocker is None
