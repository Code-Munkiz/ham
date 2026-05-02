"""Backend-only image generation (+ download) — Phase 2G.1, reference image Phase 2G.3."""

from __future__ import annotations

import os
import threading
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.api.chat import _resolve_chat_clerk_context
from src.ham.chat_attachment_store import (
    default_attachment_max_bytes,
    get_chat_attachment_store,
    is_safe_attachment_id,
)
from src.ham.generated_media_store import GeneratedMediaRecord, get_generated_media_store, is_safe_generated_media_id
from src.ham.media_jobs import create_media_job, get_media_job, is_safe_media_job_id, update_media_job
from src.ham.comfyui_provider_adapter import ComfyUIImageProviderAdapter
from src.ham.media_provider_adapter import (
    ImageGenerationError,
    VideoGenerationResult,
    default_image_model_env,
    default_image_output_max_bytes,
    default_image_prompt_max_chars,
    get_image_generation_adapter,
    prompt_digest_and_excerpt,
    reference_image_generation_enabled,
    UnconfiguredImageProviderAdapter,
    video_generation_feature_enabled,
)

router = APIRouter(tags=["creative-media"])

_REF_MIME_ALLOWED = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})


def _normalize_ref_mime(raw: str) -> str | None:
    m = (raw or "").strip().lower()
    if m == "image/jpg":
        m = "image/jpeg"
    return m if m in _REF_MIME_ALLOWED else None


# Align with chat uploads: image attachments are capped server-side on upload; keep reference read bound tight.
_REF_IMAGE_CEIL = 10 * 1024 * 1024


def _media_reference_max_bytes() -> int:
    cap = min(default_attachment_max_bytes(), _REF_IMAGE_CEIL)
    raw = (os.environ.get("HAM_MEDIA_REFERENCE_IMAGE_MAX_BYTES") or "").strip()
    if raw:
        try:
            parsed = int(raw)
            return max(1024, min(parsed, cap))
        except ValueError:
            pass
    return cap


def _ext_for_mime(mime: str) -> str:
    m = mime.lower()
    if m == "image/png":
        return "png"
    if m in ("image/jpeg", "image/jpg"):
        return "jpg"
    if m == "image/webp":
        return "webp"
    if m == "image/gif":
        return "gif"
    return "bin"


class GenerateImageRequestBody(BaseModel):
    prompt: str = Field(..., min_length=1)
    model_id: str | None = None
    reference_attachment_id: str | None = None


class GenerateVideoRequestBody(BaseModel):
    prompt: str = Field(..., min_length=1)
    model_id: str | None = None


def _owner_for_request(authorization: str | None) -> str:
    actor, _hdr = _resolve_chat_clerk_context(authorization, None, route="generate_image")
    return actor.user_id if actor is not None else ""


def _public_download_path(gmid: str) -> str:
    return f"/api/media/artifacts/{gmid}/download"


def _video_ext_for_mime(mime: str) -> str:
    m = mime.lower()
    if m == "video/mp4":
        return "mp4"
    if m == "video/webm":
        return "webm"
    return "bin"


def _run_video_job(
    *,
    job_id: str,
    prompt: str,
    model_id: str | None,
    owner: str,
) -> None:
    update_media_job(job_id, status="running")
    try:
        adapter = get_image_generation_adapter()
        if not isinstance(adapter, ComfyUIImageProviderAdapter):
            raise ImageGenerationError("VIDEO_GENERATION_FAILED", "Video generation failed.")
        res: VideoGenerationResult = adapter.generate_video(prompt=prompt, model_id=model_id)
        digest, excerpt = prompt_digest_and_excerpt(prompt)
        store = get_generated_media_store()
        gmid = store.new_id()
        ext = _video_ext_for_mime(res.mime)
        safe_name = f"ham-generated.{ext}"
        rec = GeneratedMediaRecord(
            id=gmid,
            media_type="video",
            mime=res.mime,
            size_bytes=len(res.data),
            owner_key=owner,
            status="ready",
            safe_display_name=safe_name,
            prompt_digest=digest,
            prompt_excerpt=excerpt,
            provider_slug=getattr(adapter, "provider_slug", None),
            model_id=(model_id or None),
            width=res.width,
            height=res.height,
            storage_blob_key=None,
            from_reference_image=False,
        )
        store.put(res.data, rec)
        update_media_job(
            job_id,
            status="succeeded",
            generated_media_id=gmid,
            download_url=_public_download_path(gmid),
            media_type="video",
        )
    except Exception:
        update_media_job(
            job_id,
            status="failed",
            error={"code": "VIDEO_GENERATION_FAILED", "message": "Video generation failed."},
        )


