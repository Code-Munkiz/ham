# HAM Builder — GCP-native runtime foundation

## Status

**E2B is decommissioned** as the active builder preview/runtime path in this repository.

Isolated provider probes failed at stack creation (`create_sandbox`) **outside** the HAM Builder integration surface as well. The sandbox SDK vendor path is therefore not carrying the MVP.

HAM Builder is moving to a **GCP-native runtime**: Cloud Run stays the **HAM API control plane**, **GCS** stores immutable **source bundles**, and **GKE Autopilot** with **GKE Sandbox / gVisor** is the **intended** isolation boundary for generated-app preview workloads.

**Live GKE preview is not implemented yet.** Current code carries **config scaffolding**, **dry-run**, and **explicit test-only fake success** only — no Kubernetes API calls and no cluster provisioning in-repo.

## Principles

1. **HAM preview proxy remains the only browser-facing preview path.** The dashboard iframe loads **`/api/.../builder/preview-proxy/`**, not arbitrary upstream URLs.
2. **`RuntimeSession`** and **`PreviewEndpoint`** stay **provider-neutral** persistence concepts; only the backend adapter changes over time.
3. **No fake preview success** in dry-run or production-shaped paths — readiness must be honest.
4. **No raw internal runtime URLs** in API payloads consumed by the browser for iframe embedding.
5. **TTL cleanup is mandatory** once workloads are real — ephemeral previews must expire and release resources.

## Configuration (scaffolding)

Active provider id: **`gcp_gke_sandbox`**.

Illustrative environment variables (subject to tightening during implementation):

| Variable | Role |
|----------|------|
| `HAM_BUILDER_CLOUD_RUNTIME_PROVIDER` | e.g. `gcp_gke_sandbox`, `disabled`, `local_mock`, `cloud_run_poc` |
| `HAM_BUILDER_GCP_RUNTIME_ENABLED` | Master enable for the GCP GKE scaffolding path |
| `HAM_BUILDER_GCP_RUNTIME_DRY_RUN` | Plan-only; must not emit a ready preview URL |
| `HAM_BUILDER_GCP_RUNTIME_FAKE_MODE` | Test-only explicit fake (`success` / `failure`) |
| `HAM_BUILDER_GCP_PROJECT_ID` | Target GCP project |
| `HAM_BUILDER_GCP_REGION` | Region |
| `HAM_BUILDER_GKE_CLUSTER` | Cluster id / name |
| `HAM_BUILDER_GKE_NAMESPACE_PREFIX` | Namespace prefix for workload isolation |
| `HAM_BUILDER_PREVIEW_SOURCE_BUCKET` | GCS bucket for uploaded source bundles |
| `HAM_BUILDER_PREVIEW_RUNNER_IMAGE` | Container image for install/start |
| `HAM_BUILDER_PREVIEW_TTL_SECONDS` | Preview lifetime |
| `HAM_BUILDER_PREVIEW_DEFAULT_PORT` | App listen port (default `3000`) |

Missing or disabled configuration must return a **clean not-configured** state without synthetic “ready” previews.

## Long-term flow (north star)

User prompt → **Builder blueprint** → **`SourceSnapshot`** → **GCS source bundle** → **`CloudRuntimeJob`** → **GKE Sandbox preview pod** → install / start / health → **`RuntimeSession`** → **`PreviewEndpoint`** → **HAM proxy iframe** → logs / status / evidence → publish / deploy adapters **later**.

## Post-merge operations (staging / testing)

After this change is deployed to an environment that previously bound E2B:

1. Remove E2B-related environment variables from the HAM Cloud Run service using **targeted** key removal (do not replace the entire env block).
2. Remove the E2B **secret** binding from Cloud Run when no longer referenced.
3. Optionally delete Secret Manager secret `ham-builder-sandbox-api-key` **only after** confirming no other service consumes it.
4. Preserve all **non-E2B** HAM configuration.

Automation in this repo does **not** perform cloud env cleanup unless explicitly authorized separately.

## Next implementation slice

**GCP-native preview worker** design and spike: durable job handoff from `CloudRuntimeJob` to a worker that (later) provisions/updates preview pods, records health, and drives `PreviewEndpoint` + proxy-only URLs — still with no raw upstream exposure and with mandatory TTL.

Operator-facing **manual spike scaffolding** (YAML renderer, runner Dockerfile skeleton, packaging/upload helpers — **no live Kubernetes API** from CI/tests): [`GCP_NATIVE_PREVIEW_WORKER_SPIKE.md`](GCP_NATIVE_PREVIEW_WORKER_SPIKE.md).
