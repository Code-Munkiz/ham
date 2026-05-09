"""Unified model catalog for Ham composer: Cursor API slugs (display-only for chat) + OpenRouter chat rows."""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor
from src.persistence.connected_tool_credentials import (
    has_connected_tool_credential_record,
    resolve_connected_tool_secret_plaintext,
)

from src.llm_client import (
    get_default_model,
    openrouter_api_key_is_plausible,
    resolve_openrouter_model_name_for_chat,
)
from src.persistence.cursor_credentials import get_effective_cursor_api_key

router = APIRouter(prefix="/api", tags=["models"], dependencies=[Depends(get_ham_clerk_actor)])

_OPENROUTER_MODELS_TTL_SEC = 120.0
_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
# Internal row ids that must never collide with remote OpenRouter model ids.
_RESERVED_OPENROUTER_CATALOG_IDS: frozenset[str] = frozenset(
    {"openrouter:default", "tier:auto", "tier:premium"},
)

_OPENROUTER_MODELS_LOCK = threading.Lock()
_OPENROUTER_MODELS_CACHE: dict[str, Any] = {
    "monotonic_at": 0.0,
    "items": None,  # None before first fetch in eligible mode; list afterward
    "fetch_failed": False,
}

_BYOK_MODEL_LOCK = threading.Lock()
_BYOK_MODEL_CACHE: dict[str, dict[str, Any]] = {}

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


# OpenRouter-labeled composer rows are inactive in non-openrouter modes (precise copy per mode).
_HTTP_MODE_OPENROUTER_TIERS_DISABLED = (
    "Inactive while HERMES_GATEWAY_MODE=http: dashboard chat uses the HTTP/SSE gateway "
    "(HERMES_GATEWAY_BASE_URL; typically Hermes Agent API). The upstream model is configured "
    "on the API host (e.g. HERMES_GATEWAY_MODEL), not these OpenRouter composer tiers."
)
_MOCK_MODE_OPENROUTER_TIERS_DISABLED = (
    "Inactive while the gateway is mock: chat uses the built-in mock assistant. "
    "These OpenRouter tiers apply when HERMES_GATEWAY_MODE=openrouter with a valid OPENROUTER_API_KEY."
)
_FALLBACK_OPENROUTER_TIERS_DISABLED = (
    "These OpenRouter composer tiers are active only when HERMES_GATEWAY_MODE=openrouter."
)


def _openrouter_path_disabled_reason() -> str | None:
    """When ``HERMES_GATEWAY_MODE=openrouter``: None if key is usable; else a short reason."""
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        return "OPENROUTER_API_KEY is not set."
    if not openrouter_api_key_is_plausible(key):
        return (
            "OPENROUTER_API_KEY is not a single raw token (often pasted shell text in Secret Manager). "
            "Store only the key, one line, redeploy; see docs/DEPLOY_CLOUD_RUN.md § OpenRouter key."
        )
    return None


def _openrouter_composer_row_chat() -> tuple[bool, str | None]:
    """``(supports_chat, disabled_reason)`` for OpenRouter-tier catalog rows (honest per gateway mode)."""
    gw = _gateway_mode()
    if gw == "openrouter":
        reason = _openrouter_path_disabled_reason()
        return (reason is None, reason)
    if gw == "http":
        return (False, _HTTP_MODE_OPENROUTER_TIERS_DISABLED)
    if gw == "mock":
        return (False, _MOCK_MODE_OPENROUTER_TIERS_DISABLED)
    return (False, _FALLBACK_OPENROUTER_TIERS_DISABLED)


def _composer_openrouter_tier_visibility(actor: HamActor | None) -> tuple[bool, str | None]:
    """Composer tier rows Chat-enabled when gateway openrouter, or Clerk BYOK exists in http gateway."""
    plat_chat, plat_reason = _openrouter_composer_row_chat()
    if plat_chat:
        return True, None
    gw = _gateway_mode()
    if gw == "http" and actor and has_connected_tool_credential_record(actor, "openrouter"):
        return True, None
    return plat_chat, plat_reason


def _http_chat_ready() -> bool:
    return _gateway_mode() == "http" and bool(
        (os.environ.get("HERMES_GATEWAY_BASE_URL") or "").strip(),
    )


def _looks_like_openrouter_provider_model(raw: str) -> bool:
    v = raw.strip()
    if not v:
        return False
    if v.startswith("openrouter/"):
        return True
    return "/" in v


def _catalog_openrouter_default_model(gateway_mode: str) -> str:
    """
    Model backing ``openrouter:default`` in the picker.

    In ``http`` gateway mode this must stay OpenRouter-native and must not inherit
    Hermes HTTP upstream aliases like ``hermes-agent``.
    """
    if gateway_mode == "openrouter":
        return resolve_openrouter_model_name_for_chat()
    return _normalize_openrouter_litellm_model(get_default_model().strip())


