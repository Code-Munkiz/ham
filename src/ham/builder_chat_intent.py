"""Lightweight chat intent hints for the builder happy-path (MVP heuristic)."""

from __future__ import annotations

import re
from typing import Literal

BuilderChatIntent = Literal["answer_question", "plan_only", "build_or_create"]

_ANSWER_PATTERNS = (
    r"^\s*what\b",
    r"^\s*why\b",
    r"^\s*when\b",
    r"^\s*where\b",
    r"^\s*who\b",
    r"\bwhat is\b",
    r"\bwhat are\b",
    r"\bwhat's\b",
    r"\bwhat does\b",
    r"\bwhat do\b",
    r"\bhow does\b",
    r"\bhow do\b",
    r"\bhow is\b",
    r"\bhow are\b",
    r"\bcan you explain\b",
    r"\bexplain\b",
    r"\bdefine\b",
    r"\bmeaning of\b",
    r"\berror mean\b",
    r"\bthis error\b",
)

_PLAN_PATTERNS = (
    r"\bhow should we\b",
    r"\bhow would we\b",
    r"\bhow would you\b",
    r"\bhow could you\b",
    r"\bhow to build\b",
    r"\bhow might we\b",
    r"\bhow could we\b",
    r"\barchitecture\b",
    r"\bstrategy\b",
    r"\bpricing\b",
    r"\breview this plan\b",
    r"\breview my plan\b",
    r"\bbest practice\b",
    r"\trade-?off\b",
)

# Deny build when user is clearly asking comprehension or idioms.
_DENY_BUILD = (
    r"\bmake sense\b",
    r"\bmakes sense\b",
    r"\bmake a (difference|note|wish)\b",
    r"\bmake sure\b",
    r"\bmake it clear\b",
    r"\bmake up\b",
)

_BUILD_PATTERNS = (
    r"\bbuild\b",
    r"\bcreate\b",
    r"\bscaffold\b",
    r"\bgenerate\b",
    r"\bspin up\b",
    r"\bturn .{0,40}\binto an app\b",
    r"\bturn this into\b",
    r"\bmake an app\b",
    r"\bmake a landing\b",
    r"\bmake a dashboard\b",
    r"\bmake a saas\b",
    r"\bmake a .{0,40}\b(game|clone|website|site|dashboard|app|tracker|tool)\b",
    r"\bmake me an?\b",
    r"\bmake me a\b",
    r"\bi need (to build|a build)\b",
    r"\bwe need to build\b",
    r"\bham.{0,12}build\b",
)


def _norm_chat_1l(user_plain: str) -> str:
    return " ".join(str(user_plain or "").replace("\r", " ").replace("\n", " ").split()).strip().lower()


def is_builder_advice_or_question_turn(user_plain: str) -> bool:
    """Phrasing that should not auto-mutate the active Builder project (checked before edit heuristics)."""
    low = _norm_chat_1l(user_plain)
    if not low:
        return False
    advice_patterns = (
        r"^\s*what\s+does\b",
        r"^\s*what\s+would\s+you\s+improve\b",
        r"\bwhat\s+would\s+you\s+improve\b",
        r"^\s*what\s+do\s+you\s+suggest\b",
        r"^\s*what\s+would\s+you\s+suggest\b",
        r"^\s*what\s+are\s+your\s+(thoughts|ideas|suggestions)\b",
        r"\bwhy\s+does\b",
        r"\bwhy\s+is\b",
        r"\bwhy\s+do\b",
        r"\bwhy\s+did\b",
        r"\bexplain\s+the\s+(code|changes|files?)\b",
        r"^\s*explain\s+(how|what|why)\b",
        r"\bexplain\s+how\b",
        r"\bwhat\s+files?\s+(did|have|were)\b",
        r"\bwhich\s+files?\s+did\b",
        r"^\s*how\s+would\s+you\s+improve\b",
        r"^\s*how\s+should\s+we\s+improve\b",
        r"^\s*how\s+could\s+we\s+improve\b",
        r"\bwhat\s+changes?\s+did\s+you\b",
        r"\bshould\s+i\s+use\b",
    )
    return any(re.search(p, low) for p in advice_patterns)


