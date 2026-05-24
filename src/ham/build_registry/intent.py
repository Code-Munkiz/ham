"""Conservative prompt → Build Registry v2 app type routing (ADR-0017 Phase 2E).

Pure string matching only. No I/O, no LLM calls, no registry file loads.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

IDLE_INCREMENTAL_APP_TYPE = "game.idle-incremental"

_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(tetris|tetromino|platformer|trivia|quiz)\b",
    r"\b(dashboard|landing\s*page|saas|calculator|todo|to[-\s]?do|crm)\b",
    r"\b(crypto|trading)\s+(dashboard|app|platform)\b",
    r"\b(wordle|snake|pong|asteroids|flappy)\b",
)

_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\b(idle|incremental|clicker|tycoon)\b",
    r"\bcookie\s+clicker\b",
    r"\bpassive\s+income\b",
    r"\b(idle|incremental|clicker|tycoon)\s+(game|app)\b",
    r"\b(mining|factory|business)\s+(clicker|idle|tycoon)\b",
    r"\b(clicker|idle|tycoon)\s+(game|style)\b",
    r"\b(game|app)\b.{0,100}\b(earn|collect)\b.{0,60}\b(coins?|currency|gold|resources?)\b.{0,80}\b(upgrades?|buy|purchase)\b",
    r"\b(earn|collect|mine)\b.{0,60}\b(coins?|currency|gold|resources?)\b.{0,80}\b(upgrades?|buy|purchase)\b",
)


def _normalized_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", str(prompt or "").strip().lower())


def select_registry_v2_app_type_for_prompt(prompt: str) -> str | None:
    """Return ``game.idle-incremental`` for clear idle/clicker prompts, else ``None``."""
    text = _normalized_prompt(prompt)
    if not text:
        return None
    for pattern in _NEGATIVE_PATTERNS:
        if re.search(pattern, text):
            return None
    for pattern in _POSITIVE_PATTERNS:
        if re.search(pattern, text):
            return IDLE_INCREMENTAL_APP_TYPE
    return None


def enrich_plan_metadata_with_registry_v2(
    metadata: Mapping[str, Any],
    prompt: str,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Copy metadata and add ``registry_v2_app_type`` when flag + intent match."""
    from src.ham.build_registry.scaffold_context import build_registry_v2_enabled

    merged = dict(metadata)
    if not build_registry_v2_enabled(env):
        return merged
    app_type = select_registry_v2_app_type_for_prompt(prompt)
    if app_type:
        merged["registry_v2_app_type"] = app_type
    return merged
