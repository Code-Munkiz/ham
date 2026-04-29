# HAM Durable Coding Runs — Phase 7A

Status: implementation-ready design.

Decision: READY_TO_IMPLEMENT_PHASE_7A.

## Goal

Phase 7A makes long coding, VM, and agent-adjacent work durable so HAM does not
treat an implementation task as one fragile chat response. The phase introduces
a HAM-owned coding-run record, event log, artifact index, read/status APIs, and
minimal UI visibility.

Phase 7A is not a full autonomous coding loop. It is the durable substrate that
future loops can use.

## Strategic fit

- Preserves the architecture contract: Hermes supervises, Droid executes, and
  `memory_heist` provides repo context. The coding-run model records work; it
  does not become an orchestrator.
- Complements `ControlPlaneRun`: that model records committed provider launches
  such as Cursor Cloud Agent and Factory Droid control-plane actions. Phase 7A
  records HAM-owned coding work over time, including checkpoints, events, and
  artifacts.
- Moves chat from "wait for one answer" to "launch or observe a durable run card"
  while keeping approval, cancel, and resume explicit.
- Gives Operations and Inspector enough visibility to debug stuck work without
  building mission graphs, schedulers, critic loops, or IDE control.

## Phase 7A scope

In scope:

- Durable coding-run model.
- Run event model.
- Artifact model.
- Persistence recommendation.
- API contract.
- Minimal chat run-card behavior.
- Minimal Operations and Inspector visibility.
- Status, resume, and cancel behavior.
- Tests and acceptance criteria.

Out of scope:

- Full autonomous coding loop.
- Local machine control.
- Cursor Cloud Agent execution.
- Claude/ChatGPT IDE control.
- Critic/retry loop.
- Workflow scheduler.
- FMO/TEDS workflows.

## Existing repo assets

- `docs/CONTROL_PLANE_RUN.md` defines factual provider launch records and the
  separation from bridge/Hermes run records.
- `src/persistence/control_plane_run.py` already has a bounded Pydantic model,
  server-global store default, optional project mirror, status mapping, and
  capped summary fields.
- `src/api/control_plane_runs.py` exposes read-only list/get APIs for
  `ControlPlaneRun`.
- `src/ham/chat_operator.py` returns structured `operator_result` objects with
  pending launch, droid, Cursor, and run data.
- `src/api/chat.py` carries `operator_result` through `/api/chat` responses.
- `frontend/src/lib/ham/api.ts` already models chat operator payloads/results
  and public control-plane run rows.
- `frontend/src/features/hermes-workspace/screens/chat/workspaceInspectorEvents.ts`
  provides a bounded in-memory Inspector event shape that Phase 7A can replace
  or supplement with durable events.
- `frontend/src/features/hermes-workspace/screens/operations/WorkspaceOperationsScreen.tsx`
  is the current Operations surface for local agents/jobs/activity.
- `src/ham/run_persist.py` and `src/persistence/run_store.py` remain bridge plus
  Hermes-review run history, not this new substrate.

## Proposed data model

### `CodingRun`

One durable row per HAM-owned coding task.

Required fields:

- `coding_run_id`: UUID primary key.
- `schema_version`: integer, start at `1`.
- `project_id`: registered HAM project id.
- `project_root_ref`: optional redacted/root-safe reference; do not expose raw
  private paths to renderer payloads unless already allowed by an existing API.
- `source`: `chat` | `operations` | `api` | `cli`.
- `title`: short user-facing label, capped.
- `user_goal`: original user goal or bounded summary, capped.
- `status`: `created` | `running` | `waiting_for_user` | `paused` |
  `cancel_requested` | `cancelled` | `succeeded` | `failed` | `unknown`.
- `status_reason`: short machine-readable reason, capped.
- `created_at`, `updated_at`: UTC ISO timestamps.
- `started_at`, `last_heartbeat_at`, `finished_at`: nullable UTC ISO timestamps.
- `created_by`: nullable actor attribution compatible with existing Clerk/HAM
  operator attribution.
