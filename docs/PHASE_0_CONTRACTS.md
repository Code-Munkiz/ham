# Phase 0 Contracts — Manus/Replit Parity

**Status:** Locked 2026-05-18 via `/grill-with-docs` session.
**Scope:** Six shared contracts that must exist as Pydantic models + TypeScript types before Phase 1 parallel implementation can start (per [MANUS_PARITY_ROADMAP.md § Phase 0](MANUS_PARITY_ROADMAP.md#phase-0--manual-blocks-everything-else)).
**Glossary:** [CONTEXT.md](../CONTEXT.md). **Rationale archive:** [docs/adr/0001](adr/0001-plan-is-unit-of-work.md), [0002](adr/0002-sse-with-replay-for-worker-events.md), [0003](adr/0003-approval-gate-enforces-per-project-serialization.md), [0004](adr/0004-cancel-is-step-boundary-cooperative.md).

This is a design specification, not implementation. The output of Phase 0 is the contracts; the work of writing them as code is a single small PR that Phase 1 depends on.

---

## Contract 1 — Planner output schema

### Decisions

- **Step grain:** coarse imperative goals; the Worker has latitude to choose tool calls. Matches Manus todo.md and Replit Plan Mode.
- **Schema:** homogeneous Steps (no discriminated union by Step kind).
- **Revisions:** each Planner call produces a fresh `Plan` with a new `plan_id`. No `parent_plan_id`; no revision counter. Pre-approval Plans are ephemeral.
- **Post-approval immutability:** approved Plans cannot be mutated (per ADR-0001).

### Pydantic

```python
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
import uuid

class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(default_factory=lambda: f"stp_{uuid.uuid4().hex}")
    title: str                              # short, ~50 chars, for task list UI
    description: str                        # longer rationale, ~200 chars, shown on expand
    requires_approval: bool = False         # Planner marks destructive Steps; informational under plan-level approval

class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(default_factory=lambda: f"pln_{uuid.uuid4().hex}")
    version: str = "1.0.0"
    workspace_id: str
    project_id: str
    source_snapshot_id: str | None = None   # snapshot the Plan was computed against
    user_message: str                       # the prompt that produced this Plan
    steps: list[Step]                       # ordered linearly; index = list position
    destructive: bool = False               # = any(step.requires_approval); denormalized for filtering
    planner_model: str | None = None        # e.g. "claude-opus-4-7"
    planner_confidence: Literal["high", "medium", "low"]   # matches BuilderActionDecision
    created_at: str                         # ISO 8601 UTC
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### TypeScript

```typescript
interface Step {
  step_id: string;
  title: string;
  description: string;
  requires_approval: boolean;
}

interface Plan {
  plan_id: string;
  version: string;
  workspace_id: string;
  project_id: string;
  source_snapshot_id: string | null;
  user_message: string;
  steps: Step[];
  destructive: boolean;
  planner_model: string | null;
  planner_confidence: "high" | "medium" | "low";
  created_at: string;
  metadata: Record<string, unknown>;
}
```

---

## Contract 2 — Approval state machine

### State diagram

```
                              ┌──────────────────────┐
                              ▼                      │
    Planner emits ─────► PROPOSED ──── approve() ────► APPROVED
                              │                            │
                              │ source_snapshot drift      │ create CloudRuntimeJob
                              ▼                            │ + enqueue WorkerEnvelope
                            STALE                          ▼
                       (terminal pre-                 (handoff to CloudRuntimeJob
                       approval; UI                   lifecycle in Contract 6)
                       must replan)
```

### Decisions

- **Three Plan states:** `PROPOSED`, `APPROVED`, `STALE`. No `REJECTED` (rejection is conversational — new turn produces a fresh Plan).
- **STALE is a hard wall.** When `source_snapshot_id` no longer matches the project's current snapshot, the Plan cannot be approved. UI must offer a "replan" action.
- **State machine ends at APPROVED.** Post-approval lifecycle is `CloudRuntimeJob.status` (locked in Contract 6).
- **Enqueue failures do NOT roll back to PROPOSED.** Plan stays APPROVED; `CloudRuntimeJob.last_error.error_code = "enqueue_failed"`.
- **No auto-approve in v1.** Even non-destructive Plans go through the gate. Auto-approve can land later as a per-user preference without changing the state machine.

### Pydantic

```python
PlanApprovalState = Literal["proposed", "approved", "stale"]

class PlanApprovalRecord(BaseModel):
    """Persisted alongside Plan; updated by the approval gate."""
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    state: PlanApprovalState = "proposed"
    proposed_at: str
    approved_at: str | None = None
    stale_at: str | None = None
    stale_reason: str | None = None   # e.g. "source_snapshot_drift"
```

### API surface

- `POST /api/plans/<plan_id>/approve` → `202 Accepted` (Plan moves to APPROVED, CloudRuntimeJob created, WorkerEnvelope enqueued) | `409 project_busy` | `409 plan_stale` | `404 not_found`

---

## Contract 3 — Queue message shape (`WorkerEnvelope`)

### Decisions

- **Pointer-only payload.** Plan and CloudRuntimeJob fetched from their stores by Worker on pop.
- **`job_id` is the idempotency key.** Worker checks `CloudRuntimeJob.status` before executing; exits if already terminal.
- **Per-project serialization enforced at the approval gate, not the queue** (ADR-0003).
- **No user identity for authz; auth happens at the gate.** `requested_by` is carried for observability only.
- **Queue technology is deferred** (Cloud Tasks vs Pub/Sub vs other). The contract is queue-agnostic.

### Pydantic

```python
class WorkerEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "1.0.0"
    envelope_id: str = Field(default_factory=lambda: f"env_{uuid.uuid4().hex}")
    plan_id: str
    job_id: str                  # CloudRuntimeJob.id; idempotency key
    workspace_id: str
    project_id: str
    requested_by: str            # for observability and commit attribution
    enqueued_at: str
    correlation_id: str          # tracing; can equal job_id
```

### TypeScript

```typescript
interface WorkerEnvelope {
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
```

---

## Contract 4 — SSE event envelope

### Decisions

- **Transport: Server-Sent Events.** One stream per `CloudRuntimeJob` at `GET /api/jobs/<job_id>/stream`. Opens on approve; closes at terminal status. (ADR-0002)
- **Wire format:** SSE `event:` = event type; SSE `id:` = `seq`; SSE `data:` = JSON-serialized `SSEEvent`.
- **Discriminated union** of 11 event payload types under a single `SSEEvent` wrapper. Pydantic v2 `Annotated[Union[...], Field(discriminator="type")]`.
- **Monotonic `seq` per `job_id`** starting at 1. Browser uses `Last-Event-ID` for resumption.
- **Full replay** from `seq=1` supported. API persists every emitted event for the lifetime of the job.
- **Heartbeat every 15s** when idle.
- **Curated narration, not raw token streams** in `step_log` (roadmap pattern #5).
- **No `progress_pct` field.** Step granularity is the visible progress.

### Pydantic — event payload variants

```python
class StepStartedPayload(BaseModel):
    type: Literal["step_started"]
    step_id: str
    step_index: int                          # 0-based
    title: str

class StepLogPayload(BaseModel):
    type: Literal["step_log"]
    step_id: str
    text: str                                # curated narration

class StepCompletedPayload(BaseModel):
    type: Literal["step_completed"]
    step_id: str
    step_index: int

class StepFailedPayload(BaseModel):
    type: Literal["step_failed"]
    step_id: str
    step_index: int
    error: "ErrorEnvelope"                   # see Contract 5

class JobStartedPayload(BaseModel):
    type: Literal["job_started"]

class JobCompletedPayload(BaseModel):
    type: Literal["job_completed"]

class JobFailedPayload(BaseModel):
    type: Literal["job_failed"]
    error: "ErrorEnvelope"

class JobCancelledPayload(BaseModel):
    type: Literal["job_cancelled"]
    cancelled_at_step_id: str | None         # null if cancel arrived before any Step ran

class CancelAcknowledgedPayload(BaseModel):
    type: Literal["cancel_acknowledged"]

class RuntimeErrorPayload(BaseModel):
    type: Literal["runtime_error"]
    error: "ErrorEnvelope"

class HeartbeatPayload(BaseModel):
    type: Literal["heartbeat"]

from typing import Annotated, Union
EventPayload = Annotated[
    Union[
        StepStartedPayload, StepLogPayload, StepCompletedPayload, StepFailedPayload,
        JobStartedPayload, JobCompletedPayload, JobFailedPayload, JobCancelledPayload,
        CancelAcknowledgedPayload, RuntimeErrorPayload, HeartbeatPayload,
    ],
    Field(discriminator="type"),
]

class SSEEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "1.0.0"
    seq: int                                 # monotonic per job_id, starts at 1
    job_id: str
    plan_id: str
    occurred_at: str                         # ISO 8601 UTC
    event: EventPayload
```

### Wire example

```
event: step_started
id: 42
data: {"version":"1.0.0","seq":42,"job_id":"crjb_abc","plan_id":"pln_def","occurred_at":"2026-05-18T12:00:00Z","event":{"type":"step_started","step_id":"stp_001","step_index":1,"title":"Add login form"}}

```

---

## Contract 5 — Runtime-error envelope (`ErrorEnvelope`)

### Decisions

- **Free-string `error_code`, documented catalog.** Producers must consult the catalog; consumers handle unknown codes as `internal_error`.
- **Typed-but-unconstrained `error_details: dict[str, Any] | None`.** Per-code structure documented in the catalog.
- **`retriable` and `fatal` are orthogonal.** A failure can be fatal-but-retriable (job over, user can re-approve) or non-fatal-and-retriable (Worker retries internally).
- **`CloudRuntimeJob.last_error: ErrorEnvelope | None`** replaces the flat `error_code` / `error_message` strings. Keep old strings populated for one minor version; drop in v2.0.
- **`cancel_requested` is NOT an error.** Cancel flows through Contract 4's `CancelAcknowledgedPayload` + `JobCancelledPayload`.

### Pydantic

```python
class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "1.0.0"
    error_code: str                          # snake_case; from catalog below
    error_message: str                       # one sentence, UI-displayable
    error_details: dict[str, Any] | None = None
    retriable: bool = False
    fatal: bool
    occurred_at: str
```

### Error code catalog (v1)

| Prefix | Code | When emitted | `error_details` schema |
|---|---|---|---|
| `gate.` | `plan_stale` | Plan's `source_snapshot_id` drifted before approval | `original_snapshot_id`, `current_snapshot_id` |
| `gate.` | `project_busy` | Another job is queued/running/cancelling for the project | `blocking_job_id` |
| `gate.` | `enqueue_failed` | Queue rejected the WorkerEnvelope | `queue_error` |
| `worker.` | `worker_dispatch_failed` | Worker couldn't be started | `reason` (image_pull, unschedulable, etc.) |
| `worker.` | `worker_timeout` | Worker didn't ack within budget | `timeout_seconds` |
| `worker.` | `worker_oom` | Worker out of memory | `memory_limit_mb` |
| `step.` | `step_failed` | Generic Step failure | stage-specific |
| `step.` | `step_timeout` | Step exceeded time budget | `budget_seconds`, `elapsed_seconds` |
| `step.` | `tool_call_failed` | Worker's tool call returned error | `tool`, `tool_error` |
| `step.` | `model_unavailable` | LLM provider 5xx or rate-limited | `provider`, `http_status` |
| `preview.` | `preview_pod_crashed` | Preview pod terminated unexpectedly | `exit_code`, `last_log_lines` |
| `preview.` | `preview_pod_unschedulable` | GKE couldn't schedule | `gke_reason` |
| `preview.` | `network_egress_denied` | Blocked external host (post-Tier 1 #6) | `blocked_host` |
| `preview.` | `package_install_denied` | Blocked by allowlist (post-Tier 2 #15) | `package`, `manager` |
| (none) | `internal_error` | Unexpected exception (fallback) | `exception_class`, `trace_id` |

Catalog grows by appending; not a schema change. Prefix `_.` notation is convention only; the code is the full string (e.g. `gate.plan_stale`).

---

## Contract 6 — Cancel protocol

### Decisions

- **REST verb:** `POST /api/jobs/<job_id>/cancel`. Cancel does NOT flow over SSE.
- **Cooperative interrupt at Step boundaries** (ADR-0004). Mid-Step abandon is not contracted.
- **Latency budgets:** 5s to `cancel_acknowledged`; 30s to `job_cancelled`.
- **No rollback of completed Step effects.**
- **No force-cancel verb.** Janitor (Tier 1 #7) is the backstop for non-cooperative Workers.
- **Queue-side cancellation is best-effort.** Cancelled-while-queued envelopes remain in the queue; Worker checks status on pop and exits idempotently.

### `CloudRuntimeJob.status` enum (locked here)

```python
CloudRuntimeJobStatus = Literal[
    "queued",       # in queue, or popped but not yet executing Step 1
    "running",      # Worker actively executing
    "cancelling",   # cancel signal recorded; Worker winding down
    "cancelled",    # terminal: cancelled by user
    "completed",    # terminal: all Steps successful
    "failed",       # terminal: see last_error
]
```

### New `CloudRuntimeJob` fields

```python
cancel_requested_at: str | None = None
cancel_reason: str | None = None         # optional, max ~200 chars
last_error: ErrorEnvelope | None = None  # introduced in Contract 5
```

### REST surface

```python
class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = None                # max ~200 chars

class CancelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    status: CloudRuntimeJobStatus
    cancel_requested_at: str
```

| Response | Meaning |
|---|---|
| `202 Accepted` | Cancel recorded; watch SSE for `cancel_acknowledged` then `job_cancelled` |
| `409 job_already_terminal` | Job is `cancelled`, `completed`, or `failed`; no-op |
| `404 not_found` | `job_id` not found |

### Worker behavior contract

1. **On WorkerEnvelope pop:** load `CloudRuntimeJob` by `job_id`. If status ∈ `{cancelled, completed, failed}` → exit immediately.
2. **During execution:** poll for cancel signal between Steps. Implementation can use polling, Redis pub/sub, Firestore listener — contract just requires "within 5s of cancel REST call."
3. **On cancel detected:**
   1. Emit `CancelAcknowledgedPayload` (once)
   2. Set `CloudRuntimeJob.status = "cancelling"`
   3. Complete current Step at boundary (do not abandon mid-Step)
   4. Cleanup (close files, terminate preview pod, etc.)
   5. Set `CloudRuntimeJob.status = "cancelled"`
   6. Emit `JobCancelledPayload(cancelled_at_step_id=<current_or_null>)`
   7. Close SSE stream

---

## What Phase 0 produces (single PR scope)

1. New module `src/ham/builder_plan.py` (or similar) containing all Pydantic models above with `extra="forbid"` and matching docstrings linking back to this contract doc.
2. Matching TypeScript types under `frontend/src/lib/ham/builderPlan.ts` (hand-written from this doc; codegen can come later).
3. New persistence module `src/persistence/builder_plan_store.py` analogous to the existing `BuilderRuntimeJobStore`, file-backed under `~/.ham/builder_plans.json` for dev.
4. New `PlanApprovalRecord` persistence (can share the plan store).
5. Extension of `CloudRuntimeJob` with the new fields: `last_error`, `cancel_requested_at`, `cancel_reason`. Keep `error_code` / `error_message` for one minor version.
6. New `BuilderRunEventsStore` (or equivalent) for SSE event log persistence (supports `Last-Event-ID` replay per ADR-0002).
7. Test fixtures: round-trip JSON serialization for every model; discriminated-union validation; status-enum exhaustiveness check.
8. **No API endpoints, no Worker logic, no Planner LLM calls.** Those land in Phase 1 / Phase 2 against this locked contract.

## What is explicitly NOT in Phase 0

- Choice of queue technology (Cloud Tasks vs Pub/Sub vs other)
- Worker implementation (the Manus/Replit-style Planner→Executor→Verifier loop)
- Frontend rendering of Plans, Steps, or the SSE stream
- The Planner LLM prompt / call
- Verifier semantics beyond reserving `step_verification_failed` in the catalog
- Per-step approval, mid-flight re-planning, force-cancel, multi-tab coordination
