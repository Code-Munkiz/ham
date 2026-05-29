"""Redact Build Registry v2 internals from user-visible provider/mission copy."""

from __future__ import annotations

import re

# Low false-positive literal phrases (internal routing / playbook headers).
_LITERAL_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "registry_v2_app_type",
    "pack.site",
    "pack.game",
    "site.landing-page-core",
    "site.dashboard-ui-core",
    "app.saas-dashboard-core",
    "build registry v2",
    "registry route",
    "route matched",
    "fallback_reason",
    "gate report",
    "gate review",
    "scaffold_quality",
    "recipe id",
    "pack id",
    "render length",
    "render budget",
    "playbook context",
    "build registry v2 playbook context:",
)

# Registry module ids use dotted segments with hyphens (game.idle-incremental), not filenames (game.js).
_REGISTRY_MODULE_ID_RE = re.compile(
    r"\b(?:game|site|app)\.[a-z0-9]+(?:-[a-z0-9-]+)+\b",
    re.IGNORECASE,
)

# Scaffold-quality issue codes use multiple underscore segments (dashboard_missing_*), not dashboard_layout.
_SCAFFOLD_QUALITY_CODE_RE = re.compile(
    r"\b(?:dashboard|city|tactics|landing)_[a-z0-9]+(?:_[a-z0-9]+)+\b",
    re.IGNORECASE,
)


def contains_build_registry_v2_forbidden_token(text: str) -> bool:
    """Return True when *text* looks like leaked build-registry internals."""
    lower = text.lower()
    if any(token in lower for token in _LITERAL_FORBIDDEN_SUBSTRINGS):
        return True
    if _REGISTRY_MODULE_ID_RE.search(text):
        return True
    return bool(_SCAFFOLD_QUALITY_CODE_RE.search(text))


def sanitize_normal_user_copy(text: str | None, *, fallback: str | None) -> str | None:
    if not text:
        return text
    if contains_build_registry_v2_forbidden_token(text):
        return fallback
    return text
