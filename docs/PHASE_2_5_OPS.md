# Phase 2.5 — Operational runbook

This runbook is for the one-time setup needed to make Tier 1 actually live. Everything in `src/` is environment-gated; until these steps are done in GCP, the Worker enqueue stays no-op and the GKE scheduler stays disabled (safe defaults — see ADR-0014).

Run these in order. Each step is idempotent.

## 0. Prerequisites

- A GCP project that already hosts the HAM Cloud Run service (call this `${HAM_PROJECT}`).
- A GKE cluster that will host Worker Jobs (call this `${HAM_CLUSTER}` in `${HAM_LOCATION}`). Workload Identity must be enabled on the cluster — verify with:
  ```
  gcloud container clusters describe "${HAM_CLUSTER}" \
    --location "${HAM_LOCATION}" \
    --format='value(workloadIdentityConfig.workloadPool)'
  ```
  Should return `${HAM_PROJECT}.svc.id.goog`. If empty, enable it with `gcloud container clusters update`.
- Firestore is already provisioned in `${HAM_PROJECT}` (HAM uses it for existing stores).
- `kubectl` configured for the cluster.
- `gcloud` authenticated as a user with project-owner-equivalent perms (for one-time IAM setup).

## 1. Create the Cloud Tasks queue

```
gcloud tasks queues create ham-builder-worker \
  --project="${HAM_PROJECT}" \
  --location="${HAM_LOCATION}"
```

Defaults are fine. Retry config will be tuned later if needed.

## 2. Create the GSAs

Two GCP service accounts:

- **Dispatcher GSA** — the identity Cloud Run uses to (a) enqueue tasks and (b) create K8s Jobs.
  ```
  gcloud iam service-accounts create ham-dispatcher \
    --project="${HAM_PROJECT}" \
    --display-name="HAM Cloud Run dispatcher"
  ```
- **Worker GSA** — the identity Worker pods use to talk to Firestore.
  ```
  gcloud iam service-accounts create ham-worker \
    --project="${HAM_PROJECT}" \
    --display-name="HAM GKE Worker"
  ```

## 3. IAM grants (least privilege)

### Dispatcher GSA

```
# Enqueue tasks to the worker queue.
gcloud tasks queues add-iam-policy-binding ham-builder-worker \
  --location="${HAM_LOCATION}" \
  --member="serviceAccount:ham-dispatcher@${HAM_PROJECT}.iam.gserviceaccount.com" \
  --role="roles/cloudtasks.enqueuer"

# Mint OIDC tokens whose `email` claim is the dispatcher SA itself
# (the dispatcher validates this match).
gcloud iam service-accounts add-iam-policy-binding \
  "ham-dispatcher@${HAM_PROJECT}.iam.gserviceaccount.com" \
  --project="${HAM_PROJECT}" \
  --member="serviceAccount:service-${HAM_PROJECT_NUMBER}@gcp-sa-cloudtasks.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"

# Firestore for reading/writing builder_plans / builder_runtime_jobs.
# (Cloud Run also calls the stores at approval time.)
gcloud projects add-iam-policy-binding "${HAM_PROJECT}" \
  --member="serviceAccount:ham-dispatcher@${HAM_PROJECT}.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

The Cloud Run service must be deployed with `--service-account ham-dispatcher@${HAM_PROJECT}.iam.gserviceaccount.com`.

#### Legacy Builder preview (required when `ham-api` runtime SA is `ham-dispatcher`)

Phase 2.5 switches Cloud Run to `ham-dispatcher`. That GSA must retain **legacy Builder live-preview** permissions in addition to the Worker enqueue/dispatch grants above. Without them, chat scaffold succeeds but cloud preview fails (`GCP_GKE_SOURCE_BUNDLE_UPLOAD_FAILED` / `GCP_GKE_RBAC_DENIED`).

**Staging (temporary tradeoff, 2026-05):**

```
# GCS bundle upload (bucket-scoped; not project-wide storage.admin)
gcloud storage buckets add-iam-policy-binding "gs://${HAM_PREVIEW_SOURCE_BUCKET}" \
  --project="${HAM_PROJECT}" \
  --member="serviceAccount:ham-dispatcher@${HAM_PROJECT}.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# GKE Kubernetes API auth (GCP IAM layer). Narrow K8s RoleBinding alone is insufficient.
