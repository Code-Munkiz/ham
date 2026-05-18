"""Verifier orchestration — Phase 1 #5 (Tier 1 #19).

Generates a Playwright test from ``builder_test_generator``, runs it via the
existing ``scripts/ham-builder-qa/`` harness (as subprocess), and maps the
outcome to Phase 0 SSE payloads.

The GKE client and Playwright harness live behind Protocols so tests
substitute fakes without hitting the network.

Spec: docs/MANUS_PARITY_ROADMAP.md § Tier 1 #19
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from src.ham import builder_test_generator
from src.ham.builder_error_codes import STEP_TOOL_CALL_FAILED, make_error
from src.ham.builder_plan import ErrorEnvelope, Plan

# Error code for verification failure (Phase 0 catalog: step.step_verification_failed
# maps to STEP_TOOL_CALL_FAILED in the current catalog — closest match; raised as
# step_failed outcome with descriptive message).
_VERIFICATION_FAILED_CODE = STEP_TOOL_CALL_FAILED

_DEFAULT_HARNESS_TIMEOUT = 60  # seconds
_STDOUT_SNIPPET_MAX = 2048


@dataclass(frozen=True)
class VerifierOutcome:
    success: bool
    error_envelope: ErrorEnvelope | None = None
    stdout_snippet: str = ""
    test_source: str = ""


# ---------------------------------------------------------------------------
# Harness runner Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class HarnessRunnerProtocol(Protocol):
    def run(self, test_source: str, *, timeout_seconds: int) -> tuple[int, str]:
        """Run the test source; return (returncode, stdout_snippet)."""
        ...


class SubprocessHarnessRunner:
    """Writes the test to a temp file and runs it via ``node``."""

    def __init__(self, *, node_bin: str = "node", harness_dir: str | Path | None = None) -> None:
        self._node_bin = node_bin
        # Default: scripts/ham-builder-qa relative to repo root
        if harness_dir is None:
            self._harness_dir = Path(__file__).resolve().parents[2] / "scripts" / "ham-builder-qa"
        else:
            self._harness_dir = Path(harness_dir)

    def run(self, test_source: str, *, timeout_seconds: int = _DEFAULT_HARNESS_TIMEOUT) -> tuple[int, str]:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".spec.js", delete=False, encoding="utf-8"
        ) as f:
            f.write(test_source)
            tmp_path = f.name
        try:
            result = subprocess.run(
                [self._node_bin, tmp_path],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(self._harness_dir),
            )
            stdout = (result.stdout + result.stderr)[:_STDOUT_SNIPPET_MAX]
            return result.returncode, stdout
        except subprocess.TimeoutExpired as exc:
            snippet = str(exc.stdout or "")[:_STDOUT_SNIPPET_MAX]
            return 1, f"[timeout after {timeout_seconds}s]\n{snippet}"
        except Exception as exc:  # noqa: BLE001
            return 1, f"[harness launch error: {exc}]"
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Singleton harness runner
# ---------------------------------------------------------------------------

_RUNNER_SINGLETON: list[HarnessRunnerProtocol | None] = [None]


def get_harness_runner() -> HarnessRunnerProtocol:
    if _RUNNER_SINGLETON[0] is None:
        _RUNNER_SINGLETON[0] = SubprocessHarnessRunner()
    return _RUNNER_SINGLETON[0]


def set_harness_runner_for_tests(runner: HarnessRunnerProtocol | None) -> None:
    _RUNNER_SINGLETON[0] = runner


# ---------------------------------------------------------------------------
# Verifier entrypoint
# ---------------------------------------------------------------------------


def verify(
    plan: Plan,
    preview_url: str,
    *,
    runner: HarnessRunnerProtocol | None = None,
    timeout_seconds: int = _DEFAULT_HARNESS_TIMEOUT,
) -> VerifierOutcome:
    """Generate and run a Playwright verification test for the Plan.

    Returns a :class:`VerifierOutcome` with ``success=True`` on pass, or
    ``success=False`` plus an ``ErrorEnvelope`` on failure.
    """
    test_source = builder_test_generator.generate(plan, preview_url)
    active_runner = runner or get_harness_runner()

    returncode, stdout_snippet = active_runner.run(test_source, timeout_seconds=timeout_seconds)

    if returncode == 0:
        return VerifierOutcome(success=True, test_source=test_source)

    err = make_error(
        _VERIFICATION_FAILED_CODE,
        f"Playwright verification failed for plan {plan.plan_id!r} "
        f"at {preview_url!r}.",
        fatal=False,
        retriable=True,
        details={
            "assertion_text": f"verify plan {plan.plan_id}",
            "playwright_stdout_snippet": stdout_snippet[:_STDOUT_SNIPPET_MAX],
        },
    )
    return VerifierOutcome(
        success=False,
        error_envelope=err,
        stdout_snippet=stdout_snippet,
        test_source=test_source,
    )
