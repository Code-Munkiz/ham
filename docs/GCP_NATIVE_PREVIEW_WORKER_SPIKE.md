# GCP-native Preview Worker — manual spike (not shipped live preview)

This document describes the **first GCP-native Builder preview worker slice**: scaffolding only.

**Live GKE preview is not implemented** in application code paths yet. `HAM_BUILDER_GCP_RUNTIME_ENABLED=false` and dry-run posture remain correct until operators authorize cluster/API work.

Canonical architecture background: [`BUILDER_PLATFORM_GCP_RUNTIME_PLAN.md`](BUILDER_PLATFORM_GCP_RUNTIME_PLAN.md).

## 1. Goal

Prove an isolated loop:

**Source bundle → GCS → GKE Sandbox Pod → npm install/dev → health → TTL teardown**

without exposing raw cluster URLs to browsers and **without** claiming preview success when workloads are absent.

## 2. Manual spike steps (operator)

1. Pick a trivial **Vite/React** tree locally (or generate one elsewhere).
2. **Zip** sources:

   ```bash
   python scripts/builder/package_preview_source.py --root /path/to/app --output preview-source.zip
   ```

3. **Upload** (dry-run prints command; `--apply` runs `gsutil` after authorization):

   ```bash
   python scripts/builder/upload_preview_source_gcs.py \
     --bucket-uri gs://YOUR_BUCKET/ham-preview-spike/DEMO_RUN \
     --zip-path preview-source.zip
   ```

4. Build/push **runner image** (context = repo root):

   ```bash
   docker build -f docker/preview-runner/Dockerfile -t REGION-docker.pkg.dev/PROJECT/ham/ham-preview-runner:spike .
   docker push REGION-docker.pkg.dev/PROJECT/ham/ham-preview-runner:spike
   ```

5. **Render Pod YAML** (stdout only — review before apply):

   ```bash
   python scripts/builder/render_gke_preview_manifest.py \
     --workspace-id ws_demo_001 \
     --project-id proj_demo_001 \
     --runtime-session-id rs_demo_001 \
     --namespace ham-builder-preview-spike \
     --bundle-uri gs://YOUR_BUCKET/ham-preview-spike/DEMO_RUN/preview-source.zip \
     --runner-image REGION-docker.pkg.dev/PROJECT/ham/ham-preview-runner:spike \
     --ttl-seconds 3600 \
     > /tmp/ham-preview-pod.yaml
   ```

6. Manual spike continues with **`kubectl`** against an authorized cluster: apply workload identity / bundle fetch / `npm ci` steps **outside** this repo until the worker integrates Kubernetes clients.

7. Delete Pod + stale GCS prefixes after TTL verification.

## 3. Required GCP resources (inventory checklist)

| Resource | Purpose |
|---------|---------|
| **GKE Autopilot** cluster | Sandbox workloads |
| **GKE Sandbox / gVisor** (`runtimeClassName: gvisor`) | Process isolation |
| **Artifact Registry** | `ham-preview-runner` image |
| **GCS bucket + prefix** | Immutable zip bundles (`HAM_BUILDER_PREVIEW_SOURCE_BUCKET` family) |
| **Workload Identity / IAM** | Pod reads `gs://` objects without static keys in manifests |
| **Namespace** | e.g. `ham-builder-preview-spike` |

Staging inventory notes (2026-05): Artifact Registry repos **`ham`** and **`clarity`** exist in `us-central1`. **Kubernetes Engine API** was **not** callable from an automation shell against `clarity-staging-488201` (enable API + IAM before listing clusters). Operator must confirm cluster presence in Console.

## 4. IAM (high level)

- Cloud Run **HAM API** stays the control plane; preview worker credentials are **out-of-band** for this spike.
- Preview Pod service account: **`roles/storage.objectViewer`** on bundle prefix only (not bucket-wide when avoidable).
- Least privilege on Artifact Registry **reader** for pull.
- No cluster-admin bindings for runner identities.

## 5. Source bundle format

