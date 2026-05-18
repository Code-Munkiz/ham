"""Confidence-based routing: builder mutate vs clarify vs answer-only (no LLM scaffold/worker)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from src.ham.builder_artifact_verifier import list_calculator_scaffold_verification_checks
from src.ham.builder_chat_intent import (
    classify_builder_chat_intent,
    is_builder_advice_or_question_turn,
    is_builder_edit_like_followup,
)

BuilderActionKind = Literal["mutate", "ask_clarification", "answer_only"]
Confidence = Literal["high", "medium", "low"]

_CLARIFY_ASK = re.compile(
    r"(?i)"
    r"^\s*clean\s+this\s+up\b"
    r"|^\s*make\s+it\s+better\b"
    r"|^\s*fix\s+it\b"
    r"|^\s*fix\s+the\s+project\b"
    r"|^\s*improve\s+this\b"
    r"|^\s*make\s+it\s+more\s+professional\b"
    r"|\bremove\s+the\s+old\s+stuff\b"
    r"|\bdelete\s+(the\s+)?old\s+stuff\b"
    r"|\bclean\s+up\s+the\s+project\b"
    r"|\bremove\s+unused\s+code\b"
)

_AMBIGUOUS_DELETE = re.compile(
    r"(?i)"
    r"\b(delete|remove)\b.{0,40}\b(old\s+stuff|unused\s+code|everything|all\b.{0,12}\blogs?\b)\b"
    r"|\b(delete|remove)\s+old\b"
)

_DELETE_SCOPED = re.compile(
    r"(?i)"
    r"\b(delete|remove)\b.{0,96}\b("
    r"history\s+section|mute\s+button|pause\s+button|ac\s+button|equals?\s+button|clear\s+button|settings\s+panel|"
    r"score\s+panel|title|header|footer|route\b|component\b|section\b"
    r")\b"
)

_MUTATION_CUE = re.compile(
    r"(?i)\b("
    r"add|create|build|edit|change|update|fix|refactor|rename|move|wire|integrate|style|"
    r"set|turn|make|delete|remove"
    r")\b"
)

_APP_SURFACE = re.compile(
    r"(?i)\b("
    r"button|buttons|digit|digits|key|keys|keypad|panel|section|screen|layout|ui|styling|style|css|"
    r"component|components|route|routes|page|pages|responsive|title|header|score|board|game|app|project|"
    r"file|files|code|calculator|dashboard|border|outline|particle|particles|effect|effects|background|"
    r"starfield|line|lines"
    r")\b"
)


def resolve_snapshot_project_template(active_snapshot: Any) -> str | None:
    """
    Snapshot template id (calculator, tetris, ...).

    Inline bundles often omit metadata.template in tests; infer calculator from App.tsx markers.
    """
    meta = getattr(active_snapshot, "metadata", None) or {}
    raw = str(meta.get("template") or "").strip().lower()
    if raw:
        return raw
    manifest = getattr(active_snapshot, "manifest", None) or {}
    if str(manifest.get("kind") or "") != "inline_text_bundle":
        return None
    files = manifest.get("inline_files")
    if not isinstance(files, dict):
        return None
    app = str(files.get("src/App.tsx") or "").lower()
    if "calc-app-root" in app or "ham-key-digit" in app:
        return "calculator"
    return None


def _strip_ham_leader(user_plain: str) -> str:
    t = " ".join(str(user_plain or "").replace("\r", " ").replace("\n", " ").split()).strip()
    return re.sub(r"^ham[,\s]+", "", t, flags=re.IGNORECASE).strip()


@dataclass(frozen=True)
class BuilderActionDecision:
    kind: BuilderActionKind
    confidence: Confidence
    destructive: bool
    reason: str
    target_summary: str | None = None
    clarification_prompt: str | None = None

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "confidence": self.confidence,
            "destructive": self.destructive,
            "reason": self.reason,
            "target_summary": self.target_summary,
        }


def classify_builder_project_action(
    user_plain: str,
    *,
    has_active_snapshot: bool,
    active_template: str | None = None,
) -> BuilderActionDecision:
    """
    Classify how the builder should treat this turn.

    has_active_snapshot: whether the project already has sources with an active snapshot (mutation lane).
    active_template: e.g. calculator — used only for diagnostics in reason strings here; eligibility uses it elsewhere.
    """
    raw = str(user_plain or "").strip()
    text = _strip_ham_leader(raw)
    low = text.lower()
    _ = active_template  # reserved for future template-specific clarify/mutate nuance

    if not low:
        return BuilderActionDecision("answer_only", "low", False, "empty_prompt")

    if is_builder_advice_or_question_turn(text):
        return BuilderActionDecision("answer_only", "high", False, "advice_or_question")

    if _CLARIFY_ASK.search(low):
        return BuilderActionDecision(
            "ask_clarification",
            "medium",
            False,
            "vague_improvement",
            clarification_prompt=(
                "What should I change specifically—layout, styling, a screen/component, or logic?\n\n"
            ),
        )

    if _AMBIGUOUS_DELETE.search(low):
        return BuilderActionDecision(
            "ask_clarification",
            "medium",
            True,
            "ambiguous_delete",
            clarification_prompt=(
                "Which files, sections, or UI should I remove? Name the target so we do not delete the wrong thing.\n\n"
            ),
        )

    destructive = bool(re.search(r"(?i)\b(delete|remove)\b", low))

    if destructive and _DELETE_SCOPED.search(low):
        return BuilderActionDecision(
            "mutate",
            "high",
            True,
            "scoped_delete",
            target_summary="scoped_removal",
        )

    if destructive and not _DELETE_SCOPED.search(low):
        # Residual delete/remove without clear target
        return BuilderActionDecision(
            "ask_clarification",
            "medium",
            True,
            "delete_needs_target",
            clarification_prompt="What exactly should I delete or remove?\n\n",
        )

    wants_surface = bool(
        _APP_SURFACE.search(low)
        or is_builder_edit_like_followup(text)
        or bool(re.search(r"(?i)\b(make|turn)\b.{0,40}\b(responsive|saas)\b", low))
    )
    if wants_surface and (_MUTATION_CUE.search(low) or is_builder_edit_like_followup(text)):
        conf: Confidence = "high" if (len(low) < 280 and _APP_SURFACE.search(low)) else "medium"
        return BuilderActionDecision(
            "mutate",
            conf,
            False,
            "explicit_mutation",
            target_summary=None,
        )

    if is_builder_edit_like_followup(text):
        return BuilderActionDecision("mutate", "high", False, "edit_followup_heuristic")

    bucket = classify_builder_chat_intent(text)
    if bucket == "build_or_create" and has_active_snapshot:
        return BuilderActionDecision("mutate", "medium", False, "intent_build_with_snapshot")

    return BuilderActionDecision("answer_only", "medium", False, "no_mutation_cues")


def builder_edit_worker_eligible(
    user_plain: str,
    *,
    decision: BuilderActionDecision,
    active_template: str | None,
) -> bool:
    """
    True when Hermes gateway edit worker should run before deterministic scaffold.

    Non-calculator Builder projects (Tetris, etc.): high-confidence mutations use the worker.

    Calculator: use worker unless a known verified scaffold shortcut applies
    (``list_calculator_scaffold_verification_checks`` non-empty — deterministic verifier can prove the edit).
    """
    if decision.kind != "mutate":
        return False

    tpl = (active_template or "").strip().lower()
    if tpl == "calculator":
        checks = list_calculator_scaffold_verification_checks(user_plain)
        return len(checks) == 0
    return True
