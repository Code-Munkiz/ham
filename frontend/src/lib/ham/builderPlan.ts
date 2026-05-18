// SOURCE OF TRUTH: src/ham/builder_plan.py
// Hand-written TypeScript mirror of Phase 0 Pydantic schemas.
// TODO: Replace with codegen (e.g. pydantic-to-typescript) when available.
//
// Spec: docs/PHASE_0_CONTRACTS.md
// Glossary: CONTEXT.md

// ---------------------------------------------------------------------------
// Literal types
// ---------------------------------------------------------------------------

export type CloudRuntimeJobStatus =
  | "queued"
  | "running"
  | "cancelling"
  | "cancelled"
  | "completed"
  | "failed";

export type PlanApprovalState = "proposed" | "approved" | "stale";

export type PlannerConfidence = "high" | "medium" | "low";

// ---------------------------------------------------------------------------
// Contract 1 — Plan + Step
// ---------------------------------------------------------------------------

export interface Step {
  step_id: string;
  title: string;
  description: string;
  requires_approval: boolean;
}

export interface Plan {
  plan_id: string;
  version: string;
  workspace_id: string;
  project_id: string;
  source_snapshot_id: string | null;
  user_message: string;
  steps: Step[];
  destructive: boolean;
  planner_model: string | null;
  planner_confidence: PlannerConfidence;
  created_at: string;
  metadata: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Contract 2 — Approval state machine
// ---------------------------------------------------------------------------

export interface PlanApprovalRecord {
  plan_id: string;
  state: PlanApprovalState;
  proposed_at: string;
  approved_at: string | null;
  stale_at: string | null;
  stale_reason: string | null;
}

// ---------------------------------------------------------------------------
// Contract 3 — WorkerEnvelope
// ---------------------------------------------------------------------------

export interface WorkerEnvelope {
  version: string;
  envelope_id: string;
  plan_id: string;
  job_id: string;
  workspace_id: string;
  project_id: string;
  requested_by: string;
  enqueued_at: string;
  correlation_id: string;
}

// ---------------------------------------------------------------------------
// Contract 5 — ErrorEnvelope
// ---------------------------------------------------------------------------

export interface ErrorEnvelope {
  version: string;
  error_code: string;
  error_message: string;
  error_details: Record<string, unknown> | null;
  retriable: boolean;
  fatal: boolean;
  occurred_at: string;
}

// ---------------------------------------------------------------------------
// Contract 4 — SSE event payload variants (11 types)
// ---------------------------------------------------------------------------

export interface StepStartedPayload {
  type: "step_started";
  step_id: string;
  step_index: number;
  title: string;
}

export interface StepLogPayload {
  type: "step_log";
  step_id: string;
  text: string;
}

export interface StepCompletedPayload {
  type: "step_completed";
  step_id: string;
  step_index: number;
}

export interface StepFailedPayload {
  type: "step_failed";
  step_id: string;
  step_index: number;
  error: ErrorEnvelope;
}

export interface JobStartedPayload {
  type: "job_started";
}

export interface JobCompletedPayload {
  type: "job_completed";
}

export interface JobFailedPayload {
  type: "job_failed";
  error: ErrorEnvelope;
}

export interface JobCancelledPayload {
  type: "job_cancelled";
  cancelled_at_step_id: string | null;
}

export interface CancelAcknowledgedPayload {
  type: "cancel_acknowledged";
}

export interface RuntimeErrorPayload {
  type: "runtime_error";
  error: ErrorEnvelope;
}

export interface HeartbeatPayload {
  type: "heartbeat";
}

export type EventPayload =
  | StepStartedPayload
  | StepLogPayload
  | StepCompletedPayload
  | StepFailedPayload
  | JobStartedPayload
  | JobCompletedPayload
  | JobFailedPayload
  | JobCancelledPayload
  | CancelAcknowledgedPayload
  | RuntimeErrorPayload
  | HeartbeatPayload;

// ---------------------------------------------------------------------------
// Contract 4 — SSEEvent wrapper
// ---------------------------------------------------------------------------

export interface SSEEvent {
  version: string;
  seq: number;
  job_id: string;
  plan_id: string;
  occurred_at: string;
  event: EventPayload;
}

// ---------------------------------------------------------------------------
// Contract 6 — Cancel REST DTOs
// ---------------------------------------------------------------------------

export interface CancelRequest {
  reason: string | null;
}

export interface CancelResponse {
  job_id: string;
  status: CloudRuntimeJobStatus;
  cancel_requested_at: string;
}