- Single **`preview-source.zip`** at rest in GCS.
- Archive paths are **relative** — no absolute paths, no `..` segments (`package_preview_source.py` enforces root containment).

## 6. Preview pod lifecycle (target)

1. Pod scheduled with **`runtimeClassName: gvisor`**.
2. Init/fetch logic (manual spike first) materializes files under **`/workspace`**.
3. **`npm ci`** (fail-fast on lockfile mismatch).
4. **`npm run dev -- --host 0.0.0.0 --port $PREVIEW_PORT`** (see `docker/preview-runner/entrypoint.sh`; swap command during spike if needed).
5. Internal health probe **HTTP GET** `:3000/` (or app-specific path).
6. TTL label **`ham.expires_at`** drives garbage collection automation later.

## 7. Health check behavior

Spike phase: Kubernetes **`startupProbe`/`readinessProbe`** not yet rendered by `render_gke_preview_manifest.py` — add when integrating live worker.

Until then: manual `kubectl exec` / port-forward checks only.

## 8. HAM proxy integration plan

North star remains **`/api/.../builder/preview-proxy/`** as the **only** browser-visible preview surface:

1. **`PreviewEndpoint`** stores opaque upstream metadata server-side only.
2. Browser iframe loads **HAM-relative proxy URL** with auth/session gates unchanged.
3. No raw Pod IP / internal Service DNS in REST payloads consumed by `frontend/`.

This spike **does not** wire proxy routes yet.

## 9. TTL cleanup plan

- Manifest labels **`ham.preview_ttl_seconds`** + **`ham.expires_at`** (RFC3339 sanitized for label syntax).
- Future controller deletes Pods past expiry and optionally deletes GCS spike prefixes under approved lifecycle policies.

## 10. Risks & stop conditions

| Risk | Stop / mitigation |
|------|-------------------|
| Shared multi-tenant Cloud Run subprocess preview | Explicitly **out of scope** as final architecture |
| Secrets mounted into generated apps | Forbidden unless separately approved |
| Over-wide GCS IAM | Prefix-scoped ACLs only |
| Missing gVisor runtime class | Cluster fails Pod scheduling — verify **NodePool / autopilot default** supports Sandbox |
| npm supply-chain | Spike uses pinned lockfiles only |

## 11. Not implemented yet

- Kubernetes API client in `src/ham/` for create/delete Pod.
- Automatic bundle upload from **`CloudRuntimeJob`** completion.
- **`RuntimeSession` / `PreviewEndpoint`** mutation from worker loop.
- NetworkPolicies, **`kubectl`-free** CI, production deploy.
- `startupProbe`/`readinessProbe` rendering.

---

## Appendix A — Future `gcp_gke_sandbox` provider methods

Maps proposed adapter surface onto existing HAM concepts (no calls wired):

| Method | HAM concepts |
|--------|----------------|
| `create_runtime` | `CloudRuntimeJob`, config snapshot |
| `upload_source_bundle` | `SourceSnapshot` → zip bytes → **GCS URI** (`SourceBundle`) |
| `create_preview_pod` | `CloudRuntimeJob.id`, sanitized ids → Pod manifest |
| `wait_for_pod_ready` | Job polling → `runtime_diagnostics` |
| `run_install_or_wait_for_init` | Activity → worker logs summary |
| `start_preview_server` | Container command / probes |
| `health_check` | Internal HTTP probe → `RuntimeSession.health` |
| `create_runtime_session` | Persist `RuntimeSession` record |
| `create_preview_endpoint` | Persist **`PreviewEndpoint`** (proxy-only URL externally) |
| `get_logs_summary` | Bounded fetch → `ActivityEvent` / diagnostics |
| `cleanup_runtime` | TTL worker deletes Pod + optional GCS delete markers |
| `normalize_error` | `SandboxErrorClassification` / existing classifier |

Artifacts referenced today: **`ActivityEvent`**, **`runtime_diagnostics`** JSON on sessions/jobs.
