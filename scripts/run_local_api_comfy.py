#!/usr/bin/env python3
"""
Run local HAM API with ComfyUI-friendly defaults (Phase 2G.8 dev ergonomics).

This wrapper keeps local-only values out of committed env files and makes the
active backend explicit for smoke runs.

Usage (from repo root):

    .venv\Scripts\python.exe scripts\run_local_api_comfy.py

Optional overrides (shell env wins):
    HAM_COMFYUI_BASE_URL
    HAM_COMFYUI_CHECKPOINT_NAME
    HAM_COMFYUI_VIDEO_WORKFLOW (default ``comfy_video_local_poc``; use ``wan_hq_t2v_local`` for Wan HQ T2V)
    HAM_COMFYUI_WAN_VIDEO_MODEL_NAME / HAM_COMFYUI_WAN_CLIP_MODEL_NAME / HAM_COMFYUI_WAN_VAE_MODEL_NAME
    HAM_GENERATED_MEDIA_DIR
    PORT / HAM_API_PORT
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_generated_media_dir() -> str:
    return str(Path.home() / ".ham-generated-media")


def _apply_local_comfy_defaults() -> None:
    os.environ.setdefault("HAM_MEDIA_PROVIDER", "comfyui")
    os.environ.setdefault("HAM_MEDIA_IMAGE_GENERATION_ENABLED", "true")
    os.environ.setdefault("HAM_MEDIA_VIDEO_GENERATION_ENABLED", "true")
    os.environ.setdefault("HAM_COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    os.environ.setdefault("HAM_COMFYUI_DEFAULT_WORKFLOW", "sdxl_baseline")
    os.environ.setdefault("HAM_COMFYUI_WORKER_PROFILE", "local_gpu_workstation")
    os.environ.setdefault("HAM_COMFYUI_TIMEOUT_SEC", "180")
    os.environ.setdefault("HAM_COMFYUI_OUTPUT_POLL_SEC", "2")
    os.environ.setdefault("HAM_COMFYUI_VIDEO_TIMEOUT_SEC", "600")
    os.environ.setdefault("HAM_COMFYUI_VIDEO_OUTPUT_MAX_BYTES", str(100 * 1024 * 1024))
    # Placeholder template needs a real checkpoint name for local Comfy workers.
    os.environ.setdefault("HAM_COMFYUI_CHECKPOINT_NAME", "sd_xl_base_1.0.safetensors")
    os.environ.setdefault(
        "HAM_COMFYUI_DEFAULT_NEGATIVE_PROMPT",
        "low quality, blurry, distorted, deformed, text, watermark",
    )
    os.environ.setdefault("HAM_GENERATED_MEDIA_STORE", "local")
    os.environ.setdefault("HAM_GENERATED_MEDIA_DIR", _default_generated_media_dir())


def main() -> None:
    root = _project_root()
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    _apply_local_comfy_defaults()

    print("HAM local Comfy mode")
    print(f"- HAM_MEDIA_PROVIDER={os.environ.get('HAM_MEDIA_PROVIDER')}")
    print(f"- HAM_COMFYUI_BASE_URL={os.environ.get('HAM_COMFYUI_BASE_URL')}")
    print(f"- HAM_COMFYUI_DEFAULT_WORKFLOW={os.environ.get('HAM_COMFYUI_DEFAULT_WORKFLOW')}")
    print(f"- HAM_COMFYUI_CHECKPOINT_NAME={os.environ.get('HAM_COMFYUI_CHECKPOINT_NAME')}")
    print(f"- HAM_COMFYUI_VIDEO_WORKFLOW={(os.environ.get('HAM_COMFYUI_VIDEO_WORKFLOW') or 'comfy_video_local_poc').strip()}")
    print(f"- HAM_GENERATED_MEDIA_STORE={os.environ.get('HAM_GENERATED_MEDIA_STORE')}")
    print(f"- HAM_GENERATED_MEDIA_DIR={os.environ.get('HAM_GENERATED_MEDIA_DIR')}")
    gw = (os.environ.get("HERMES_GATEWAY_MODE") or "").strip().lower() or "mock"
    print(f"- HERMES_GATEWAY_MODE={gw} (chat path; unrelated to media jobs)")
    if gw == "mock":
        print(
            "  Tip: Composer + -> Generate video calls Comfy. Chat text still uses mock echo "
            "unless you set HERMES_GATEWAY_MODE=openrouter (and OPENROUTER_API_KEY) or http."
        )

    from scripts.run_local_api import main as run_local_main

    run_local_main()


if __name__ == "__main__":
    main()