- `current_step`: nullable capped string.
- `resume_token`: nullable opaque token present only when resumable.
- `cancel_requested_at`: nullable timestamp.
- `control_plane_ham_run_id`: optional link only when a separate
  `ControlPlaneRun` exists; never required.

Deferred fields:

- Parent/child graph edges.
- Retry policy.
- Scheduler metadata.
- Critic verdicts.
- Full prompts, full logs, embeddings, or unbounded metadata.

### `CodingRunEvent`

Append-only event rows for timeline and recovery.

Required fields:

- `event_id`: UUID primary key.
- `coding_run_id`: foreign key.
- `seq`: monotonic integer per run.
- `occurred_at`: UTC ISO timestamp.
- `type`: `created` | `started` | `heartbeat` | `status_changed` |
  `checkpoint` | `message` | `command_started` | `command_finished` |
  `artifact_created` | `approval_required` | `approval_recorded` |
  `resume_requested` | `cancel_requested` | `cancelled` | `failed` |
  `succeeded`.
- `level`: `debug` | `info` | `warning` | `error`.
- `summary`: user-safe capped text.
- `data`: small JSON object with documented keys and hard size cap.

Rules:

- Events are append-only.
- Event payloads must not contain secrets, raw tokens, cookies, private keys, or
  full browser/profile paths.
- Command output must be stored as an artifact or capped excerpt, not inline
  unbounded event data.
- Every status transition must emit a `status_changed` event.
- Every artifact row must have a matching `artifact_created` event.

### `CodingRunArtifact`

Index of outputs produced or attached during a coding run.

Required fields:

- `artifact_id`: UUID primary key.
- `coding_run_id`: foreign key.
- `created_at`: UTC ISO timestamp.
- `kind`: `log` | `diff` | `patch` | `test_output` | `screenshot` |
  `video` | `file_snapshot` | `summary` | `other`.
- `label`: short user-facing label.
- `media_type`: MIME type or `text/plain`.
- `storage_ref`: internal path, content-addressed key, or external artifact ref.
- `size_bytes`: integer.
- `sha256`: content digest.
- `visibility`: `user_visible` | `internal`.
- `redaction_state`: `not_needed` | `redacted` | `blocked`.

Rules:

- Store large content outside the run row.
- Artifacts are immutable after creation.
- New versions create new artifacts linked by event sequence.
- User-visible APIs return metadata plus a download URL, not raw host paths.

## Persistence recommendation

Use SQLite plus artifact files:

- Default DB: `~/.ham/coding_runs/coding_runs.sqlite`.
- Override: `HAM_CODING_RUNS_DB`.
- Artifact root: `~/.ham/coding_runs/artifacts/`.
- Override: `HAM_CODING_RUNS_ARTIFACT_DIR`.
- Optional project mirror: `<project_root>/.ham/coding_runs/` for developer
  inspection only, never the sole source of truth.

Rationale:

- SQLite is in the Python standard library and avoids a new service dependency.
- Long runs need transactional status updates, monotonic event sequence,
  pagination, and filtering that are awkward with one JSON file per event.
- Artifact files keep large logs, patches, screenshots, and videos out of rows.
- The server-global default matches the hosted-first bias already documented for
  control-plane runs.

Minimum tables:

- `coding_runs`
- `coding_run_events`
- `coding_run_artifacts`

Implementation requirements:

- WAL mode where available.
- Foreign keys enabled.
- Atomic event append plus run `updated_at` update in one transaction.
- Hard caps on text fields and JSON payload size.
- Secret redaction before persistence.
- Best-effort migration path by `schema_version`.

## Proposed API contract

All endpoints are under `/api/coding-runs`. Mutating routes require the same
operator-auth pattern as existing chat/operator writes.

### Create run

`POST /api/coding-runs`

Request:

- `project_id`: string.
- `title`: string.
- `user_goal`: string.
- `source`: `chat` | `operations` | `api` | `cli`.
- `start_mode`: `record_only` | `start_now`.

