"""Render a compact, safe text block of HAMgomoon learning hints."""
from __future__ import annotations

from pathlib import Path

from src.ham.hamgomoon_learning.store import summarize_learning_hints

_HEADER = "# HAMgomoon learning hints\n"
_EMPTY = _HEADER + "(no learning hints yet)\n"


def _bounded(items: list[str], cap: int) -> list[str]:
    return list(items[:cap]) if items else []


def render_hamgomoon_learning_hints(
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
    channel: str | None = None,
    limit: int = 20,
    path: Path | None = None,
) -> str:
    """Compact hint block. Never includes external IDs, secrets, or raw review logs."""
    hints = summarize_learning_hints(
        workspace_id=workspace_id,
        project_id=project_id,
        channel=channel,
        limit=limit,
        path=path,
    )
    lessons = _bounded(hints.get("recent_lessons", []), 3)
    avoid = _bounded(hints.get("avoid_list", []), 3)
    prefs = _bounded(hints.get("recurring_preferences", []), 3)

    if not lessons and not avoid and not prefs:
        return _EMPTY

    lines = [_HEADER.rstrip("\n")]
    if lessons:
        lines.append("Recent lessons:")
        for item in lessons:
            lines.append(f"- {item}")
    if avoid:
        lines.append("Avoid:")
        for item in avoid:
            lines.append(f"- {item}")
    if prefs:
        lines.append("Recurring preferences:")
        for item in prefs:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


__all__ = ["render_hamgomoon_learning_hints"]