def _resolve_reference_attachment(
    *,
    attachment_id: str,
    authorization_actor_user_id: str | None,
) -> tuple[bytes, str]:
    """Load reference bytes for image generation; raises HTTPException on client errors."""
    aid = attachment_id.strip()
    if not is_safe_attachment_id(aid):
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "IMAGE_GEN_REFERENCE_ATTACHMENT_INVALID",
                    "message": "Invalid reference attachment id.",
                },
            },
        )

    store = get_chat_attachment_store()
    got = store.get(aid)
    if got is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "ATTACHMENT_NOT_FOUND", "message": "Unknown attachment id."}},
        )
    data, rec = got
    ok = (rec.owner_key or "").strip()
    if ok:
        viewer = (authorization_actor_user_id or "").strip()
        if viewer != ok:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "ATTACHMENT_FORBIDDEN",
                        "message": "Not allowed to use this attachment.",
                    },
                },
            )

    if rec.kind != "image":
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "IMAGE_GEN_REFERENCE_NOT_IMAGE",
                    "message": "Reference attachment must be an image.",
                },
            },
        )

    mime = _normalize_ref_mime(rec.mime or "")
    if not mime:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "IMAGE_GEN_REFERENCE_MIME_UNSUPPORTED",
                    "message": "Reference image type is not supported for generation.",
                },
            },
        )

    max_ref = _media_reference_max_bytes()
    if len(data) > max_ref:
        raise HTTPException(
            status_code=413,
            detail={
                "error": {
                    "code": "IMAGE_GEN_REFERENCE_TOO_LARGE",
                    "message": f"Reference image exceeds maximum size ({max_ref} bytes).",
                },
            },
        )

    return data, mime


@router.post("/api/media/images/generate")
async def post_generate_image(
    body: GenerateImageRequestBody,
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    """Text-to-image MVP; optional Phase 2G.3 reference attachment for image-conditioned generation."""
    mc = default_image_prompt_max_chars()
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "IMAGE_GEN_PROMPT_EMPTY", "message": "Prompt must not be empty."}},
        )
    if len(prompt) > mc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "IMAGE_GEN_PROMPT_TOO_LONG",
                    "message": f"Prompt exceeds maximum length ({mc} characters).",
                },
            },
        )

    ref_raw = (body.reference_attachment_id or "").strip() or None
    actor_for_owner, _ = _resolve_chat_clerk_context(authorization, None, route="generate_image")
    viewer_id = actor_for_owner.user_id if actor_for_owner is not None else None

    owner = _owner_for_request(authorization)

    adapter = get_image_generation_adapter()
    if isinstance(adapter, UnconfiguredImageProviderAdapter):
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "IMAGE_GEN_NOT_CONFIGURED",
                    "message": "Image generation is not enabled or is not configured on this server.",
                },
            },
        )

    reference_image: tuple[bytes, str] | None = None
    used_reference = False
    if ref_raw is not None:
        if not reference_image_generation_enabled():
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "code": "IMAGE_TO_IMAGE_NOT_SUPPORTED",
                        "message": "Image editing / reference-conditioned generation is not enabled on this server.",
                    },
                },
            )
        ref_bytes, ref_mime = _resolve_reference_attachment(
            attachment_id=ref_raw,
            authorization_actor_user_id=viewer_id,
        )
        reference_image = (ref_bytes, ref_mime)
        used_reference = True

    try:
        result = adapter.generate_image(prompt=prompt, model_id=body.model_id, reference_image=reference_image)
    except ImageGenerationError as exc:
        status = 400
        if exc.code in (
            "IMAGE_GEN_NOT_CONFIGURED",
            "IMAGE_GEN_MODEL_MISSING",
        ):
            status = 503 if exc.code == "IMAGE_GEN_NOT_CONFIGURED" else 400
        if exc.code == "IMAGE_GEN_UPSTREAM_TIMEOUT":
            status = 504
        if exc.code in ("IMAGE_REFERENCE_INVALID",):
            status = 400
        if exc.code in ("IMAGE_EDIT_PROVIDER_NOT_CONFIGURED", "IMAGE_TO_IMAGE_NOT_SUPPORTED"):
            status = 503
        raise HTTPException(
            status_code=status,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc

    max_b = default_image_output_max_bytes()
    if len(result.data) > max_b:
        raise HTTPException(
            status_code=413,
            detail={
                "error": {
                    "code": "IMAGE_GEN_OUTPUT_TOO_LARGE",
                    "message": "Generated image exceeds the maximum allowed size.",
                },
            },
        )

    digest, excerpt = prompt_digest_and_excerpt(prompt)
    store = get_generated_media_store()
    gmid = store.new_id()
    ext = _ext_for_mime(result.mime)
    safe_name = f"ham-generated.{ext}"
    rec = GeneratedMediaRecord(
        id=gmid,
        media_type="image",
        mime=result.mime,
        size_bytes=len(result.data),
        owner_key=owner,
        status="ready",
        safe_display_name=safe_name,
        prompt_digest=digest,
        prompt_excerpt=excerpt,
        provider_slug=getattr(adapter, "provider_slug", None),
        model_id=(body.model_id or default_image_model_env() or None),
        width=result.width,
        height=result.height,
        storage_blob_key=None,
        from_reference_image=used_reference,
    )
    store.put(result.data, rec)

    out: dict[str, Any] = {
        "generated_media_id": gmid,
        "media_type": "image",
        "mime_type": result.mime,
        "status": "ready",
        "download_url": _public_download_path(gmid),
        "width": result.width,
        "height": result.height,
    }
    if used_reference:
        out["generated_from_reference_image"] = True
    return out


@router.post("/api/media/videos/generate")
async def post_generate_video(
    body: GenerateVideoRequestBody,
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    prompt = body.prompt.strip()
    mc = default_image_prompt_max_chars()
    if not prompt:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "VIDEO_GEN_PROMPT_EMPTY", "message": "Prompt must not be empty."}},
        )
    if len(prompt) > mc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "VIDEO_GEN_PROMPT_TOO_LONG",
                    "message": f"Prompt exceeds maximum length ({mc} characters).",
                },
            },
        )
    if not video_generation_feature_enabled():
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "VIDEO_GEN_NOT_CONFIGURED",
                    "message": "Video generation is not enabled or is not configured on this server.",
                },
            },
        )
    adapter = get_image_generation_adapter()
    if isinstance(adapter, UnconfiguredImageProviderAdapter) or not isinstance(adapter, ComfyUIImageProviderAdapter):
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "VIDEO_GEN_NOT_CONFIGURED",
                    "message": "Video generation is not enabled or is not configured on this server.",
                },
            },
        )
    owner = _owner_for_request(authorization)
    job = create_media_job(status="queued", owner_key=owner)
    t = threading.Thread(
        target=_run_video_job,
        kwargs={
            "job_id": str(job["job_id"]),
            "prompt": prompt,
            "model_id": body.model_id,
            "owner": owner,
        },
        daemon=True,
    )
    t.start()
    return {"job_id": job["job_id"], "status": "queued"}


