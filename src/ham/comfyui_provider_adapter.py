"""ComfyUI HTTP adapter — text-to-image + text-to-video (Phase 2G.6+, AnimateDiff 2G.12).

Calls a **remote** ComfyUI instance (`HAM_COMFYUI_BASE_URL`). No GPU stack in ham-api.

Workflow graphs are shipped as **tracked templates** under ``configs/media/comfyui/`` (no checkpoints).

Local / operator workers: templates keep a checkpoint **placeholder**. Set optional
``HAM_COMFYUI_CHECKPOINT_NAME`` (filename only as listed by ComfyUI, e.g. ``sd_xl_base_1.0.safetensors``)
to override ``CheckpointLoaderSimple.ckpt_name`` before ``POST /prompt``. Video graphs use
``HAM_COMFYUI_VIDEO_WORKFLOW`` (default ``comfy_video_local_poc``). Wan 2.1 T2V templates use
``UNETLoader`` / ``CLIPLoader`` / ``VAELoader`` placeholders; filenames may be overridden with
``HAM_COMFYUI_WAN_VIDEO_MODEL_NAME``, ``HAM_COMFYUI_WAN_CLIP_MODEL_NAME``, and ``HAM_COMFYUI_WAN_VAE_MODEL_NAME``.
Do not put weights in-repo.
"""

from __future__ import annotations

