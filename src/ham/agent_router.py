"""Provider-agnostic agent intent router for Workspace Chat."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AgentIntent = Literal[
    "normal_chat",
    "agent_preview",
    "agent_launch",
    "agent_status",
    "agent_cancel",
    "agent_continue",
    "agent_choose_provider",
]
AgentMode = Literal["chat", "preview", "launch", "status", "cancel", "continue", "choose_provider"]
AgentProvider = Literal["cursor", "claude", "codex", "factory", "ham_local", "auto"]

_WORK_VERB_RE = re.compile(
    r"\b(launch|start|fire\s+up|run|execute|kick\s*off|send|use|have)\b",
    re.I,
)
_PREVIEW_RE = re.compile(r"\b(preview|plan|propose|what\s+would)\b", re.I)
_STATUS_RE = re.compile(r"\b(status|progress|checkpoint|is\s+it\s+done|show\s+logs)\b", re.I)
_CANCEL_RE = re.compile(r"\b(cancel|stop|abort|kill)\b", re.I)
_CONTINUE_RE = re.compile(r"\b(continue|resume|follow\s*up)\b", re.I)
_QUESTION_RE = re.compile(r"^\s*(what|how|why|when|where)\b|\?$", re.I)
_INFO_ONLY_RE = re.compile(
    r"\b(explain|what\s+is|tell\s+me\s+about|compare|comparison|summarize)\b",
    re.I,
)
_AGENT_HINT_RE = re.compile(
    r"\b(agent|cloud\s+agent|managed\s+mission|best\s+agent|coding\s+agent)\b",
    re.I,
)
_PROVIDER_CURSOR_RE = re.compile(r"\b(cursor|cursor\s+cloud)\b", re.I)
_PROVIDER_CLAUDE_RE = re.compile(r"\bclaude\b", re.I)
_PROVIDER_CODEX_RE = re.compile(r"\bcodex\b", re.I)
_PROVIDER_FACTORY_RE = re.compile(r"\b(factory|factory\s+droid|droid)\b", re.I)
_PROVIDER_LOCAL_RE = re.compile(r"\b(ham\s+local|local\s+worker|desktop\s+executor)\b", re.I)
_PROJECT_HINT_RE = re.compile(r"\bproject\.[a-z0-9._-]+\b", re.I)


class AgentRouteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: AgentIntent
    mode: AgentMode
    provider: AgentProvider
    task: str | None = None
    repo_ref: str | None = None
    branch: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    missing: list[str] = Field(default_factory=list)
    reason_code: str | None = None


def _extract_provider(text: str) -> AgentProvider | None:
    if _PROVIDER_CURSOR_RE.search(text):
        return "cursor"
    if _PROVIDER_CLAUDE_RE.search(text):
        return "claude"
    if _PROVIDER_CODEX_RE.search(text):
        return "codex"
    if _PROVIDER_FACTORY_RE.search(text):
        return "factory"
    if _PROVIDER_LOCAL_RE.search(text):
        return "ham_local"
    return None


def _extract_task(text: str) -> str:
    out = text.strip()
    patterns = (
        r"^\s*(?:please\s+)?(?:create|make)\s+(?:an?\s+)?agent\s+preview(?:\s+to|\s+for)?\s*",
        r"^\s*(?:please\s+)?(?:create|make)\s+(?:an?\s+)?cloud\s+agent\s+preview(?:\s+to|\s+for)?\s*",
        r"^\s*(?:please\s+)?(?:launch|start|fire\s+up|run|execute|kick\s*off)\s+(?:an?\s+)?(?:cloud\s+)?agent(?:\s+to|\s+for)?\s*",
        r"^\s*(?:please\s+)?(?:have|use|send)\s+(?:cursor|claude|codex|factory(?:\s+droid)?|ham\s+local)\s+(?:do|to|for)?\s*",
        r"^\s*(?:please\s+)?spin\s+up\s+(?:the\s+)?best\s+agent(?:\s+for|\s+to)?\s*",
    )
    for pat in patterns:
        out = re.sub(pat, "", out, flags=re.I).strip()
    out = re.sub(r"^\s*(?:to|for|on)\s+", "", out, flags=re.I).strip()
    return out


def route_agent_intent(
    user_text: str,
    *,
    default_provider: AgentProvider = "auto",
    default_project_id: str | None = None,
) -> AgentRouteResult:
    text = user_text.strip()
    low = text.lower()
    if not text:
        return AgentRouteResult(intent="normal_chat", mode="chat", provider="auto", confidence=0.0)

    has_work_verb = bool(_WORK_VERB_RE.search(low))
    has_agent_hint = bool(_AGENT_HINT_RE.search(low))
    provider_explicit = _extract_provider(low)
    has_project_context = bool(default_project_id or _PROJECT_HINT_RE.search(low))

    if _INFO_ONLY_RE.search(low) and not has_work_verb:
        return AgentRouteResult(intent="normal_chat", mode="chat", provider="auto", confidence=0.0)
    if _QUESTION_RE.search(text) and not has_work_verb and not provider_explicit:
        return AgentRouteResult(intent="normal_chat", mode="chat", provider="auto", confidence=0.0)

    if not ((provider_explicit and has_work_verb) or (has_agent_hint and (has_work_verb or _PREVIEW_RE.search(low) or _STATUS_RE.search(low) or _CANCEL_RE.search(low) or _CONTINUE_RE.search(low)))):
        return AgentRouteResult(intent="normal_chat", mode="chat", provider="auto", confidence=0.0)

    provider: AgentProvider = provider_explicit or default_provider
    if provider == "auto":
        provider = "cursor"

    if _CANCEL_RE.search(low):
        missing: list[str] = []
        if not has_project_context:
            missing.append("project")
        return AgentRouteResult(
            intent="agent_cancel",
            mode="cancel",
            provider=provider,
            confidence=0.9,
            missing=missing,
            reason_code="provider_not_implemented" if provider != "cursor" else None,
        )
    if _STATUS_RE.search(low):
        missing = []
        if not has_project_context:
            missing.append("project")
        return AgentRouteResult(
            intent="agent_status",
            mode="status",
            provider=provider,
            confidence=0.9,
            missing=missing,
            reason_code="provider_not_implemented" if provider != "cursor" else None,
        )
    if _CONTINUE_RE.search(low):
        return AgentRouteResult(
            intent="agent_continue",
            mode="continue",
            provider=provider,
            confidence=0.85,
            reason_code="provider_not_implemented" if provider != "cursor" else None,
        )

    mode: AgentMode = "preview" if _PREVIEW_RE.search(low) else "launch"
    intent: AgentIntent = "agent_preview" if mode == "preview" else "agent_launch"
    task = _extract_task(text)
    missing = []
    if not task:
        missing.append("task")
    if not has_project_context:
        missing.append("project")
    reason_code = None
    if provider != "cursor":
        reason_code = "provider_not_implemented"
    elif missing:
        reason_code = "missing_task" if "task" in missing else "missing_project_ref"
    return AgentRouteResult(
        intent=intent,
        mode=mode,
        provider=provider,
        task=task or None,
        confidence=0.94 if provider_explicit else 0.88,
        missing=missing,
        reason_code=reason_code,
    )
