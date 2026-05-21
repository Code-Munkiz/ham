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

_NO_BUILD_PATTERNS = (
    r"\b(?:don'?t|do\s+not)\s+(?:actually\s+)?(?:build|create|make|generate|scaffold|spin\s+up|start)\b",
    r"\bwithout\s+(?:building|creating|scaffolding|coding)\b",
    r"\bbefore\s+(?:building|coding|implement(?:ing)?|scaffolding)\b",
    r"\bplan\s+only\b",
    r"\bjust\s+plan\b",
    r"\btalk\s+(?:it\s+)?through\b",
    r"\bshow me the plan\b",
)

# Leading plan phrasing without an explicit build verb (plan-only conversation).
_LEADING_PLAN_ONLY = (
    r"^\s*plan\b",
    r"\bhelp me plan\b",
    r"\btalk (?:me )?through\b",
)

_BUILD_PATTERNS = (
    r"\bbuild\b",
    r"\bcreate\b",
    r"\bscaffold\b",
    r"\bgenerate\b",
    r"\bdesign\b.{0,48}\b(landing|website|site|app|dashboard|tool|tracker|saas|portal|crm|game|clone|mvp|prototype)\b",
    r"\bupdate\b.{0,48}\b(landing|website|site|app|dashboard|tool|tracker|game|clone|preview|ui|screen|layout)\b",
    r"\bchange\b.{0,48}\b(landing|website|site|app|dashboard|tool|tracker|game|clone|preview|ui|screen|layout|theme|design)\b",
    r"\bfix\b.{0,48}\b(landing|website|site|app|dashboard|tool|tracker|game|clone|preview|ui|screen|build|bug|error)\b",
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
    r"\btry\s+building\b",
    r"\bbuilding\b\s+\w*\s*(game|app|clone|website|tool|site|page|component|prototype|mvp)\b",
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


_CRUD_FEATURE_BUILD = re.compile(
    r"(?i)"
    r"\b(crud|c\.r\.u\.d\.)\b"
    r"|\bcreate\b.{0,56}\bedit\b.{0,56}\bdelete\b"
    r"|\bcreate\b.{0,56}\bdelete\b.{0,56}\bedit\b"
    r"|\bedit\b.{0,56}\bdelete\b.{0,56}\bcreate\b"
    r"|\bbuild\b.{0,160}\b(task\s+tracker|todo\s+app|todo\b|crud)\b"
    r"|\b(task\s+tracker|todo\s+app)\b.{0,120}\b(create|edit|delete)\b"
    r"|\b(delete|remove)\s+(an?\s+)?(item|items|entry|entries|task|tasks|record|records)\b"
    r"|\b(empty\s+state|form\s+validation).{0,96}\b(create|edit|delete|remove)\b"
)


def is_crud_feature_build_request(user_plain: str) -> bool:
    """True when delete/remove names a product feature (CRUD), not a destructive command."""
    low = _norm_chat_1l(user_plain)
    if not low:
        return False
    if not any(re.search(p, low) for p in _BUILD_PATTERNS):
        if not re.search(
            r"\b(make|build|create)\b.{0,48}\b(task\s+tracker|todo|tracker|crud)\b",
            low,
        ):
            return False
    return bool(_CRUD_FEATURE_BUILD.search(low))


def looks_like_explicit_no_build(text: str) -> bool:
    """Return True when the prompt explicitly defers or refuses to build.

    Pattern set is intentionally narrow — only phrases that unambiguously
    signal 'don't scaffold right now'. Idioms like 'build character' are
    not matched. Used as a defense-in-depth guard in the chat hook and
    scaffold entry, independent of intent classification.
    """
    if not text:
        return False
    low = text.lower()
    return any(re.search(pat, low) for pat in _NO_BUILD_PATTERNS)


def classify_builder_chat_intent(user_plain: str) -> BuilderChatIntent:
    """Return MVP intent bucket; never raises."""
    text = " ".join(str(user_plain or "").replace("\r", " ").replace("\n", " ").split()).strip()
    low = text.lower()
    if not low:
        return "answer_question"
    if looks_like_explicit_no_build(low):
        return "plan_only"
    if any(re.search(p, low) for p in _LEADING_PLAN_ONLY) and not any(
        re.search(p, low) for p in _BUILD_PATTERNS
    ):
        return "plan_only"
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


_STATUS_DIAGNOSTIC_PATTERNS = (
    r"\bpreview\b.{0,48}\b(blank|empty|broken|not working|doesn't work|doesnt work|missing|nothing|white|black)\b",
    r"\b(blank|empty|broken)\b.{0,48}\bpreview\b",
    r"\bi (?:do not|don't|dont) see\b",
    r"\bnothing shows\b",
    r"\bnothing (?:in|on|in the|shows in)\b.{0,32}\bpreview\b",
    r"\bit didn't build\b",
    r"\bit did not build\b",
    r"\bwhere is it\b",
    r"\bpreview (?:is )?(?:blank|empty|broken|not working)\b",
    r"\bdidn't (?:build|generate|show)\b",
    r"\bdid not (?:build|generate|show)\b",
)


def is_builder_status_diagnostic_turn(user_plain: str) -> bool:
    """True when the user is complaining about preview/build visibility (not pure Q&A)."""
    low = _norm_chat_1l(user_plain)
    if not low:
        return False
    if any(re.search(p, low) for p in _ANSWER_PATTERNS) and not any(
        re.search(p, low) for p in _STATUS_DIAGNOSTIC_PATTERNS
    ):
        return False
    return any(re.search(p, low) for p in _STATUS_DIAGNOSTIC_PATTERNS)
