"""Registry metadata for creative media backends (Phase 2G.5).

Selection is backend-only via env (`HAM_MEDIA_PROVIDER`). Real adapters live in
`media_provider_adapter.py`; placeholders (ComfyUI, Replicate, …) declare metadata only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from src.ham.media_provider_adapter import ImageProviderAdapter

SupportedMediaMode = Literal[
    "text_to_image",
    "image_to_image",
    "image_editing",
    "text_to_video",
    "image_to_video",
]

@dataclass(frozen=True)
class MediaProviderCapabilityMetadata:
    """Product-facing provider row (never URLs or secrets)."""

    provider_id: str
    display_name: str
    configured: bool
    supports_text_to_image: bool
    supports_image_to_image: bool
    supports_image_editing: bool
    supports_text_to_video: bool
    supports_image_to_video: bool


# Declared for roadmap / UI; adapters not implemented except ComfyUI (Phase 2G.6) when configured.
_FUTURE_PLACEHOLDER_IDS: dict[str, str] = {
    "openai_images": "OpenAI Images",
    "replicate": "Replicate",
    "runway": "Runway",
    "luma": "Luma",
    "kling": "Kling",
}


_ALLOWED_HAM_MEDIA_PROVIDER = frozenset(
    {
        "",
        "openrouter",
        "router",
        "or",
        "comfyui",
        "openai_images",
        "replicate",
        "runway",
        "luma",
        "kling",
        "none",
        "unconfigured",
        "disabled",
        "off",
        "test_synthetic",
        "synthetic",
        "synthetic_test",
    }
)


def normalized_ham_media_provider_env() -> str:
    """Raw ``HAM_MEDIA_PROVIDER`` normalized, or ``openrouter`` when unset."""
    raw = (os.environ.get("HAM_MEDIA_PROVIDER") or "").strip().lower()
    return raw or "openrouter"


def _coerce_provider_id(raw: str) -> str:
    if raw in _FUTURE_PLACEHOLDER_IDS:
        return raw
    if raw == "comfyui":
        return "comfyui"
    if raw in ("none", "unconfigured", "disabled", "off"):
        return "unconfigured"
    if raw in ("openrouter", "router", "or"):
        return "openrouter"
    if raw in ("test_synthetic", "synthetic", "synthetic_test"):
        return "test_synthetic"
    # Unknown typos: stay compatible with pre-registry behavior (OpenRouter path).
    return "openrouter"


def active_media_provider_id() -> str:
    """Canonical id backing capability ``active_media_provider`` (requested selection after coercion)."""
    return _coerce_provider_id(normalized_ham_media_provider_env())


def _openrouter_effectively_configured() -> bool:
    from src.ham.media_provider_adapter import (
        image_generation_feature_enabled,
        openrouter_api_key_configured,
    )

    return bool(image_generation_feature_enabled() and openrouter_api_key_configured())


def comfyui_capabilities_row() -> MediaProviderCapabilityMetadata:
    """Metadata only — no outbound calls."""
    from src.ham.comfyui_provider_adapter import comfyui_image_generation_ready, comfyui_video_generation_ready

    ready_img = comfyui_image_generation_ready()
    ready_vid = comfyui_video_generation_ready()
    return MediaProviderCapabilityMetadata(
        provider_id="comfyui",
        display_name="ComfyUI (separate GPU service)",
        configured=bool(ready_img or ready_vid),
        supports_text_to_image=ready_img,
        supports_image_to_image=False,
        supports_image_editing=False,
        supports_text_to_video=ready_vid,
        supports_image_to_video=False,
    )


def openrouter_capabilities_row() -> MediaProviderCapabilityMetadata:
    """OpenRouter adapter row from current env (no outbound calls)."""
    from src.ham.media_provider_adapter import reference_image_generation_enabled

    configured = _openrouter_effectively_configured()
    t2i = configured
    i2i = bool(configured and reference_image_generation_enabled())
    return MediaProviderCapabilityMetadata(
        provider_id="openrouter",
        display_name="OpenRouter",
        configured=configured,
        supports_text_to_image=t2i,
        supports_image_to_image=i2i,
        supports_image_editing=False,
        supports_text_to_video=False,
        supports_image_to_video=False,
    )


def _placeholder_row(provider_id: str, display_name: str) -> MediaProviderCapabilityMetadata:
    return MediaProviderCapabilityMetadata(
        provider_id=provider_id,
        display_name=display_name,
        configured=False,
        supports_text_to_image=False,
        supports_image_to_image=False,
        supports_image_editing=False,
        supports_text_to_video=False,
        supports_image_to_video=False,
    )


def all_media_providers_metadata() -> list[MediaProviderCapabilityMetadata]:
    """Stable order: live OpenRouter first, explicit unconfigured, synthetic, then placeholders."""
    rows: list[MediaProviderCapabilityMetadata] = [
        openrouter_capabilities_row(),
        MediaProviderCapabilityMetadata(
            provider_id="unconfigured",
            display_name="Disabled / not configured",
            configured=False,
            supports_text_to_image=False,
            supports_image_to_image=False,
            supports_image_editing=False,
            supports_text_to_video=False,
            supports_image_to_video=False,
        ),
        MediaProviderCapabilityMetadata(
            provider_id="test_synthetic",
            display_name="Synthetic (tests only)",
            configured=False,
            supports_text_to_image=False,
            supports_image_to_image=False,
            supports_image_editing=False,
            supports_text_to_video=False,
            supports_image_to_video=False,
        ),
    ]
    rows.append(comfyui_capabilities_row())
    for pid, label in sorted(_FUTURE_PLACEHOLDER_IDS.items()):
        rows.append(_placeholder_row(pid, label))
    return rows


def availability_dict_rows() -> list[dict[str, Any]]:
    """JSON-safe ``available_media_providers`` entries (subset of registry)."""
    out: list[dict[str, Any]] = []
    for row in all_media_providers_metadata():
        entry: dict[str, Any] = {
            "id": row.provider_id,
            "display_name": row.display_name,
            "configured": row.configured,
            "supports_text_to_image": row.supports_text_to_image,
            "supports_image_to_image": row.supports_image_to_image,
            "supports_image_editing": row.supports_image_editing,
            "supports_text_to_video": row.supports_text_to_video,
            "supports_image_to_video": row.supports_image_to_video,
        }
        out.append(entry)
    return out


def build_selected_image_generation_adapter() -> ImageProviderAdapter:
    """Resolve ``HAM_MEDIA_PROVIDER`` to an :class:`ImageProviderAdapter`."""
    from src.ham.media_provider_adapter import (
        OpenRouterImageProviderAdapter,
        SyntheticTestOnlyImageAdapter,
        UnconfiguredImageProviderAdapter,
        image_generation_feature_enabled,
        openrouter_api_key_configured,
    )
    from src.llm_client import get_openrouter_base_url

    pid = active_media_provider_id()

    if pid == "unconfigured":
        return UnconfiguredImageProviderAdapter()

    if pid == "comfyui":
        from src.ham.comfyui_provider_adapter import (
            ComfyUIImageProviderAdapter,
            comfyui_api_key_optional,
            comfyui_base_url,
            comfyui_image_generation_ready,
        )

        if not comfyui_image_generation_ready():
            return UnconfiguredImageProviderAdapter()
        return ComfyUIImageProviderAdapter(
            base_url=comfyui_base_url(),
            api_key=comfyui_api_key_optional(),
        )

    if pid in _FUTURE_PLACEHOLDER_IDS:
        return UnconfiguredImageProviderAdapter()

    if pid == "test_synthetic":
        # Only for explicit test env or local dev; never default in production images.
        allow = (os.environ.get("HAM_MEDIA_ALLOW_SYNTHETIC_ADAPTER") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if allow:
            return SyntheticTestOnlyImageAdapter()
        return UnconfiguredImageProviderAdapter()

    # openrouter (default)
    if not image_generation_feature_enabled():
        return UnconfiguredImageProviderAdapter()
    if not openrouter_api_key_configured():
        return UnconfiguredImageProviderAdapter()
    key_val = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not key_val:
        return UnconfiguredImageProviderAdapter()
    api_base = get_openrouter_base_url().rstrip("/")
    return OpenRouterImageProviderAdapter(api_url=api_base, api_key=key_val)


def provider_notes_for_capabilities() -> list[str]:
    """Human-facing notes about registry selection (no secrets)."""
    notes: list[str] = []
    raw = (os.environ.get("HAM_MEDIA_PROVIDER") or "").strip()
    if raw and raw.lower() not in _ALLOWED_HAM_MEDIA_PROVIDER:
        notes.append(
            f"Unrecognized HAM_MEDIA_PROVIDER={raw!r}; treating selection as OpenRouter-compatible defaults."
        )
    active = active_media_provider_id()
    if active == "comfyui":
        from src.ham.comfyui_provider_adapter import comfyui_base_url_configured
        from src.ham.media_provider_adapter import image_generation_feature_enabled

        if not image_generation_feature_enabled():
            notes.append(
                "Image generation is disabled on this server (HAM_MEDIA_IMAGE_GENERATION_ENABLED)."
            )
        elif not comfyui_base_url_configured():
            notes.append(
                "HAM_MEDIA_PROVIDER is ComfyUI but HAM_COMFYUI_BASE_URL is not set — generation is unavailable."
            )

    elif active in _FUTURE_PLACEHOLDER_IDS:
        notes.append(
            f"Media provider {active!r} is not implemented on this server yet — "
            "generation remains disabled until a supported backend is configured."
        )
    synth_allow = (os.environ.get("HAM_MEDIA_ALLOW_SYNTHETIC_ADAPTER") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if active == "test_synthetic" and not synth_allow:
        notes.append(
            "HAM_MEDIA_PROVIDER requests synthetic adapter but HAM_MEDIA_ALLOW_SYNTHETIC_ADAPTER is not enabled."
        )
    return notes
