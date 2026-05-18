"""Smoke tests for tests/fixtures/phase0_contracts.py.

Verifies each fixture builder produces a valid Pydantic model with zero
args and that **overrides correctly substitutes fields.
"""

from __future__ import annotations

from tests.fixtures.phase0_contracts import (
    make_test_approval_record,
    make_test_envelope,
    make_test_error,
    make_test_plan,
    make_test_runtime_job,
    make_test_sse_event,
    make_test_step,
)


class TestZeroArgDefaults:
    def test_make_test_step(self):
        step = make_test_step()
        assert step.title == "Test step"
        step.model_dump_json()

    def test_make_test_plan(self):
        plan = make_test_plan()
        assert len(plan.steps) == 2
        plan.model_dump_json()

    def test_make_test_approval_record(self):
        rec = make_test_approval_record()
        assert rec.state == "proposed"
        rec.model_dump_json()

    def test_make_test_envelope(self):
        env = make_test_envelope()
        assert env.plan_id == "pln_test"
        env.model_dump_json()

    def test_make_test_error(self):
        err = make_test_error()
        assert err.error_code == "internal_error"
        err.model_dump_json()

    def test_make_test_sse_event(self):
        evt = make_test_sse_event()
        assert evt.seq == 1
        evt.model_dump_json()

    def test_make_test_runtime_job(self):
        job = make_test_runtime_job()
        assert job.status == "queued"
        job.model_dump_json()


class TestOverrides:
    def test_step_override(self):
        step = make_test_step(title="Custom", description="Override desc")
        assert step.title == "Custom"
        assert step.description == "Override desc"

    def test_plan_override(self):
        plan = make_test_plan(project_id="proj_custom", steps_count=5)
        assert plan.project_id == "proj_custom"
        assert len(plan.steps) == 5

    def test_approval_record_override(self):
        rec = make_test_approval_record(state="approved", approved_at="2026-01-01T00:00:00Z")
        assert rec.state == "approved"
        assert rec.approved_at == "2026-01-01T00:00:00Z"

    def test_envelope_override(self):
        env = make_test_envelope(plan_id="pln_custom", requested_by="custom@test.com")
        assert env.plan_id == "pln_custom"
        assert env.requested_by == "custom@test.com"

    def test_error_override(self):
        err = make_test_error(code="gate.plan_stale", fatal=True)
        assert err.error_code == "gate.plan_stale"
        assert err.fatal is True

    def test_sse_event_override(self):
        evt = make_test_sse_event(
            seq=42,
            payload={"type": "job_started"},
        )
        assert evt.seq == 42
        assert evt.event.type == "job_started"  # type: ignore[union-attr]

    def test_runtime_job_override(self):
        job = make_test_runtime_job(status="running", provider="gcp")
        assert job.status == "running"
        assert job.provider == "gcp"
