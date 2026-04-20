"""Unified model catalog for Ham composer: Cursor API slugs (display-only for chat) + OpenRouter chat rows."""
from __future__ import annotations

import os
from typing import Any, Literal

import httpx
from fastapi import APIRouter

from src.llm_client import resolve_openrouter_model_name_for_chat
from src.persistence.cursor_credentials import get_effective_cursor_api_key

router = APIRouter(prefix="/api", tags=["models"])

CURSOR_CHAT_DISABLED_REASON = (
    "Dashboard chat is OpenRouter-backed only. Cursor API models are listed for alignment; "
    "use Cloud Agents (POST /api/cursor/agents/launch) for Cursor-side execution."
)

# Slug -> (label, tag, description) for approved UI shape; unknown slugs still listed by API value.
_CURSOR_SLUG_META: dict[str, tuple[str, str, str]] = {
    "composer-2": (
        "Composer 2",
        "LATEST",
        "Standard production engine for complex tasks.",
    ),
    "claude-opus-4-7-thinking-high": (
        "Opus 4.7",
        "HIGH",
        "Supreme logic for architectural decisions.",
    ),
    "gpt-5.3-codex-high": (
        "Codex 5.3",
        "MEDIUM",
        "Pure code generation and symbolic reasoning.",
    ),
    "gpt-5.4-high": (
        "GPT-5.4",
        "MEDIUM",
        "Experimental next-gen frontier model.",
    ),
    "claude-4.6-opus-high-thinking-fast": (
        "Sonnet 4.6",
        "MEDIUM",
        "Ideal trade-off between speed and intelligence.",
    ),
}

# When Cursor API is unreachable, show these slugs so the UI matches product language (still chat-disabled).
_FALLBACK_CURSOR_SLUGS: list[str] = [
    "composer-2",
    "claude-opus-4-7-thinking-high",
    "gpt-5.3-codex-high",
    "gpt-5.4-high",
    "claude-4.6-opus-high-thinking-fast",
]


def _gateway_mode() -> str:
    raw = (os.environ.get("HERMES_GATEWAY_MODE") or "").strip().lower()
    if raw == "mock":
        return "mock"
    if raw == "openrouter":
        return "openrouter"
    if raw == "http":
        return "http"
    base = (os.environ.get("HERMES_GATEWAY_BASE_URL") or "").strip()
    return "http" if base else "mock"


def _openrouter_chat_ready() -> bool:
    if _gateway_mode() != "openrouter":
        return False
    return bool((os.environ.get("OPENROUTER_API_KEY") or "").strip())


def _normalize_openrouter_litellm_model(raw: str) -> str:
    r = raw.strip()
    if not r:
        return resolve_openrouter_model_name_for_chat()
    if r.startswith("openrouter/"):
        return r
    return f"openrouter/{r}"


def _fetch_cursor_slugs() -> list[str]:
    key = get_effective_cursor_api_key()
    if not key:
        return []
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                "https://api.cursor.com/v0/models",
                auth=(key.strip(), ""),
            )
        if resp.status_code != 200:
            return []
        data = resp.json()
        models = data.get("models")
        if not isinstance(models, list):
            return []
        out: list[str] = []
        for m in models:
            if isinstance(m, str) and m.strip():
                out.append(m.strip())
        return sorted(set(out))
    except (httpx.RequestError, ValueError, TypeError):
        return []


def _slug_row(slug: str) -> dict[str, Any]:
    meta = _CURSOR_SLUG_META.get(slug)
    if meta:
        label, tag, desc = meta
    else:
        label, tag, desc = slug, "API", "Listed by Cursor API for this key."
    return {
        "id": f"cursor:{slug}",
        "label": label,
        "tag": tag,
        "tier": None,
        "provider": "cursor",
        "description": desc,
        "supports_chat": False,
        "disabled_reason": CURSOR_CHAT_DISABLED_REASON,
        "cursor_slug": slug,
    }


