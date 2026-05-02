# ComfyUI worker target profiles — Phase 2G.7

HAM **never** installs ComfyUI or GPU stacks in this repo or in `ham-api` Cloud Run. Creative generation reaches an **external** Comfy process via **`HAM_COMFYUI_BASE_URL`** (backend-only).

Canonical machine-readable summaries live in **`configs/media/comfyui/worker_targets.example.json`** (placeholders only; **no IPs, URLs, secrets, checkpoints, paths, or literal `gs://` text** committed).

---

## Default POC profile (**internal / developer**)

| Field | Value |
|-------|--------|
| **`default_profile`** | **`local_gpu_workstation`** |
| Rationale | Most internal HAM users have strong **NVIDIA GeForce / RTX** class GPUs; validating SDXL vanilla on the desk is fastest. |

Set on **`ham-api`** only (not Vercel):

```txt
HAM_COMFYUI_WORKER_PROFILE=local_gpu_workstation
```

This value is surfaced in **`GET /api/chat/capabilities`** as **`generation.comfy_worker_profile`** **only when** `HAM_MEDIA_PROVIDER=comfyui` and the string matches a **built-in allowlist** (unknown values are omitted so typos cannot leak verbatim operator notes).

---

## Supported profiles (topology)

### `local_gpu_workstation`

ComfyUI runs on a **developer or internal workstation** with a local NVIDIA GPU.

- **Typical URLs** (stored in secrets / env — **never** git): LAN IP, **`127.0.0.1`** when **`ham-api` is co-hosted**, **Tailscale / ZeroTier** tailnet IPs, **`localhost`** SSH reverse tunnel listened from the API host.
- **Security:** do not expose Comfy’s HTTP port raw to the internet; prefer tailnet/VPN/firewall boundaries.
- **Important:** **`ham-api` on Cloud Run cannot reach `127.0.0.1` on your laptop.** For a GCP-hosted API plus *local-laptop* Comfy you need **`ham-api` locally** or a **VPN/tailnet** path where the API process can HTTP to the workstation. Document your pairing in operator runbooks (redacted — not git).

### `dedicated_gpu_vm`

Always-on GPU VM (same cloud project/VPC or routed VPN).

- **`HAM_COMFYUI_BASE_URL`** points at VM private hostname or authenticated reverse-proxy fronting Comfy.

### `runpod_vast_beam_worker`

Bursty/ephemeral GPUs at a SaaS/hosted-worker vendor.

- **Endpoint + auth model** differs by provider; **`HAM_COMFYUI_API_KEY`** may map to Bearer or gateway header your proxy defines.

### `managed_comfy_cloud_worker`

Hosted “Comfy-as-a-Service” APIs.

- Contract may drift from stock Comfy **`/prompt` / `/history` / `/view`** — adapter tweaks may belong in **`fix(media): align…`** follow-ups (**Phase 2G.8+**).

---

## Workflow IDs (**vanilla SDXL vs enhanced**)

| ID | Repo status |
|----|---------------|
| **`sdxl_baseline`** | Shipped Phase 2G.6 templates (`configs/media/comfyui/sdxl_baseline.*`). |
| **`sdxl_vanilla`** | **Alias → `sdxl_baseline`** inside `ham-api` (**no duplicate graph files** required). **`HAM_COMFYUI_DEFAULT_WORKFLOW=sdxl_vanilla`** supported. |
| **`comfy_video_local_poc`** | Repeated-frame **`video/mp4`** template for local POC; default when **`HAM_COMFYUI_VIDEO_WORKFLOW`** unset. |
| **`animatediff_sdxl_gen1_mp4`** | AnimateDiff Gen1 **SDXL** true-motion (**`video/mp4`**); requires **`ComfyUI-AnimateDiff-Evolved`** + listed motion/base filenames on the **worker only** — select via **`HAM_COMFYUI_VIDEO_WORKFLOW`** (**`comfy_video_local_poc`** remains manifest **fallback_workflow** / operator default).

### SeargeSDXL (`sdxl_searge`)

**Deferred** unless an operator verifies custom nodes Comfy-version alignment on **their GPU host**.

- Do **not** commit SeargeSDXL sources, checkpoints, or LoRA binaries into HAM.

