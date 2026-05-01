# ComfyUI provider plan (Phase 2G.5–2G.7)

HAM **must not** bundle ComfyUI, PyTorch/CUDA, or model checkpoints in this repository or in the default `ham-api` Cloud Run image. ComfyUI is a **separate GPU-backed service**. HAM integrates only through a **backend media provider adapter** (`src/ham/comfyui_provider_adapter.py`) that:

1. Resolves configuration from **environment / Secret Manager** (never from the browser).
2. Submits **prompt + workflow JSON** (or queue API payload) **server-to-server**.
3. **Polls or streams** until output bytes are available **on the ComfyUI side**.
4. **Downloads finished image/video bytes** inside `ham-api`.
5. Persists artifacts through the existing **`GeneratedMediaStore`** pipeline (`hamgm_*` ids, GCS or local dev).
6. Exposes only **opaque ids** and **`/api/media/artifacts/{id}`** download routes to clients.

Phase **2G.6** (code): **`ComfyUIImageProviderAdapter`** + **SDXL** templates (`configs/media/comfyui/`). Selecting Comfy requires **`HAM_MEDIA_PROVIDER=comfyui`**, **`HAM_MEDIA_IMAGE_GENERATION_ENABLED`**, and **`HAM_COMFYUI_BASE_URL`**. Integration tests mock Comfy REST.

Phase **2G.7** extends **documentation / configuration contracts** — multi-target profiles, operator topology guidance, **`HAM_COMFYUI_WORKER_PROFILE`** allowlisting (surfaced cautiously under **`generation.comfy_worker_profile`**), **`sdxl_vanilla` → `sdxl_baseline` workflow aliasing**. **Live NVIDIA smoke**, **staging Cloud Run rollout**, **GCS proofs**, **Vercel UI proof** remain **manual** labelling steps — see **`docs/COMFYUI_WORKER_TARGETS.md`**.


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

### SDXL baseline templates (**no checkpoints in-repo**)

| Path | Contents |
|------|-----------|
| `configs/media/comfyui/sdxl_baseline.manifest.json` | Stable `workflow_id`, **`model_family: sdxl`**, **`license_check_required`**, and **`comfy_patches`** (which graph nodes receive prompt, size, seed). |
| `configs/media/comfyui/sdxl_baseline.workflow.example.json` | Minimal graph; checkpoint field carries the **`OPERATOR_SDXL_BASE_CHECKPOINT_NAME`** placeholder (operators substitute on GPU after licensing). |

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
| `HAM_MEDIA_PROVIDER` | Set **`comfyui`** to select the Comfy adapter (**OpenRouter** remains default when unset). |
| `HAM_MEDIA_IMAGE_GENERATION_ENABLED` | Must be enabled for Comfy generation (same gate as OpenRouter media). |
| `HAM_COMFYUI_BASE_URL` | Base URL for Comfy HTTP API (**Secret / env**, never surfaced in `/capabilities` or client JSON). |
| `HAM_COMFYUI_API_KEY` | Optional **`Authorization: Bearer …`** secret when a gateway protects Comfy. |
| `HAM_COMFYUI_DEFAULT_WORKFLOW` | Stem under `configs/media/comfyui/` (default **`sdxl_baseline`**; **`sdxl_vanilla`** resolves to that manifest via code alias). |
| `HAM_COMFYUI_WORKER_PROFILE` | Opaque topology label (`local_gpu_workstation`, …). Surfaced under **`generation.comfy_worker_profile`** only when Comfy is selected **and** the value matches built-in allowlist — see **`docs/COMFYUI_WORKER_TARGETS.md`** + **`configs/media/comfyui/worker_targets.example.json`**. |
| `HAM_COMFYUI_TIMEOUT_SEC` | Wall-clock ceiling for enqueue + polling (default **120**). |
| `HAM_COMFYUI_OUTPUT_POLL_SEC` | Sleep between **`/history/{prompt_id}`** polls (default **2**). |
| `HAM_COMFYUI_OUTPUT_MAX_BYTES` | Max bytes accepted from **`/view`** before rejecting (inherits floor/ceiling logic from shared media caps when unset). |
| `HAM_COMFYUI_DEFAULT_WIDTH` / `HAM_COMFYUI_DEFAULT_HEIGHT` | Latent dimensions for the SDXL baseline template (**256–4096**, default **1024**). |
| `HAM_COMFYUI_DEFAULT_NEGATIVE_PROMPT` | Optional negative text wired into manifest **negative_prompt** patch. |

Additional knobs (future): `HAM_COMFYUI_MAX_NODES`, concurrency caps, tenant quotas.

#### Phase 2G.7 — manual checklist (operators)

1. Run ComfyUI on a GPU host reachable **only from `ham-api` network** (VPN / VPC / SSH tunnel dev-only).
2. Install licensed SDXL checkpoints and align **`ckpt_name`** in operator-owned workflow overrides (do not rely on placeholders in production JSON).
3. Set **`HAM_COMFYUI_*`** secrets on **`ham-api`**; confirm **`GET /api/chat/capabilities`** shows Comfy **`configured: true`** but **never** echoes the worker URL. Use **`?model_id=openai/gpt-4o`** (chat SKU) rather than repurposing **`model_id`** as a workflow slug.
4. Smoke **`POST /api/media/images/generate`** and verify **`hamgm_*`** + download route (no **`/view`** or Comfy filenames in JSON).

---

## Workflow governance

- Store workflow JSON under **version control or an internal artifact bucket**, not ad hoc strings from anonymous users without review.
- Record **workflow version / content hash** in generated-media metadata (`meta_json`) for audit.
- Record **checkpoint / LoRA / custom node identifiers** required to reproduce renders (opaque names, **not** local filesystem paths on HAM hosts).
- **License review** before commercial deployment of third-party checkpoints and LoRAs.
- Avoid exposing raw workflow internals in **product APIs** unless a deliberate **debug/admin** route is gated and redacted.

---

## Security checklist (non‑negotiables)

- [x] Backend-only Comfy access; browsers never receive Comfy base URL (**`/capabilities`** audited in tests).
- [x] No `gs://` or filesystem paths in client payloads (same **`GeneratedMediaStore`** path as OpenRouter).
- [x] No Comfy **`/view`** URLs or raw disk filenames echoed in HAM **`POST /generate`** responses.
- [ ] Operational: redact bearer tokens / worker hostnames from application logs beyond existing HAM observability norms.

---

## Phase 2G.6 vs 2G.7

| Slice | Delivered |
|-------|-----------|
| **2G.6** | `ComfyUIImageProviderAdapter`, registry/capabilities for **`comfyui`**, **`configs/media/comfyui`** SDXL manifest + workflow example, mocked HTTP tests — no bundled Comfy in `ham-api`. |
| **2G.7 (automation in this repo)** | Worker profile docs + **`worker_targets.example.json`**, **`HAM_COMFYUI_WORKER_PROFILE`** allowlist + optional capability echo, **`sdxl_vanilla` → `sdxl_baseline`**. |
| **2G.7 (operator-only smoke)** | Reachable Comfy on GPU, real checkpoint names, **`POST /generate` + GCS + Vercel UI** proof; **SeargeSDXL** deferred until custom nodes proven off-repo (`SEARGE_SDXL_WORKFLOW_DEFERRED`). |
