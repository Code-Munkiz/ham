"""Phase 1C autonomy decision engine for HAM-on-X.

This module decides what HAM *would* do next. It never executes xurl or model
calls, and ``execution_allowed`` is hard-false throughout Phase 1C.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.action_envelope import SocialActionEnvelope
from src.ham.ham_x.campaign import HamXCampaignConfig
from src.ham.ham_x.config import HamXConfig, load_ham_x_config

AutonomyDecision = Literal[
    "auto_reject",
    "ignore",
    "monitor",
    "draft_only",
    "queue_exception",
    "queue_review",
    "auto_approve",
]
ExecutionState = Literal["not_applicable", "candidate_only", "blocked"]
RiskLevel = Literal["low", "medium", "high"]


class AutonomyDecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: AutonomyDecision
    execution_state: ExecutionState
    execution_allowed: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    risk_level: RiskLevel
    reasons: list[str] = Field(default_factory=list)
    requires_human_review: bool
    score_100: int = Field(ge=0, le=100)
    raw_score: float | None = None
    safety_severity: Literal["low", "medium", "high"] = "low"
    tenant_id: str
    agent_id: str
    campaign_id: str
    account_id: str
    profile_id: str
    policy_profile_id: str
    brand_voice_id: str
    autonomy_mode: Literal["draft", "approval", "guarded", "goham"]
    catalog_skill_id: str
    action_id: str


def normalize_score_100(raw_score: float | int | None) -> int:
    """Normalize 0-1 or 0-100 scores to integer 0-100."""
    if raw_score is None:
        return 0
    score = float(raw_score)
    if score <= 1.0:
        score *= 100.0
    return max(0, min(100, int(round(score))))


def decide_autonomy(
    envelope: SocialActionEnvelope,
    *,
    policy_result: dict[str, Any] | None = None,
    budget_result: dict[str, Any] | None = None,
    rate_limit_result: dict[str, Any] | None = None,
    campaign: HamXCampaignConfig | None = None,
    config: HamXConfig | None = None,
    confidence: float | None = None,
    reasons: list[str] | None = None,
) -> AutonomyDecisionResult:
    """Return a deterministic Phase 1C autonomy decision without execution."""
    cfg = config or load_ham_x_config()
    raw_score = envelope.score
    score_100 = normalize_score_100(raw_score)
    policy = policy_result or envelope.policy_result or {}
    budget = budget_result or envelope.budget_result or {}
    rate = rate_limit_result or envelope.rate_limit_result or {}
    risk_level = _risk_level(envelope, campaign=campaign, score_100=score_100)
    safety_severity = str(policy.get("severity") or "low")
    safety_severity = safety_severity if safety_severity in {"low", "medium", "high"} else "low"
    policy_allowed = bool(policy.get("allowed", True))
    budget_allowed = bool(budget.get("allowed", True))
    rate_allowed = bool(rate.get("allowed", True))
    mode = envelope.autonomy_mode
    decision_reasons = list(reasons or [])
    if envelope.reason:
        decision_reasons.extend([part.strip() for part in envelope.reason.split(";") if part.strip()])
    decision: AutonomyDecision

    if cfg.emergency_stop:
        decision = "queue_exception"
        decision_reasons.append("emergency_stop")
    elif not policy_allowed or safety_severity == "high":
        decision = "auto_reject"
        decision_reasons.append("policy_or_high_severity_safety_block")
    elif not budget_allowed or not rate_allowed:
        decision = "queue_exception" if score_100 >= 50 else "monitor"
        decision_reasons.append("budget_or_rate_guardrail_block")
    elif score_100 < 25:
        decision = "ignore"
        decision_reasons.append("score_below_ignore_threshold")
    elif score_100 < 50:
        decision = "monitor"
        decision_reasons.append("score_below_action_threshold")
    elif score_100 < 75:
        decision = "queue_exception" if risk_level != "low" else "draft_only"
        decision_reasons.append("mid_confidence_candidate")
    elif score_100 < 90:
        decision = _decision_for_75_89(mode, risk_level)
        decision_reasons.append("high_confidence_candidate")
    else:
        decision = _decision_for_90_plus(mode, risk_level)
        decision_reasons.append("very_high_confidence_candidate")

    if decision == "auto_approve":
        execution_state: ExecutionState = "candidate_only"
        decision_reasons.append("execution_blocked_phase1c")
    elif decision in {"ignore", "monitor", "draft_only"}:
        execution_state = "not_applicable"
    else:
        execution_state = "blocked"

    return AutonomyDecisionResult(
        decision=decision,
        execution_state=execution_state,
        execution_allowed=False,
        confidence=max(0.0, min(1.0, confidence if confidence is not None else score_100 / 100.0)),
        risk_level=risk_level,
        reasons=_dedupe(decision_reasons),
        requires_human_review=decision in {"queue_exception", "queue_review"},
        score_100=score_100,
        raw_score=raw_score,
        safety_severity=safety_severity,  # type: ignore[arg-type]
        tenant_id=envelope.tenant_id,
        agent_id=envelope.agent_id,
        campaign_id=envelope.campaign_id,
        account_id=envelope.account_id,
        profile_id=envelope.profile_id,
        policy_profile_id=envelope.policy_profile_id,
        brand_voice_id=envelope.brand_voice_id,
        autonomy_mode=mode,
        catalog_skill_id=envelope.catalog_skill_id,
        action_id=envelope.action_id,
    )


def _decision_for_75_89(mode: str, risk_level: RiskLevel) -> AutonomyDecision:
    if mode == "draft":
        return "draft_only"
    if mode == "approval":
        return "queue_review"
    if mode == "guarded":
        return "auto_approve" if risk_level == "low" else "queue_review"
    if mode == "goham":
        return "auto_approve" if risk_level in {"low", "medium"} else "queue_exception"
    return "queue_review"


def _decision_for_90_plus(mode: str, risk_level: RiskLevel) -> AutonomyDecision:
    if mode == "draft":
        return "draft_only"
    if mode == "approval":
        return "queue_review"
    if mode in {"guarded", "goham"} and risk_level == "low":
        return "auto_approve"
    if mode == "goham" and risk_level == "medium":
        return "auto_approve"
    return "queue_exception"


def _risk_level(
    envelope: SocialActionEnvelope,
    *,
    campaign: HamXCampaignConfig | None,
    score_100: int,
) -> RiskLevel:
    configured = getattr(campaign, "risk_level", "low") if campaign is not None else "low"
    if configured in {"medium", "high"}:
        return configured  # type: ignore[return-value]
    reasons = (envelope.reason or "").lower()
    if score_100 < 65 or "hostile" in reasons or "spam" in reasons:
        return "medium"
    if envelope.action_type in {"post", "quote", "like"}:
        return "medium"
    return "low"


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = item.strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out
