from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.bridge.contracts import (
    BridgeResult,
    BridgeStatus,
    CommandEvidence,
    CommandSpec,
    CommandState,
    ExecutionIntent,
    LimitSpec,
    PolicyDecision,
    ScopeSpec,
)


def _dump(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _valid_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="intent-1",
        request_id="request-1",
        run_id="run-1",
        task_class="inspect",
        commands=[
            CommandSpec(
                command_id="cmd-1",
                argv=["python", "-c", "print('ok')"],
                working_dir=".",
            )
        ],
        scope=ScopeSpec(allowed_roots=["."]),
        limits=LimitSpec(
            max_commands=1,
            timeout_sec_per_command=10,
            max_stdout_chars=1000,
            max_stderr_chars=1000,
            max_total_output_chars=2000,
        ),
        reason="bridge contract smoke",
    )


def test_execution_intent_requires_ids():
    with pytest.raises(ValidationError):
        ExecutionIntent(
            intent_id="",
            request_id="req",
            run_id="run",
            task_class="inspect",
            commands=[CommandSpec(command_id="c1", argv=["python"], working_dir=".")],
            scope=ScopeSpec(allowed_roots=["."]),
            limits=LimitSpec(
                max_commands=1,
                timeout_sec_per_command=1,
                max_stdout_chars=1,
                max_stderr_chars=1,
                max_total_output_chars=2,
            ),
            reason="x",
        )


def test_enum_constraints_hold():
    intent = _valid_intent()
    assert intent.task_class == "inspect"
    with pytest.raises(ValidationError):
        # noinspection PyTypeChecker
        ExecutionIntent(**{**_dump(intent), "task_class": "execute"})


def test_limit_bounds_enforced():
    with pytest.raises(ValidationError):
        LimitSpec(
            max_commands=0,
            timeout_sec_per_command=10,
            max_stdout_chars=1000,
            max_stderr_chars=1000,
            max_total_output_chars=2000,
        )


def test_bridge_result_serializes_deterministically():
    evidence = CommandEvidence(
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
    result = BridgeResult(
        intent_id="intent-1",
        request_id="request-1",
        run_id="run-1",
        status=BridgeStatus.EXECUTED,
        policy_decision=PolicyDecision(
            accepted=True,
            reasons=[],
            policy_version="bridge-v0",
        ),
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
        duration_ms=1000,
        commands=[evidence],
        summary="ok",
    )

    d1 = _dump(result)
    d2 = _dump(result)
    assert d1 == d2
    assert d1["status"] == "executed"
    assert d1["commands"][0]["status"] == "executed"

    s1 = json.dumps(d1, sort_keys=True)
    s2 = json.dumps(d2, sort_keys=True)
    assert s1 == s2

