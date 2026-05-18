"""Phase 0 Pydantic schemas — Plan, Step, WorkerEnvelope, ErrorEnvelope, SSEEvent.

Single source of truth for all Phase 0 contracts.
Spec: docs/PHASE_0_CONTRACTS.md
Glossary: CONTEXT.md
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Helpers (same convention as builder_runtime_job_store._utc_now_iso)
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Literal types (exported for Issue #2 state validators / Issue #4 job-store)
# ---------------------------------------------------------------------------

CloudRuntimeJobStatus = Literal[
    "queued",
    "running",
    "cancelling",
    "cancelled",
    "completed",
    "failed",
]

PlanApprovalState = Literal["proposed", "approved", "stale"]

# ---------------------------------------------------------------------------
# Contract 1 — Plan + Step
# ---------------------------------------------------------------------------


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(default_factory=lambda: f"stp_{uuid.uuid4().hex}")
    title: str
    description: str
    requires_approval: bool = False


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(default_factory=lambda: f"pln_{uuid.uuid4().hex}")
    version: str = "1.0.0"
    workspace_id: str
    project_id: str
    source_snapshot_id: str | None = None
    user_message: str
    steps: list[Step]
    destructive: bool = False
    planner_model: str | None = None
    planner_confidence: Literal["high", "medium", "low"]
    created_at: str = Field(default_factory=_utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Contract 2 — Approval state machine
# ---------------------------------------------------------------------------


class PlanApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    state: PlanApprovalState = "proposed"
    proposed_at: str = Field(default_factory=_utc_now_iso)
    approved_at: str | None = None
    stale_at: str | None = None
    stale_reason: str | None = None


# ---------------------------------------------------------------------------
# Contract 3 — WorkerEnvelope (queue message)
# ---------------------------------------------------------------------------


class WorkerEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "1.0.0"
    envelope_id: str = Field(default_factory=lambda: f"env_{uuid.uuid4().hex}")
    plan_id: str
    job_id: str
    workspace_id: str
    project_id: str
    requested_by: str
    enqueued_at: str = Field(default_factory=_utc_now_iso)
    correlation_id: str


# ---------------------------------------------------------------------------
# Contract 5 — ErrorEnvelope (defined before Contract 4 payloads that use it)
# ---------------------------------------------------------------------------


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "1.0.0"
    error_code: str
    error_message: str
    error_details: dict[str, Any] | None = None
    retriable: bool = False
    fatal: bool
    occurred_at: str = Field(default_factory=_utc_now_iso)


# ---------------------------------------------------------------------------
# Contract 4 — SSE event payload variants (11 types)
# ---------------------------------------------------------------------------


class StepStartedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["step_started"] = "step_started"
    step_id: str
    step_index: int
    title: str


class StepLogPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["step_log"] = "step_log"
    step_id: str
    text: str


class StepCompletedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["step_completed"] = "step_completed"
    step_id: str
    step_index: int


class StepFailedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["step_failed"] = "step_failed"
    step_id: str
    step_index: int
    error: ErrorEnvelope


class JobStartedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["job_started"] = "job_started"


class JobCompletedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["job_completed"] = "job_completed"


class JobFailedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["job_failed"] = "job_failed"
    error: ErrorEnvelope


class JobCancelledPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["job_cancelled"] = "job_cancelled"
    cancelled_at_step_id: str | None = None


class CancelAcknowledgedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["cancel_acknowledged"] = "cancel_acknowledged"


class RuntimeErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["runtime_error"] = "runtime_error"
    error: ErrorEnvelope


class HeartbeatPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["heartbeat"] = "heartbeat"


EventPayload = Annotated[
    Union[
        StepStartedPayload,
        StepLogPayload,
        StepCompletedPayload,
        StepFailedPayload,
        JobStartedPayload,
        JobCompletedPayload,
        JobFailedPayload,
        JobCancelledPayload,
        CancelAcknowledgedPayload,
        RuntimeErrorPayload,
        HeartbeatPayload,
    ],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Contract 4 — SSEEvent wrapper
# ---------------------------------------------------------------------------


class SSEEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "1.0.0"
    seq: int
    job_id: str
    plan_id: str
    occurred_at: str = Field(default_factory=_utc_now_iso)
    event: EventPayload


# ---------------------------------------------------------------------------
# Contract 6 — Cancel REST DTOs
# ---------------------------------------------------------------------------


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None


class CancelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: CloudRuntimeJobStatus
    cancel_requested_at: str
