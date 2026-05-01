"""Conservative chat model capability metadata for the workspace (product-facing, no secrets).

``supports_document_text_context`` means HAM extracts document text server-side and adds bounded
text to the model request — not that the model natively ingests PDF/DOCX blobs.

``supports_pdf_export`` means HAM can export the persisted transcript to PDF — not model-generated PDF.
"""

from __future__ import annotations

import re
from typing import Any

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
        "PDF and DOCX files are text-extracted by HAM before being sent to the model.",
        "Scanned PDFs are not OCRed in this phase.",
        "Video analysis is not implemented yet.",
        "Export PDF downloads the HAM transcript; the model does not generate the PDF.",
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

    return {
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
        "limitations": limitations,
        "document_context_mode": document_context_mode,
        "notes": notes,
    }
