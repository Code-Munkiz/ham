"""Backend-only image generation (+ download) — Phase 2G.1."""

from __future__ import annotations


from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.api.chat import _resolve_chat_clerk_context
from src.ham.generated_media_store import GeneratedMediaRecord, get_generated_media_store, is_safe_generated_media_id
from src.ham.media_provider_adapter import (
    ImageGenerationError,
    default_image_model_env,
    default_image_output_max_bytes,
    default_image_prompt_max_chars,
    get_image_generation_adapter,
    prompt_digest_and_excerpt,
    UnconfiguredImageProviderAdapter,
)

router = APIRouter(tags=["creative-media"])


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


def _owner_for_request(authorization: str | None) -> str:
    actor, _hdr = _resolve_chat_clerk_context(authorization, None, route="generate_image")
    return actor.user_id if actor is not None else ""


def _public_download_path(gmid: str) -> str:
    return f"/api/media/artifacts/{gmid}/download"


@router.post("/api/media/images/generate")
async def post_generate_image(
    body: GenerateImageRequestBody,
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    """Text-to-image MVP: server generates, stores, returns opaque metadata + relative download path."""
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

    try:
        result = adapter.generate_image(prompt=prompt, model_id=body.model_id)
    except ImageGenerationError as exc:
        status = 400
        if exc.code in (
            "IMAGE_GEN_NOT_CONFIGURED",
            "IMAGE_GEN_MODEL_MISSING",
        ):
            status = 503 if exc.code == "IMAGE_GEN_NOT_CONFIGURED" else 400
        if exc.code == "IMAGE_GEN_UPSTREAM_TIMEOUT":
            status = 504
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
    )
    store.put(result.data, rec)

    return {
        "generated_media_id": gmid,
        "media_type": "image",
        "mime_type": result.mime,
        "status": "ready",
        "download_url": _public_download_path(gmid),
        "width": result.width,
        "height": result.height,
    }


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
