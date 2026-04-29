"""Deterministic candidate target scoring for HAM-on-X Phase 1B."""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.ham.ham_x.action_envelope import utc_now_iso
from src.ham.ham_x.campaign import HamXCampaignConfig, campaign_from_config
from src.ham.ham_x.config import (
    DEFAULT_ACCOUNT_ID,
    DEFAULT_AGENT_ID,
    DEFAULT_AUTONOMY_MODE,
    DEFAULT_BRAND_VOICE_ID,
    DEFAULT_CATALOG_SKILL_ID,
    DEFAULT_CAMPAIGN_ID,
    DEFAULT_POLICY_PROFILE_ID,
    DEFAULT_PROFILE_ID,
    DEFAULT_TENANT_ID,
)
from src.ham.ham_x.safety_policy import check_social_action

ScoreDecision = Literal["ignore", "monitor", "draft", "queue"]

BASE_TERMS = frozenset(
    {
        "base",
        "base ecosystem",
        "coinbase",
        "onchain",
        "l2",
        "builders",
        "builder",
        "farcaster",
        "aerodrome",
        "degen",
        "agent",
        "agents",
        "autonomous",
    }
)
SPAM_TERMS = frozenset(
    {
        "airdrop",
        "giveaway",
        "100x",
        "pump",
        "moon",
        "buy now",
        "promo code",
        "dm me",
        "referral",
        "claim now",
    }
)
HIGH_SIGNAL_TERMS = frozenset(
    {
        "launch",
        "shipping",
        "building",
        "builders",
        "demo",
        "tooling",
        "developer",
        "hackathon",
        "ecosystem",
        "open source",
        "agent",
        "automation",
    }
)


class CandidateTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = DEFAULT_TENANT_ID
    agent_id: str = DEFAULT_AGENT_ID
    campaign_id: str = DEFAULT_CAMPAIGN_ID
    account_id: str = DEFAULT_ACCOUNT_ID
    profile_id: str = DEFAULT_PROFILE_ID
    policy_profile_id: str = DEFAULT_POLICY_PROFILE_ID
    brand_voice_id: str = DEFAULT_BRAND_VOICE_ID
    autonomy_mode: str = DEFAULT_AUTONOMY_MODE
    catalog_skill_id: str = DEFAULT_CATALOG_SKILL_ID
    source: str = "dry_run"
    source_post_id: str | None = None
    source_url: str | None = None
    author_handle: str | None = None
    matched_keywords: list[str] = Field(default_factory=list)
    text_excerpt: str = ""
    discovered_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("matched_keywords")
    @classmethod
    def _v_keywords(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            word = str(item).strip().lower()
            if word and word not in seen:
                seen.add(word)
                out.append(word)
        return out[:32]

    @field_validator("text_excerpt")
    @classmethod
    def _v_excerpt(cls, value: str) -> str:
        return (value or "")[:1000]


class TargetScoreResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=1.0)
    decision: ScoreDecision
    reasons: list[str] = Field(default_factory=list)


def candidate_from_record(
    record: dict[str, Any],
    *,
    campaign: HamXCampaignConfig | None = None,
) -> CandidateTarget:
    camp = campaign or campaign_from_config()
    data = {**camp.platform_context(), **record}
    if not data.get("matched_keywords"):
        data["matched_keywords"] = _infer_keywords(
            str(data.get("text_excerpt") or ""),
            camp.topics,
        )
    return CandidateTarget.model_validate(data)


def score_candidate(
    candidate: CandidateTarget,
    *,
    campaign: HamXCampaignConfig | None = None,
) -> TargetScoreResult:
    camp = campaign or campaign_from_config()
    text = candidate.text_excerpt.lower()
    reasons: list[str] = []
    score = 0.0

    keyword_hits = set(candidate.matched_keywords)
    topic_hits = {topic for topic in camp.topics if topic.lower() in text}
    base_hits = {term for term in BASE_TERMS if term in text}
    high_signal_hits = {term for term in HIGH_SIGNAL_TERMS if term in text}
    spam_hits = {term for term in SPAM_TERMS if term in text}
    policy = check_social_action(candidate.text_excerpt)

    if keyword_hits:
        score += min(0.25, 0.08 * len(keyword_hits))
        reasons.append("keyword_match")
    if topic_hits:
        score += min(0.25, 0.08 * len(topic_hits))
        reasons.append("campaign_topic_match")
    if base_hits:
        score += min(0.25, 0.07 * len(base_hits))
        reasons.append("base_ecosystem_relevance")
    if high_signal_hits:
        score += min(0.2, 0.05 * len(high_signal_hits))
        reasons.append("high_signal_pr_opportunity")
    if _looks_natural(candidate):
        score += 0.1
        reasons.append("natural_engagement_fit")

    if spam_hits:
        score -= 0.35
        reasons.append("spam_or_promo_language")
    if _looks_bot_like(candidate):
        score -= 0.35
        reasons.append("bot_like_content")
    if not policy.allowed:
        score -= 0.45 if policy.severity == "high" else 0.3
        reasons.extend(policy.reasons)

    final_score = max(0.0, min(1.0, round(score, 3)))
    decision = _decision(final_score, reasons, policy.allowed)
    return TargetScoreResult(score=final_score, decision=decision, reasons=reasons or ["no_signal"])


def _infer_keywords(text: str, topics: list[str]) -> list[str]:
    low = text.lower()
    return [topic.lower() for topic in topics if topic.lower() in low]


def _looks_bot_like(candidate: CandidateTarget) -> bool:
    text = candidate.text_excerpt
    low = text.lower()
    hashtags = re.findall(r"#[a-zA-Z0-9_]+", text)
    mentions = re.findall(r"@[a-zA-Z0-9_]+", text)
    urls = re.findall(r"https?://", text)
    return (
        len(hashtags) >= 8
        or len(mentions) >= 5
        or len(urls) >= 3
        or low.count("!!!") >= 2
        or "follow back" in low
    )


def _looks_natural(candidate: CandidateTarget) -> bool:
    words = candidate.text_excerpt.split()
    return 8 <= len(words) <= 80 and not _looks_bot_like(candidate)


def _decision(score: float, reasons: list[str], policy_allowed: bool) -> ScoreDecision:
    if not policy_allowed or "bot_like_content" in reasons or "spam_or_promo_language" in reasons:
        return "ignore"
    if score >= 0.62:
        return "queue"
    if score >= 0.45:
        return "draft"
    if score >= 0.25:
        return "monitor"
    return "ignore"
