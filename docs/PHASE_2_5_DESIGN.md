# Phase 2.5 — Operational close-out of Tier 1

Phase 2 shipped the code-level Tier 1 surface (Planner → Approval gate → Cloud Tasks dispatch → Worker pod → SSE → Cancel) but three boundary-crossing surfaces ship as no-op stubs and three persistence stores are file-only at `~/.ham/*.json`. The API on Cloud Run and the Worker on GKE cannot share data; the enqueue and pod-scheduling hooks return without doing anything. **Phase 2.5 closes the operational gap so Tier 1 is live, not just compiled.**

## Stubs being replaced

| File | Stub | Replacement |
|---|---|---|
| `src/ham/builder_plan_approval_service.py` | `_NoOpWorkerEnqueue` | `BuilderWorkerEnqueueCloudTasks` (new) |
| `src/api/internal_dispatcher.py` | `_DisabledPodScheduler` | `WorkerPodSchedulerGKE` (new) |
| `src/persistence/builder_plan_store.py` | file-only | Firestore variant + env-gated factory |
| `src/persistence/builder_runtime_job_store.py` | file-only | Firestore variant + env-gated factory |
| `src/persistence/builder_run_events_store.py` | file-only | Firestore variant + env-gated factory |

Stubs remain as the default (no env, no GCP) so local dev and tests keep working unchanged.

## Decisions locked (see ADRs 0012–0015)

| Decision | Choice | ADR |
|---|---|---|
| Worker→browser events transport | Worker writes Firestore; API polls Firestore every 500ms inside the per-job SSE handler | ADR-0012 |
| Event `seq` assignment | In-memory counter in Worker (one Worker per `job_id` is already an invariant) + Firestore `create()`-only writes + startup guard that fails loudly if events already exist for a supposedly-fresh job | ADR-0013 |
| Worker pod spec | K8s `Job` (`backoffLimit: 0`, `restartPolicy: Never`, `ttlSecondsAfterFinished: 3600`), same image as API with different CMD, env-vars-only bootstrap, Workload Identity, namespace-scoped RBAC | ADR-0014 |
| Worker pod egress | No NetworkPolicy in Phase 2.5; documented as temporary; deferred to Phase 3 hardening | ADR-0015 |

## Schema

```
builder_plans/{plan_id}
  └─ Plan fields + nested map: approval: { state, proposed_at, approved_at, stale_at, stale_reason }

builder_runtime_jobs/{job_id}
  └─ CloudRuntimeJob fields (flat doc, model_dump)

builder_run_events/{job_id}/events/{seq:010d}
  └─ SSEEvent fields (zero-padded seq is the document ID → free lex-order)
```

Layout note: the file-backed `BuilderPlanStore` keeps separate `plans` and `approval_records` arrays in one JSON file. The Firestore variant nests approval inside the Plan document because it's 1:1 and always read together. The `BuilderPlanStoreProtocol` is unchanged — callers don't care about the physical layout.

## Worker bootstrap contract

The K8s Job pod receives these env vars and nothing else:

| Var | Purpose |
|---|---|
| `HAM_JOB_ID` | The `CloudRuntimeJob.id` to execute |
| `HAM_PLAN_ID` | The Plan ID the Worker expects (verified against `Job.metadata.plan_id`) |
| `HAM_WORKSPACE_ID` | Verified against `Job.workspace_id` |
| `HAM_PROJECT_ID` | Verified against `Job.project_id` |
| `HAM_WORKER_IMAGE` | The full digest-pinned image ref (`gcr.io/.../ham@sha256:...`) — required; Worker logs it at startup |
| `HAM_*_STORE_BACKEND=firestore` | Activates the Firestore variants of the three stores |
| `HAM_FIRESTORE_PROJECT_ID`, `HAM_FIRESTORE_DATABASE` | Firestore project + database (existing convention) |

On startup, `src/ham/worker_main.py`:

1. Logs the build identity (image ref).
2. Fetches the `CloudRuntimeJob` and `Plan` from Firestore.
3. Verifies `Job.workspace_id == HAM_WORKSPACE_ID`, `Job.project_id == HAM_PROJECT_ID`, `Job.metadata['plan_id'] == HAM_PLAN_ID`. Fails loudly on mismatch.
4. Delegates to `BuilderWorker(job_id).run()` (which already implements the Step loop, SSE emission, cancel-check at step boundaries, and terminal-status writes per Phase 2 PRs #355–#362).
5. On unhandled exception, marks the Firestore Job `failed` with an `ErrorEnvelope` before exiting nonzero. **Does not rely on K8s `Job` failure status alone** (3b guardrail).

## Cancel protocol (unchanged from Phase 2)

`POST /api/jobs/{job_id}/cancel` sets `CloudRuntimeJob.status=cancelling` + `cancel_requested_at`. Worker polls the Job at every Step boundary; on detection, emits `cancel_acknowledged`, finishes the in-flight Step, emits `job_cancelled`, transitions to `cancelled`, exits 0. ADR-0004 budget: 5s ack target, 30s terminal target. No mid-Step abandon.

## Dispatcher idempotency strengthening

Phase 2 dispatcher (`POST /api/internal/dispatch-worker`) already skips when `Job.status` is terminal. Phase 2.5 adds a `phase` transition (`received → scheduled`) before returning so that:

- Cloud Tasks redelivery sees `phase=scheduled`, short-circuits before hitting K8s (3e guardrail), and returns the cached pod name from `Job.metadata["pod_name"]`.
- The scheduler's own get-before-create on `Job` name (`ham-worker-{job_id_short}`) is the second line of defence — if the dispatcher crashes between the schedule call and the phase update, K8s still won't create a duplicate Job on the next redelivery.

The `phase` field is used instead of `status` because the `CloudRuntimeJobStatus` Literal is locked by Phase 0 and does not include `scheduled`. `phase` is a free-string marker used by the dispatcher and the Worker for sub-status visibility.

## Operational surface (in `docs/PHASE_2_5_OPS.md`)

- Create the Cloud Tasks queue (`gcloud tasks queues create`).
- Apply the K8s namespace + RBAC + KSA manifests in `deploy/k8s/`.
- Bind the KSA to a GSA via Workload Identity for Firestore + Cloud Tasks access.
- Set production env vars on Cloud Run (`HAM_WORKER_ENQUEUE_BACKEND=cloud_tasks`, `HAM_WORKER_POD_SCHEDULER_BACKEND=gke`, plus the per-store Firestore backend toggles).
- Smoke runbook: approve a small Plan, observe Cloud Tasks delivery, GKE Job creation, SSE stream, completion.

## Out of scope for Phase 2.5

- Fleshing out the Step executor stub in `BuilderWorker._execute_step` (lands when the Planner emits typed Step kinds).
- NetworkPolicy on Worker pods (ADR-0015, deferred).
- Cleanup/janitor automation for Worker pods (covered by `ttlSecondsAfterFinished`).
- Multi-region failover for the Cloud Tasks queue.
- Cloud Tasks dead-letter handling beyond the platform default.