**Label:** **`SEARGE_SDXL_WORKFLOW_DEFERRED`** until a validated worker graph exists outside this repo.

---

## Operator smoke playbook (HAM API checklist)

Endpoints (unchanged):

- **`POST /api/media/images/generate`**
- **`GET /api/media/artifacts/{id}`**
- **`GET /api/media/artifacts/{id}/download`**

**Capabilities:**

- **`GET /api/chat/capabilities?model_id=openai/gpt-4o`** (or another real workspace chat SKU) — **`model_id` selects chat/vision UX**, **not** the Comfy workflow. Do **not** pass `sdxl_baseline` as `model_id` unless you deliberately use it as chat id (normally you would not).

**Expected when Comfy configured:** `generation.active_media_provider=comfyui`, **`supports_image_generation=true`**, no Comfy URL, no `gs://`, no **`/view`** echoes on generate response.

Live Cloud Run revisions, VPC/VPN wiring, CUDA/driver versions on your GPU box, **and UI smoke against `https://ham-nine-mu.vercel.app`** are **operator-owned** (**Phase 2G.7 handoff**) — reproduce steps only in private notes with secrets redacted.

---

## Phase 2G.8 — local Comfy dev profile / proxy alignment

Problem addressed: frontend local smoke can silently hit the wrong API process when `frontend/.env.local` has an old `VITE_HAM_API_PROXY_TARGET` (for example `:8001` while Comfy-enabled `ham-api` is on `:8000`).

Recommended local run pair:

```txt
# API (repo root)
.venv\Scripts\python.exe scripts/run_local_api_comfy.py

# Frontend (frontend/)
npm run dev:comfy
```

What this does:

- `scripts/run_local_api_comfy.py` sets Comfy-friendly env defaults for local-only smoke (`HAM_MEDIA_PROVIDER=comfyui`, local generated-media store, workflow/profile defaults, checkpoint filename override) before delegating to `scripts/run_local_api.py`.
- `npm run dev:comfy` forces `VITE_HAM_API_PROXY_TARGET=http://127.0.0.1:8000` for that shell run, so stale `.env.local` values do not silently point the SPA at a non-Comfy API.
- Workspace composer action subtitle includes the active media backend label (`ComfyUI (...)` vs `openrouter`) so operator state is visible in UI.

Regression follow-up for local smoke:

1. Send an image-generation prompt in workspace chat.
2. Verify `POST /api/media/images/generate` returns 200 and image card renders.
3. Immediately send a normal text follow-up (for example `thanks — now summarize this result in one sentence`) and confirm text send/response works.

---

## Phase 2G.10 — video UI MVP (explicit action only)

- Workspace chat now exposes **`+ → Generate video`** in local/dev mode when capabilities report video generation support.
- The UI uses backend routes only: **`POST /api/media/videos/generate`** + poll **`GET /api/media/jobs/{id}`** + download through existing generated-media artifact routes.
- Natural-language auto-routing for prompts like **create a video…** stays **off** (**explicit menu action only**) even when AnimateDiff true-motion (**`HAM_COMFYUI_VIDEO_WORKFLOW=animatediff_sdxl_gen1_mp4`**) is provisioned on the worker.
- If worker/model/custom node setup is missing, expected behavior is queued/running/failure/unavailable UI states (not fake success).

---

## Labels (Phase 2G.7)

- **`COMFYUI_WORKER_TARGET_PROFILES_DEFINED`**
- **`LOCAL_GPU_WORKSTATION_DEFAULT_SELECTED`**
- **`GPU_VM_PROFILE_DOCUMENTED`**, **`RUNPOD_VAST_BEAM_PROFILE_DOCUMENTED`**, **`MANAGED_COMFY_CLOUD_PROFILE_DOCUMENTED`**
- Operational passes: **`LOCAL_COMFYUI_WORKER_TARGET_SELECTED`**, **`VANILLA_SDXL_WORKER_SMOKE_PASSED`**, **`HAM_COMFYUI_GENERATION_SMOKE_PASSED`**, **`COMFYUI_OUTPUT_STORED_IN_GCS`**, **`NO_COMFYUI_URL_LEAKAGE`** (earn only after human smoke)
