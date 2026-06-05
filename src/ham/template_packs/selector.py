"""Select a backstage template pack from user prompt and app intent (no user-facing picker)."""

from __future__ import annotations

import re

from src.ham.template_packs.registry import load_template_pack_registry
from src.ham.template_packs.schema import TemplatePack

_DEFAULT_LANDING = "landing/agency-modern"
_DEFAULT_DASHBOARD = "dashboard/project-management"
_FALLBACK_LANDING = "landing/saas-clean"
_FALLBACK_ANALYTICS = "dashboard/analytics"


def _normalize_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", (prompt or "").strip().lower())


def _prompt_has_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def select_template_pack(
    user_prompt: str,
    *,
    registry: dict[str, TemplatePack] | None = None,
) -> TemplatePack:
    """Pick the best template pack for a native build prompt (deterministic)."""
    packs = registry if registry is not None else load_template_pack_registry()
    text = _normalize_prompt(user_prompt)

    def _get(pack_id: str, *, fallback: str) -> TemplatePack:
        if pack_id in packs:
            return packs[pack_id]
        if fallback in packs:
            return packs[fallback]
        # Last resort: first pack in registry (tests with single pack).
        return next(iter(packs.values()))

    if _prompt_has_any(
        text,
        (
            "analytics",
            "metrics",
            "kpi",
            "chart",
            "reporting dashboard",
            "data dashboard",
        ),
    ):
        return _get(_FALLBACK_ANALYTICS, fallback=_DEFAULT_DASHBOARD)

    if _prompt_has_any(
        text,
        (
            "dashboard",
            "project management",
            "project-management",
            "team workload",
            "workload",
            "kanban",
            "sprint board",
            "task board",
            "status board",
        ),
    ):
        return _get(_DEFAULT_DASHBOARD, fallback=_DEFAULT_DASHBOARD)

    if _prompt_has_any(
        text,
        (
            "saas",
            "startup landing",
            "startup page",
            "product landing",
            "b2b landing",
        ),
    ):
        return _get(_FALLBACK_LANDING, fallback=_DEFAULT_LANDING)

    if _prompt_has_any(
        text,
        (
            "landing page",
            "landing",
            "agency",
            "consultant",
            "marketing site",
            "marketing website",
            "automation shop",
            "ai automation",
            "website",
            "homepage",
            "hero",
            "pricing section",
        ),
    ):
        return _get(_DEFAULT_LANDING, fallback=_DEFAULT_LANDING)

    # Default: polished agency landing baseline for generic "build app" prompts.
    return _get(_DEFAULT_LANDING, fallback=_DEFAULT_LANDING)


__all__ = ["select_template_pack"]
