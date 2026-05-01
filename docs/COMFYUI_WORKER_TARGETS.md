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

## Labels (Phase 2G.7)

- **`COMFYUI_WORKER_TARGET_PROFILES_DEFINED`**
- **`LOCAL_GPU_WORKSTATION_DEFAULT_SELECTED`**
- **`GPU_VM_PROFILE_DOCUMENTED`**, **`RUNPOD_VAST_BEAM_PROFILE_DOCUMENTED`**, **`MANAGED_COMFY_CLOUD_PROFILE_DOCUMENTED`**
- Operational passes: **`LOCAL_COMFYUI_WORKER_TARGET_SELECTED`**, **`VANILLA_SDXL_WORKER_SMOKE_PASSED`**, **`HAM_COMFYUI_GENERATION_SMOKE_PASSED`**, **`COMFYUI_OUTPUT_STORED_IN_GCS`**, **`NO_COMFYUI_URL_LEAKAGE`** (earn only after human smoke)