gcloud projects add-iam-policy-binding "${HAM_PROJECT}" \
  --member="serviceAccount:ham-dispatcher@${HAM_PROJECT}.iam.gserviceaccount.com" \
  --role="roles/container.developer"

# Namespace-scoped K8s RBAC in ham-builder-preview-spike (no ClusterRole, no secrets):
# Role ham-preview-dispatcher → pods/services lifecycle + pods/log read
# RoleBinding subject: ham-dispatcher@${HAM_PROJECT}.iam.gserviceaccount.com
```

**Security model (staging):**

| Layer | Worker Jobs (`ham-worker`) | Builder preview (`ham-builder-preview-spike`) |
|-------|---------------------------|-----------------------------------------------|
| GCP IAM | `datastore.user`, `container.clusterViewer`, Cloud Tasks enqueuer | **`container.developer`** (temporary), `storage.objectAdmin` on preview bucket |
| K8s RBAC | Role: `jobs` create/get/list/watch only — **no delete** | Role: pods/services create/get/list/watch/delete + pods/log get — **preview namespace only** |

Do **not** grant `roles/editor`, `roles/owner`, or `roles/container.admin` to `ham-dispatcher`.

**Phase 3 follow-up:** replace `roles/container.developer` with a custom GCP IAM role listing only the `container.pods.*` / `container.services.*` permissions the preview client uses, once smoke cycles confirm the exact set. Keep namespace-scoped K8s RBAC as the second authorization layer.

### Worker GSA

```
# Firestore for plans/jobs/events.
gcloud projects add-iam-policy-binding "${HAM_PROJECT}" \
  --member="serviceAccount:ham-worker@${HAM_PROJECT}.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

**Do not** grant the Worker GSA anything else. Not `cloudtasks.enqueuer`, not storage, not pubsub. The Worker reads/writes Firestore. That is all.

## 4. Apply the K8s manifests

The manifests in `deploy/k8s/` have two placeholders to fill in:

- `HAM_WORKER_GSA_EMAIL` in `worker-ksa.yaml` → `ham-worker@${HAM_PROJECT}.iam.gserviceaccount.com`
- `HAM_DISPATCHER_GSA_EMAIL` in `worker-rbac.yaml` → `ham-dispatcher@${HAM_PROJECT}.iam.gserviceaccount.com`

Apply:

```
kubectl apply -f deploy/k8s/worker-namespace.yaml
sed "s|HAM_WORKER_GSA_EMAIL|ham-worker@${HAM_PROJECT}.iam.gserviceaccount.com|g" \
    deploy/k8s/worker-ksa.yaml | kubectl apply -f -
sed "s|HAM_DISPATCHER_GSA_EMAIL|ham-dispatcher@${HAM_PROJECT}.iam.gserviceaccount.com|g" \
    deploy/k8s/worker-rbac.yaml | kubectl apply -f -
```

## 5. Bind Workload Identity

### Worker GSA ↔ Worker KSA

```
gcloud iam service-accounts add-iam-policy-binding \
  "ham-worker@${HAM_PROJECT}.iam.gserviceaccount.com" \
  --project="${HAM_PROJECT}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${HAM_PROJECT}.svc.id.goog[ham-worker/ham-worker]"
```

### Dispatcher GSA → GKE access (Cloud Run is *outside* the cluster)

The dispatcher Cloud Run service uses its attached GSA to mint a GKE access token via `google.auth.default()`. It needs Kubernetes RBAC binding *and* GCP-level permission to fetch cluster info:

```
gcloud projects add-iam-policy-binding "${HAM_PROJECT}" \
  --member="serviceAccount:ham-dispatcher@${HAM_PROJECT}.iam.gserviceaccount.com" \
  --role="roles/container.clusterViewer"
```

