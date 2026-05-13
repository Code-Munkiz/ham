# GCP preview runtime — spike artifacts

Manifest rendering for **manual GKE Sandbox spikes only**. Nothing here provisions clusters or applies workloads automatically.

## Contents

| Path | Purpose |
|------|---------|
| `../../docker/preview-runner/` | Spike runner image (`Dockerfile` + entrypoint expecting `/workspace/package.json`) |
| `../../scripts/builder/render_gke_preview_manifest.py` | Emit Pod YAML (`runtimeClassName: gvisor`) — stdout only |
| `../../scripts/builder/package_preview_source.py` | Zip local source tree |
| `../../scripts/builder/upload_preview_source_gcs.py` | Print `gsutil cp` by default (`--apply` runs upload) |

Canonical operator narrative: **`docs/GCP_NATIVE_PREVIEW_WORKER_SPIKE.md`**.

Live preview is **not** shipped until `gcp_gke_sandbox` executes against the Kubernetes API under explicit governance.