def _catalog_openrouter_premium_model(gateway_mode: str) -> str:
    """Model backing ``tier:premium`` with safe fallback in HTTP gateway mode."""
    explicit = (os.environ.get("HAM_CHAT_PREMIUM_MODEL") or "").strip()
    if explicit:
        return _normalize_openrouter_litellm_model(explicit)
    gw_model = (os.environ.get("HERMES_GATEWAY_MODEL") or "").strip()
    if gateway_mode == "openrouter" and _looks_like_openrouter_provider_model(gw_model):
        return _normalize_openrouter_litellm_model(gw_model)
    return _normalize_openrouter_litellm_model("anthropic/claude-3.5-sonnet")


def _normalize_openrouter_litellm_model(raw: str) -> str:
    r = raw.strip()
    if not r:
        return resolve_openrouter_model_name_for_chat()
    if r.startswith("openrouter/"):
        return r
    return f"openrouter/{r}"


def reset_openrouter_catalog_cache_for_tests() -> None:
    """Test-only: clear in-process OpenRouter list cache."""
    with _OPENROUTER_MODELS_LOCK:
        _OPENROUTER_MODELS_CACHE["monotonic_at"] = 0.0
        _OPENROUTER_MODELS_CACHE["items"] = None
        _OPENROUTER_MODELS_CACHE["fetch_failed"] = False
    with _BYOK_MODEL_LOCK:
        _BYOK_MODEL_CACHE.clear()