def build_catalog_payload() -> dict[str, Any]:
    slugs = _fetch_cursor_slugs()
    source: Literal["cursor_api", "fallback"] = "cursor_api" if slugs else "fallback"
    if not slugs:
        slugs = list(_FALLBACK_CURSOR_SLUGS)

    cursor_items: list[dict[str, Any]] = []
    for s in slugs:
        cursor_items.append(_slug_row(s))
        # Reference UI: second row for the same slug, FAST vs LATEST (still Cursor / not chat).
        if s == "composer-2":
            cursor_items.append(
                {
                    "id": "cursor:composer-2-fast",
                    "label": "Composer 2",
                    "tag": "FAST",
                    "tier": None,
                    "provider": "cursor",
                    "description": "Optimized for rapid iteration and small patches.",
                    "supports_chat": False,
                    "disabled_reason": CURSOR_CHAT_DISABLED_REASON,
                    "cursor_slug": "composer-2",
                },
            )

    or_ready = _openrouter_chat_ready()
    or_reason = None if or_ready else (
        "Set HERMES_GATEWAY_MODE=openrouter and OPENROUTER_API_KEY on the API host for chat."
        if _gateway_mode() != "openrouter"
        else "OPENROUTER_API_KEY is not set."
    )

    openrouter_items: list[dict[str, Any]] = [
        {
            "id": "openrouter:default",
            "label": "OpenRouter AI",
            "tag": "EXTERNAL",
            "tier": None,
            "provider": "openrouter",
            "description": "Unified access via Ham chat gateway (OpenRouter).",
            "supports_chat": or_ready,
            "disabled_reason": or_reason,
            "openrouter_model": resolve_openrouter_model_name_for_chat(),
        },
        {
            "id": "tier:auto",
            "label": "Auto",
            "tag": "EFFICIENCY",
            "tier": "auto",
            "provider": "openrouter",
            "description": "Efficiency-oriented default (DEFAULT_MODEL / gateway default).",
            "supports_chat": or_ready,
            "disabled_reason": or_reason,
            "openrouter_model": _normalize_openrouter_litellm_model(
                (os.environ.get("DEFAULT_MODEL") or "openai/gpt-4o-mini").strip(),
            ),
        },
        {
            "id": "tier:premium",
            "label": "Premium",
            "tag": "INTELLIGENCE",
            "tier": "premium",
            "provider": "openrouter",
            "description": "Higher-capability default (HAM_CHAT_PREMIUM_MODEL or HERMES_GATEWAY_MODEL).",
            "supports_chat": or_ready,
            "disabled_reason": or_reason,
            "openrouter_model": _normalize_openrouter_litellm_model(
                (
                    (os.environ.get("HAM_CHAT_PREMIUM_MODEL") or "").strip()
                    or (os.environ.get("HERMES_GATEWAY_MODEL") or "").strip()
                    or "anthropic/claude-3.5-sonnet"
                ),
            ),
        },
    ]

    items = openrouter_items + cursor_items
    return {
        "items": items,
        "source": source,
        "gateway_mode": _gateway_mode(),
        "openrouter_chat_ready": or_ready,
    }


def resolve_model_id_for_chat(model_id: str | None) -> str | None:
    """
    Return LiteLLM model string for OpenRouter, or None to use gateway default.
    Raises ValueError if model_id is set but not allowed for chat (e.g. cursor:*).
    """
    if not model_id or not str(model_id).strip():
        return None
    mid = str(model_id).strip()
    if mid.startswith("cursor:"):
        raise ValueError("CURSOR_MODEL_NOT_CHAT_ENABLED")
    payload = build_catalog_payload()
    for it in payload["items"]:
        if it.get("id") == mid:
            if not it.get("supports_chat"):
                raise ValueError("MODEL_NOT_AVAILABLE_FOR_CHAT")
            om = it.get("openrouter_model")
            if isinstance(om, str) and om.strip():
                return om.strip()
            return resolve_openrouter_model_name_for_chat()
    raise ValueError("UNKNOWN_MODEL_ID")


@router.get("/models")
async def get_models_catalog() -> dict[str, Any]:
    """Composer catalog: OpenRouter chat-capable rows + Cursor slugs (chat disabled)."""
    return build_catalog_payload()
