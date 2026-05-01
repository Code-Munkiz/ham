# ComfyUI provider plan (Phase 2G.5 / Phase 2G.6 precursor)

HAM **must not** bundle ComfyUI, PyTorch/CUDA, or model checkpoints in this repository or in the default `ham-api` Cloud Run image. ComfyUI is a **separate GPU-backed service**. HAM integrates only through a **backend media provider adapter** that:

1. Resolves configuration from **environment / Secret Manager** (never from the browser).
2. Submits **prompt + workflow JSON** (or queue API payload) **server-to-server**.
3. **Polls or streams** until output bytes are available **on the ComfyUI side**.
4. **Downloads finished image/video bytes** inside `ham-api`.
5. Persists artifacts through the existing **`GeneratedMediaStore`** pipeline (`hamgm_*` ids, GCS or local dev).
6. Exposes only **opaque ids** and **`/api/media/artifacts/{id}`** download routes to clients.

This document is planning only until **Phase 2G.6 — ComfyUI Service POC** is approved.

---

## Architecture (target)

```
Browser → HAM FastAPI (/api/media/images/generate or future route)
       → Media provider registry selects `comfyui` adapter when configured
       → ComfyUI adapter (httpx) → ComfyUI worker URL (VPC / TLS)
       ← image bytes
       → GeneratedMediaStore.put(...) → hamgm_*
       ← JSON with download_url path only
```

- **No** ComfyUI URL, internal hostname, or workflow file paths in capability JSON or chat responses.
- **No** browser → ComfyUI traffic.
- **Optional** gateway API key (`HAM_COMFYUI_API_KEY`) if the worker sits behind auth.

---

## Deployment options for the ComfyUI worker (outside HAM)

| Option | When to use | Notes |
|--------|--------------|-------|
| **Local workstation POC** | Dev / demo | GPU on desk; expose via tunnel **only for non-prod**; never bake tunnel URLs into HAM commits. |
| **Dedicated GPU VM** | Stable staging/prod-lite | GCP `compute`/Azure/AWS VM with NVIDIA driver + Comfy; private IP; HAM connects over VPC/VPN. |
| **Runpod / Vast / Beam-style GPU worker** | Elastic GPU | Treat as external SaaS boundary; egress from `ham-api` only; contractual privacy review. |
| **Managed Comfy / Comfy Cloud** | Low-ops teams | Depends on vendor API; adapter maps to their HTTP contract. |
| **Kubernetes GPU (GKE/EKS)** | Org standard for ML | Larger lift; fits when other batch inference already runs on GPU nodes. |

HAM’s adapter should assume **timeouts**, **retries with backoff**, and **bounded output size** consistent with `HAM_MEDIA_IMAGE_OUTPUT_MAX_BYTES` (and future video caps).

---

## Environment placeholders (HAM API only)

Set on **Cloud Run / local API**, not Vercel except through existing `VITE_*` wiring for **HAM API origin** only (never Comfy endpoint).

| Variable | Purpose |
|----------|---------|
| `HAM_MEDIA_PROVIDER` | `comfyui` when the ComfyUI adapter is implemented and selected (today: registry acknowledges id; adapter **not** implemented in 2G.5). |
| `HAM_COMFYUI_BASE_URL` | Base URL for ComfyUI HTTP API (**Secret / env**, not logged in responses). |
| `HAM_COMFYUI_API_KEY` | Optional Bearer or custom header for a reverse proxy / worker auth. |
| `HAM_COMFYUI_DEFAULT_WORKFLOW` | Workflow id **or** inline JSON registry key referencing an **approved** workflow artifact (not user scratch). |
| `HAM_COMFYUI_TIMEOUT_SEC` | Upper bound on queue + render wait (default TBD in 2G.6). |

Additional knobs (future): `HAM_COMFYUI_MAX_NODES`, concurrency limits, and per-tenant quotas.

---

## Workflow governance

- Store workflow JSON under **version control or an internal artifact bucket**, not ad hoc strings from anonymous users without review.
- Record **workflow version / content hash** in generated-media metadata (`meta_json`) for audit.
- Record **checkpoint / LoRA / custom node identifiers** required to reproduce renders (opaque names, **not** local filesystem paths on HAM hosts).
- **License review** before commercial deployment of third-party checkpoints and LoRAs.
- Avoid exposing raw workflow internals in **product APIs** unless a deliberate **debug/admin** route is gated and redacted.

---

## Security checklist (non‑negotiables)

- [ ] Browser never receives ComfyUI URL or LAN addresses.
- [ ] No `gs://` bucket paths or machine file paths returned to clients.
- [ ] No provider API keys echoed in JSON or logs at info level.
- [ ] Outputs pass through **`GeneratedMediaStore`** with same redaction posture as OpenRouter-backed images today.

---

## Phase 2G.6 POC scope (proposal)

1. Stand up single Comfy worker (VM or SaaS GPU) reachable from **`ham-api` only**.
2. Implement `ComfyUIImageProviderAdapter` behind `HAM_MEDIA_PROVIDER=comfyui`.
3. One frozen workflow + one smoke test (CI uses synthetic path; optional integration test behind flag).
4. Document firewall / TLS between HAM and worker.

Until then, `HAM_MEDIA_PROVIDER=comfyui` keeps **generation disabled** with explicit capability notes (registry placeholder).
