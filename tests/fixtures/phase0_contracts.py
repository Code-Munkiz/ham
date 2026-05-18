"""Shared test fixture builders for Phase 0 contracts.

Each builder produces a valid Pydantic model instance with sensible
defaults. Use **overrides to swap any field.

Usage:
    from tests.fixtures.phase0_contracts import make_test_plan
    plan = make_test_plan(project_id="proj_custom", steps_count=3)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.ham.builder_plan import (
    CloudRuntimeJobStatus,
    ErrorEnvelope,
    Plan,
    PlanApprovalRecord,
    PlanApprovalState,
    SSEEvent,
    Step,
    WorkerEnvelope,
)
from src.persistence.builder_runtime_job_store import CloudRuntimeJob


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_test_step(*, title: str = "Test step", **overrides: Any) -> Step:
    defaults: dict[str, Any] = {
        "title": title,
        "description": "A test step description",
    }
    defaults.update(overrides)
    return Step(**defaults)


def make_test_plan(
    *,
    project_id: str = "proj_test",
    steps_count: int = 2,
    **overrides: Any,
) -> Plan:
    defaults: dict[str, Any] = {
        "workspace_id": "ws_test",
        "project_id": project_id,
        "user_message": "Build something for testing",
        "steps": [make_test_step(title=f"Step {i + 1}") for i in range(steps_count)],
        "planner_confidence": "high",
        "created_at": _utc_now_iso(),
    }
    defaults.update(overrides)
    return Plan(**defaults)


def make_test_approval_record(
    plan_id: str = "pln_test",
    state: PlanApprovalState = "proposed",
    **overrides: Any,
) -> PlanApprovalRecord:
    defaults: dict[str, Any] = {
        "plan_id": plan_id,
        "state": state,
        "proposed_at": _utc_now_iso(),
    }
    defaults.update(overrides)
    return PlanApprovalRecord(**defaults)


def make_test_envelope(
    *,
    plan_id: str = "pln_test",
    job_id: str = "crjb_test",
    **overrides: Any,
) -> WorkerEnvelope:
    defaults: dict[str, Any] = {
        "plan_id": plan_id,
        "job_id": job_id,
        "workspace_id": "ws_test",
        "project_id": "proj_test",
        "requested_by": "test@example.com",
        "correlation_id": job_id,
    }
    defaults.update(overrides)
    return WorkerEnvelope(**defaults)


def make_test_error(
    *,
    code: str = "internal_error",
    message: str = "boom",
    fatal: bool = False,
    **overrides: Any,
) -> ErrorEnvelope:
    defaults: dict[str, Any] = {
        "error_code": code,
        "error_message": message,
        "fatal": fatal,
        "occurred_at": _utc_now_iso(),
    }
    defaults.update(overrides)
    return ErrorEnvelope(**defaults)


def make_test_sse_event(
    *,
    job_id: str = "crjb_test",
    plan_id: str = "pln_test",
    payload: dict[str, Any] | None = None,
    seq: int = 1,
    **overrides: Any,
) -> SSEEvent:
    defaults: dict[str, Any] = {
        "seq": seq,
        "job_id": job_id,
        "plan_id": plan_id,
        "occurred_at": _utc_now_iso(),
        "event": payload or {"type": "heartbeat"},
    }
    defaults.update(overrides)
    return SSEEvent(**defaults)


def make_test_runtime_job(
    *,
    status: CloudRuntimeJobStatus = "queued",
    **overrides: Any,
) -> CloudRuntimeJob:
    defaults: dict[str, Any] = {
        "workspace_id": "ws_test",
        "project_id": "proj_test",
        "status": status,
    }
    defaults.update(overrides)
    return CloudRuntimeJob(**defaults)
