# HAM Builder Platform — Context

The chat-to-app builder vertical: how user intent becomes an approved Plan, gets queued, executed in a preview runtime, streamed back to the workbench, and made cancellable.

## Language

**Plan**:
An ordered list of Steps produced by the Planner that, if executed, satisfies a user-requested change. Approved as a unit; queued as a unit; executed as a unit. Concrete schema: `Plan` Pydantic model with `plan_id`, `steps`, `source_snapshot_id`, `planner_confidence`, and related provenance fields.
_Avoid_: todo list, task list, action plan (use **Plan**).

**Step**:
A single atomic operation inside a **Plan** — coarse-grained, human-readable goal (e.g. "Add a login form"). Steps run sequentially within a single **Worker** process; the Worker has latitude to decide tool calls and file edits per Step.
_Avoid_: task, subtask, action, todo item (use **Step**).

**Planner**:
The component that turns a user message + project context into a **Plan**. Runs inline in `POST /api/chat/stream` for builder-mutation turns (after `route_agent_intent` classifies the turn type and `builder_mutation_router` flags it as a mutation). Calls the user's BYO OpenRouter key via `complete_chat_messages_openrouter`; falls back to today's regex `route_agent_intent` flow when no key is configured (per ADR-0009). Streams Plan generation to the chat surface as it produces output.
_Avoid_: orchestrator (that's something else), router, classifier.

**Worker**:
The process that executes one approved **Plan** end-to-end. One Worker per Plan; lives for the duration of the Plan (potentially minutes to hours); emits Step events over the **SSE envelope**; honors a cooperative cancel signal at Step boundaries.
_Avoid_: executor, agent (overloaded), runner.

**Approval gate**:
The point in a Plan's lifecycle where the user must explicitly accept the **Plan** before it is enqueued. State machine: PROPOSED → APPROVED, with STALE as a terminal pre-approval state (snapshot drift blocks approval). Extends — does not replace — the existing `BuilderActionDecision.destructive` + `ask_clarification` lanes.
_Avoid_: review step, confirmation prompt (these are UI affordances; the gate is the state-machine transition).

**WorkerEnvelope** (the **Queue message**):
The payload enqueued on Plan approval. Pointers only — `plan_id`, `job_id`, `workspace_id`, `project_id`, `requested_by`. The Worker fetches the full **Plan** and **CloudRuntimeJob** from their stores on pop. Idempotency key: `job_id`.
_Avoid_: task, queue payload (use **WorkerEnvelope**).

**CloudRuntimeJob**:
The persisted record of a Worker run. Pre-dates the Planner work; lives in [src/persistence/builder_runtime_job_store.py](src/persistence/builder_runtime_job_store.py). Status enum is locked: `queued | running | cancelling | cancelled | completed | failed`. Carries `last_error: ErrorEnvelope | None` and cancel metadata. **Not** the **WorkerEnvelope**.

**SSE envelope** (`SSEEvent`):
The wire format for Worker→browser streaming. One stream per **CloudRuntimeJob** at `GET /api/jobs/<job_id>/stream`. Discriminated union of event types (`step_started`, `step_log`, `step_completed`, `step_failed`, `job_started`, `job_completed`, `job_failed`, `job_cancelled`, `cancel_acknowledged`, `runtime_error`, `heartbeat`) under a single wrapper carrying `seq`, `job_id`, `plan_id`, `occurred_at`. Full replay supported via `Last-Event-ID`.
_Avoid_: event stream (too generic), feed (used by older API).

**ErrorEnvelope**:
The shape of error data emitted in SSE failure events and stored in `CloudRuntimeJob.last_error`. Carries free-string `error_code` (from a documented catalog), `error_message`, optional `error_details`, plus `retriable` and `fatal` flags.
_Avoid_: error payload, exception envelope (use **ErrorEnvelope**).

**Dispatcher endpoint**:
The internal FastAPI route `POST /api/internal/dispatch-worker` that receives push deliveries from Cloud Tasks (per ADR-0007) and schedules a Worker GKE pod. OIDC-authenticated. Returns 200 immediately after scheduling; does not wait for the Worker to finish. The dispatcher is the bridge between the queue and the Worker host.
_Avoid_: queue handler, worker launcher.

**Step executor**:
The CLI-agentic runtime that the **Worker** invokes to actually execute one **Step**. Today: `src/tools/droid_executor.py` or one of the Hermes adapters under `src/ham/worker_adapters/`. The Worker is an orchestrator over the Step executor — it does not embed its own LLM agent loop (per `AGENTS.md` CLI-first execution surface).
_Avoid_: agent, runtime (overloaded).

**Approval card**:
The UI affordance that surfaces a proposed **Plan** for user review. Renders as a rich inline message in the chat thread (one Approval card per chat turn that produced a Plan). Approve / Re-plan buttons; destructive Steps highlighted. On approval, transforms in-place into an **In-flight card** rather than disappearing.
_Avoid_: review dialog, plan modal (these are different UX patterns we did not choose).

**In-flight card**:
The Approval card after approval — same visual position in the chat thread, but with per-Step status indicators that update via the SSE stream as Steps progress. Cancel button visible while job is running. On terminal status (completed / failed / cancelled) the card freezes with a summary line.
_Avoid_: progress panel, run status widget.

## Relationships

- A user message produces zero or one **Plan** (Planner output)
- A **Plan** contains one or more ordered **Steps**
- An approved **Plan** produces exactly one **WorkerEnvelope** and exactly one **CloudRuntimeJob**
- A **WorkerEnvelope** is consumed by exactly one **Worker**
- A **Worker** emits zero or more **SSEEvents** through the per-job SSE stream for the lifetime of its **Plan**
- An **SSEEvent** of type `step_failed`, `job_failed`, or `runtime_error` embeds one **ErrorEnvelope**
- A **CloudRuntimeJob** holds at most one **ErrorEnvelope** as its `last_error`
- The **Approval gate** rejects approval when any **CloudRuntimeJob** for the project is in `{queued, running, cancelling}` (per-project serialization; ADR-0003)

## Example dialogue

> **Dev:** "When the user approves a **Plan**, is the **Worker** running already?"
> **Designer:** "No — approval creates the **CloudRuntimeJob** and pushes a **WorkerEnvelope** onto the queue. The Worker pops it asynchronously and emits `job_started` over the **SSE envelope** when it actually begins."
>
> **Dev:** "What if the user cancels while a **Step** is mid-execution?"
> **Designer:** "Cancel is REST, not SSE. The Worker checks the cancel signal at the next **Step** boundary and emits `cancel_acknowledged`, finishes its current Step, then emits `job_cancelled` with the `cancelled_at_step_id`. Already-completed Steps' effects stay on disk."

## Flagged ambiguities

- **"Job"** in the codebase (`CloudRuntimeJob`) refers to the persisted run record, not the **WorkerEnvelope**. Resolved: `CloudRuntimeJob` for the record, **WorkerEnvelope** for the queue payload, **Plan** for the design artifact.
- **"Agent"** is overloaded — used for the cloud-agent CLI providers (Cursor, Factory, Claude), for the LLM behind the **Planner**, and historically for "**Worker**". Resolved in this context: **Worker** for the runtime process; **Planner** for the LLM-driven planner; "agent" reserved for external CLI providers per `AGENTS.md`.
- **"Cancel"** vs error: cancel is user-initiated termination and flows through `cancel_acknowledged` + `job_cancelled` events, NOT through **ErrorEnvelope**. The `cancel_requested` error code was considered and rejected.
- **"Event"** in the SSE context is always an `SSEEvent` (wire format). The legacy "feed events" used by the older REST polling API are a separate concept; not to be conflated.