Response:

- `kind`: `coding_run`.
- `run`: public `CodingRun`.

Phase 7A may support only `record_only` if no executor is wired yet.

### List runs

`GET /api/coding-runs?project_id=...&status=...&limit=50&cursor=...`

Response:

- `kind`: `coding_run_list`.
- `project_id`.
- `runs`: newest-first public summaries.
- `next_cursor`: nullable.

### Get run

`GET /api/coding-runs/{coding_run_id}`

Response:

- `kind`: `coding_run`.
- `run`: public `CodingRun`.
- `latest_events`: capped recent events.
- `artifact_count`.

### List events

`GET /api/coding-runs/{coding_run_id}/events?after_seq=...&limit=100`

Response:

- `kind`: `coding_run_event_list`.
- `coding_run_id`.
- `events`.
- `next_after_seq`.

### List artifacts

`GET /api/coding-runs/{coding_run_id}/artifacts`

Response:

- `kind`: `coding_run_artifact_list`.
- `coding_run_id`.
- `artifacts`: metadata only.

### Download artifact

`GET /api/coding-runs/{coding_run_id}/artifacts/{artifact_id}/download`

Response:

- Binary or text response with safe content type.
- 404 when artifact is missing or not visible.

### Status refresh

`POST /api/coding-runs/{coding_run_id}/status`

Behavior:

- Returns current persisted status.
- May append a heartbeat/status event if the owning process reports liveness.
- Must not start new work.

### Resume

`POST /api/coding-runs/{coding_run_id}/resume`

Behavior:

- Allowed only from `paused`, `waiting_for_user`, `failed` when resumable, or
  `unknown` when a valid `resume_token` exists.
- Requires explicit user approval.
- Appends `resume_requested`.
- In Phase 7A, may return `202 accepted` plus `status: paused` if executor
  resume is not wired. The durable request is still recorded.

### Cancel

`POST /api/coding-runs/{coding_run_id}/cancel`

Behavior:

- Allowed from `created`, `running`, `waiting_for_user`, `paused`, or `unknown`.
- Sets `cancel_requested` immediately and appends `cancel_requested`.
- If an owning process acknowledges cancellation, transition to `cancelled`.
- If no owner is live, remain `cancel_requested` with `status_reason:
  cancel_requested_owner_unavailable`.

## Proposed UI contract

### Minimal chat run card

When a chat turn creates or references a `coding_run_id`, render a compact card
inside the assistant response:

- Title.
- Status pill.
- Current step.
- Last updated time.
- Latest event summary.
- Artifact count.
- Actions: `View`, `Refresh`, `Cancel` when cancellable, `Resume` when
  resumable.

The chat card must not stream full logs into the transcript. It should poll or
refresh durable status and link to the detailed view.

### Minimal Operations visibility

Add a "Coding Runs" section or tab to Operations:

- Recent runs filtered by project.
- Status, title, updated time, current step, artifact count.
- Empty state that explains no durable coding runs have been created.
- Error state when the API is unavailable.
- Click row to open detail.

Do not add scheduling controls in Phase 7A.

### Minimal Inspector visibility

For the selected run:

- Summary header with status and cancel/resume affordances.
- Timeline from durable `CodingRunEvent` rows.
- Artifact list with download/open actions.
- Logs tab showing capped event data and artifact metadata.

Inspector events should be read from the durable API when a `coding_run_id` is
present. Existing in-memory chat Inspector events can remain for ordinary chat
turns.

## Status, resume, and cancel semantics

- `created`: row exists, no execution has started.
- `running`: owner has started and heartbeat is current enough.
- `waiting_for_user`: run needs approval, clarification, or credentials from the
  user.
- `paused`: no active owner, but run has a valid checkpoint/resume token.
- `cancel_requested`: user requested cancellation; owner has not acknowledged.
- `cancelled`: terminal cancellation acknowledged or safely finalized.
- `succeeded`: terminal success.
- `failed`: terminal failure with error summary.
- `unknown`: persisted state cannot be reconciled with owner/process state.

