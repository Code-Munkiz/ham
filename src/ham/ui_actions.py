"""
Structured UI actions for chat → dashboard (navigate, settings tab, toast, control panel).

The model appends a single line after its reply:
  HAM_UI_ACTIONS_JSON: {"actions":[...]}

We strip that line before persisting the assistant message. The client applies actions safely.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

_MARKER = "HAM_UI_ACTIONS_JSON:"
_MAX_ACTIONS = 8

_ALLOWED_NAV_PREFIXES = (
    "/",
    "/chat",
    "/settings",
    "/droids",
    "/runs",
    "/logs",
    "/activity",
    "/analytics",
    "/profiles",
    "/extensions",
    "/storage",
)


class NavigateAction(BaseModel):
    type: Literal["navigate"] = "navigate"
    path: str = Field(max_length=256)


class OpenSettingsAction(BaseModel):
    type: Literal["open_settings"] = "open_settings"
    tab: str | None = Field(default=None, max_length=64)


class ToastAction(BaseModel):
    type: Literal["toast"] = "toast"
    level: Literal["info", "success", "warning", "error"] = "info"
    message: str = Field(max_length=500)


class ToggleControlPanelAction(BaseModel):
    type: Literal["toggle_control_panel"] = "toggle_control_panel"
    open: bool | None = None


WorkbenchViewMode = Literal["chat", "split", "preview", "war_room"]


class SetWorkbenchViewAction(BaseModel):
    type: Literal["set_workbench_view"] = "set_workbench_view"
    mode: WorkbenchViewMode


UiAction = (
    NavigateAction
    | OpenSettingsAction
    | ToastAction
    | ToggleControlPanelAction
    | SetWorkbenchViewAction
)
_action_adapter: TypeAdapter[UiAction] = TypeAdapter(UiAction)


def _safe_nav_path(path: str) -> bool:
    p = path.strip()
    if not p.startswith("/") or p.startswith("//"):
        return False
    if ".." in p or "\n" in p or "\r" in p:
        return False
    base = p.split("?", 1)[0].split("#", 1)[0]
    if base == "/":
        return True
    return any(base == pref or base.startswith(pref + "/") for pref in _ALLOWED_NAV_PREFIXES if pref != "/")


def _validate_action(obj: dict[str, Any]) -> UiAction | None:
    try:
        act = _action_adapter.validate_python(obj)
    except Exception:
        return None
    if isinstance(act, NavigateAction) and not _safe_nav_path(act.path):
        return None
    return act


def split_assistant_ui_actions(assistant_raw: str) -> tuple[str, list[dict[str, Any]]]:
    """
    Remove trailing HAM_UI_ACTIONS_JSON line and return (visible_text, actions_payload).

    Accepts the marker on its own line at end of message (possibly after whitespace).
    """
    text = assistant_raw.rstrip()
    if _MARKER not in text:
        return assistant_raw, []

    idx = text.rfind(_MARKER)
    if idx == -1:
        return assistant_raw, []
    visible = text[:idx].rstrip()
    json_part = text[idx + len(_MARKER) :].strip()
    if not json_part:
        return visible, []

    try:
        payload = json.loads(json_part)
    except json.JSONDecodeError:
        return assistant_raw, []

    raw_actions = payload.get("actions") if isinstance(payload, dict) else None
    if not isinstance(raw_actions, list):
        return visible, []

    out: list[dict[str, Any]] = []
    for item in raw_actions[:_MAX_ACTIONS]:
        if not isinstance(item, dict):
            continue
        validated = _validate_action(item)
        if validated is None:
            continue
        out.append(validated.model_dump())

    return visible, out


def ui_actions_system_instructions() -> str:
    """Appended to chat system prompt when structured UI actions are enabled."""
    tabs = (
        "api-keys, environment, tools-extensions, context-memory, execution-history, "
        "system-logs, diagnostics, kernel-health, context-audit, bridge-dump, "
        "workforce-profiles, resource-storage, jobs"
    )
    paths = ", ".join(sorted(x for x in _ALLOWED_NAV_PREFIXES if x != "/")) + ", / (home)"
    return f"""
**Structured UI actions:** If the user clearly wants navigation, a settings tab, a toast, the **right-side control panel** toggled, or the **`/chat` workbench top bar** (CHAT / SPLIT / PREVIEW / WAR ROOM), add **one final line** after your reply (no code fence):
{_MARKER}{{"actions":[...]}}

**Map common asks (workbench header ≠ control panel):**
- “split view” / “split the workbench” / “side by side” (main workbench) → `set_workbench_view` with `mode: split`
- “preview” / “preview mode” / “preview screen” (workbench) → `mode: preview`
- “war room” → `mode: war_room`
- “chat only” / “full width chat” → `mode: chat`
- “open the control panel” / “workspace panel” / “side panel” → `toggle_control_panel`

Allowed action objects (array may be empty):
- `{{"type":"navigate","path":"<path>"}}` — path must start with one of: {paths}
- `{{"type":"open_settings","tab":"<optional>"}}` — tab one of: {tabs}
- `{{"type":"toast","level":"info|success|warning|error","message":"<short>"}}`
- `{{"type":"toggle_control_panel","open":true|false}}` — omit `open` to toggle (**right rail only**)
- `{{"type":"set_workbench_view","mode":"chat|split|preview|war_room"}}` — **top bar** on `/chat`

If no UI change is needed, omit the line entirely or use {{"actions":[]}}.
Do not repeat the marker elsewhere in your message.
""".strip()
