"""Chat context meter helpers — safe aggregates only (no message bodies in API responses).

Used by ``GET /api/chat/context-meters``. Estimates are labeled; no tokenizer-perfect accounting.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Literal

from src.metadata_stamps import ScanMode
from src.memory_heist import DEFAULT_SESSION_COMPACTION_MAX_TOKENS, context_engine_dashboard_payload

ColorBand = Literal["green", "amber", "red"]

# Feature flag: unset or "1" / "true" / "yes" enables (local-friendly default).
_ENV_FLAG = "HAM_CONTEXT_METERS"

# Conservative token ceiling when catalog metadata is missing (not a universal model constant claim).
_FALLBACK_MODEL_CONTEXT_TOKENS = 32_768

# Rough fixed overhead for system routing / tooling strings not modeled per-turn (estimate only).
_SYSTEM_ROUTING_OVERHEAD_TOKENS_EST = 900

# Named ceiling for thread transcript when session compaction config cannot be merged from repo (chars ≈ tokens×4).
DEFAULT_THREAD_BUDGET_CHARS = DEFAULT_SESSION_COMPACTION_MAX_TOKENS * 4


def context_meters_feature_enabled() -> bool:
    raw = (os.environ.get(_ENV_FLAG) or "").strip().lower()
    if raw in {"", "1", "true", "yes", "on"}:
        return True
    return raw not in {"0", "false", "no", "off"}


def meters_color_for_ratio(fill_ratio: float | None) -> ColorBand | None:
    if fill_ratio is None:
        return None
    try:
        x = float(fill_ratio)
    except (TypeError, ValueError):
        return None
    if x < 0.60:
        return "green"
    if x <= 0.85:
        return "amber"
    return "red"


def clamp_display_ratio(raw: float | None) -> float | None:
    if raw is None:
        return None
    try:
        x = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return max(0.0, min(1.0, x))


def chars_to_tokens_estimate(chars: int) -> int:
    if chars <= 0:
        return 0
    return max(1, int(math.ceil(chars / 4.0)))


def resolve_model_context_tokens(model_id: str | None, catalog_items: list[dict[str, Any]]) -> tuple[int | None, bool]:
    """Return (limit_tokens, from_catalog)."""
    mid = (model_id or "").strip()
    if not mid:
        return None, False
    for it in catalog_items:
        if not isinstance(it, dict):
            continue
        if str(it.get("id") or "").strip() != mid:
            continue
        ctx = it.get("context_length")
        try:
            if ctx is None:
                return _FALLBACK_MODEL_CONTEXT_TOKENS, False
            n = int(ctx)
            return (max(1024, n), True) if n > 0 else (_FALLBACK_MODEL_CONTEXT_TOKENS, False)
        except (TypeError, ValueError):
            return _FALLBACK_MODEL_CONTEXT_TOKENS, False
    return _FALLBACK_MODEL_CONTEXT_TOKENS, False


def approx_transcript_chars_from_turns(turns: list[Any]) -> int:
    total = 0
    for t in turns:
        if hasattr(t, "content"):
            total += len(getattr(t, "content", "") or "")
        elif isinstance(t, dict):
            total += len(str(t.get("content", "") or ""))
    return total


def compute_thread_meter_block(
    *,
    turns: list[Any],
    thread_budget_chars: int,
) -> dict[str, Any] | None:
    approx_chars = approx_transcript_chars_from_turns(turns)
    if thread_budget_chars <= 0:
        return None
    ratio_raw = approx_chars / float(thread_budget_chars)
    ratio = clamp_display_ratio(ratio_raw)
    if ratio is None:
        return None
    col = meters_color_for_ratio(ratio)
    return {
        "fill_ratio": ratio,
        "color": col,
        "approx_transcript_chars": approx_chars,
        "thread_budget_chars": thread_budget_chars,
        "unit": "chars_estimate",
    }


def workspace_snapshot_and_meter(
    *,
    root: Path,
    scan_mode: ScanMode = ScanMode.CACHED,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Single ``context_engine_dashboard_payload`` pass — workspace ring + thread budget from ``session_memory``."""
    try:
        payload = context_engine_dashboard_payload(root, scan_mode=scan_mode)
    except Exception:
        return None, {}
    mem = payload.get("session_memory") if isinstance(payload.get("session_memory"), dict) else {}
    try:
        cmt = int(mem.get("compact_max_tokens") or 0)
    except (TypeError, ValueError):
        cmt = 0
    thread_budget_chars = max(DEFAULT_THREAD_BUDGET_CHARS, cmt * 4) if cmt > 0 else DEFAULT_THREAD_BUDGET_CHARS
    roles = payload.get("roles") if isinstance(payload.get("roles"), dict) else {}
    best_ratio = -1.0
    bottleneck: str | None = None
    used_pick = 0
    limit_pick = 1
    for key in ("architect", "commander", "critic"):
        blk = roles.get(key)
        if not isinstance(blk, dict):
            continue
        try:
            lim = int(blk.get("instruction_budget_chars") or 0)
            used = int(blk.get("rendered_chars") or 0)
        except (TypeError, ValueError):
            continue
        if lim <= 0:
            continue
        r = used / float(lim)
        if r > best_ratio:
            best_ratio = r
            bottleneck = key
            used_pick = used
            limit_pick = lim
    ws_block: dict[str, Any] | None
    if best_ratio < 0:
        ws_block = None
    else:
        ratio = clamp_display_ratio(best_ratio)
        if ratio is None:
            ws_block = None
        else:
            col = meters_color_for_ratio(ratio)
            ws_block = {
                "fill_ratio": ratio,
                "color": col,
                "bottleneck_role": bottleneck,
                "source": "local",
                "used": used_pick,
                "limit": limit_pick,
                "unit": "chars",
            }
    return ws_block, {"thread_budget_chars": thread_budget_chars}


def compute_this_turn_meter_block(
    *,
    turns: list[Any],
    model_limit_tokens: int | None,
    model_id: str | None,
) -> dict[str, Any] | None:
    if not model_limit_tokens or model_limit_tokens <= 0:
        return None
    transcript_chars = approx_transcript_chars_from_turns(turns)
    transcript_tokens = chars_to_tokens_estimate(transcript_chars)
    used_tokens = transcript_tokens + _SYSTEM_ROUTING_OVERHEAD_TOKENS_EST
    used_tokens = min(used_tokens, model_limit_tokens)
    ratio_raw = used_tokens / float(model_limit_tokens)
    ratio = clamp_display_ratio(ratio_raw)
    if ratio is None:
        return None
    col = meters_color_for_ratio(ratio)
    mid = (model_id or "").strip() or None
    return {
        "fill_ratio": ratio,
        "color": col,
        "unit": "estimate_tokens",
        "used": used_tokens,
        "limit": model_limit_tokens,
        "model_id": mid,
    }
