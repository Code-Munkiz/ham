"""Tests for src/ham/builder_plan.py — Phase 0 Pydantic schemas.

Covers:
- Round-trip (.model_dump_json() -> .model_validate_json()) for every model
- Discriminator selects the correct variant for each of the 11 SSE type values
- extra="forbid" rejects unknown fields
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.ham.builder_plan import (
    CancelAcknowledgedPayload,
    CancelRequest,
    CancelResponse,
    ErrorEnvelope,
    HeartbeatPayload,
    JobCancelledPayload,
    JobCompletedPayload,
    JobFailedPayload,
    JobStartedPayload,
    Plan,
    PlanApprovalRecord,
    RuntimeErrorPayload,
    SSEEvent,
    Step,
    StepCompletedPayload,
    StepFailedPayload,
    StepLogPayload,
    StepStartedPayload,
    WorkerEnvelope,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = "2026-05-18T12:00:00Z"


def _make_error() -> ErrorEnvelope:
    return ErrorEnvelope(
        error_code="step.step_failed",
        error_message="Something broke",
        fatal=True,
        occurred_at=_TS,
    )


def _round_trip(model_cls, instance):
    """Serialize to JSON and back; assert equality."""
    raw = instance.model_dump_json()
    restored = model_cls.model_validate_json(raw)
    assert restored == instance
    return restored


# ---------------------------------------------------------------------------
# Round-trip: every top-level model
# ---------------------------------------------------------------------------


class TestStepRoundTrip:
    def test_round_trip(self):
        step = Step(
            step_id="stp_abc123",
            title="Add login form",
            description="Create a React login component",
        )
        _round_trip(Step, step)

    def test_default_id_prefix(self):
        step = Step(title="t", description="d")
        assert step.step_id.startswith("stp_")


class TestPlanRoundTrip:
    def test_round_trip(self):
        plan = Plan(
            plan_id="pln_abc123",
            workspace_id="ws_1",
            project_id="proj_1",
            user_message="Add auth",
            steps=[Step(step_id="stp_1", title="t", description="d")],
            planner_confidence="high",
            created_at=_TS,
        )
        _round_trip(Plan, plan)

    def test_default_id_prefix(self):
        plan = Plan(
            workspace_id="ws",
            project_id="p",
            user_message="msg",
            steps=[],
            planner_confidence="low",
        )
        assert plan.plan_id.startswith("pln_")

    def test_version_default(self):
        plan = Plan(
            workspace_id="ws",
            project_id="p",
            user_message="msg",
            steps=[],
            planner_confidence="medium",
        )
        assert plan.version == "1.0.0"


class TestPlanApprovalRecordRoundTrip:
    def test_round_trip(self):
        rec = PlanApprovalRecord(
            plan_id="pln_abc",
            state="approved",
            proposed_at=_TS,
            approved_at=_TS,
        )
        _round_trip(PlanApprovalRecord, rec)


class TestWorkerEnvelopeRoundTrip:
    def test_round_trip(self):
        env = WorkerEnvelope(
            envelope_id="env_abc",
            plan_id="pln_1",
            job_id="crjb_1",
            workspace_id="ws_1",
            project_id="proj_1",
            requested_by="user@example.com",
            enqueued_at=_TS,
            correlation_id="crjb_1",
        )
        _round_trip(WorkerEnvelope, env)

    def test_default_id_prefix(self):
        env = WorkerEnvelope(
            plan_id="pln_1",
            job_id="crjb_1",
            workspace_id="ws_1",
            project_id="proj_1",
            requested_by="u",
            correlation_id="c",
        )
        assert env.envelope_id.startswith("env_")


class TestErrorEnvelopeRoundTrip:
    def test_round_trip(self):
        err = _make_error()
        _round_trip(ErrorEnvelope, err)

    def test_with_details(self):
        err = ErrorEnvelope(
            error_code="gate.plan_stale",
            error_message="Snapshot drifted",
            error_details={"original_snapshot_id": "s1", "current_snapshot_id": "s2"},
            retriable=False,
            fatal=True,
            occurred_at=_TS,
        )
        _round_trip(ErrorEnvelope, err)


class TestCancelRequestRoundTrip:
    def test_round_trip(self):
        req = CancelRequest(reason="user changed mind")
        _round_trip(CancelRequest, req)

    def test_none_reason(self):
        req = CancelRequest()
        assert req.reason is None
        _round_trip(CancelRequest, req)


class TestCancelResponseRoundTrip:
    def test_round_trip(self):
        resp = CancelResponse(
            job_id="crjb_1",
            status="cancelling",
            cancel_requested_at=_TS,
        )
        _round_trip(CancelResponse, resp)


# ---------------------------------------------------------------------------
# SSEEvent discriminator: each of the 11 payload types
# ---------------------------------------------------------------------------

_DISCRIMINATOR_CASES = [
    (
        "step_started",
        StepStartedPayload,
        {"step_id": "stp_1", "step_index": 0, "title": "Create file"},
    ),
    (
        "step_log",
        StepLogPayload,
        {"step_id": "stp_1", "text": "Writing index.tsx..."},
    ),
    (
        "step_completed",
        StepCompletedPayload,
        {"step_id": "stp_1", "step_index": 0},
    ),
    (
        "step_failed",
        StepFailedPayload,
        {"step_id": "stp_1", "step_index": 0, "error": _make_error().model_dump(mode="json")},
    ),
    (
        "job_started",
        JobStartedPayload,
        {},
    ),
    (
        "job_completed",
        JobCompletedPayload,
        {},
    ),
    (
        "job_failed",
        JobFailedPayload,
        {"error": _make_error().model_dump(mode="json")},
    ),
    (
        "job_cancelled",
        JobCancelledPayload,
        {"cancelled_at_step_id": "stp_1"},
    ),
    (
        "cancel_acknowledged",
        CancelAcknowledgedPayload,
        {},
    ),
    (
        "runtime_error",
        RuntimeErrorPayload,
        {"error": _make_error().model_dump(mode="json")},
    ),
    (
        "heartbeat",
        HeartbeatPayload,
        {},
    ),
]


class TestSSEEventDiscriminator:
    @pytest.mark.parametrize(
        "event_type, expected_cls, extra_fields",
        _DISCRIMINATOR_CASES,
        ids=[c[0] for c in _DISCRIMINATOR_CASES],
    )
    def test_discriminator_selects_correct_variant(self, event_type, expected_cls, extra_fields):
        payload = {"type": event_type, **extra_fields}
        sse = SSEEvent(
            seq=1,
            job_id="crjb_1",
            plan_id="pln_1",
            occurred_at=_TS,
            event=payload,
        )
        assert isinstance(sse.event, expected_cls)

    @pytest.mark.parametrize(
        "event_type, expected_cls, extra_fields",
        _DISCRIMINATOR_CASES,
        ids=[c[0] for c in _DISCRIMINATOR_CASES],
    )
    def test_sse_event_round_trip(self, event_type, expected_cls, extra_fields):
        payload = {"type": event_type, **extra_fields}
        sse = SSEEvent(
            seq=42,
            job_id="crjb_1",
            plan_id="pln_1",
            occurred_at=_TS,
            event=payload,
        )
        restored = SSEEvent.model_validate_json(sse.model_dump_json())
        assert restored == sse
        assert isinstance(restored.event, expected_cls)


# ---------------------------------------------------------------------------
# extra="forbid" rejection
# ---------------------------------------------------------------------------


class TestExtraForbid:
    def test_plan_rejects_unknown_field(self):
        data = {
            "workspace_id": "ws",
            "project_id": "p",
            "user_message": "msg",
            "steps": [],
            "planner_confidence": "high",
            "created_at": _TS,
            "bogus_field": "should fail",
        }
        with pytest.raises(ValidationError, match="extra_forbidden"):
            Plan.model_validate(data)

    def test_step_rejects_unknown_field(self):
        data = {"title": "t", "description": "d", "nope": 1}
        with pytest.raises(ValidationError, match="extra_forbidden"):
            Step.model_validate(data)

    def test_sse_event_rejects_unknown_field(self):
        data = {
            "seq": 1,
            "job_id": "j",
            "plan_id": "p",
            "occurred_at": _TS,
            "event": {"type": "heartbeat"},
            "extra_key": True,
        }
        with pytest.raises(ValidationError, match="extra_forbidden"):
            SSEEvent.model_validate(data)

    def test_error_envelope_rejects_unknown_field(self):
        data = {
            "error_code": "internal_error",
            "error_message": "oops",
            "fatal": True,
            "occurred_at": _TS,
            "unexpected": 42,
        }
        with pytest.raises(ValidationError, match="extra_forbidden"):
            ErrorEnvelope.model_validate(data)

    def test_worker_envelope_rejects_unknown_field(self):
        data = {
            "plan_id": "pln_1",
            "job_id": "crjb_1",
            "workspace_id": "ws",
            "project_id": "p",
            "requested_by": "u",
            "correlation_id": "c",
            "enqueued_at": _TS,
            "rogue": "value",
        }
        with pytest.raises(ValidationError, match="extra_forbidden"):
            WorkerEnvelope.model_validate(data)

    def test_payload_variant_rejects_unknown_field(self):
        data = {
            "type": "heartbeat",
            "should_not_exist": True,
        }
        with pytest.raises(ValidationError, match="extra_forbidden"):
            HeartbeatPayload.model_validate(data)
