# Phase 2 Design — Manus/Replit Parity

**Status:** Locked 2026-05-19 via `/grill-with-docs`. Builds on Phase 0 contracts ([`docs/PHASE_0_CONTRACTS.md`](PHASE_0_CONTRACTS.md)) and Phase 1 infrastructure (PRs #347–#353 plus catalog patch).
**Scope:** Six remaining Tier 1 items from [`docs/MANUS_PARITY_ROADMAP.md`](MANUS_PARITY_ROADMAP.md) — the items that touch the hot files (`chat.py`, `builder_sources.py`, `WorkspaceWorkbench.tsx`) and must serialize per the roadmap's "Phase 2" section.
**Glossary:** [`CONTEXT.md`](../CONTEXT.md). **Rationale archive:** ADRs [`0001`](adr/0001-plan-is-unit-of-work.md) through [`0011`](adr/0011-llm-scaffold-staged-by-template-kind.md). New ADRs from this design pass: [`0009`](adr/0009-planner-byo-openrouter-with-regex-fallback.md), [`0010`](adr/0010-sse-migration-hard-cut.md), [`0011`](adr/0011-llm-scaffold-staged-by-template-kind.md).

This is a design specification, not an implementation. The output of Phase 2 design is the spec; the work of writing it as code happens across multiple sequential PRs (per the roadmap's "serialize, review each PR" framing).

The doc is split into Phase 2a (backend data flow) and Phase 2b (frontend UX) — both will ship via `/to-prd` and `/to-issues` as Phase 1 did, but each is its own implementation pass.

---

## Architectural anchor

Phase 0 laid the pipes. Phase 1 lit the security and infra perimeter. Phase 2 carries traffic.

```
User chat turn (POST /api/chat/stream)
    │
    ▼
route_agent_intent (existing regex)
    │
    ├── normal_chat / agent_preview / agent_status / agent_cancel / agent_continue   → today's flow
    │
    └── (builder mutation detected by builder_mutation_router)
              │
              ▼
         Planner LLM (Phase 2a — inline; streamed via SSE; BYO OpenRouter key per ADR-0009)
              │
              ├── No BYO key → fallback to today's regex-driven scaffold flow
              │
              └── Has BYO key → Plan produced, persisted to BuilderPlanStore
                       │
                       ▼
                  Approval card rendered (Phase 2b)
                       │
                       └── User approves
                              │
                              ▼
                       Approval gate validates per-project serialization (ADR-0003)
                              │
                              ▼
                       Cloud Tasks enqueue WorkerEnvelope (ADR-0007)
                              │
                              ▼
                       Cloud Tasks pushes to POST /api/internal/dispatch-worker
                              │
                              ▼
                       Dispatcher schedules GKE pod, returns 200 to Cloud Tasks
                              │
                              ▼
                       Worker pod boots
                              │
                              ├── Loads Plan from BuilderPlanStore
                              ├── For each Step:
                              │     · Delegates to droid_executor / Hermes adapter (ADR-equivalent: AGENTS.md CLI-first)
                              │     · Captures stdout, applies changes to source snapshot
                              │     · Emits SSEEvents to BuilderRunEventsStore
                              │     · Checks cancel signal at Step boundary (ADR-0004)
                              ├── Invokes builder_verifier at end (Phase 1 #19; once per Plan)
                              └── Updates CloudRuntimeJob to terminal status

Browser consumes per-job SSE stream (ADR-0002; Phase 2b useJobStream hook)
    │
    ▼
In-flight card updates Step-by-Step in chat thread (Phase 2b)
    │
    ├── Cancel button visible during running → POST /api/jobs/<id>/cancel
    │   then status flows cancelling → cancelled via SSE (ADR-0004)
    ├── step_failed / job_failed → inline error rendering + terminal assistant message
    └── job_completed → frozen summary card; user moves on
```

---

## Phase 2a — Backend data flow

### Subsystem 1 — Planner

#### Decisions

- **Placement:** inline in `POST /api/chat/stream`. The Planner runs as part of the existing chat-stream handler, producing SSE events that the chat UI consumes. One HTTP round-trip per turn; no separate planning endpoint.
- **LLM source:** user's BYO OpenRouter key, via the existing `complete_chat_messages_openrouter` path in `src/llm_client.py` (per ADR-0009).
- **No-key fallback:** if `normalized_openrouter_api_key()` returns empty, skip the Planner entirely and route the turn through today's regex `route_agent_intent` + `builder_mutation_router` flow (per ADR-0009).
- **Model:** same as chat by default (`HERMES_GATEWAY_MODEL` / `DEFAULT_MODEL`). Optional `HAM_PLANNER_MODEL` env override for users who want a different model for planning (e.g. cheaper/faster).
- **Context:** reuse `memory_heist`'s per-role budget. Add a `planner` role with a ~4K-token default budget for project context. The Planner sees: latest user message + last 4 turns of conversation + source snapshot file tree + top 5–10 file contents selected by memory_heist's heuristic + active scaffold template id + CONTEXT.md / SWARM.md instruction excerpts.
- **Coexistence with `route_agent_intent`:** the regex stays as first-stage classifier for non-builder intents (`normal_chat`, `agent_preview`, `agent_launch`, `agent_status`, `agent_cancel`, `agent_continue`, `agent_choose_provider`). For builder-mutation turns (`builder_mutation_router` returns `mutate`), dispatch to the Planner. Other intents stay on today's flow.
- **Reliability:** if the Planner LLM returns a payload that fails Pydantic validation against the Phase 0 `Plan` schema, retry once with a stricter system prompt appended ("Your previous response was not valid JSON for the Plan schema. Output ONLY the JSON object."). If the second attempt also fails, emit an error to chat ("Planner couldn't produce a valid Plan; please rephrase") and let the user re-prompt. No synthetic fallback Plan.

#### Component contract

- Module: `src/ham/builder_planner.py` (or analogous path).
- Public API:
  - `produce_plan(*, user_message: str, project_id: str, workspace_id: str, requested_by: str, conversation_history: list[ChatTurn], source_snapshot_id: str | None) -> Plan | None`
  - Returns a Phase 0 `Plan` model on success; `None` when the no-key fallback triggers (caller dispatches to legacy flow).
  - May raise `PlannerOutputInvalidError` after the retry budget is exhausted; chat handler maps this to an error SSE event.
- Persistence: on success, the returned `Plan` is written to `BuilderPlanStore` along with a `PlanApprovalRecord(state="proposed")`.
- SSE events emitted during streaming: a small additive set on the existing chat-stream channel (NOT the per-job stream — the per-job stream only exists after approval):
  - `planner_started` — informational
  - `planner_progress` — interim Steps as they generate (optional; only if the model is streamed)
  - `plan_proposed` — final event with the `plan_id`; UI uses this to render the Approval card

### Subsystem 2 — Queue dispatcher

#### Decisions

- **Transport:** Cloud Tasks, per ADR-0007. No re-litigation.
- **Push target:** `POST /api/internal/dispatch-worker` mounted on the existing FastAPI service (Cloud Run-hosted).
- **Auth:** OIDC token verification on the dispatcher endpoint. Cloud Tasks injects the token via its built-in OIDC support; the FastAPI route validates the audience claim.
- **Queue creation:** infrastructure-as-code (the existing GCP setup pattern — Terraform if HAM uses it, gcloud scripts otherwise). One queue per environment (staging vs prod). Documented in the deploy guide alongside `docs/DEPLOY_CLOUD_RUN.md`.
- **Retry policy:** Cloud Tasks default with explicit caps. Suggested values for the implementation PR: `max_attempts=3`, `min_backoff=10s`, `max_doublings=2`. The Worker is idempotent on re-delivery (per ADR-0003 and Phase 0 Worker contract).
- **Body size:** `WorkerEnvelope` is pointer-only (~1 KB). Cloud Tasks' 100 KB body limit is never close.

#### Component contract

- The dispatcher endpoint is internal; it is NOT exposed to the public API surface. Mount it under `/api/internal/` and verify the OIDC service-account identity matches the Cloud Tasks service account.
- Handler responsibilities:
  1. Validate the OIDC token's `iss` and `aud` claims
  2. Parse the request body as `WorkerEnvelope` (Phase 0 schema; `extra="forbid"`)
  3. Idempotency check: load `CloudRuntimeJob` by `job_id` — if its status is already terminal, return 200 and skip
  4. Schedule a GKE Worker pod (using the existing preview-pool / GKE client) passing `job_id` as an env var
  5. Return 200 to Cloud Tasks immediately (does NOT wait for the Worker)
- Failure modes:
  - GKE scheduler failure → return non-2xx to Cloud Tasks (which will retry); also set `CloudRuntimeJob.last_error = worker.worker_dispatch_failed`
  - Token validation failure → return 401; Cloud Tasks does not retry on auth failures

### Subsystem 3 — Worker

#### Decisions

- **Hosting:** GKE pod, scheduled by the dispatcher endpoint. Same security spec as preview pods (gVisor sandbox, non-root, read-only-FS, dropped caps, NetworkPolicy egress label from Phase 1 #6).
- **Execution model:** the Worker is an orchestrator, not an embedded LLM agent. For each Step, it delegates to a Step executor — one of HAM's existing CLI-agentic runtimes: `src/tools/droid_executor.py`, the Claude Agent adapter in `src/ham/worker_adapters/`, or the Hermes adapter (selected per the existing `DroidRecord` registry conventions). The Worker is the loop; the Step executor is the muscle. Aligns with AGENTS.md "CLI-first execution surface."
- **Cancel polling:** the Worker checks `CloudRuntimeJob.status` from the persistence store between Steps. To honor ADR-0004's 5-second acknowledge target during long-running Steps, the Worker passes a `cancel_check: Callable[[], bool]` into each Step executor invocation so the executor can poll mid-Step. On cancel detection: emit `cancel_acknowledged`, finish current Step (per ADR-0004 step-boundary), cleanup, emit `job_cancelled`.
- **SSE event emission:** Worker writes directly to `BuilderRunEventsStore` (Phase 0). The API's `GET /api/jobs/<id>/stream` reads from that same store and streams to the browser. The Worker does not call the API; it touches the same backing store.
- **Verifier integration:** invoked once at the end of the Plan (per Phase 2 design decision). After all Steps complete, the Worker calls `builder_verifier.run(plan, preview_url)`. Pass → emit `job_completed`. Fail → emit `step_failed` (attributed to the final Step) carrying `STEP_VERIFICATION_FAILED` from the Phase 0 catalog, then `job_failed`.
- **Snapshot handling:** the Worker reads the source snapshot at start (pinned to `Plan.source_snapshot_id`), applies Step changes in-place, captures a new snapshot at end. Existing `BuilderSourceStore` patterns. Per-Step snapshots (rewind) are Tier 2 #11, NOT Phase 2.
- **Terminal status:**
  - all Steps succeed + verifier passes → `completed`
  - any Step's executor returns failure → `failed`, `last_error.error_code = step.step_failed` (or a more specific `step.*` code from the catalog)
  - verifier fails → `failed`, `last_error.error_code = step.step_verification_failed`
  - cancel requested + honored → `cancelled`
  - dispatch failure / OOM / preview pod crash → `failed`, `last_error.error_code` from the catalog's `worker.*` or `preview.*` namespaces

#### Component contract

- Module: `src/ham/builder_worker.py` (or analogous path).
- Pod entrypoint: a Python script that reads `HAM_WORKER_JOB_ID` from env, calls `BuilderWorker(job_id).run()`, exits.
- Public API of the `BuilderWorker` class:
  - `run() -> None` — the full lifecycle: load Plan, execute Steps, run verifier, update terminal status
  - `_execute_step(step: Step) -> StepResult` — single Step execution via the configured Step executor
  - `_check_cancel() -> bool` — reads `CloudRuntimeJob.status` and returns True if `cancelling` or `cancelled`
- The Worker is single-process, single-Plan. No threading inside the Worker itself (Step executors may use subprocesses).

### Per-job SSE API route (PR 1 — required before PR 3)

Phase 0 Contract 4 and ADR-0002 define `GET /api/jobs/<job_id>/stream`, but the route is **not on `main` yet**. PR 1 must land it alongside the Worker and stores so PR 3's `useJobStream` hook has a real backend to connect to.

#### Decisions

- **Ownership:** PR 1 (backend foundation). PR 3 is frontend-only for this stream (delete legacy polling consumer/endpoints; do **not** add a second implementation of the per-job route).
- **Data source:** reads persisted events from `BuilderRunEventsStore` (same store the Worker writes to in Subsystem 3).
- **Replay:** honors `Last-Event-ID` for reconnect (ADR-0002); monotonic `seq` per `job_id`; 15s heartbeat when idle (Phase 0 Contract 4).
- **Auth:** same Clerk/session gate as other builder control-plane routes (match existing `builder_sources` / workspace permission patterns).

#### Component contract

- Route: `GET /api/jobs/<job_id>/stream` → `text/event-stream` (`SSEEvent` wire format from Phase 0).
- Module: new `src/api/jobs.py` (or a small route block on `src/api/server.py` — follow existing FastAPI router conventions).
- Handler responsibilities:
  1. Load `CloudRuntimeJob` by `job_id`; `404` if missing
  2. Stream events from `BuilderRunEventsStore` starting after `Last-Event-ID` (or from `seq=1` on fresh connect)
  3. Close the stream when the job reaches a terminal status (`completed`, `failed`, `cancelled`)
- Tests: `tests/test_jobs_stream.py` (or equivalent) with fake store fixtures; no browser required.

---

## Phase 2b — Frontend UX

### Subsystem 4 — SSE migration

#### Decisions

- **Prerequisite:** PR 1 merged `GET /api/jobs/<job_id>/stream` (see Per-job SSE API route above). This PR does not implement that route.
- **Migration strategy:** hard cut in one PR (per ADR-0010). Polling code for the activity feed is deleted; SSE consumer is the only path.
- **Consumer architecture:** a custom `useJobStream(jobId)` React hook in `frontend/src/lib/ham/useJobStream.ts`. Owns the EventSource, parses incoming `SSEEvent` JSON, narrows by `event.type` from the Phase 0 discriminated union, exposes `events`, `connectionState`, `lastSeq` to consumers. Honors `Last-Event-ID` on reconnect (per ADR-0002).
- **Lifecycle:** the hook opens the EventSource when a `jobId` is provided, closes it when the component unmounts or the job reaches a terminal status, and reconnects automatically on transient disconnect.
- **No new dependency:** the SSE plumbing for `POST /api/chat/stream` already exists in `frontend/`; the hook reuses the same EventSource patterns.

#### Component contract

- Module: `frontend/src/lib/ham/useJobStream.ts`.
- Public API:
  - `useJobStream(jobId: string | null) → { events: SSEEvent[], connectionState: "connecting"|"open"|"closed"|"error", lastSeq: number }`
  - Returns empty `events` and `closed` state when `jobId` is `null` (e.g. before a Plan is approved).
- Test surface: `useJobStream.test.ts` with vitest + a fake `EventSource` global.

### Subsystem 5 — Approval card UI

#### Decisions

- **Rendering:** rich inline card in the chat thread (Cursor / Replit / Manus pattern). One Approval card per chat turn that produced a Plan.
- **Card contents:**
  - Header: brief Plan summary ("4 steps; touches the auth flow")
  - Step list: title + description + destructive badge (red, for Steps where `requires_approval=true`)
  - Actions: `Approve` (primary) and `Re-plan` (secondary)
  - STALE state: card greys out with a banner ("Project has changed since this plan was created; ask me again"); `Approve` button disabled; only `Re-plan` is clickable
- **Approve action:** `POST /api/plans/<plan_id>/approve`. On 202: card transitions in-place to the In-flight card (Subsystem 6). On 409 `project_busy`: error banner ("Another build is running for this project; cancel it first"). On 409 `plan_stale`: transitions to STALE banner.
- **Re-plan action:** opens a small inline prompt asking what to change; the user's reply becomes a new chat message that triggers the Planner again with conversation history (per ADR-0001 pre-approval Plans are ephemeral).

#### Component contract

- Component: `frontend/src/features/hermes-workspace/chat/ApprovalCard.tsx`.
- Props: `plan: Plan`, `approvalState: PlanApprovalState`, `onApprove: () → void`, `onReplan: (request: string) → void`.
- Persistence: the card reads `Plan` from the chat-stream `plan_proposed` event payload; subsequent state transitions come from `useJobStream` once approval kicks off a job.

### Subsystem 6 — In-flight card UI

#### Decisions

- **In-place transformation:** on approval, the same card visually transforms — buttons become per-Step status indicators driven by `useJobStream`. The chat-thread position is preserved (the user does NOT need to scroll to a different surface).
- **Step statuses:** pending (∘) → running (▶, animated) → completed (✓) or failed (✗).
- **Cancel button:** visible while job is `running` or `cancelling`. Disabled with label "Cancelling…" once clicked. See Subsystem 7.
- **Terminal display:** on `job_completed` / `job_failed` / `job_cancelled`, the card freezes with a one-line summary footer. Subsequent chat messages render below it as normal.

### Subsystem 7 — Cancel UX

#### Decisions

- **Placement:** the cancel button lives in the In-flight card (Subsystem 6). No top-bar cancel; no slash-command cancel.
- **API call:** `POST /api/jobs/<job_id>/cancel`. On 202: button disables, label "Cancelling…". On 409 `job_already_terminal`: button hides (job has already finished).
- **States during wind-down (per ADR-0004):**
  - **Click received:** button → disabled, label "Cancelling…"; status text "Sending cancel signal…"
  - **`cancel_acknowledged` SSE event received:** status text "Cancelling — current step finishing…"
  - **`job_cancelled` SSE event received:** card freezes; summary "Cancelled after Step N of M. Steps 1–N's changes were applied."
  - **30 seconds elapsed without `job_cancelled`:** small warning text appears below status ("Cancellation taking longer than expected; the janitor will force-terminate"). No automatic refresh, no error; the janitor (Phase 1 #7) is the backstop.
- **No rollback affordance:** per ADR-0004, already-completed Steps' file changes stay. The summary explicitly tells the user this so they don't expect undo.

### Subsystem 8 — Runtime errors in chat

#### Decisions

- **Inline rendering on the In-flight card:** when `step_failed` or `runtime_error` SSE events arrive, the affected Step (or the most-recent Step for `runtime_error`) shows a red status indicator plus an expandable details section: `error_code` badge (monospace, for grep-ability) + `error_message` (one line, UI-displayable) + a truncated view of `error_details`.
- **Terminal assistant message on `job_failed`:** when the job reaches terminal `failed` status, a new assistant message appears below the (frozen) In-flight card. Contents: friendly error summary ("Plan failed: <error_message>") + action buttons `Try again` (re-uses the prior Plan as a fresh Planner input) and `Edit and re-plan` (opens the inline re-plan prompt from Subsystem 5).
- **Error code visibility:** the badge with `error_code` is always shown next to the expanded error. This makes audit / postmortem grep'ing trivial — users and developers see the same string the catalog (`src/ham/builder_error_codes.py`) defines.
- **No separate error panel:** errors live in the chat surface, not in a workbench devtools-like panel. Aligns with the "everything is a chat conversation" UX premise.

### Subsystem 9 — LLM-generated scaffolds (staged migration per ADR-0011)

#### Decisions

- **Strategy:** staged by template kind (per ADR-0011). Phase 2 ships the LLM-scaffold path alongside the existing deterministic path; routing per template kind decides which path executes.
- **Routing:**
  - Template kind in `{"calculator", "tetris"}` → existing `src/ham/builder_chat_scaffold.py` path (unchanged)
  - All other kinds (new in Phase 2: `todo`, `dashboard`, `landing-page`, ...) → new `src/ham/builder_llm_scaffold.py` path
- **`builder_llm_scaffold` contract:**
  - Public API: `generate_scaffold(plan: Plan, project_id: str, workspace_id: str) -> ScaffoldResult`
  - Internally: one LLM call (via `complete_chat_messages_openrouter`, BYO key) with the Plan + Step list as input; produces a set of file changes (path → content); applies via the existing `BuilderSourceStore` pattern
  - Output gated by `builder_verifier` (Phase 1 #19) at end-of-Plan: scaffold failures surface as `step.step_verification_failed`
- **No deterministic-path deprecation in Phase 2:** the existing `~1400 LoC` of templates stay untouched. Tier 2 follow-up work A/B tests LLM vs deterministic on calculator/tetris and deprecates incrementally.
- **Template registry:** introduce `src/ham/builder_template_kinds.py` (or extend an existing module) that lists the known kinds plus their routing target (`deterministic` vs `llm`). Adding a new kind = appending to that registry.

#### Component contract

- Module: `src/ham/builder_llm_scaffold.py`.
- Routing helper: `select_scaffold_path(template_kind: str) -> Literal["deterministic", "llm"]`.
- Worker integration: in Subsystem 3's Step execution loop, when a Step's intent is "scaffold a new project from template kind X", the Worker calls `select_scaffold_path(X)` and dispatches to the right path.

---

## What Phase 2 produces (PR scope; sequential per the roadmap)

Per the roadmap's "Phase 2 — serialize, review each PR" framing, the implementation flows through 5–8 PRs landing one at a time. Rough order:

1. **Backend foundation:** Planner module + dispatcher endpoint + Worker pod orchestration + **`GET /api/jobs/<job_id>/stream`** (Phase 0 / ADR-0002; reads `BuilderRunEventsStore`). NOT yet wired to chat. Tests against fakes.
2. **Wire Planner into chat-stream:** `route_agent_intent` + `builder_mutation_router` → Planner path. New `plan_proposed` SSE event. No UI yet.
3. **SSE migration (hard cut per ADR-0010):** `useJobStream` hook + delete polling. **Frontend only** for the per-job stream (PR 1 owns the route). No new UI surfaces in this PR — just the consumer plumbing.
4. **Approval card UI:** `ApprovalCard` component + chat-stream integration to render it on `plan_proposed`.
5. **In-flight card + Cancel UX:** transform-in-place + cancel button + SSE-driven status. Subsystems 6 + 7 together (they share the same component).
6. **Runtime errors in chat:** inline error rendering + terminal-failure assistant message.
7. **LLM-scaffold path:** new `builder_llm_scaffold` module + routing registry. Calculator/Tetris stay on deterministic.
8. **Verifier integration at Worker end-of-Plan:** wire `builder_verifier` into the Worker's terminal-step path.

Each PR is independently reviewable; subsequent PRs depend on prior ones merging.

## What is explicitly NOT in Phase 2

- **Tier 2 items entirely:** snapshot + rewind, real publish target, BYO key UI consolidation, project export, lint/typecheck verifier gate, GitHub OAuth, content-addressed snapshot diff, user-writable skills.
- **Tier 3 items entirely.**
- **A/B testing or deprecation of `builder_chat_scaffold.py`:** Phase 2 keeps it; Tier 2 evaluates and deprecates incrementally.
- **Per-Step verification:** verifier runs once at end of Plan; per-Step is a future possibility, NOT shipped now.
- **Per-Step git commits / per-Step rewind:** matches Tier 2 #11 (deferred).
- **Top-bar cancel button or `/cancel` slash command:** per-card cancel only.
- **A separate error panel in the workbench:** errors render in chat.
- **A new SSE library or test runner dependency:** vitest + custom hook are sufficient.
- **A queue dashboard or admin UI:** Cloud Tasks' GCP console is the operational surface; HAM does not embed it.

## Coordination with Phase 0/1

- Phase 0 schemas: every Plan / WorkerEnvelope / SSEEvent / ErrorEnvelope shape consumed here is unchanged. Phase 2 imports; it does NOT redefine.
- Phase 1 infra: Sentry SDK init (ADR-0008) + request-ID middleware fires on every chat-stream + dispatcher + cancel request. Janitor (Phase 1 #7) is the cancel backstop. NetworkPolicy egress (ADR-0006) constrains Worker pod outbound; LLM provider hosts are not on the allowlist by design (Worker calls LLMs via the API, not directly from the pod — confirmed by Phase 2 design).
- Phase 1 catalog patch: `STEP_VERIFICATION_FAILED` (Phase 1 follow-up) is the verifier failure code used by Subsystem 3.
- Phase 0 stores: `BuilderPlanStore` and `BuilderRunEventsStore` (Phase 0 #332) now have real callers — the Planner writes to them; the Worker writes to them; the API streams from them.

## Handoff path

1. `/to-prd` against this doc produces two PRDs — one for Phase 2a (Subsystems 1–3) and one for Phase 2b (Subsystems 4–9), since the roadmap explicitly wants serialized PR review per item. Alternative: one PRD covering both with a sequential implementation note.
2. `/to-issues` splits each PRD into the per-PR implementation tickets listed above.
3. PRs land sequentially; review each.
4. Phase 2 closes when the 8th PR merges; Tier 1 is then complete.