def is_builder_edit_like_followup(user_plain: str) -> bool:
    """True when the user is asking for concrete app/UI/source edits (not Q&A-only), never raises."""
    if is_builder_advice_or_question_turn(user_plain):
        return False
    low = _norm_chat_1l(user_plain)
    if not low:
        return False
    if re.search(r"\benhance\b", low):
        return True
    if re.search(r"\bas i type\b", low) and re.search(
        r"\b(number|digit|equation|formula|calculator|calc|show|display|typing)\b",
        low,
    ):
        return True
    if re.search(r"\bi want\b", low) and re.search(r"\b(calculator|calc)\b", low) and re.search(
        r"\b(show|display|equation|numbers?|typing)\b",
        low,
    ):
        return True
    if re.search(
        r"\b(make|change|update|adjust|set|turn)\b.{0,72}\b(buttons?|digits?|keys?|keypad|numpad|layout|ui|preview|screen)\b",
        low,
    ):
        return True
    if re.search(
        r"\b(buttons?|digits?|keys?)\b.{0,48}\b(purple|violet|lavender|yellow|gold|amber)\b",
        low,
    ):
        return True
    if re.search(
        r"\b(change|turn|make)\b.{0,48}\b(buttons?|digits?|keys?)\b.{0,48}\b(purple|to\s+purple|violet)\b",
        low,
    ):
        return True
    if re.search(r"\b(add|give)\b.{0,64}\b(border|outline|ring)\b", low) and re.search(
        r"\b(yellow|gold|amber|buttons?|digits?|keys?|around)\b",
        low,
    ):
        return True
    if re.search(r"\b(random|different)\s+colors?\b", low) and re.search(
        r"\b(buttons?|keys?|digits?|them|those|these)\b",
        low,
    ):
        return True
    if re.search(r"\b(layout|ui)\b.{0,48}\b(wider|narrower|taller|larger|smaller)\b", low):
        return True
    if re.search(
        r"\b(make|make\s+it)\b.{0,48}\b(look|feel)\b.{0,32}\b(modern|polished|cleaner|sleeker)\b",
        low,
    ):
        return True
    if re.search(r"^\s*nice\b", low) and re.search(r"\b(make|change|update|add|remove)\b", low):
        return True
    return False


def classify_builder_chat_intent(user_plain: str) -> BuilderChatIntent:
    """Return MVP intent bucket; never raises."""
    text = " ".join(str(user_plain or "").replace("\r", " ").replace("\n", " ").split()).strip()
    low = text.lower()
    if not low:
        return "answer_question"
    if re.search(r"^\s*how\s+(would|could|should)\s+(you|we)\s+build\b", low):
        return "plan_only"
    for pat in _DENY_BUILD:
        if re.search(pat, low):
            # Still allow explicit build verbs later in the same message.
            if not any(re.search(p, low) for p in _BUILD_PATTERNS):
                if "make sense" in low:
                    return "answer_question"
                return "answer_question" if any(re.search(p, low) for p in _ANSWER_PATTERNS) else "plan_only"
    if any(re.search(p, low) for p in _ANSWER_PATTERNS) and not any(re.search(p, low) for p in _BUILD_PATTERNS):
        return "answer_question"
    if any(re.search(p, low) for p in _PLAN_PATTERNS) and not any(re.search(p, low) for p in _BUILD_PATTERNS):
        return "plan_only"
    if any(re.search(p, low) for p in _BUILD_PATTERNS):
        return "build_or_create"
    # Plain "make X" without other cues — require noun product-ish words.
    if re.search(
        r"\b(make|design)\b.{0,40}\b(landing|website|site|app|dashboard|tool|tracker|saas|portal|crm)\b",
        low,
    ):
        return "build_or_create"
    if re.search(r"^\s*make\s+", low) and len(low) < 220:
        return "plan_only"
    return "answer_question"