def _pricing_hint(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    p = raw.get("prompt")
    c = raw.get("completion")
    if p is None and c is None:
        return None

    def fmt_one(v: Any) -> str | None:
        if v is None:
            return None
        try:
            f = float(v)
            if f == 0.0:
                return "free"
            s = f"{f:.6g}".rstrip("0").rstrip(".")
            return f"${s}/1M"
        except (TypeError, ValueError):
            text = str(v).strip()
            return text[:48] if text else None

    pp = fmt_one(p)
    cc = fmt_one(c)
    if pp and cc:
        return f"in {pp} · out {cc}"
    return pp or cc


def _model_row_likely_chat_capable(row: dict[str, Any]) -> bool:
    mid = str(row.get("id") or "").lower()
    if "text-embedding" in mid or mid.endswith("embedding"):
        return False
    arch = row.get("architecture")
    if not isinstance(arch, dict):
        return True
    outs = arch.get("output_modalities")
    if isinstance(outs, list) and outs:
        lowered = {str(x).lower() for x in outs}
        if lowered and lowered <= {"embedding", "embeddings"}:
            return False
    return True


def _sanitize_openrouter_models_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_list = data.get("data")
    if not isinstance(raw_list, list):
        return []
    out: list[dict[str, Any]] = []
    for m in raw_list:
        if not isinstance(m, dict):
            continue
        if not _model_row_likely_chat_capable(m):
            continue
        mid = m.get("id")
        if not isinstance(mid, str) or not mid.strip():
            continue
        mid = mid.strip()
        if mid in _RESERVED_OPENROUTER_CATALOG_IDS:
            continue
        name = m.get("name")
        label = name.strip() if isinstance(name, str) and name.strip() else mid
        desc = m.get("description")
        description = desc.strip() if isinstance(desc, str) else ""
        if len(description) > 600:
            description = description[:597] + "..."
        ctx = m.get("context_length")
        context_length: int | None
        try:
            context_length = int(ctx) if ctx is not None else None
        except (TypeError, ValueError):
            context_length = None
        family = mid.split("/", 1)[0] if "/" in mid else "openrouter"
        pricing = _pricing_hint(m.get("pricing"))
        out.append(
            {
                "id": mid,
                "label": label,
                "tag": "API",
                "tier": None,
                "provider": family,
                "description": description or f"OpenRouter model `{mid}`.",
                "supports_chat": True,
                "disabled_reason": None,
                "openrouter_model": _normalize_openrouter_litellm_model(mid),
                "context_length": context_length,
                "pricing_display": pricing,
            },
        )
    out.sort(key=lambda r: (str(r.get("label") or "").lower(), r.get("id") or ""))
    return out


def _fetch_openrouter_models_with_api_key(api_key: str) -> tuple[list[dict[str, Any]], bool]:
    ak = api_key.strip()
    if not ak or not openrouter_api_key_is_plausible(ak):
        return [], False
    try:
        with httpx.Client(timeout=25.0) as client:
            resp = client.get(
                _OPENROUTER_MODELS_URL,
                headers={"Authorization": f"Bearer {ak}"},
            )
    except httpx.RequestError:
        return [], True
    if resp.status_code != 200:
        return [], True
    try:
        data = resp.json()
    except (ValueError, TypeError):
        return [], True
    if not isinstance(data, dict):
        return [], True
    rows = _sanitize_openrouter_models_payload(data)
    return rows, False


def _fetch_openrouter_public_models_from_network() -> tuple[list[dict[str, Any]], bool]:
    """Pull OpenRouter /api/v1/models using platform ``OPENROUTER_API_KEY``."""
    platform_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    return _fetch_openrouter_models_with_api_key(platform_key)


def _cached_byok_openrouter_dynamic_rows(actor: HamActor | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {
        "remote_models_fetched": False,
        "remote_model_count": 0,
        "remote_fetch_failed": False,
        "cache_ttl_sec": int(_OPENROUTER_MODELS_TTL_SEC),
        "byok_namespace": True,
    }
    if actor is None or not has_connected_tool_credential_record(actor, "openrouter"):
        return [], meta

    key = resolve_connected_tool_secret_plaintext(actor, "openrouter") or ""
    if not key or not openrouter_api_key_is_plausible(key):
        return [], meta

    uid = str(actor.user_id).strip()
    now = time.monotonic()
    with _BYOK_MODEL_LOCK:
        entry = _BYOK_MODEL_CACHE.get(uid)
        if entry and (now - float(entry["monotonic_at"])) < _OPENROUTER_MODELS_TTL_SEC:
            rows = list(entry["items"])  # type: ignore[list-item]
            meta["remote_models_fetched"] = True
            meta["remote_model_count"] = len(rows)
            meta["remote_fetch_failed"] = bool(entry.get("fetch_failed"))
            return rows, meta

    rows, failed = _fetch_openrouter_models_with_api_key(key)
    with _BYOK_MODEL_LOCK:
        _BYOK_MODEL_CACHE[uid] = {
            "monotonic_at": now,
            "items": list(rows),
            "fetch_failed": failed,
        }
    meta["remote_models_fetched"] = True
    meta["remote_model_count"] = len(rows)
    meta["remote_fetch_failed"] = failed
    return rows, meta


def _merge_dynamic_items(
    *,
    precedence_first: list[dict[str, Any]],
    precedence_second: list[dict[str, Any]],
    composer_chat_enabled: bool,
    gated_reason: str | None,
) -> list[dict[str, Any]]:
    """Merge deduped by catalog ``id``. First wins; gated rows downgrade second copy."""
    if not composer_chat_enabled:
        gated = []
        merged = [*precedence_first, *precedence_second]
        for r in merged:
            gated.append({**r, "supports_chat": False, "disabled_reason": gated_reason})
        seen: dict[str, dict[str, Any]] = {}
        for row in gated:
            rid = str(row.get("id") or "")
            if rid and rid not in seen:
                seen[rid] = row
        return list(seen.values())

    merged_map: dict[str, dict[str, Any]] = {}
    for bundle in (precedence_second, precedence_first):
        for row in bundle:
            rid = str(row.get("id") or "").strip()
            if not rid:
                continue
            merged_map[rid] = dict(row)

    merged_list = list(merged_map.values())
    merged_list.sort(key=lambda r: (str(r.get("label") or "").lower(), str(r.get("id") or "")))
    return merged_list


def _cached_openrouter_dynamic_rows(
    *,
    gateway_mode: str,
    openrouter_chat_ready: bool,
    composer_row_chat: bool,
    composer_disabled_reason: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    TTL-cached OpenRouter model rows merged only when dashboard OpenRouter path is live.
    """
    meta: dict[str, Any] = {
        "remote_models_fetched": False,
        "remote_model_count": 0,
        "remote_fetch_failed": False,
        "cache_ttl_sec": int(_OPENROUTER_MODELS_TTL_SEC),
    }
    if gateway_mode != "openrouter" or not openrouter_chat_ready:
        return [], meta

    now = time.monotonic()
    with _OPENROUTER_MODELS_LOCK:
        cached = _OPENROUTER_MODELS_CACHE["items"]
        at = float(_OPENROUTER_MODELS_CACHE["monotonic_at"])
        if cached is not None and (now - at) < _OPENROUTER_MODELS_TTL_SEC:
            meta["remote_models_fetched"] = True
            meta["remote_model_count"] = len(cached)
            meta["remote_fetch_failed"] = bool(_OPENROUTER_MODELS_CACHE["fetch_failed"])
            rows = list(cached)
        else:
            rows, failed = _fetch_openrouter_public_models_from_network()
            _OPENROUTER_MODELS_CACHE["items"] = list(rows)
            _OPENROUTER_MODELS_CACHE["monotonic_at"] = now
            _OPENROUTER_MODELS_CACHE["fetch_failed"] = failed
            meta["remote_models_fetched"] = True
            meta["remote_model_count"] = len(rows)
            meta["remote_fetch_failed"] = failed

    if not composer_row_chat:
        disabled = composer_disabled_reason or "OpenRouter composer rows inactive for this gateway mode."
        gated = []
        for r in rows:
            gated.append(
                {
                    **r,
                    "supports_chat": False,
                    "disabled_reason": disabled,
                },
            )
        meta["remote_model_count"] = len(gated)
        return gated, meta

    return rows, meta


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


def build_catalog_payload(ham_actor: HamActor | None = None) -> dict[str, Any]:
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

    gw = _gateway_mode()
    or_ready = gw == "openrouter" and _openrouter_path_disabled_reason() is None
    tier_chat, tier_reason = _composer_openrouter_tier_visibility(ham_actor)
    http_ready = _http_chat_ready()
    dashboard_chat_ready = or_ready or http_ready or (gw == "mock")

    connected_or = bool(
        ham_actor and has_connected_tool_credential_record(ham_actor, "openrouter"),
    )

    openrouter_items: list[dict[str, Any]] = [
        {
            "id": "openrouter:default",
            "label": "OpenRouter AI",
            "tag": "EXTERNAL",
            "tier": None,
            "provider": "openrouter",
            "description": "Unified access via Ham chat gateway (OpenRouter).",
            "supports_chat": tier_chat,
            "disabled_reason": tier_reason,
            "openrouter_model": _catalog_openrouter_default_model(gw),
        },
        {
            "id": "tier:auto",
            "label": "Auto",
            "tag": "EFFICIENCY",
            "tier": "auto",
            "provider": "openrouter",
            "description": "Efficiency-oriented default (DEFAULT_MODEL / gateway default).",
            "supports_chat": tier_chat,
            "disabled_reason": tier_reason,
            "openrouter_model": _normalize_openrouter_litellm_model(
                get_default_model().strip(),
            ),
        },
        {
            "id": "tier:premium",
            "label": "Premium",
            "tag": "INTELLIGENCE",
            "tier": "premium",
            "provider": "openrouter",
            "description": "Higher-capability default (HAM_CHAT_PREMIUM_MODEL or HERMES_GATEWAY_MODEL).",
            "supports_chat": tier_chat,
            "disabled_reason": tier_reason,
            "openrouter_model": _catalog_openrouter_premium_model(gw),
        },
    ]

    byok_dyn, byok_meta = _cached_byok_openrouter_dynamic_rows(ham_actor)

    plat_dyn, plat_cat_meta = _cached_openrouter_dynamic_rows(
        gateway_mode=gw,
        openrouter_chat_ready=or_ready,
        composer_row_chat=tier_chat,
        composer_disabled_reason=tier_reason,
    )

    dyn_rows = _merge_dynamic_items(
        precedence_first=byok_dyn,
        precedence_second=plat_dyn,
        composer_chat_enabled=tier_chat,
        gated_reason=tier_reason,
    )
    merged_meta = {
        **plat_cat_meta,
        "byok_openrouter": byok_meta,
    }

    items = openrouter_items + dyn_rows + cursor_items
    http_primary = (os.environ.get("HERMES_GATEWAY_MODEL") or "").strip() or None
    http_fallback = (os.environ.get("HAM_CHAT_FALLBACK_MODEL") or "").strip() or None
    return {
        "items": items,
        "source": source,
        "gateway_mode": gw,
        "openrouter_chat_ready": or_ready,
        "openrouter_user_byok_connected": connected_or,
        "http_chat_ready": http_ready,
        "dashboard_chat_ready": dashboard_chat_ready,
        "http_chat_model_primary": http_primary,
        "http_chat_model_fallback": http_fallback,
        "openrouter_catalog": merged_meta,
    }


def resolve_model_id_for_chat(
    model_id: str | None,
    ham_actor: HamActor | None = None,
) -> str | None:
    """
    Return LiteLLM model string for OpenRouter, or None to use gateway default.
    Raises ValueError if model_id is set but not allowed for chat (e.g. cursor:*).
    """
    if not model_id or not str(model_id).strip():
        return None
    mid = str(model_id).strip()
    if mid.startswith("cursor:"):
        raise ValueError("CURSOR_MODEL_NOT_CHAT_ENABLED")
    payload = build_catalog_payload(ham_actor)
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
async def get_models_catalog(_actor: object = Depends(get_ham_clerk_actor)) -> dict[str, Any]:
    """Composer catalog: OpenRouter chat-capable rows + Cursor slugs (chat disabled)."""
    actor = _actor if isinstance(_actor, HamActor) else None
    return build_catalog_payload(ham_actor=actor)