import copy
import json
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from src.ham.media_provider_adapter import (
    ImageGenerationError,
    ImageGenerationResult,
    ImageProviderAdapter,
    VideoGenerationResult,
    _normalize_mime_image,
    _png_dimensions_safe,
    default_image_output_max_bytes,
    default_image_prompt_max_chars,
    default_video_output_max_bytes,
    image_generation_feature_enabled,
    video_generation_feature_enabled,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def comfyui_base_url_configured() -> bool:
    return bool((os.environ.get("HAM_COMFYUI_BASE_URL") or "").strip())


def comfyui_base_url() -> str:
    return (os.environ.get("HAM_COMFYUI_BASE_URL") or "").strip().rstrip("/")


def comfyui_api_key_optional() -> str | None:
    k = (os.environ.get("HAM_COMFYUI_API_KEY") or "").strip()
    return k or None


_WORKFLOW_ALIAS: dict[str, str] = {
    "sdxl_vanilla": "sdxl_baseline",
}

_ALLOWED_COMFY_WORKER_PROFILES: frozenset[str] = frozenset(
    {
        "local_gpu_workstation",
        "dedicated_gpu_vm",
        "runpod_vast_beam_worker",
        "managed_comfy_cloud_worker",
    }
)


def comfyui_normalize_workflow_key(workflow_key: str) -> str:
    """Stable manifest stem (`sdxl_vanilla` → `sdxl_baseline`)."""
    k = (workflow_key or "").strip()
    if not k:
        k = (os.environ.get("HAM_COMFYUI_DEFAULT_WORKFLOW") or "sdxl_baseline").strip()
    k = k or "sdxl_baseline"
    return _WORKFLOW_ALIAS.get(k, k)


def comfyui_default_workflow_key_raw() -> str:
    k = (os.environ.get("HAM_COMFYUI_DEFAULT_WORKFLOW") or "sdxl_baseline").strip()
    return k or "sdxl_baseline"


def comfyui_default_workflow_key() -> str:
    """Alias-expanded key used when resolving manifest files."""
    return comfyui_normalize_workflow_key(comfyui_default_workflow_key_raw())


def comfyui_worker_profile_for_capabilities() -> str | None:
    raw = (os.environ.get("HAM_COMFYUI_WORKER_PROFILE") or "").strip().lower().replace("-", "_")
    if not raw:
        return None
    return raw if raw in _ALLOWED_COMFY_WORKER_PROFILES else None


def comfyui_image_generation_ready() -> bool:
    """True when registry may return the live Comfy adapter (feature flag + base URL)."""
    return bool(image_generation_feature_enabled() and comfyui_base_url_configured())


def comfyui_video_generation_ready() -> bool:
    """True when local video generation can be attempted against ComfyUI."""
    return bool(video_generation_feature_enabled() and comfyui_base_url_configured())


def comfyui_timeout_sec() -> float:
    raw = (os.environ.get("HAM_COMFYUI_TIMEOUT_SEC") or "").strip()
    if raw:
        try:
            return max(5.0, min(600.0, float(raw)))
        except ValueError:
            pass
    return 120.0


def comfyui_poll_interval_sec() -> float:
    raw = (os.environ.get("HAM_COMFYUI_OUTPUT_POLL_SEC") or "").strip()
    if raw:
        try:
            return max(0.25, min(10.0, float(raw)))
        except ValueError:
            pass
    return 2.0


def comfyui_output_max_bytes() -> int:
    raw = (os.environ.get("HAM_COMFYUI_OUTPUT_MAX_BYTES") or "").strip()
    if raw:
        try:
            return max(10_000, min(30 * 1024 * 1024, int(raw)))
        except ValueError:
            pass
    return default_image_output_max_bytes()


def comfyui_video_timeout_sec() -> float:
    raw = (os.environ.get("HAM_COMFYUI_VIDEO_TIMEOUT_SEC") or "").strip()
    if raw:
        try:
            return max(10.0, min(1200.0, float(raw)))
        except ValueError:
            pass
    return 600.0


def comfyui_video_output_max_bytes() -> int:
    raw = (os.environ.get("HAM_COMFYUI_VIDEO_OUTPUT_MAX_BYTES") or "").strip()
    if raw:
        try:
            return max(200_000, min(500 * 1024 * 1024, int(raw)))
        except ValueError:
            pass
    return default_video_output_max_bytes()


def comfyui_video_workflow_key() -> str:
    raw = (os.environ.get("HAM_COMFYUI_VIDEO_WORKFLOW") or "comfy_video_local_poc").strip()
    return raw or "comfy_video_local_poc"


def _workflow_config_dir() -> Path:
    return _project_root() / "configs" / "media" / "comfyui"


def load_comfy_manifest_and_workflow(workflow_key: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load manifest + workflow template from repo configs (never from user input paths)."""
    canonical = comfyui_normalize_workflow_key(workflow_key)
    base = _workflow_config_dir()
    man_path = base / f"{canonical}.manifest.json"
    if not man_path.is_file():
        raise ImageGenerationError(
            "IMAGE_GEN_COMFY_WORKFLOW_MISSING",
            "ComfyUI workflow manifest is missing on the server.",
        )
    with man_path.open(encoding="utf-8") as f:
        manifest = json.load(f)
    wf_file = (manifest.get("workflow_file") or "").strip()
    if not wf_file or ".." in wf_file or wf_file.startswith(("/", "\\")):
        raise ImageGenerationError(
            "IMAGE_GEN_COMFY_WORKFLOW_INVALID",
            "ComfyUI workflow manifest is invalid.",
        )
    wf_path = base / wf_file
    if not wf_path.is_file():
        raise ImageGenerationError(
            "IMAGE_GEN_COMFY_WORKFLOW_MISSING",
            "ComfyUI workflow template file is missing on the server.",
        )
    with wf_path.open(encoding="utf-8") as f:
        workflow = json.load(f)
    if not isinstance(workflow, dict):
        raise ImageGenerationError(
            "IMAGE_GEN_COMFY_WORKFLOW_INVALID",
            "ComfyUI workflow template is invalid.",
        )
    return manifest, workflow


def _apply_workflow_patches(
    workflow: dict[str, Any],
    manifest: dict[str, Any],
    *,
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    seed: int,
) -> dict[str, Any]:
    w = copy.deepcopy(workflow)
    patches = manifest.get("comfy_patches")
    if not isinstance(patches, dict):
        raise ImageGenerationError(
            "IMAGE_GEN_COMFY_WORKFLOW_INVALID",
            "ComfyUI workflow manifest is invalid.",
        )
    mapping: dict[str, Any] = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "seed": seed,
    }
    for key, val in mapping.items():
        spec = patches.get(key)
        if key == "negative_prompt" and spec is None:
            continue
        if not isinstance(spec, dict):
            raise ImageGenerationError(
                "IMAGE_GEN_COMFY_WORKFLOW_INVALID",
                "ComfyUI workflow manifest is invalid.",
            )
        node_id = str(spec.get("node") or "").strip()
        input_key = str(spec.get("input") or "").strip()
        if not node_id or not input_key:
            raise ImageGenerationError(
                "IMAGE_GEN_COMFY_WORKFLOW_INVALID",
                "ComfyUI workflow manifest is invalid.",
            )
        node = w.get(node_id)
        if not isinstance(node, dict):
            raise ImageGenerationError(
                "IMAGE_GEN_COMFY_WORKFLOW_INVALID",
                "ComfyUI workflow template is invalid.",
            )
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            raise ImageGenerationError(
                "IMAGE_GEN_COMFY_WORKFLOW_INVALID",
                "ComfyUI workflow template is invalid.",
            )
        inputs[input_key] = val
    return w


def _checkpoint_filename_from_env_optional() -> str | None:
    raw = (os.environ.get("HAM_COMFYUI_CHECKPOINT_NAME") or "").strip()
    return raw if raw else None


def _animatediff_model_name_from_env_optional() -> str | None:
    raw = (os.environ.get("HAM_COMFYUI_ANIMATEDIFF_MODEL_NAME") or "").strip()
    return raw if raw else None


def _animatediff_beta_schedule_from_env_optional() -> str | None:
    raw = (os.environ.get("HAM_COMFYUI_ANIMATEDIFF_BETA_SCHEDULE") or "").strip()
    return raw if raw else None


def _wan_video_unet_name_from_env_optional() -> str | None:
    raw = (os.environ.get("HAM_COMFYUI_WAN_VIDEO_MODEL_NAME") or "").strip()
    return raw if raw else None


def _wan_clip_model_name_from_env_optional() -> str | None:
    raw = (os.environ.get("HAM_COMFYUI_WAN_CLIP_MODEL_NAME") or "").strip()
    return raw if raw else None


def _wan_vae_model_name_from_env_optional() -> str | None:
    raw = (os.environ.get("HAM_COMFYUI_WAN_VAE_MODEL_NAME") or "").strip()
    return raw if raw else None


def _apply_wan_loader_env_overrides(graph: dict[str, Any]) -> None:
    """Substitute WAN template loader filenames when HAM_COMFYUI_WAN_* env vars are set."""
    unet = _wan_video_unet_name_from_env_optional()
    clip = _wan_clip_model_name_from_env_optional()
    vae = _wan_vae_model_name_from_env_optional()
    if not unet and not clip and not vae:
        return
    for node in graph.values():
        if not isinstance(node, dict):
            continue
        ctype = node.get("class_type")
        inp = node.get("inputs")
        if not isinstance(inp, dict):
            continue
        if ctype == "UNETLoader" and unet:
            inp["unet_name"] = unet
        elif ctype == "CLIPLoader" and clip:
            inp["clip_name"] = clip
        elif ctype == "VAELoader" and vae:
            inp["vae_name"] = vae


def _apply_checkpoint_name_env_override(graph: dict[str, Any]) -> None:
    """Substitute CheckpointLoaderSimple ckpt_name when HAM_COMFYUI_CHECKPOINT_NAME is set."""
    name = _checkpoint_filename_from_env_optional()
    if not name:
        return
    for node in graph.values():
        if not isinstance(node, dict) or node.get("class_type") != "CheckpointLoaderSimple":
            continue
        inp = node.get("inputs")
        if isinstance(inp, dict):
            inp["ckpt_name"] = name
        break


def _apply_animatediff_loader_env_override(graph: dict[str, Any]) -> None:
    """Optional overrides for ``ADE_AnimateDiffLoaderGen1`` motion module pairing."""
    mm = _animatediff_model_name_from_env_optional()
    bs = _animatediff_beta_schedule_from_env_optional()
    if not mm and not bs:
        return
    for node in graph.values():
        if not isinstance(node, dict) or node.get("class_type") != "ADE_AnimateDiffLoaderGen1":
            continue
        inp = node.get("inputs")
        if not isinstance(inp, dict):
            continue
        if mm:
            inp["model_name"] = mm
        if bs:
            inp["beta_schedule"] = bs
        break


def _apply_video_workflow_patches(
    workflow: dict[str, Any],
    manifest: dict[str, Any],
    *,
    prompt: str,
    negative_prompt: str,
    seed: int,
) -> dict[str, Any]:
    w = copy.deepcopy(workflow)
    patches = manifest.get("comfy_patches")
    if not isinstance(patches, dict):
        raise ImageGenerationError(
            "VIDEO_GEN_COMFY_WORKFLOW_INVALID",
            "ComfyUI video workflow manifest is invalid.",
        )
    mapping: dict[str, Any] = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "seed": seed,
    }
    for key, val in mapping.items():
        spec = patches.get(key)
        if key == "negative_prompt" and not isinstance(spec, dict):
            continue
        if not isinstance(spec, dict):
            continue
        node_id = str(spec.get("node") or "").strip()
        input_key = str(spec.get("input") or "").strip()
        if not node_id or not input_key:
            continue
        node = w.get(node_id)
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        inputs[input_key] = val
    return w


def comfyui_defaults_width_height() -> tuple[int, int]:
    def _one(env_name: str, default: int) -> int:
        raw = (os.environ.get(env_name) or "").strip()
        if raw:
            try:
                return max(256, min(4096, int(raw)))
            except ValueError:
                pass
        return default

    return _one("HAM_COMFYUI_DEFAULT_WIDTH", 1024), _one("HAM_COMFYUI_DEFAULT_HEIGHT", 1024)


def comfyui_default_negative_prompt() -> str:
    return (os.environ.get("HAM_COMFYUI_DEFAULT_NEGATIVE_PROMPT") or "").strip()


def _sniff_mime(data: bytes) -> str | None:
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 6 and data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def _sniff_video_mime(data: bytes) -> str | None:
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video/mp4"
    if len(data) >= 4 and data[:4] == b"\x1a\x45\xdf\xa3":
        return "video/webm"
    return None


def _looks_like_video_filename(name: str) -> bool:
    fn = (name or "").strip().lower()
    return fn.endswith(".mp4") or fn.endswith(".webm") or fn.endswith(".gif")


def _history_media_ref(first: dict[str, Any]) -> dict[str, str] | None:
    fn = first.get("filename")
    typ = first.get("type") or "output"
    sub = first.get("subfolder") or ""
    if isinstance(fn, str) and fn.strip():
        return {
            "filename": fn.strip(),
            "type": str(typ) if typ else "output",
            "subfolder": str(sub) if isinstance(sub, str) else "",
        }
    return None


def _history_pick_entry(hist_body: dict[str, Any], prompt_id: str) -> dict[str, Any] | None:
    if prompt_id in hist_body and isinstance(hist_body[prompt_id], dict):
        return hist_body[prompt_id]  # type: ignore[no-any-return]
    if len(hist_body) == 1:
        only = next(iter(hist_body.values()))
        if isinstance(only, dict):
            return only
    return None


def _history_output_image(entry: dict[str, Any]) -> dict[str, str] | None:
    outputs = entry.get("outputs")
    if not isinstance(outputs, dict):
        return None
    for _, node_out in outputs.items():
        if not isinstance(node_out, dict):
            continue
        images = node_out.get("images")
        if not isinstance(images, list) or not images:
            continue
        first = images[0]
        if not isinstance(first, dict):
            continue
        fn = first.get("filename")
        typ = first.get("type") or "output"
        sub = first.get("subfolder") or ""
        if isinstance(fn, str) and fn.strip():
            return {
                "filename": fn.strip(),
                "type": str(typ) if typ else "output",
                "subfolder": str(sub) if isinstance(sub, str) else "",
            }
    return None


def _history_output_video(entry: dict[str, Any]) -> dict[str, str] | None:
    outputs = entry.get("outputs")
    if not isinstance(outputs, dict):
        return None
    for _, node_out in outputs.items():
        if not isinstance(node_out, dict):
            continue
        vids = node_out.get("videos")
        if isinstance(vids, list) and vids:
            first = vids[0]
            if isinstance(first, dict):
                ref = _history_media_ref(first)
                if ref:
                    return ref
        gifs = node_out.get("gifs")
        if isinstance(gifs, list) and gifs:
            first = gifs[0]
            if isinstance(first, dict):
                ref = _history_media_ref(first)
                if ref:
                    return ref
        # Some workflows (CreateVideo + SaveVideo) surface MP4/WebM/GIF in images[].
        # Allow this only when it is explicitly video-like to avoid normal PNG/JPG pickup.
        images = node_out.get("images")
        if isinstance(images, list) and images:
            animated = bool(node_out.get("animated"))
            for cand in images:
                if not isinstance(cand, dict):
                    continue
                ref = _history_media_ref(cand)
                if not ref:
                    continue
                if animated or _looks_like_video_filename(ref["filename"]):
                    return ref
    return None


class ComfyUIImageProviderAdapter(ImageProviderAdapter):
    provider_slug = "comfyui"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout_sec: float | None = None,
        poll_sec: float | None = None,
        workflow_key: str | None = None,
    ) -> None:
        self._base = base_url.strip().rstrip("/")
        self._api_key = (api_key or "").strip() or None
        self._timeout = float(timeout_sec) if timeout_sec is not None else comfyui_timeout_sec()
        self._poll = float(poll_sec) if poll_sec is not None else comfyui_poll_interval_sec()
        self._workflow_key = (workflow_key or "").strip() or comfyui_default_workflow_key()

    def _headers(self) -> dict[str, str]:
        if self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    def generate_video(self, *, prompt: str, model_id: str | None = None) -> VideoGenerationResult:
        pstrip = prompt.strip()
        mc = default_image_prompt_max_chars()
        if not pstrip:
            raise ImageGenerationError("VIDEO_GEN_PROMPT_EMPTY", "Prompt must not be empty.")
        if len(pstrip) > mc:
            raise ImageGenerationError(
                "VIDEO_GEN_PROMPT_TOO_LONG",
                f"Prompt exceeds maximum length ({mc} characters).",
            )
        _ = model_id

        manifest, workflow_template = load_comfy_manifest_and_workflow(comfyui_video_workflow_key())
        graph = _apply_video_workflow_patches(
            workflow_template,
            manifest,
            prompt=pstrip,
            negative_prompt=comfyui_default_negative_prompt(),
            seed=secrets.randbelow(2**31 - 1),
        )
        _apply_checkpoint_name_env_override(graph)
        _apply_animatediff_loader_env_override(graph)
        _apply_wan_loader_env_overrides(graph)

        client_id = str(uuid.uuid4())
        enqueue = {"prompt": graph, "client_id": client_id}
        max_out = comfyui_video_output_max_bytes()
        deadline = time.monotonic() + comfyui_video_timeout_sec()
        with httpx.Client(timeout=comfyui_video_timeout_sec()) as client:
            r = client.post(
                f"{self._base}/prompt",
                json=enqueue,
                headers=self._headers(),
            )
            if r.status_code >= 400:
                raise ImageGenerationError(
                    "VIDEO_GEN_UPSTREAM_REJECTED",
                    "Video generation failed.",
                )
            try:
                resp = r.json()
            except json.JSONDecodeError as exc:
                raise ImageGenerationError(
                    "VIDEO_GEN_INVALID_RESPONSE",
                    "Video generation returned an unexpected response.",
                ) from exc
            if not isinstance(resp, dict):
                raise ImageGenerationError(
                    "VIDEO_GEN_INVALID_RESPONSE",
                    "Video generation returned an unexpected response.",
                )
            node_errors = resp.get("node_errors")
            if isinstance(node_errors, dict) and node_errors:
                raise ImageGenerationError("VIDEO_GEN_UPSTREAM_REJECTED", "Video generation failed.")
            pid = resp.get("prompt_id")
            if not isinstance(pid, str) or not pid.strip():
                raise ImageGenerationError(
                    "VIDEO_GEN_INVALID_RESPONSE",
                    "Video generation returned an unexpected response.",
                )
            pid = pid.strip()

            video_ref: dict[str, str] | None = None
            while time.monotonic() < deadline:
                hr = client.get(f"{self._base}/history/{pid}", headers=self._headers())
                if hr.status_code == 200:
                    try:
                        hist = hr.json()
                    except json.JSONDecodeError:
                        hist = None
                    if isinstance(hist, dict):
                        entry = _history_pick_entry(hist, pid)
                        if isinstance(entry, dict):
                            video_ref = _history_output_video(entry)
                            if video_ref:
                                break
                time.sleep(self._poll)

            if video_ref is None:
                raise ImageGenerationError("VIDEO_GEN_UPSTREAM_TIMEOUT", "Video generation timed out.")

            q = (
                f"filename={quote(video_ref['filename'], safe='')}"
                f"&type={quote(video_ref['type'], safe='')}"
            )
            sub = video_ref.get("subfolder") or ""
            if sub.strip():
                q += f"&subfolder={quote(sub.strip(), safe='')}"
            vr = client.get(f"{self._base}/view?{q}", headers=self._headers())
            if vr.status_code >= 400:
                raise ImageGenerationError("VIDEO_GEN_UPSTREAM_REJECTED", "Video generation failed.")

            blob = vr.content
            if len(blob) > max_out:
                raise ImageGenerationError(
                    "VIDEO_GEN_OUTPUT_TOO_LARGE",
                    "Generated video exceeds the maximum allowed size.",
                )
            ct_hdr = vr.headers.get("content-type") or ""
            mime = ct_hdr.split(";", 1)[0].strip().lower() if ct_hdr else ""
            allowed_mimes = ("video/mp4", "video/webm", "image/gif")
            if mime not in allowed_mimes:
                sniffed = _sniff_video_mime(blob)
                if sniffed:
                    mime = sniffed
                else:
                    sniffed_img = _sniff_mime(blob)
                    mime = sniffed_img or ""
            if mime not in allowed_mimes:
                raise ImageGenerationError("VIDEO_GEN_NO_VIDEO", "The upstream service returned no usable video.")
            return VideoGenerationResult(data=blob, mime=mime)

    def generate_image(
        self,
        *,
        prompt: str,
        model_id: str | None,
        reference_image: tuple[bytes, str] | None = None,
    ) -> ImageGenerationResult:
        if reference_image:
            raise ImageGenerationError(
                "IMAGE_TO_IMAGE_NOT_SUPPORTED",
                "Reference-conditioned image generation is not enabled for ComfyUI in this deployment.",
            )
        pstrip = prompt.strip()
        mc = default_image_prompt_max_chars()
        if not pstrip:
            raise ImageGenerationError("IMAGE_GEN_PROMPT_EMPTY", "Prompt must not be empty.")
        if len(pstrip) > mc:
            raise ImageGenerationError(
                "IMAGE_GEN_PROMPT_TOO_LONG",
                f"Prompt exceeds maximum length ({mc} characters).",
            )
        _ = model_id  # SDXL baseline: checkpoint placeholder in template unless HAM_COMFYUI_CHECKPOINT_NAME

        manifest, workflow_template = load_comfy_manifest_and_workflow(self._workflow_key)
        w_px, h_px = comfyui_defaults_width_height()
        seed = secrets.randbelow(2**31 - 1)
        neg = comfyui_default_negative_prompt()
        graph = _apply_workflow_patches(
            workflow_template,
            manifest,
            prompt=pstrip,
            negative_prompt=neg,
            width=w_px,
            height=h_px,
            seed=seed,
        )
        _apply_checkpoint_name_env_override(graph)

        client_id = str(uuid.uuid4())
        enqueue = {"prompt": graph, "client_id": client_id}
        max_out = comfyui_output_max_bytes()
        deadline = time.monotonic() + self._timeout

        try:
            with httpx.Client(timeout=self._timeout) as client:
                r = client.post(
                    f"{self._base}/prompt",
                    json=enqueue,
                    headers=self._headers(),
                )
                if r.status_code >= 400:
                    raise ImageGenerationError(
                        "IMAGE_GEN_UPSTREAM_REJECTED",
                        "Image generation failed. Adjust your prompt or try again.",
                    )
                try:
                    resp = r.json()
                except json.JSONDecodeError as exc:
                    raise ImageGenerationError(
                        "IMAGE_GEN_INVALID_RESPONSE",
                        "Image generation returned an unexpected response.",
                    ) from exc
                if not isinstance(resp, dict):
                    raise ImageGenerationError(
                        "IMAGE_GEN_INVALID_RESPONSE",
                        "Image generation returned an unexpected response.",
                    )

                node_errors = resp.get("node_errors")
                if isinstance(node_errors, dict) and node_errors:
                    raise ImageGenerationError(
                        "IMAGE_GEN_UPSTREAM_REJECTED",
                        "Image generation failed. Adjust your prompt or try again.",
                    )

                pid = resp.get("prompt_id")
                if not isinstance(pid, str) or not pid.strip():
                    raise ImageGenerationError(
                        "IMAGE_GEN_INVALID_RESPONSE",
                        "Image generation returned an unexpected response.",
                    )
                pid = pid.strip()

                image_ref: dict[str, str] | None = None
                while time.monotonic() < deadline:
                    hr = client.get(f"{self._base}/history/{pid}", headers=self._headers())
                    if hr.status_code == 200:
                        try:
                            hist = hr.json()
                        except json.JSONDecodeError:
                            hist = None
                        if isinstance(hist, dict):
                            entry = _history_pick_entry(hist, pid)
                            if isinstance(entry, dict):
                                image_ref = _history_output_image(entry)
                                if image_ref:
                                    break
                    time.sleep(self._poll)

                if image_ref is None:
                    raise ImageGenerationError(
                        "IMAGE_GEN_UPSTREAM_TIMEOUT",
                        "Image generation timed out.",
                    )

                q = (
                    f"filename={quote(image_ref['filename'], safe='')}"
                    f"&type={quote(image_ref['type'], safe='')}"
                )
                sub = image_ref.get("subfolder") or ""
                if sub.strip():
                    q += f"&subfolder={quote(sub.strip(), safe='')}"

                vr = client.get(f"{self._base}/view?{q}", headers=self._headers())
                if vr.status_code >= 400:
                    raise ImageGenerationError(
                        "IMAGE_GEN_UPSTREAM_REJECTED",
                        "Image generation failed while retrieving output.",
                    )

                blob = vr.content
                if len(blob) > max_out:
                    raise ImageGenerationError(
                        "IMAGE_GEN_OUTPUT_TOO_LARGE",
                        "Generated image exceeds the maximum allowed size.",
                    )

                ct_hdr = vr.headers.get("content-type") or ""
                mime = ""
                if ";" in ct_hdr:
                    mime = ct_hdr.split(";", 1)[0].strip()
                elif ct_hdr:
                    mime = ct_hdr.strip()
                mime_n = _normalize_mime_image(mime) if mime else None
                if not mime_n:
                    sniffed = _sniff_mime(blob)
                    mime_n = _normalize_mime_image(sniffed) if sniffed else None

                if not mime_n:
                    raise ImageGenerationError(
                        "IMAGE_GEN_NO_IMAGE",
                        "The upstream service returned no usable image.",
                    )

                wd: int | None
                ht: int | None
                if mime_n == "image/png":
                    wd, ht = _png_dimensions_safe(blob)
                else:
                    wd, ht = None, None
                return ImageGenerationResult(data=blob, mime=mime_n, width=wd, height=ht)

        except httpx.TimeoutException as exc:
            raise ImageGenerationError(
                "IMAGE_GEN_UPSTREAM_TIMEOUT",
                "Image generation timed out.",
            ) from exc
        except httpx.HTTPError as exc:
            raise ImageGenerationError(
                "IMAGE_GEN_UPSTREAM_ERROR",
                "Could not reach the image generation service.",
            ) from exc
