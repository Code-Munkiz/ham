# HAM preview janitor CronJob (staging, Option B)

Operator runbook for **`deploy/gke/staging/ham-preview-janitor cronjob-dryrun.yaml`** and
**`docker/ham-preview-janitor/Dockerfile`**.

## What ships today (foundation)

- **Dry-run only:** the CronJob runs `kubectl get` (pods / services / endpoints) then
  **`python .../ham_preview_janitor.py`** with **no `--apply`**.
- **RBAC:** `Role` + `RoleBinding` in **`ham-builder-preview-spike` only** — **verbs:
  `get`, `list`, `watch`** on **`pods`**, **`services`**, **`endpoints`**. No `delete`, no
  Secrets, no cluster-wide objects.
- **Log output:** the janitor prints a **JSON summary** (counts, reasons, **redacted**
  hashes) to **stdout** → **Cloud Logging** after deploy.
- **Cadence:** **every 15 minutes** (`*/15 * * * *`), **`concurrencyPolicy: Forbid`**.

## In-cluster vs operator `LiveGkePreviewRuntimeClient`

Dry-run does **not** use **`LiveGkePreviewRuntimeClient`** (that path is for **ADC / operator**
style control-plane access and **`--apply`**). In-cluster, **`kubectl`** with the CronJob’s
**ServiceAccount** token supplies List JSON to the **pure** `preview_janitor` plan logic.

**Future apply mode:** add **`delete`** verbs (and a **narrow** `Role` or second Role) plus
either an **in-cluster delete client** or a vetted `kubectl delete` flow — **explicit
governance only** after review.

## Build image (do not run until approved)

From repo root (example only):

```bash
# DO NOT RUN until reviewed
docker build -f docker/ham-preview-janitor/Dockerfile -t "${REGION}-docker.pkg.dev/${PROJECT}/ham/ham-preview-janitor:staging" .
docker push "${REGION}-docker.pkg.dev/${PROJECT}/ham/ham-preview-janitor:staging"
```

Replace **`JANITOR_IMAGE_REPLACE_ME`** in **`cronjob-dryrun.yaml`** with that reference (or
use **`kubectl apply -k`** / **`sed`** in your pipeline).

## Deploy dry-run CronJob (do not run until approved)

```bash
# DO NOT RUN until reviewed — verify context: gke_${PROJECT}_us-central1_ham-preview-spike
kubectl apply -f deploy/gke/staging/ham-preview-janitor/cronjob-dryrun.yaml
```

## Review logs

- **Cloud Logging** (GKE workload): filter resource type for the workload / namespace
  **`ham-builder-preview-spike`**, labels **`app.kubernetes.io/name=ham-preview-janitor`**.
- **Expected:** each run logs **one JSON object** with **`dry_run": true`**, **`destructive_apply_executed": false`**, counts only.

## Flip to apply (after separate approval)

1. Extend **RBAC** with **`delete`** on **`pods`** and **`services`** (still **namespace-local**).
2. Append **`--apply`** to the janitor invocation **or** add env flag gated in script.
3. Re-apply manifest; watch first run in dev/staging.

```bash
# DO NOT RUN — illustration only
# kubectl apply -f .../cronjob-apply.yaml
```

## Rollback / disable

```bash
# DO NOT RUN unless executing rollback
# kubectl delete cronjob ham-preview-janitor-dryrun -n ham-builder-preview-spike
# or: kubectl patch cronjob ham-preview-janitor-dryrun -n ham-builder-preview-spike -p '{"spec":{"suspend":true}}'
```

Previews can be **re-created from Builder** after any cleanup; janitor cannot undelete.

---

## Preview concurrency helpers (reporting only)

| Item | Plan |
|------|------|
| **Purpose** | **`preview_janitor.check_preview_concurrency_violation`** and related helpers
  support **dry-run cost visibility** and tests. They **do not block**
  **`create_preview_pod`** — repeated same-session Builder previews are allowed. |
| **Defaults** | Session **3** / workspace **5** align with **`PreviewJanitorConfig`** for reports only. |
| **Blocking** | **None** in the Builder path; reclaim stale previews via **TTL / janitor**, not user-facing caps. |
| **Mechanism** | **List** pods in namespace with HAM preview label; **count** by labels (no IP/URL logging). |

No code for this slice lives in the CronJob manifest.