@router.get("/api/media/jobs/{job_id}")
async def get_media_job_status(
    job_id: str,
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    if not is_safe_media_job_id(job_id):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "MEDIA_JOB_NOT_FOUND", "message": "Unknown media job id."}},
        )
    job = get_media_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "MEDIA_JOB_NOT_FOUND", "message": "Unknown media job id."}},
        )
    actor, _hdr = _resolve_chat_clerk_context(authorization, None, route="get_media_job_status")
    owner = str(job.get("owner_key") or "").strip()
    if owner and (actor is None or actor.user_id != owner):
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "MEDIA_JOB_FORBIDDEN", "message": "Not allowed to read this media job."}},
        )
    out: dict[str, Any] = {"job_id": job["job_id"], "status": job["status"]}
    if job.get("status") == "succeeded":
        out["generated_media_id"] = job.get("generated_media_id")
        out["download_url"] = job.get("download_url")
        out["media_type"] = "video"
    elif job.get("status") == "failed":
        out["error"] = {"code": "VIDEO_GENERATION_FAILED", "message": "Video generation failed."}
    return out


@router.get("/api/media/artifacts/{generated_media_id}")
async def get_generated_media_meta(
    generated_media_id: str,
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    actor, _hdr = _resolve_chat_clerk_context(authorization, None, route="get_generated_media_meta")
    if not is_safe_generated_media_id(generated_media_id):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "GENERATED_MEDIA_NOT_FOUND", "message": "Unknown generated media id."}},
        )
    store = get_generated_media_store()
    meta = store.get_meta(generated_media_id)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "GENERATED_MEDIA_NOT_FOUND", "message": "Unknown generated media id."}},
        )
    owner = (meta.owner_key or "").strip()
    if owner and (actor is None or actor.user_id != owner):
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "GENERATED_MEDIA_FORBIDDEN", "message": "Not allowed to read this artifact."}},
        )

    out = meta.to_public_meta()
    out["download_url"] = _public_download_path(generated_media_id)
    return out


@router.get("/api/media/artifacts/{generated_media_id}/download")
async def download_generated_media(
    generated_media_id: str,
    authorization: str | None = Header(None, alias="Authorization"),
) -> Response:
    actor, _hdr = _resolve_chat_clerk_context(authorization, None, route="download_generated_media")
    if not is_safe_generated_media_id(generated_media_id):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "GENERATED_MEDIA_NOT_FOUND", "message": "Unknown generated media id."}},
        )
    store = get_generated_media_store()
    got = store.get(generated_media_id)
    if got is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "GENERATED_MEDIA_NOT_FOUND", "message": "Unknown generated media id."}},
        )
    data, rec = got
    owner = (rec.owner_key or "").strip()
    if owner and (actor is None or actor.user_id != owner):
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "GENERATED_MEDIA_FORBIDDEN", "message": "Not allowed to read this artifact."}},
        )
    safe_name = (rec.safe_display_name or "image").replace('"', "").replace("\r", "").replace("\n", "")[:200]
    return Response(
        content=data,
        media_type=rec.mime,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "Cache-Control": "no-store",
        },
    )
