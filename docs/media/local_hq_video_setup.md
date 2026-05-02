# Local high-quality Wan 2.1 video (HAM + ComfyUI)

**Scope:** Developer workstation only. This workflow is registered in-repo as **`wan_hq_t2v_local`** and must not be treated as production, multi-user, or hosted‑webapp video.

HAM ships **manifest + sanitized API-format workflow templates** under `configs/media/comfyui/`. You place **weights and Comfy binaries** outside the repo.

## Required manual files on the worker (not in git)

Use the filenames that actually appear in your ComfyUI model pickers (examples match the tracked template defaults):

| Role | Example filename | Typical ComfyUI directory (under your install, e.g. `C:\AI\ComfyUI`) |
|------|-----------------|----------------------------------------------------------------------|
| Wan T2V diffusion model | `wan2.1_t2v_1.3B_fp16.safetensors` (or `*_bf16.safetensors`, etc.) | `models/diffusion_models/` |
| UMT5 text encoder (CLIP type **wan**) | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `models/text_encoders/` |
| Wan VAE | `wan_2.1_vae.safetensors` | `models/vae/` |

**Image-to-video (future):** a separate workflow (`wan_hq_i2v_local`) would add CLIP Vision / conditioning nodes and optional encoder weights under `models/clip_vision/` — not shipped yet; this doc focuses on **T2V** first.

Verify Comfy sees files: open Comfy UI → loaders / model lists should contain the filenames, or queue a trivial graph load.

## ComfyUI version

Use a **recent ComfyUI** build that includes Wan example nodes (`UNETLoader`, `CLIPLoader` with type `wan`, `EmptyHunyuanLatentVideo`, `ModelSamplingSD3`). If nodes are missing, upgrade Comfy and compare your install to [ComfyUI_examples/wan](https://github.com/comfyanonymous/ComfyUI_examples/tree/master/wan).

## Env-gated activation (PowerShell examples)

Ham API must call Comfy **server-side** only; browser uses HAM **`/api/...`** routes.

```powershell
$env:HAM_MEDIA_PROVIDER="comfyui"
$env:HAM_MEDIA_VIDEO_GENERATION_ENABLED="true"
$env:HAM_COMFYUI_BASE_URL="http://127.0.0.1:8188"
$env:HAM_COMFYUI_VIDEO_WORKFLOW="wan_hq_t2v_local"
$env:HAM_COMFYUI_VIDEO_TIMEOUT_SEC="900"
$env:HAM_COMFYUI_VIDEO_OUTPUT_MAX_BYTES="209715200"
$env:HAM_GENERATED_MEDIA_STORE="local"
$env:HAM_GENERATED_MEDIA_DIR="C:\AI\HAMGeneratedMedia"
```

Optional overrides (filename only — **no paths**):

```powershell
$env:HAM_COMFYUI_WAN_VIDEO_MODEL_NAME="wan2.1_t2v_1.3B_bf16.safetensors"
$env:HAM_COMFYUI_WAN_CLIP_MODEL_NAME="umt5_xxl_fp8_e4m3fn_scaled.safetensors"
$env:HAM_COMFYUI_WAN_VAE_MODEL_NAME="wan_2.1_vae.safetensors"
```

Rollback to AnimateDiff SDXL clip:

```powershell
$env:HAM_COMFYUI_VIDEO_WORKFLOW="animatediff_sdxl_gen1_mp4"
```

Rollback to repeated-frame POC:

```powershell
$env:HAM_COMFYUI_VIDEO_WORKFLOW="comfy_video_local_poc"
# or unset HAM_COMFYUI_VIDEO_WORKFLOW (defaults to comfy_video_local_poc)
```

Timeouts and max output size:

- **`HAM_COMFYUI_VIDEO_TIMEOUT_SEC`** — polled job wait cap (backend `generate_video`; default in code up to **1200** s).
- **`HAM_COMFYUI_VIDEO_OUTPUT_MAX_BYTES`** — rejects oversized downloads after Comfy **`/view`** (default up to **500 MiB** in code).

## Start order

1. Start ComfyUI on the worker (`127.0.0.1:8188` or your LAN URL).
2. From repo root, start API with provider + workflow env vars (wrapper or your own launcher):

   `.\scripts\run_local_api_comfy.py` (then override **`HAM_COMFYUI_VIDEO_WORKFLOW`** and paths in the shell as above).

3. Start the frontend dev server with proxy to the **same** API port (see `frontend` runbooks / `npm run dev:comfy`).

## Expected HTTP flow (browser → HAM)

- `POST /api/media/videos/generate`
- Poll `GET /api/media/jobs/{job_id}` until succeeded
- `GET /api/media/artifacts/{id}/download`

The browser must **not** call `8188`, Comfy **`/view`**, or emit Windows paths / `gs://` / secrets in payloads. Regression: inspect DevTools Network and confirm only same-origin **`/api/...`** for generation and artifacts.

## Smoke prompts

- Short T2V: *“Drone shot over snowy pine forest at sunrise, slow forward motion.”*
- Confirm job: `queued` → `running` → `succeeded`.
- Video card renders; playback works; download returns `video/mp4` (or allowed video MIME after transcode upstream).

## Regression matrix (manual)

Before/after HQ video:

- Normal **text chat** works (Hermes/OpenRouter/mock as configured).
- **Generate image** (SDXL Comfy baseline) still works.
- **Export PDF** opens or fails gracefully without crashing the session shell.

## Performance caveats

- Wan HQ is heavier than **`comfy_video_local_poc`** and often slower than **`animatediff_sdxl_gen1_mp4`** on small GPUs.
- Larger resolutions / frame lengths in **`EmptyHunyuanLatentVideo`** are operator edits only (do **not** commit operator-specific graphs with paths).

## If CreateVideo fails on your Wan build

Upstream examples sometimes terminate with **`SaveWEBM`** / **`SaveAnimatedWEBP`**. If MP4 mux fails locally:

1. In ComfyUI, export **API-format** workflow from your working graph.

2. Keep HAM **`comfy_patches`** aligned: **`prompt`** → **`CLIPTextEncode` positive**, **`negative_prompt`** → **`CLIPTextEncode` negative**, **`seed`** → **`KSampler`**.

3. Replace **only** the template JSON on the worker (not necessarily in-repo) — or propose a guarded graph variant in a PR after you validate node IDs.

## Labels

Earn **only after** Checkpoint 2 human smoke passes (examples):

`LOCAL_HQ_VIDEO_WORKFLOW_REGISTERED`, `LOCAL_HQ_VIDEO_COMFY_SMOKE_PASSED`, `LOCAL_HQ_VIDEO_HAM_API_SMOKE_PASSED`, `NO_COMFYUI_URL_LEAKAGE`, `NO_STORAGE_PATH_LEAKAGE`, rollback verified.

Combined: **`LOCAL_HIGH_QUALITY_VIDEO_WORKFLOW_ACCEPTED`** only when all applicable checkpoints pass locally.
