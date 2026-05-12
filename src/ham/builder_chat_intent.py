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
