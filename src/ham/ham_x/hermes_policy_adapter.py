"""Deterministic Hermes policy adapter scaffold for HAM-on-X.

This is a no-network Phase 1A.2 placeholder. It shapes a Hermes-style review
result over ``SocialActionEnvelope`` using the local HAM-on-X safety policy;
future phases can replace the internals with real Hermes review calls while
keeping the same envelope-facing contract.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.action_envelope import SocialActionEnvelope
from src.ham.ham_x.safety_policy import check_social_action

HermesPolicyStatus = Literal["allowed", "blocked"]


class HermesPolicyReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: HermesPolicyStatus
    allowed: bool
    reasons: list[str] = Field(default_factory=list)
    severity: Literal["low", "medium", "high"] = "low"
    reviewer: str = "ham_x_phase_1a_local_policy"
    live_calls: int = 0


def review_social_action(envelope: SocialActionEnvelope) -> HermesPolicyReviewResult:
    """Review one social action envelope without making live Hermes/LLM calls."""
    policy = check_social_action(envelope.text, action_type=envelope.action_type)
    return HermesPolicyReviewResult(
        status="allowed" if policy.allowed else "blocked",
        allowed=policy.allowed,
        reasons=policy.reasons,
        severity=policy.severity,
    )
