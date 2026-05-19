"""Tests for src/ham/builder_verifier.py — Phase 1 #5 (Tier 1 #19).

Covers: pass/fail outcome mapping, error envelope content, fake harness.
"""

from __future__ import annotations

import pytest

from src.ham.builder_error_codes import STEP_VERIFICATION_FAILED
from src.ham.builder_plan import Plan, Step
from src.ham.builder_verifier import (
    HarnessRunnerProtocol,
    VerifierOutcome,
    get_harness_runner,
    set_harness_runner_for_tests,
    verify,
)

_PREVIEW_URL = "http://localhost:3000"


def _simple_plan() -> Plan:
    return Plan(
        plan_id="pln_verifier_test",
        workspace_id="ws_v",
        project_id="proj_v",
        user_message="Test",
        planner_confidence="high",
        steps=[Step(step_id="stp_1", title="Add button", description="Create a button")],
    )


class _PassRunner:
    def run(self, test_source: str, *, timeout_seconds: int) -> tuple[int, str]:
        return 0, "1 passed"


class _FailRunner:
    def __init__(self, stdout: str = "Error: expect(page.getByRole('button')).toBeVisible()") -> None:
        self._stdout = stdout

    def run(self, test_source: str, *, timeout_seconds: int) -> tuple[int, str]:
        return 1, self._stdout


@pytest.fixture(autouse=True)
def _reset_runner():
    set_harness_runner_for_tests(None)
    yield
    set_harness_runner_for_tests(None)


class TestVerifierPassPath:
    def test_pass_runner_returns_success(self):
        result = verify(_simple_plan(), _PREVIEW_URL, runner=_PassRunner())
        assert result.success is True

    def test_pass_result_has_no_error_envelope(self):
        result = verify(_simple_plan(), _PREVIEW_URL, runner=_PassRunner())
        assert result.error_envelope is None

    def test_pass_result_has_test_source(self):
        result = verify(_simple_plan(), _PREVIEW_URL, runner=_PassRunner())
        assert len(result.test_source) > 0
        assert "pln_verifier_test" in result.test_source


class TestVerifierFailPath:
    def test_fail_runner_returns_failure(self):
        result = verify(_simple_plan(), _PREVIEW_URL, runner=_FailRunner())
        assert result.success is False

    def test_fail_result_has_error_envelope(self):
        result = verify(_simple_plan(), _PREVIEW_URL, runner=_FailRunner())
        assert result.error_envelope is not None

    def test_fail_error_code_is_verification_failed(self):
        result = verify(_simple_plan(), _PREVIEW_URL, runner=_FailRunner())
        assert result.error_envelope is not None
        assert result.error_envelope.error_code == STEP_VERIFICATION_FAILED

    def test_fail_error_details_include_playwright_snippet(self):
        stdout = "1 failed: expect(locator).toBeVisible()"
        result = verify(_simple_plan(), _PREVIEW_URL, runner=_FailRunner(stdout=stdout))
        assert result.error_envelope is not None
        assert result.error_envelope.error_details is not None
        assert "playwright_stdout_snippet" in result.error_envelope.error_details

    def test_fail_error_details_include_assertion_text(self):
        result = verify(_simple_plan(), _PREVIEW_URL, runner=_FailRunner())
        assert result.error_envelope is not None
        assert result.error_envelope.error_details is not None
        assert "assertion_text" in result.error_envelope.error_details

    def test_fail_stdout_snippet_in_outcome(self):
        stdout = "Error details here"
        result = verify(_simple_plan(), _PREVIEW_URL, runner=_FailRunner(stdout=stdout))
        assert stdout in result.stdout_snippet


class TestHarnessRunnerSingleton:
    def test_get_harness_runner_returns_protocol_impl(self):
        runner = get_harness_runner()
        assert isinstance(runner, HarnessRunnerProtocol)

    def test_set_for_tests_overrides_singleton(self):
        set_harness_runner_for_tests(_PassRunner())
        assert get_harness_runner() is not None

    def test_reset_to_none_restores_default(self):
        set_harness_runner_for_tests(_PassRunner())
        set_harness_runner_for_tests(None)
        runner = get_harness_runner()
        assert isinstance(runner, HarnessRunnerProtocol)
