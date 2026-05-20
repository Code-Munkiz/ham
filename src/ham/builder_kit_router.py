"""Prompt → Builder Kit router.

Maps a free-form user prompt to the most appropriate kit id. Returns
"generic" when no archetype matches. Pure function, no I/O, no live
runtime imports — safe to call from chat-stream hot path.
"""
from __future__ import annotations

import re
from typing import Final

from src.ham.builder_kits import get_kit

_LANDING_PAGE: Final = (
    r"\b(landing\s*page|home\s*page|hero\s+section|marketing\s+(?:site|page)|product\s+launch|waitlist|coming\s+soon|splash\s+page)\b",
)
_DASHBOARD: Final = (
    r"\b(dashboard|admin\s+panel|analytics\s+(?:page|app)?|kpi(?:\s+dashboard)?|metrics(?:\s+dashboard)?)\b",
)
_TODO: Final = (
    r"\b(todo|to[-\s]?do|task\s+list|task\s+tracker|checklist|crud(?:\s+app)?|create\s+edit\s+delete)\b",
)
_CALCULATOR: Final = (
    r"\b(calculator|calc\s+app|four[-\s]function|math\s+app|utility\s+calculator)\b",
)
_TETRIS: Final = (
    r"\b(tetris|tetromino|falling[-\s]blocks?|arcade\s+(?:clone|game)|block\s+game)\b",
)

_PROMPT_KIT_RULES: Final = (
    ("landing-page", _LANDING_PAGE),
    ("dashboard", _DASHBOARD),
    ("todo", _TODO),
    ("calculator", _CALCULATOR),
    ("tetris", _TETRIS),
)


def select_kit_for_prompt(text: str) -> str:
    """Return the kit id that best matches the prompt, or 'generic'.

    Always returns a kit id that exists in the registry. Never raises.
    """
    if not text or not text.strip():
        return "generic"
    low = text.lower()
    for kit_id, patterns in _PROMPT_KIT_RULES:
        for pat in patterns:
            if re.search(pat, low):
                return kit_id if get_kit(kit_id) is not None else "generic"
    return "generic"


__all__ = ["select_kit_for_prompt"]
