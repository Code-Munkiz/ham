"""
Rule-based harness advisory for operator preview flows (droid / Cursor Cloud Agent).

Advisory only — never control-plane fact, never launch policy. See docs in mission spec.
An optional LLM-backed strategy can be added later behind the same public interface.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.persistence.cursor_credentials import get_effective_cursor_api_key

# --- Caps (v1) -----------------------------------------------------------------

MAX_RATIONALE_CHARS = 800
MAX_LIST_ITEMS = 5
MAX_LIST_ITEM_CHARS = 200

_Suggested = Literal["cursor_cloud_agent", "factory_droid", "unclear"]
_Confidence = Literal["high", "limited"]


def harness_advisory_enabled() -> bool:
    """Off unless explicitly enabled (safe default for deployments)."""
    raw = (os.environ.get("HAM_HARNESS_ADVISORY") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _clip(s: str, n: int) -> str:
    t = s.strip()
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


def _clip_list(items: list[str], *, max_items: int, max_item: int) -> list[str]:
    out: list[str] = []
    for x in items[:max_items]:
        t = str(x).strip()
        if not t:
            continue
        out.append(_clip(t, max_item))
    return out


class HarnessAdvisory(BaseModel):
    """Structured preview-only hint; not launch authorization."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    advisory_version: Literal["1"] = "1"
    advice_kind: Literal["preview_harness_hint"] = "preview_harness_hint"
    suggested_harness: _Suggested
    confidence: _Confidence
    rationale: str = Field(max_length=MAX_RATIONALE_CHARS)
    risks: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    missing_prerequisites: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    inputs_hash: str | None = Field(default=None, max_length=32)

    @field_validator("rationale", mode="after")
    @classmethod
    def _v_rationale(cls, v: str) -> str:
        return _clip(v, MAX_RATIONALE_CHARS)

    @field_validator("risks", "missing_prerequisites", mode="after")
    @classmethod
    def _v_str_lists(cls, v: list[str]) -> list[str]:
        if not v:
            return []
        return _clip_list([str(x) for x in v], max_items=MAX_LIST_ITEMS, max_item=MAX_LIST_ITEM_CHARS)


PR_LIKE = re.compile(
    r"\b(pull request|open\s+a?\s*pr|merge request|cursor cloud agent|remote agent)\b",
    re.IGNORECASE,
)
GITHUB_HINT = re.compile(r"github\.com/", re.IGNORECASE)