`container.clusterViewer` is intentionally narrow — read-only on cluster metadata. The RoleBinding in `worker-rbac.yaml` is what actually grants Job create/get/list rights for the **Worker** path.

**Staging exception:** legacy Builder live preview also requires `roles/container.developer` on `ham-dispatcher` (see *Legacy Builder preview* under §3). That grant is **broader than Worker scheduling needs** and is documented as a temporary staging unblock — not the long-term target. Do not grant `container.admin`.

## 6. Build and push the Worker image

Same image as the API. Build with the existing pipeline; capture the digest:

```
IMAGE_REF="${REGISTRY}/${IMAGE}@${DIGEST}"
```

Set `HAM_WORKER_IMAGE=${IMAGE_REF}` in the Cloud Run environment. The scheduler refuses to launch without a digest-pinned ref (no `:latest` fallback).

## 7. Set the Cloud Run env

```
gcloud run services update ham-api \
  --project="${HAM_PROJECT}" \
  --region="${HAM_LOCATION}" \
  --update-env-vars=\
HAM_WORKER_ENQUEUE_BACKEND=cloud_tasks,\
HAM_WORKER_POD_SCHEDULER_BACKEND=gke,\
HAM_BUILDER_PLAN_STORE_BACKEND=firestore,\
HAM_BUILDER_RUNTIME_JOB_STORE_BACKEND=firestore,\
HAM_BUILDER_RUN_EVENTS_STORE_BACKEND=firestore,\
HAM_FIRESTORE_PROJECT_ID=${HAM_PROJECT},\
HAM_CLOUD_TASKS_PROJECT_ID=${HAM_PROJECT},\
HAM_CLOUD_TASKS_LOCATION=${HAM_LOCATION},\
HAM_CLOUD_TASKS_QUEUE=ham-builder-worker,\
HAM_CLOUD_TASKS_SERVICE_ACCOUNT=ham-dispatcher@${HAM_PROJECT}.iam.gserviceaccount.com,\
HAM_DISPATCHER_URL=https://ham-api-...run.app/api/internal/dispatch-worker,\
HAM_DISPATCHER_AUDIENCE=https://ham-api-...run.app,\
HAM_GKE_CLUSTER_PROJECT_ID=${HAM_PROJECT},\
HAM_GKE_CLUSTER_LOCATION=${HAM_LOCATION},\
HAM_GKE_CLUSTER_NAME=${HAM_CLUSTER},\
HAM_WORKER_NAMESPACE=ham-worker,\
HAM_WORKER_KSA=ham-worker,\
HAM_WORKER_IMAGE=${IMAGE_REF}
```

`HAM_DISPATCHER_URL` and `HAM_DISPATCHER_AUDIENCE` must point at the dispatcher endpoint on the same Cloud Run service. The audience is what the OIDC validation in `_validate_oidc_token` checks; the URL is what Cloud Tasks POSTs to.

## 8. Smoke

1. Open the workbench, send a small builder-mutation message.
2. Watch the chat — Approval card should appear (Phase 2 PR4).
3. Approve.
4. Watch in the GCP console:
   - Cloud Tasks queue `ham-builder-worker` shows one task.
   - That task reaches Cloud Run within seconds; dispatcher logs say `dispatch_worker: scheduled pod ham-worker-...`.
   - `kubectl get jobs -n ham-worker` shows a new `ham-worker-...` Job.
   - `kubectl logs job/ham-worker-... -n ham-worker` shows the Worker startup banner with the image digest.
5. The In-flight card in chat updates as the Worker emits events.
6. On completion, the Job stays around for 1h (`ttlSecondsAfterFinished: 3600`) then K8s deletes it.

## 9. What's NOT in this runbook (Phase 3+)

- NetworkPolicy on the Worker namespace — deferred per ADR-0015.
- Cloud Tasks dead-letter queue and retry tuning.
- Sentry DSN provisioning (ADR-0008 deferred-DSN posture is unchanged).
- Multi-region cluster + queue failover.
- Worker pod resource limits beyond the Job defaults — tune once we have real Worker workloads to size against.
