"""Strict eligibility policy for Phase 2C guarded GoHAM execution."""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.autonomy import AutonomyDecisionResult
from src.ham.ham_x.config import HamXConfig
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.safety_policy import check_social_action

GOHAM_EXECUTION_KIND = "goham_autonomous"
MAX_GOHAM_TEXT_CHARS = 240

_LINK_RE = re.compile(r"(?i)(https?://|\bt\.co/|\[[^\]]+\]\([^\)]+\))")
_FINANCE_RE = re.compile(
    r"(?i)\b("
    r"financial advice|buy|sell|price|token|coin|pump|moon|10x|100x|gain|gains|"
    r"guaranteed|guarantee|roi|returns?|airdrop|promo|referral"
    r")\b"
)


class GoHamEligibilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reasons: list[str] = Field(default_factory=list)
    execution_kind: str = GOHAM_EXECUTION_KIND
    execution_allowed: bool = False
    mutation_attempted: bool = False


def allowed_goham_actions(config: HamXConfig) -> set[str]:
    return {
        item.strip()
        for item in (config.goham_allowed_actions or "").split(",")
        if item.strip()
    }


def evaluate_goham_eligibility(
    request: Any,
    *,
    decision: AutonomyDecisionResult,
    config: HamXConfig,
    journal: ExecutionJournal,
    per_run_count: int = 0,
) -> GoHamEligibilityResult:
    """Return deterministic block reasons before any autonomous provider call."""
    reasons: list[str] = []
    if not config.enable_goham_execution:
        reasons.append("goham_execution_disabled")
    if not config.autonomy_enabled:
        reasons.append("autonomy_disabled")
    if config.dry_run:
        reasons.append("dry_run_enabled")
    if config.emergency_stop:
        reasons.append("emergency_stop")
    if not config.enable_live_execution:
        reasons.append("live_execution_disabled")

    action_type = str(getattr(request, "action_type", "") or "")
    if action_type != "post" or action_type not in allowed_goham_actions(config):
        reasons.append("unsupported_action_type")

    text = str(getattr(request, "text", "") or "")
    if not text.strip():
        reasons.append("empty_text")
    if len(text) > MAX_GOHAM_TEXT_CHARS:
        reasons.append("text_too_long")
    if config.goham_block_links and _LINK_RE.search(text):
        reasons.append("links_not_allowed")
    if _FINANCE_RE.search(text):
        reasons.append("financial_or_buy_language")

    if str(getattr(request, "target_post_id", "") or "").strip():
        reasons.append("target_post_not_allowed")
    if str(getattr(request, "quote_target_id", "") or "").strip():
        reasons.append("quote_target_not_allowed")
    if str(getattr(request, "reply_target_id", "") or "").strip():
        reasons.append("reply_target_not_allowed")

    safety = check_social_action(text, action_type="post")
    if not safety.allowed:
        reasons.extend([f"safety_policy:{reason}" for reason in safety.reasons])
    if safety.severity != "low":
        reasons.append("safety_severity_not_low")

    if decision.decision != "auto_approve":
        reasons.append("decision_not_auto_approve")
    if decision.risk_level != "low":
        reasons.append("risk_not_low")
    if decision.score_100 < int(round(config.goham_min_score * 100)):
        reasons.append("score_below_goham_threshold")
    if decision.confidence < config.goham_min_confidence:
        reasons.append("confidence_below_goham_threshold")

    if per_run_count >= config.goham_autonomous_per_run_cap:
        reasons.append("goham_per_run_cap_exceeded")
    if journal.daily_executed_count(execution_kind=GOHAM_EXECUTION_KIND) >= config.goham_autonomous_daily_cap:
        reasons.append("goham_daily_cap_exceeded")
    if journal.has_executed(
        action_id=str(getattr(request, "action_id", "")),
        idempotency_key=str(getattr(request, "idempotency_key", "")),
    ):
        reasons.append("duplicate_execution")

    return GoHamEligibilityResult(
        allowed=not reasons,
        reasons=_dedupe(reasons),
        execution_allowed=False,
        mutation_attempted=False,
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