def _inputs_hash_blob(blob: dict[str, Any]) -> str:
    raw = json.dumps(blob, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# --- Rule-based v1 (default) -------------------------------------------------


def build_harness_advisory_for_droid_preview(
    *,
    workflow_id: str,
    mutates: bool | None,
    tier: str | None,
    requires_launch_token: bool,
    droid_exec_token_configured: bool,
    user_prompt: str,
) -> HarnessAdvisory:
    """Heuristic advisory for a successful Factory Droid preview."""
    pr_signal = bool(PR_LIKE.search(user_prompt) or GITHUB_HINT.search(user_prompt))
    risks: list[str] = []
    missing: list[str] = []
    suggested: _Suggested = "factory_droid"
    conf: _Confidence = "high"
    rationale = (
        f"Preview targets allowlisted Droid workflow `{workflow_id}` "
        f"({'mutating' if mutates else 'read-only'}). "
        "Use the Droid launch path when you want local `droid exec` under this digest."
    )

    if requires_launch_token and not droid_exec_token_configured:
        conf = "limited"
        missing.append(
            "Mutating Droid launch requires HAM_DROID_EXEC_TOKEN (or operator bearer) on the API host."
        )

    if pr_signal and not mutates:
        suggested = "unclear"
        conf = "limited"
        risks.append(
            "Task text suggests a PR or remote/GitHub-style workflow; "
            "Droid is local exec — a Cursor Cloud Agent may fit better if you need a hosted agent with a repo PR."
        )
        rationale = (
            f"Droid read-only workflow `{workflow_id}` fits repo audit, but the prompt also hints at PR/remote work. "
            "Confirm which execution model you need before launching."
        )

    if pr_signal and mutates and droid_exec_token_configured:
        risks.append("PR/remote language in prompt: verify local Droid edit scope matches intent.")

    blob = {
        "kind": "droid",
        "workflow_id": workflow_id,
        "mutates": mutates,
        "tier": tier,
        "requires_launch_token": requires_launch_token,
        "droid_exec_token_configured": droid_exec_token_configured,
        "pr_signal": pr_signal,
    }
    return HarnessAdvisory(
        suggested_harness=suggested,
        confidence=conf,
        rationale=_clip(rationale, MAX_RATIONALE_CHARS),
        risks=_clip_list(risks, max_items=MAX_LIST_ITEMS, max_item=MAX_LIST_ITEM_CHARS),
        missing_prerequisites=_clip_list(missing, max_items=MAX_LIST_ITEMS, max_item=MAX_LIST_ITEM_CHARS),
        inputs_hash=_inputs_hash_blob(blob),
    )


def build_harness_advisory_for_cursor_preview(
    *,
    repository_resolved: bool,
    mutates: bool | None,
    auto_create_pr: bool,
    cursor_launch_token_configured: bool,
    task_prompt: str,
) -> HarnessAdvisory:
    """Heuristic advisory for a successful Cursor Cloud Agent preview."""
    cursor_key = bool(get_effective_cursor_api_key())
    pr_signal = bool(PR_LIKE.search(task_prompt))
    risks: list[str] = []
    missing: list[str] = []
    suggested: _Suggested = "cursor_cloud_agent"
    conf: _Confidence = "high"

    if not repository_resolved:
        suggested = "unclear"
        conf = "limited"
        missing.append("Resolve a GitHub repository (project metadata `cursor_cloud_repository` or `cursor_repository` in launch).")
        rationale = "Cursor Cloud Agent requires a target repository; none is resolved in this preview."
    else:
        rationale = (
            "This preview is for a Cursor Cloud Agent against the resolved repository. "
            "Use Cursor launch when you want a hosted agent (optional PR branch intent)."
        )
        if auto_create_pr:
            risks.append("auto_create_pr is enabled: confirm branch/PR intent matches your policy.")

    if not cursor_key:
        missing.append("CURSOR_API_KEY (or HAM-saved cursor key) on the API host is required to launch, not for digest preview.")
        conf = "limited"

    if not cursor_launch_token_configured:
        missing.append("HAM_CURSOR_AGENT_LAUNCH_TOKEN (operator bearer) is required to commit a launch on this host.")

    if pr_signal and repository_resolved:
        risks.append("Prompt mentions PR/MR-style work; confirm repository/ref and review policy before launch.")

    blob = {
        "kind": "cursor",
        "repository_resolved": repository_resolved,
        "mutates": mutates,
        "auto_create_pr": auto_create_pr,
        "cursor_key_configured": cursor_key,
        "cursor_launch_token_configured": cursor_launch_token_configured,
        "pr_signal": pr_signal,
    }
    return HarnessAdvisory(
        suggested_harness=suggested,
        confidence=conf,
        rationale=_clip(rationale, MAX_RATIONALE_CHARS),
        risks=_clip_list(risks, max_items=MAX_LIST_ITEMS, max_item=MAX_LIST_ITEM_CHARS),
        missing_prerequisites=_clip_list(missing, max_items=MAX_LIST_ITEMS, max_item=MAX_LIST_ITEM_CHARS),
        inputs_hash=_inputs_hash_blob(blob),
    )


def build_harness_advisory_for_preview(
    *,
    preview_kind: Literal["droid_preview", "cursor_agent_preview"],
    **kwargs: Any,
) -> HarnessAdvisory:
    """
    Public entry: dispatches to rule-based builders. ``kwargs`` must match the chosen kind.

    For a future LLM strategy, this function could branch on ``HAM_HARNESS_ADVISORY_STRATEGY=rules|llm`` (not implemented in v1).
    """
    if preview_kind == "droid_preview":
        return build_harness_advisory_for_droid_preview(**kwargs)
    return build_harness_advisory_for_cursor_preview(**kwargs)


def format_harness_advisory_for_operator_message(adv: HarnessAdvisory) -> str:
    """Compact markdown block appended to `format_operator_assistant_message` preview paths."""
    lines: list[str] = [
        "\n\n---\n**Advisory (Hermes) — not a launch decision**",
        "_Suggestion only. HAM still requires a matching digest and your confirm; this does not authorize execution._\n",
        f"- **Suggested harness:** `{adv.suggested_harness}`",
        f"- **Confidence:** {adv.confidence}",
        f"- **Rationale:** {adv.rationale}",
    ]
    if adv.risks:
        lines.append(f"- **Risks:** " + " ".join(f"— {r}" for r in adv.risks))
    if adv.missing_prerequisites:
        lines.append(
            f"- **Missing prerequisites:** " + " ".join(f"— {m}" for m in adv.missing_prerequisites)
        )
    if adv.inputs_hash:
        lines.append(f"- _Inputs ref:_ `{adv.inputs_hash}`")
    return "\n".join(lines)
