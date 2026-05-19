# 0014 — Worker pod is a K8s Job, same image as API with different CMD, Workload Identity for GCP auth

Phase 2.5 replaces `_DisabledPodScheduler` with a real GKE scheduler. This ADR captures the pod spec decisions and the auth/identity model that go with it.

## Pod object: K8s Job

`batch/v1.Job` with:

- `restartPolicy: Never` — Worker dies → Plan fails. Matches ADR-0001 (no mid-flight resume).
- `backoffLimit: 0` — no K8s retries. Cloud Tasks redelivery is the retry surface; per-pod retry would double-write events.
- `ttlSecondsAfterFinished: 3600` — K8s deletes the Job + pod 1 hour after completion. No janitor required.
- `parallelism: 1`, `completions: 1` — single-shot.

Why not a raw `Pod`: gives up Job lifecycle/status semantics and forces us to write cleanup code. Why not a `Deployment`: this is task execution, not a long-running service.

## Image strategy: same image as API, different CMD

The Dockerfile at repo root builds one image that contains everything HAM needs (FastAPI, Hermes, droid_executor, builder_*). The K8s Job overrides the Dockerfile's `CMD` field with `["python", "-m", "src.ham.worker_main"]`.

- Pro: API and Worker stay locked to the same Python deps and the same code version. One Dockerfile to maintain.
- Pro: pull cost is dominated by GKE scheduling latency at our scale; the ~30MB of FastAPI deps the Worker doesn't use is irrelevant.
- Con: image is bigger than a hand-tuned Worker image would be. Not worth the build complexity at this scale.

The image must be supplied to the scheduler as a digest-pinned ref via `HAM_WORKER_IMAGE` (`gcr.io/.../ham@sha256:...`). The Worker logs this at startup. The scheduler refuses to launch a Job if `HAM_WORKER_IMAGE` is unset — no `:latest` fallback, no silent drift in production.

## Bootstrap: env-vars only

The pod receives only identifiers as env vars; it fetches the `Plan` and `CloudRuntimeJob` from Firestore on startup, per CONTEXT.md "Worker fetches the full Plan and CloudRuntimeJob from their stores on pop." The `WorkerEnvelope` from Cloud Tasks is consumed by the dispatcher and discarded — the Worker never sees it directly.

The Worker verifies `Job.workspace_id`, `Job.project_id`, and `Job.metadata['plan_id']` match the env-supplied identifiers; mismatch is a loud failure (3c guardrail).

## Auth: Workload Identity end-to-end

- **Dispatcher (Cloud Run) → GKE API.** The Cloud Run service's GCP service account is bound to a Kubernetes `Role` (namespace-scoped) with verbs `create, get, list` on `jobs` in the worker namespace. Not `roles/container.developer`. Not `ClusterRole`. The `kubernetes` Python client uses `google-auth` to mint short-lived GKE access tokens; no JSON keys.
- **Worker pod → Firestore.** The pod runs as a Kubernetes service account bound to a GCP service account via Workload Identity. That GCP SA has `roles/datastore.user` (Firestore) only. No JSON keys mounted, no broad permissions.
- **Cloud Tasks → Dispatcher.** Cloud Tasks signs HTTP push deliveries with an OIDC token whose `aud` matches `HAM_DISPATCHER_AUDIENCE`. The dispatcher already validates this (`src/api/internal_dispatcher.py:_validate_oidc_token`). The enqueue side mints the matching token with the queue-side service account.

## Idempotency

Job name is deterministic: `ham-worker-{job_id_short}` (first 12 chars of `job_id`). Scheduler does `get_namespaced_job(name=...)` before `create_namespaced_job(...)`. If the Job exists, scheduler returns 200 with the existing name. Cloud Tasks redelivery → no double-launch.

The dispatcher additionally transitions `CloudRuntimeJob.phase` to `scheduled` and caches `pod_name` in `Job.metadata` after a successful schedule. Subsequent redeliveries see `phase=scheduled`, short-circuit before reaching K8s, and return 200 with the cached `pod_name` (3e guardrail). The `phase` field is used instead of `status` because `CloudRuntimeJobStatus` is a locked Phase 0 Literal that does not include `scheduled`.

## Consequences

- One image, one CI pipeline.
- Worker pod is ephemeral; cleanup is K8s-managed.
- IAM/RBAC surface is bounded: dispatcher SA has create/get/list on Jobs in one namespace; Worker SA has Firestore access only.
- No JSON keys anywhere in the stack.
- Adding new env vars to the Worker requires updating both `src/ham/worker_main.py` (read) and `src/api/internal_dispatcher_gke.py` (set). Treat this as the contract surface.
- If the Worker image grows large (e.g., adds CUDA), the same-image trade-off should be revisited.
