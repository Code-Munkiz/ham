from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

import src.ham.one_shot_run as one_shot_mod
from src.bridge.contracts import (
    BridgeResult,
    BridgeStatus,
    CommandEvidence,
    CommandState,
    PolicyDecision,
)


_FAKE_API_KEY = "sk-or-v1-hamtests-only-fake-key-000000000"


@dataclass
class _FakeAssembly:
    user_prompt: str
    critic_backstory: str = "critic-context"
    droid_executor: object = object()


def _bridge_result() -> BridgeResult:
    return BridgeResult(
        intent_id="intent-1",
        request_id="request-1",
        run_id="run-oneshot-x",
        status=BridgeStatus.EXECUTED,
        policy_decision=PolicyDecision(
            accepted=True, reasons=[], policy_version="bridge-v0"
        ),
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
        duration_ms=1000,
        commands=[
            CommandEvidence(
                command_id="cmd-1",
                argv=["python", "-c", "print('ok')"],
                working_dir=".",
                status=CommandState.EXECUTED,
                exit_code=0,
                timed_out=False,
                stdout="ok",
                stderr="",
                stdout_truncated=False,
                stderr_truncated=False,
                started_at="2026-01-01T00:00:00Z",
                ended_at="2026-01-01T00:00:01Z",
                duration_ms=1000,
            )
        ],
        summary="ok",
        mutation_detected=False,
    )


@pytest.fixture()
def _patch_deps(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", _FAKE_API_KEY)
    monkeypatch.setattr(
        one_shot_mod,
        "assemble_ham_run",
        lambda prompt, project_root=None: _FakeAssembly(user_prompt=prompt),
    )
    monkeypatch.setattr(
        one_shot_mod,
        "persist_ham_run_record",
        lambda *_args, **_kwargs: None,
    )
    return tmp_path


def test_one_shot_runs_without_name_error(_patch_deps, monkeypatch):
    """Regression: line 118 referenced ``MAX_REVIEW_CONTEXT_CHARS`` but the constant
    is defined as ``_MAX_REVIEW_CONTEXT_CHARS``. Every successful bridge run through
    ``run_ham_one_shot`` (chat operator ``launch_run`` handler) raised NameError."""
    monkeypatch.setattr(
        one_shot_mod,
        "run_bridge_v0",
        lambda _assembly, _intent: _bridge_result(),
    )
    fake_reviewer = MagicMock()
    fake_reviewer.evaluate.return_value = {
        "ok": True,
        "notes": [],
        "code": "x",
        "context": "y",
    }
    monkeypatch.setattr(one_shot_mod, "HermesReviewer", lambda: fake_reviewer)

    result = one_shot_mod.run_ham_one_shot(_patch_deps, "test prompt")
    assert result.ok is True
    assert result.run_id == "run-oneshot-x"
    # Reviewer was actually reached (no NameError before line 136 call).
    assert fake_reviewer.evaluate.call_count == 1


def test_one_shot_review_failure_does_not_break_envelope(_patch_deps, monkeypatch):
    """Independent of mutation path: reviewer crashes should fall through to
    a conservative review envelope rather than propagating the exception."""
    monkeypatch.setattr(
        one_shot_mod,
        "run_bridge_v0",
        lambda _assembly, _intent: _bridge_result(),
    )

    class _BoomReviewer:
        def evaluate(self, _code, _context=None):
            raise RuntimeError("critic crashed")

    monkeypatch.setattr(one_shot_mod, "HermesReviewer", _BoomReviewer)

    result = one_shot_mod.run_ham_one_shot(_patch_deps, "boom")
    assert result.ok is True
    review = result.envelope["hermes_review"]
    assert review["ok"] is False
    assert "RuntimeError" in review["notes"][0] or "critic crashed" in review["notes"][0]
