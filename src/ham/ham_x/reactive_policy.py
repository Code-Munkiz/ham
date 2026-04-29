"""Deterministic classification and safety policy for GoHAM reactive replies."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.inbound_client import ReactiveInboundItem
from src.ham.ham_x.redaction import redact
from src.ham.ham_x.review_queue import _cap
from src.ham.ham_x.safety_policy import SafetyPolicyResult, check_social_action

ReactiveClassification = Literal[
    "genuine_question",
    "support_request",
    "positive_comment",
    "criticism",
    "spam_bot",
    "toxic_harassing",
    "price_token_bait",
    "off_topic",
    "requires_human_operator",
]
ReactiveRoute = Literal["reply_candidate", "ignore", "exception"]

_LINK_RE = re.compile(r"(?i)(https?://|\bt\.co/|\[[^\]]+\]\([^\)]+\))")
_PRICE_BAIT_RE = re.compile(
    r"(?i)\b("
    r"price|token|coin|airdrop|buy|sell|pump|moon|10x|100x|financial advice|"
    r"worth|market cap|chart|ca|contract address"
    r")\b"
)
_SPAM_RE = re.compile(r"(?i)\b(free money|promo|referral|follow back|check my profile|giveaway|airdrop)\b")
_TOXIC_RE = re.compile(r"(?i)\b(kill yourself|kys|go die|scam trash|worthless idiot|target and harass)\b")
_SECRET_RE = re.compile(r"(?i)\b(private key|seed phrase|password|api key|access token|secret|credential)\b")
_SUPPORT_RE = re.compile(r"(?i)\b(help|issue|bug|broken|can't|cannot|error|support|how do i|where do i)\b")
_POSITIVE_RE = re.compile(r"(?i)\b(great|love|nice|awesome|based|cool|excited|congrats|good work)\b")
_CRITICISM_RE = re.compile(r"(?i)\b(why|concern|worried|bad|confusing|unclear|skeptical|not sure)\b")
_HAM_RELEVANCE_RE = re.compile(r"(?i)\b(ham|goham|hermes|base|agent|agents|automation|campaign|x)\b")


class ReactivePolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: ReactiveClassification
    route: ReactiveRoute
    allowed: bool
    relevance_score: float = Field(ge=0.0, le=1.0)
    safety: SafetyPolicyResult
    reasons: list[str] = Field(default_factory=list)
    reply_text: str | None = None
    execution_allowed: bool = False
    mutation_attempted: bool = False

    def redacted_dump(self) -> dict[str, object]:
        return redact(_cap(self.model_dump(mode="json")))


def evaluate_reactive_policy(
    item: ReactiveInboundItem,
    *,
    config: HamXConfig | None = None,
) -> ReactivePolicyDecision:
    cfg = config or load_ham_x_config()
    text = item.text or ""
    reasons: list[str] = []
    classification = classify_inbound_item(item)
    relevance = _relevance(item)
    route: ReactiveRoute = "ignore"

    if item.already_answered:
        reasons.append("already_answered")
    if relevance < cfg.goham_reactive_min_relevance:
        reasons.append("relevance_below_threshold")
    if cfg.goham_reactive_block_links and _LINK_RE.search(text):
        reasons.append("inbound_link_present")
    if _SECRET_RE.search(text):
        reasons.append("private_or_secret_request")

    safety = check_social_action(text, action_type="reply")
    if not safety.allowed:
        reasons.extend([f"safety_policy:{reason}" for reason in safety.reasons])

    if classification in {"spam_bot", "off_topic"}:
        route = "ignore"
    elif classification in {"toxic_harassing", "price_token_bait", "requires_human_operator"}:
        route = "exception"
    elif reasons:
        route = "exception" if any(_exception_reason(reason) for reason in reasons) else "ignore"
    else:
        route = "reply_candidate"

    allowed = route == "reply_candidate"
    reply_text = _reply_text(item, classification) if allowed else None
    if reply_text:
        reply_safety = check_social_action(reply_text, action_type="reply")
        if not reply_safety.allowed:
            reasons.extend([f"reply_safety_policy:{reason}" for reason in reply_safety.reasons])
            route = "exception"
            allowed = False
            reply_text = None

    return ReactivePolicyDecision(
        classification=classification,
        route=route,
        allowed=allowed,
        relevance_score=relevance,
        safety=safety,
        reasons=_dedupe(reasons),
        reply_text=reply_text,
    )


def classify_inbound_item(item: ReactiveInboundItem) -> ReactiveClassification:
    text = item.text or ""
    if _TOXIC_RE.search(text):
        return "toxic_harassing"
    if _SECRET_RE.search(text):
        return "requires_human_operator"
    if _SPAM_RE.search(text) or len(re.findall(r"#[A-Za-z0-9_]+", text)) >= 6:
        return "spam_bot"
    if _PRICE_BAIT_RE.search(text):
        return "price_token_bait"
    if not _HAM_RELEVANCE_RE.search(text) and item.relevance_score < 0.75:
        return "off_topic"
    if _SUPPORT_RE.search(text) or "?" in text:
        return "support_request" if _SUPPORT_RE.search(text) else "genuine_question"
    if _CRITICISM_RE.search(text):
        return "criticism"
    if _POSITIVE_RE.search(text):
        return "positive_comment"
    return "off_topic" if item.relevance_score < 0.75 else "requires_human_operator"


def _reply_text(item: ReactiveInboundItem, classification: ReactiveClassification) -> str:
    handle = (item.author_handle or "").strip().lstrip("@")
    prefix = f"@{handle} " if handle else ""
    if classification == "genuine_question":
        return prefix + "Good question. Ham is designed to keep autonomous social actions governed by caps, policy checks, audit trails, and operator controls."
    if classification == "support_request":
        return prefix + "Thanks for flagging this. Ham treats support-style issues as governed follow-ups with audit trails so operators can inspect what happened."
    if classification == "positive_comment":
        return prefix + "Appreciate it. Ham is moving carefully: governed autonomy, clear audit trails, and no unchecked posting."
    if classification == "criticism":
        return prefix + "Fair pushback. The goal is controlled autonomy: clear limits, safety checks, and auditable decisions before anything expands."
    return prefix + "Thanks for reaching out. Ham will keep this interaction governed and auditable."


def _relevance(item: ReactiveInboundItem) -> float:
    text = item.text or ""
    if _HAM_RELEVANCE_RE.search(text):
        return max(float(item.relevance_score), 0.85)
    return float(item.relevance_score)


def _exception_reason(reason: str) -> bool:
    return (
        reason.startswith("safety_policy:")
        or reason in {"private_or_secret_request", "inbound_link_present"}
    )


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = item.strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out