Resume:

- Never infer resume from a chat reload.
- Requires explicit user action.
- Must use `resume_token` or equivalent checkpoint data.
- Must append a durable event even when actual executor resume is deferred.

Cancel:

- Must be durable before best-effort process interruption.
- Must be idempotent.
- Must not delete artifacts or events.
- Must not be confused with retry or rollback.

## Test plan

Unit tests:

- Model validation rejects unknown statuses, oversized fields, unsafe artifact
  refs, and invalid UUIDs.
- Event append increments `seq` monotonically per run.
- Status transition writes both run status and event in one transaction.
- Artifact create writes metadata, digest, size, and matching event.
- Redaction removes secrets from event data and summaries.
- Resume policy accepts only resumable states.
- Cancel is idempotent and preserves artifacts/events.

API tests:

- `POST /api/coding-runs` creates a durable row.
- `GET /api/coding-runs` filters by project/status and paginates.
- `GET /api/coding-runs/{id}` returns bounded latest events.
- `GET /events` returns ordered events with `after_seq`.
- `GET /artifacts` returns metadata without host paths.
- `download` returns content only for visible artifacts.
- `resume` records `resume_requested` and rejects non-resumable terminal states.
- `cancel` moves active runs to `cancel_requested` and is idempotent.
- Mutating endpoints enforce operator auth.

UI tests:

- Chat renders a run card when `operator_result.data.coding_run_id` is present.
- Run card buttons call refresh/cancel/resume endpoints as appropriate.
- Operations lists recent coding runs and handles empty/error states.
- Inspector renders durable timeline and artifact metadata.
- Long logs are not rendered inline in chat.

Acceptance criteria:

- A coding run can outlive a chat HTTP response and be fetched after API restart.
- A user can see current status, latest events, and artifacts from API and UI.
- Cancel intent is durable even if no owner is live.
- Resume intent is durable and gated by explicit user action.
- No Phase 7A API or UI implies scheduler, Cloud Agent execution, local machine
  control, IDE control, critic retry, or full autonomous loop.
- Tests cover model, persistence, API, and minimal UI behavior.

## Red flags

- Reusing `ControlPlaneRun` for coding-run events and artifacts.
- Storing full logs, prompts, provider payloads, or review blobs in the run row.
- Adding graph, retry, scheduler, or mission semantics under the Phase 7A name.
- Treating `resume` as automatic continuation after page reload.
- Treating `cancel_requested` as proof that work stopped.
- Exposing host paths or raw artifact paths to the renderer.
- Letting chat transcript state be the only source of truth.
- Adding Cloud Agent, Claude/ChatGPT IDE, local machine control, FMO, or TEDS
  behavior while implementing this phase.

## Phase 7A implementation sequence

1. Add `CodingRun`, `CodingRunEvent`, and `CodingRunArtifact` models with caps,
   validation, and public serialization helpers.
2. Add SQLite-backed `CodingRunStore` with migrations, event append, artifact
   registration, status transitions, list/get, and pagination.
3. Add `/api/coding-runs` read/create/status/resume/cancel/artifact routes.
4. Add tests for model, store, API auth, event ordering, resume, cancel, and
   artifact visibility.
5. Add chat response support for `coding_run_id` in `operator_result.data`
   without changing existing ordinary chat behavior.
6. Add minimal chat run card, Operations list/detail entry point, and Inspector
   durable event/artifact view.
7. Add UI tests for run-card and durable visibility behavior.
8. Update `VISION.md` and related run docs only after behavior lands.

## Decision

READY_TO_IMPLEMENT_PHASE_7A.

Reason:

- The repo already has adjacent patterns for bounded run records, chat operator
  results, read APIs, and Operations/Inspector surfaces.
- Phase 7A can be implemented as a narrow durability layer without violating
  architecture boundaries or pulling in out-of-scope execution systems.
- The key implementation risk is scope creep, not technical uncertainty.
