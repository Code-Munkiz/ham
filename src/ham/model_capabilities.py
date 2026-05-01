"""Conservative chat model capability metadata for the workspace (product-facing, no secrets).

``supports_document_text_context`` means HAM extracts document text server-side and adds bounded
text to the model request — not that the model natively ingests PDF/DOCX blobs.

``supports_pdf_export`` means HAM can export the persisted transcript to PDF — not model-generated PDF.
"""

from __future__ import annotations

import re
from typing import Any

from src.ham.media_provider_adapter import (
    default_image_model_env,
    image_generation_feature_enabled,
    openrouter_api_key_configured,
    reference_image_generation_enabled,
)
from src.ham.media_provider_registry import (
    active_media_provider_id,
    availability_dict_rows,
    comfyui_capabilities_row,
    openrouter_capabilities_row,
    provider_notes_for_capabilities,
)

# Display labels for slugs we see often (OpenRouter-style ``org/model``).
_DISPLAY_OVERRIDES: dict[str, str] = {
    "openai/gpt-4o": "GPT-4o",
    "openai/gpt-4o-mini": "GPT-4o mini",
    "anthropic/claude-3.5-sonnet": "Claude 3.5 Sonnet",
    "google/gemini-2.0-flash-001": "Gemini 2.0 Flash",
    "qwen/qwen3-235b-a22b-instruct-2507": "Qwen3 235B Instruct",
}


def _slug_display_name(model_id: str) -> str:
    mid = model_id.strip()
    if mid in _DISPLAY_OVERRIDES:
        return _DISPLAY_OVERRIDES[mid]
    tail = mid.split("/")[-1] if "/" in mid else mid
    # Humanize: qwen3-5-flash -> Qwen3 5 Flash
    if len(tail) > 48:
        return mid
    return re.sub(r"[-_]+", " ", tail).strip().title() or mid


def _vision_heuristic(model_id: str) -> bool:
    """True when id strongly suggests a multimodal/vision SKU (conservative list)."""
    mid = model_id.lower()
    needles = (
        "gpt-4o",
        "gpt-4-turbo",
        "gpt-5",
        "o4",
        "claude-3",
        "claude-3.5",
        "claude-sonnet-4",
        "gemini",
        "qwen2-vl",
        "qwen3-vl",
        "qwen-vl",
        "llava",
        "-vl-",
        "/vl",
        "vision",
        "multimodal",
    )
    return any(n in mid for n in needles)


def _build_generation_capabilities_payload() -> dict[str, Any]:
    """Conservative media-generation flags (orthogonal to chat model / vision input)."""
    core_ok = bool(image_generation_feature_enabled() and openrouter_api_key_configured())
    default_model = bool(default_image_model_env())
    orow = openrouter_capabilities_row()
    active = active_media_provider_id()

    supports_image_generation = False
    supports_image_to_image = False
    supports_reference_images = False
    media_generation_provider: str | None = None

    notes: list[str] = []
    notes.extend(provider_notes_for_capabilities())

    if active == "openrouter":
        supports_image_generation = orow.supports_text_to_image
        ref_ok = reference_image_generation_enabled()
        supports_image_to_image = bool(supports_image_generation and ref_ok)
        supports_reference_images = supports_image_to_image
        if supports_image_generation:
            media_generation_provider = "openrouter"
        if core_ok and not default_model:
            notes.append(
                "Image generation requests should include model_id unless HAM_MEDIA_IMAGE_DEFAULT_MODEL is set."
            )
        if core_ok and not ref_ok:
            notes.append(
                "Reference-conditioned / image-to-image generation may be unavailable until enabled "
                "(HAM_MEDIA_IMAGE_TO_IMAGE_ENABLED when set, compatible HAM_MEDIA_IMAGE_DEFAULT_MODEL)."
            )
        if not core_ok:
            notes.append(
                "Image generation is unavailable until enabled on the server "
                "(HAM_MEDIA_IMAGE_GENERATION_ENABLED and OPENROUTER_API_KEY)."
            )
    elif active == "comfyui":
        crow = comfyui_capabilities_row()
        supports_image_generation = crow.supports_text_to_image
        supports_image_to_image = False
        supports_reference_images = False
        if supports_image_generation:
            media_generation_provider = "comfyui"

    notes = list(dict.fromkeys(notes))
    available = availability_dict_rows()

    payload: dict[str, Any] = {
        "active_media_provider": active,
        "available_media_providers": available,
        "supports_text_to_image": supports_image_generation,
        "supports_image_generation": supports_image_generation,
        "supports_image_editing": False,
        "supports_image_to_image": supports_image_to_image,
        "supports_text_to_video": False,
        "supports_video_generation": False,
        "supports_image_to_video": False,
        "supports_video_editing": False,
        "supports_async_media_jobs": False,
        "supports_reference_images": supports_reference_images,
        "generated_media_max_duration_sec": None,
        "generated_media_max_resolution": None,
        "generated_media_output_types": (
            ["image/png", "image/jpeg", "image/webp", "image/gif"] if supports_image_generation else []
        ),
        "media_generation_provider": media_generation_provider,
        "media_generation_notes": notes,
        "provider_notes": notes,
    }

    if active == "comfyui":
        from src.ham.comfyui_provider_adapter import comfyui_worker_profile_for_capabilities

        profile = comfyui_worker_profile_for_capabilities()
        if profile:
            payload["comfy_worker_profile"] = profile

    return payload


