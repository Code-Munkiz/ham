"""Deterministic firehose governor for GoHAM Phase 3A."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.goham_campaign import GohamCampaignProfile, campaign_profile_from_config
from src.ham.ham_x.goham_policy import GOHAM_EXECUTION_KIND
from src.ham.ham_x.redaction import redact
from src.ham.ham_x.safety_policy import check_social_action

RiskMode = Literal["normal", "cautious", "stopped"]
ActionTier = Literal["observe_only", "draft_only", "auto_original_post", "auto_quote", "exception_queue"]

_LINK_RE = re.compile(r"(?i)(https?://|\bt\.co/|\[[^\]]+\]\([^\)]+\))")


class GohamGovernorCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    source_action_id: str
    idempotency_key: str
    action_type: str = "post"
    text: str
    topic: str | None = None
    target_post_id: str | None = None
    quote_target_id: str | None = None
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def text_key(self) -> str:
        normalized = " ".join((self.text or "").lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class GohamGovernorState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duplicate_text_keys: set[str] = Field(default_factory=set)
    duplicate_source_keys: set[str] = Field(default_factory=set)
    duplicate_idempotency_keys: set[str] = Field(default_factory=set)
    per_topic_cooldowns: dict[str, str] = Field(default_factory=dict)
    per_target_cooldowns: dict[str, str] = Field(default_factory=dict)
    consecutive_provider_failures: int = 0
    last_provider_status_code: int | None = None
    policy_rejection_count: int = 0
    model_timeout_count: int = 0
    risk_mode: RiskMode = "normal"


class GohamActionBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_actions_used: int
    total_actions_remaining: int
    original_posts_used: int
    original_posts_remaining: int
    quotes_used: int
    quotes_remaining: int
    next_allowed_action_at: str | None = None
    per_topic_cooldowns: dict[str, str] = Field(default_factory=dict)
    per_target_cooldowns: dict[str, str] = Field(default_factory=dict)
    duplicate_text_keys: list[str] = Field(default_factory=list)
    duplicate_source_keys: list[str] = Field(default_factory=list)
    risk_mode: RiskMode = "normal"


class GohamGovernorDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    action_tier: ActionTier
    reasons: list[str] = Field(default_factory=list)
    provider_call_allowed: bool = False
    provider_block_reasons: list[str] = Field(default_factory=list)
    budget: GohamActionBudget
    execution_allowed: bool = False
    mutation_attempted: bool = False

    def redacted_dump(self) -> dict[str, Any]:
        return redact(self.model_dump(mode="json"))


def evaluate_goham_governor(
    candidate: GohamGovernorCandidate,
    *,
    config: HamXConfig | None = None,
    journal: ExecutionJournal | None = None,
    profile: GohamCampaignProfile | None = None,
    state: GohamGovernorState | None = None,
    actions_this_run: int = 0,
    now: datetime | None = None,
) -> GohamGovernorDecision:
    cfg = config or load_ham_x_config()
    jrnl = journal or ExecutionJournal(config=cfg)
    prof = profile or campaign_profile_from_config(cfg)
    st = state or GohamGovernorState()
    current = now or datetime.now(timezone.utc)
    budget = build_action_budget(config=cfg, journal=jrnl, profile=prof, state=st, now=current)
    reasons: list[str] = []
    provider_blocks: list[str] = []

    if cfg.emergency_stop:
        reasons.append("emergency_stop")
    if not cfg.enable_goham_controller:
        reasons.append("controller_disabled")
    if st.risk_mode == "stopped":
        reasons.append("risk_mode_stopped")
    if st.last_provider_status_code in {401, 403}:
        reasons.append("provider_auth_stop")
    if st.consecutive_provider_failures >= cfg.goham_consecutive_failure_stop:
        reasons.append("consecutive_provider_failures_stop")
    if st.policy_rejection_count >= cfg.goham_policy_rejection_stop:
        reasons.append("policy_rejection_stop")
    if st.model_timeout_count >= cfg.goham_model_timeout_stop:
        reasons.append("model_timeout_stop")

    if budget.total_actions_remaining <= 0:
        reasons.append("daily_total_action_budget_exhausted")
    if actions_this_run >= cfg.goham_max_actions_per_run:
        reasons.append("max_actions_per_run_reached")
    if candidate.action_type == "post" and budget.original_posts_remaining <= 0:
        reasons.append("daily_original_post_cap_exhausted")
    if candidate.action_type == "quote" and budget.quotes_remaining <= 0:
        reasons.append("daily_quote_cap_exhausted")

    if candidate.action_type == "quote":
        if "quote" not in prof.allowed_action_types:
            reasons.append("quote_disabled")
        if candidate.quote_target_id is None and candidate.target_post_id is None:
            reasons.append("quote_target_required")
    elif candidate.action_type != "post":
        reasons.append("unsupported_action_type")
    elif "post" not in prof.allowed_action_types:
        reasons.append("original_post_disabled")

    if _LINK_RE.search(candidate.text or "") and not prof.link_policy:
        reasons.append("links_not_allowed")
    safety = check_social_action(candidate.text, action_type=candidate.action_type)
    if not safety.allowed:
        reasons.extend([f"safety_policy:{reason}" for reason in safety.reasons])
    if jrnl.has_executed(action_id=candidate.action_id, idempotency_key=candidate.idempotency_key):
        reasons.append("duplicate_execution")
    if candidate.text_key() in st.duplicate_text_keys:
        reasons.append("duplicate_text")
    if candidate.source_action_id in st.duplicate_source_keys:
        reasons.append("duplicate_source")
    if candidate.idempotency_key in st.duplicate_idempotency_keys:
        reasons.append("duplicate_idempotency_key")

    spacing_block = _spacing_block(jrnl, cfg, current)
    if spacing_block:
        reasons.append("min_spacing_not_elapsed")
        budget.next_allowed_action_at = spacing_block
    if candidate.topic and _cooldown_active(st.per_topic_cooldowns.get(candidate.topic), cfg, current):
        reasons.append("topic_cooldown_active")
    target_key = candidate.target_post_id or candidate.quote_target_id
    if target_key and _cooldown_active(st.per_target_cooldowns.get(target_key), cfg, current):
        reasons.append("target_cooldown_active")

    if cfg.goham_controller_dry_run:
        provider_blocks.append("controller_dry_run_provider_call_block")

    allowed = not reasons
    return GohamGovernorDecision(
        allowed=allowed,
        action_tier=_tier(candidate, allowed),
        reasons=_dedupe(reasons),
        provider_call_allowed=allowed and not provider_blocks,
        provider_block_reasons=provider_blocks,
        budget=budget,
    )


def build_action_budget(
    *,
    config: HamXConfig,
    journal: ExecutionJournal,
    profile: GohamCampaignProfile,
    state: GohamGovernorState,
    now: datetime | None = None,
) -> GohamActionBudget:
    current = now or datetime.now(timezone.utc)
    rows = _today_goham_rows(journal, current)
    total_used = len(rows)
    post_used = sum(1 for row in rows if row.get("action_type") == "post")
    quote_used = sum(1 for row in rows if row.get("action_type") == "quote")
    return GohamActionBudget(
        total_actions_used=total_used,
        total_actions_remaining=max(0, min(profile.daily_action_budget, config.goham_max_total_actions_per_day) - total_used),
        original_posts_used=post_used,
        original_posts_remaining=max(0, min(profile.max_posts_per_day, config.goham_max_original_posts_per_day) - post_used),
        quotes_used=quote_used,
        quotes_remaining=max(0, min(profile.max_quotes_per_day, config.goham_max_quotes_per_day) - quote_used),
        next_allowed_action_at=_spacing_block(journal, config, current),
        per_topic_cooldowns=state.per_topic_cooldowns,
        per_target_cooldowns=state.per_target_cooldowns,
        duplicate_text_keys=sorted(state.duplicate_text_keys),
        duplicate_source_keys=sorted(state.duplicate_source_keys),
        risk_mode=state.risk_mode,
    )


def _today_goham_rows(journal: ExecutionJournal, now: datetime) -> list[dict[str, Any]]:
    day = now.date().isoformat()
    return [
        row
        for row in journal.records()
        if row.get("status") == "executed"
        and row.get("execution_kind") == GOHAM_EXECUTION_KIND
        and str(row.get("executed_at", "")).startswith(day)
    ]


def _spacing_block(journal: ExecutionJournal, config: HamXConfig, now: datetime) -> str | None:
    latest: datetime | None = None
    for row in journal.records():
        if row.get("status") != "executed" or row.get("execution_kind") != GOHAM_EXECUTION_KIND:
            continue
        parsed = _parse_ts(str(row.get("executed_at") or ""))
        if parsed and (latest is None or parsed > latest):
            latest = parsed
    if latest is None:
        return None
    next_allowed = latest + timedelta(minutes=config.goham_min_spacing_minutes)
    if now < next_allowed:
        return _iso(next_allowed)
    return None


def _cooldown_active(value: str | None, config: HamXConfig, now: datetime) -> bool:
    parsed = _parse_ts(value or "")
    if parsed is None:
        return False
    return now < parsed + timedelta(minutes=config.goham_min_spacing_minutes)


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _tier(candidate: GohamGovernorCandidate, allowed: bool) -> ActionTier:
    if not allowed:
        return "exception_queue"
    if candidate.action_type == "quote":
        return "auto_quote"
    return "auto_original_post"


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
