"""Conservative prompt → Build Registry v2 app type routing (ADR-0017 Phase 2E).

Pure string matching only. No I/O, no LLM calls, no registry file loads.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

IDLE_INCREMENTAL_APP_TYPE = "game.idle-incremental"
TRIVIA_TIMER_APP_TYPE = "game.trivia-timer"

_GLOBAL_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(dashboard|landing\s*page|saas|calculator|todo|to[-\s]?do|crm)\b",
    r"\b(crypto|trading)\s+(dashboard|app|platform)\b",
    r"\b(wordle|snake|pong|asteroids|flappy)\b",
    r"\b(tetris|tetromino|platformer)\b",
)

_IDLE_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(trivia|quiz)\b",
    r"\bmemory\s+(card|match)\b",
    r"\bbranching\s+story\b",
    r"\bchoose\s+your\s+own\s+adventure\b",
)

_TRIVIA_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(idle|incremental|clicker|tycoon)\b",
    r"\bcookie\s+clicker\b",
    r"\bpassive\s+income\b",
    r"\bmemory\s+(card|match)\b",
    r"\bbranching\s+story\b",
    r"\bchoose\s+your\s+own\s+adventure\b",
    r"\binteractive\s+fiction\b",
    r"\bsurvey\b",
    r"\bflashcard\b",
    r"\bform\b.{0,80}\bmultiple\s+choice\b",
    r"\bmultiple\s+choice\b.{0,80}\bform\b",
    r"\beducation\s+website\b",
)

_IDLE_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\b(idle|incremental|clicker|tycoon)\b",
    r"\bcookie\s+clicker\b",
    r"\bpassive\s+income\b",
    r"\b(idle|incremental|clicker|tycoon)\s+(game|app)\b",
    r"\b(mining|factory|business)\s+(clicker|idle|tycoon)\b",
    r"\b(clicker|idle|tycoon)\s+(game|style)\b",
    r"\b(game|app)\b.{0,100}\b(earn|collect)\b.{0,60}\b(coins?|currency|gold|resources?)\b.{0,80}\b(upgrades?|buy|purchase)\b",
    r"\b(earn|collect|mine)\b.{0,60}\b(coins?|currency|gold|resources?)\b.{0,80}\b(upgrades?|buy|purchase)\b",
)

_TRIVIA_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\btrivia\b.{0,100}\b(timer|timed|countdown|seconds|game|quiz|challenge|score|question)\b",
    r"\b(timer|timed|countdown)\b.{0,100}\b(trivia|quiz)\b",
    r"\b(timed|timer|countdown)\b.{0,80}\b(quiz|trivia)\b.{0,80}\bgame\b",
    r"\bquiz\s+game\b",
    r"\btrivia\s+game\b",
    r"\bmultiple\s+choice\b.{0,80}\b(trivia|quiz)\b.{0,80}\bgame\b",
    r"\b(trivia|quiz)\b.{0,80}\bmultiple\s+choice\b",
    r"\b(trivia|quiz)\s+challenge\b",
    r"\b\d+\s+question\b.{0,80}\b(trivia|quiz)\b",
    r"\b(trivia|quiz)\b.{0,80}\b(score|questions?)\b",
    r"\btrivia\s+quiz\b",
    r"\bhistory\s+trivia\b",
)


def _normalized_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", str(prompt or "").strip().lower())


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _matches_recipe(text: str, *, negatives: tuple[str, ...], positives: tuple[str, ...]) -> bool:
    if _matches_any(text, negatives):
        return False
    return _matches_any(text, positives)


def _matches_trivia(text: str) -> bool:
    return _matches_recipe(text, negatives=_TRIVIA_NEGATIVE_PATTERNS, positives=_TRIVIA_POSITIVE_PATTERNS)


def _matches_idle(text: str) -> bool:
    return _matches_recipe(text, negatives=_IDLE_NEGATIVE_PATTERNS, positives=_IDLE_POSITIVE_PATTERNS)


def select_registry_v2_app_type_for_prompt(prompt: str) -> str | None:
    """Return a Game Pack app type id for clear prompt matches, else ``None``."""
    text = _normalized_prompt(prompt)
    if not text:
        return None
    if _matches_any(text, _GLOBAL_NEGATIVE_PATTERNS):
        return None
    # Trivia is checked before idle so quiz/trivia prompts are not blocked by idle negatives.
    if _matches_trivia(text):
        return TRIVIA_TIMER_APP_TYPE
    if _matches_idle(text):
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
