"""Deterministic safety policy for proposed HAM-on-X actions."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["low", "medium", "high"]


class SafetyPolicyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reasons: list[str] = Field(default_factory=list)
    severity: Severity = "low"


_PRICE_PROMISE_RE = re.compile(
    r"\b(guaranteed|guarantee|will|must)\b.{0,40}\b("
    r"profit|gain|gains|pump|moon|10x|100x|price|return|returns|roi)\b",
    re.I,
)
_FINANCIAL_ADVICE_RE = re.compile(
    r"\b(financial advice|buy this|sell this|ape in|all in|can't lose|risk[- ]free)\b",
    re.I,
)
_EVASION_RE = re.compile(
    r"\b(bypass|evade|avoid|trick|beat)\b.{0,30}\b(filter|moderation|ban|shadowban|spam|rules?)\b",
    re.I,
)
_HARASSMENT_RE = re.compile(
    r"\b(kill yourself|kys|worthless idiot|go die|target and harass)\b",
    re.I,
)
_CREDENTIAL_RE = re.compile(
    r"\b(send|share|disclose|dump|leak|reveal)\b.{0,40}\b("
    r"private key|seed phrase|password|api key|access token|credential|secret)\b",
    re.I,
)
_BUY_LINK_RE = re.compile(
    r"\b(buy now|click (the )?link|limited time|act now|use my referral|promo code)\b",
    re.I,
)
_HASHTAG_RE = re.compile(r"#[A-Za-z0-9_]+")
_MENTION_RE = re.compile(r"@[A-Za-z0-9_]{1,20}")


def check_social_action(text: str | None, *, action_type: str | None = None) -> SafetyPolicyResult:
    """Return a deterministic allow/reject decision for proposed X text."""
    body = text or ""
    reasons: list[str] = []
    severity: Severity = "low"

    def add(reason: str, level: Severity = "medium") -> None:
        nonlocal severity
        reasons.append(reason)
        if level == "high" or severity == "low":
            severity = level

    if _PRICE_PROMISE_RE.search(body):
        add("price_promise_or_guaranteed_gain")
    if _FINANCIAL_ADVICE_RE.search(body):
        add("financial_advice_phrasing")
    if _EVASION_RE.search(body):
        add("bypass_or_evasion_language", "high")
    if _HARASSMENT_RE.search(body):
        add("direct_harassment", "high")
    if _CREDENTIAL_RE.search(body):
        add("private_credential_request", "high")
    if _BUY_LINK_RE.search(body):
        add("buy_link_spam_language")

    hashtags = [h.lower() for h in _HASHTAG_RE.findall(body)]
    if len(hashtags) >= 8 or any(hashtags.count(h) >= 3 for h in set(hashtags)):
        add("spammy_repeated_hashtags")

    mentions = _MENTION_RE.findall(body)
    if len(set(m.lower() for m in mentions)) >= 5:
        add("mass_tagging")

    return SafetyPolicyResult(allowed=not reasons, reasons=reasons, severity=severity)