def build_chat_capabilities_payload(
    *,
    model_id: str | None,
    gateway_mode: str | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable payload safe for the browser (no paths, URLs, tokens, env dumps)."""
    mid = (model_id or "").strip() or None
    gm = (gateway_mode or "").strip().lower() or None

    supports_text_chat = True
    supports_image_input = bool(mid and _vision_heuristic(mid))
    # If gateway is mock/local without a concrete model, still avoid claiming vision.
    if gm == "mock":
        supports_image_input = False

    supports_document_text_context = True
    supports_native_pdf = False
    supports_audio_input = False
    supports_video_input = False
    supports_tool_use = False
    supports_pdf_export = True

    display_name = _slug_display_name(mid) if mid else "Chat model"

    limitations = [
        "PDF, DOCX, XLSX, and CSV files are text-extracted by HAM before being sent to the model (bounded).",
        "Legacy .xls files may be stored but are not text-extracted in this phase.",
        "Scanned PDFs are not OCRed in this phase.",
        "MP4/MOV/WebM videos may be attached and stored for the session only; transcripts, thumbnails, "
        "and keyframes are not generated in this phase.",
        "Video attachments are stored for the session — this is not native video generation or editing.",
        "Export PDF downloads the HAM transcript; the model does not generate the PDF.",
        "HAM image uploads (forwarded only when marked vision-capable) are not the same product object as "
        "server-generated pixels (creative image generation APIs are gated separately when enabled).",
    ]
    if not supports_image_input:
        limitations.append(
            "This model is not marked as vision-capable in HAM; image uploads may still work but "
            "may not be forwarded as vision input."
        )

    if not mid:
        notes = (
            "No model id provided; using conservative defaults (image input off until a "
            "vision-capable model is selected)."
        )
    elif supports_image_input:
        notes = (
            "Model id matches HAM vision heuristics; images may be forwarded when the gateway "
            "supports multimodal chat."
        )
    else:
        notes = "Conservative defaults for this model id; vision routing is not assumed."

    document_context_mode = "ham_bounded_text_extraction"

    gen_block = _build_generation_capabilities_payload()

    payload = {
        "model": {
            "id": mid or "",
            "display_name": display_name,
        },
        "capabilities": {
            "text_chat": supports_text_chat,
            "image_input": supports_image_input,
            "document_text_context": supports_document_text_context,
            "native_pdf": supports_native_pdf,
            "audio_input": supports_audio_input,
            "video_input": supports_video_input,
            "pdf_export": supports_pdf_export,
            "tool_use": supports_tool_use,
        },
        "generation": gen_block,
        "limitations": limitations,
        "document_context_mode": document_context_mode,
        "notes": notes,
    }
    return payload
