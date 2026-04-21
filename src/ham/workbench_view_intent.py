"""
Infer /chat workbench header mode (CHAT / SPLIT / PREVIEW / WAR ROOM) from user text.

Used to augment HAM_UI_ACTIONS when the model omits set_workbench_view.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from src.ham.ui_actions import _MAX_ACTIONS

WorkbenchViewMode = Literal["chat", "split", "preview", "war_room"]

# Imperative phrasing only — avoid matching UI labels in descriptions ("War Room button").
_SPLIT = re.compile(
    r"\b("
    r"split\s*view|split\s*mode|split\s*screen|side\s*by\s*side|"
    r"show\s+(me\s+)?(?:the\s+)?split\b|open\s+(?:the\s+)?split\b|"
    r"switch\s+to\s+(?:the\s+)?split\b|go\s+to\s+(?:the\s+)?split\b|"
    r"use\s+split\b|in\s+split\b"
    r")\b",
    re.IGNORECASE,
)
_PREVIEW = re.compile(
    r"\b("
    r"preview\s*mode|preview\s*screen|"
    r"show\s+(me\s+)?(?:the\s+)?preview(?:\s+screen|\s+mode|\s+view)?\b|"
    r"open\s+(?:the\s+)?preview\b|switch\s+to\s+(?:the\s+)?preview\b|go\s+to\s+(?:the\s+)?preview\b|"
    r"use\s+preview\b"
    r")\b",
    re.IGNORECASE,
)
_WAR_ROOM = re.compile(
    r"\b("
    r"show\s+(me\s+)?(?:the\s+)?war\s*room\b|open\s+(?:the\s+)?war\s*room\b|"
    r"switch\s+to\s+(?:the\s+)?war\s*room\b|go\s+to\s+(?:the\s+)?war\s*room\b|"
    r"use\s+war\s*room\b|enter\s+(?:the\s+)?war\s*room\b"
    r")\b",
    re.IGNORECASE,
)
_CHAT = re.compile(
    r"\b("
    r"chat\s*only|full[\s-]*width\s+chat|single\s+column|"
    r"back\s+to\s+chat|exit\s+split|leave\s+split|close\s+split|"
    r"switch\s+to\s+chat|go\s+to\s+chat\b"
    r")\b",
    re.IGNORECASE,
)


def infer_workbench_view_mode(user_text: str) -> WorkbenchViewMode | None:
    """Return a workbench header mode if the user clearly asked to switch to it."""
    t = (user_text or "").strip()
    if len(t) > 2_000:
        t = t[:2_000]
    if not t:
        return None
    # Skip likely refusals / meta ("don't switch", "why is there no")
    if re.search(r"\b(don't|do\s*not|dont)\b", t, re.IGNORECASE) and re.search(
        r"\b(split|preview|war\s*room)\b",
        t,
        re.IGNORECASE,
    ):
        return None

    if _WAR_ROOM.search(t):
        return "war_room"
    if _PREVIEW.search(t):
        return "preview"
    if _SPLIT.search(t):
        return "split"
    if _CHAT.search(t):
        return "chat"
    return None


def augment_workbench_view_actions(
    user_text: str,
    actions: list[dict[str, Any]],
    *,
    enable_ui_actions: bool,
) -> list[dict[str, Any]]:
    """
    If UI actions are on and the model did not emit set_workbench_view, append it when
    user text clearly requests a header mode (prepend so it runs within MAX_ACTIONS).
    """
    if not enable_ui_actions:
        return actions
    if any(a.get("type") == "set_workbench_view" for a in actions):
        return actions
    mode = infer_workbench_view_mode(user_text)
    if mode is None:
        return actions
    injected: dict[str, Any] = {"type": "set_workbench_view", "mode": mode}
    merged = [injected, *actions]
    return merged[:_MAX_ACTIONS]
