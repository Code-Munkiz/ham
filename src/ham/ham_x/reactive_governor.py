"""Dry-run reactive reply governor for GoHAM Phase 4A."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.inbound_client import ReactiveInboundItem
from src.ham.ham_x.reactive_policy import ReactivePolicyDecision
from src.ham.ham_x.redaction import redact

GOHAM_REACTIVE_EXECUTION_KIND = "goham_reactive_reply"
ReactiveActionTier = Literal["no_reply", "reply_candidate", "exception"]


class ReactiveGovernorState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handled_inbound_ids: set[str] = Field(default_factory=set)
    response_fingerprints: set[str] = Field(default_factory=set)
    per_user_last_reply_at: dict[str, str] = Field(default_factory=dict)
    per_thread_last_reply_at: dict[str, str] = Field(default_factory=dict)
    recent_reply_times: list[str] = Field(default_factory=list)
    user_reply_counts_today: dict[str, int] = Field(default_factory=dict)
    thread_reply_counts_today: dict[str, int] = Field(default_factory=dict)
    consecutive_provider_failures: int = 0
    last_provider_status_code: int | None = None
    policy_rejection_count: int = 0


class ReactiveGovernorDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    action_tier: ReactiveActionTier
    reasons: list[str] = Field(default_factory=list)
    response_fingerprint: str | None = None
    execution_kind: str = GOHAM_REACTIVE_EXECUTION_KIND
    execution_allowed: bool = False
    mutation_attempted: bool = False

    def redacted_dump(self) -> dict[str, object]:
        return redact(self.model_dump(mode="json"))


def evaluate_reactive_governor(
    item: ReactiveInboundItem,
    policy: ReactivePolicyDecision,
    *,
    config: HamXConfig | None = None,
    state: ReactiveGovernorState | None = None,
    actions_this_run: int = 0,
    now: datetime | None = None,
) -> ReactiveGovernorDecision:
    cfg = config or load_ham_x_config()
    st = state or ReactiveGovernorState()
    current = now or datetime.now(timezone.utc)
    reasons: list[str] = []

    if cfg.emergency_stop:
        reasons.append("emergency_stop")
    if not cfg.enable_goham_reactive:
        reasons.append("reactive_disabled")
    if not cfg.goham_reactive_dry_run:
        reasons.append("reactive_dry_run_required")
    if cfg.goham_reactive_live_canary:
        reasons.append("reactive_live_canary_disabled_phase4a")
    if policy.route != "reply_candidate" or not policy.allowed:
        reasons.append(f"policy_route_{policy.route}")
    if policy.relevance_score < cfg.goham_reactive_min_relevance:
        reasons.append("relevance_below_threshold")
    if item.inbound_id in st.handled_inbound_ids:
        reasons.append("duplicate_inbound")
    if actions_this_run >= cfg.goham_reactive_max_replies_per_run:
        reasons.append("max_replies_per_run_reached")
    if st.last_provider_status_code in {401, 403}:
        reasons.append("provider_auth_stop")
    if st.consecutive_provider_failures >= cfg.goham_reactive_failure_stop:
        reasons.append("provider_failure_stop")
    if st.policy_rejection_count >= cfg.goham_reactive_policy_rejection_stop:
        reasons.append("policy_rejection_stop")

    response_fingerprint = _fingerprint(policy.reply_text or "")
    if response_fingerprint and response_fingerprint in st.response_fingerprints:
        reasons.append("duplicate_response_text")

    user_key = item.author_id or item.author_handle or "unknown_user"
    thread_key = item.thread_id or item.conversation_id or item.post_id or item.inbound_id
    if _cooldown_active(st.per_user_last_reply_at.get(user_key), cfg.goham_reactive_min_seconds_between_replies, current):
        reasons.append("per_user_cooldown_active")
    if _cooldown_active(st.per_thread_last_reply_at.get(thread_key), cfg.goham_reactive_min_seconds_between_replies, current):
        reasons.append("per_thread_cooldown_active")
    if st.user_reply_counts_today.get(user_key, 0) >= cfg.goham_reactive_max_replies_per_user_per_day:
        reasons.append("per_user_daily_cap_reached")
    if st.thread_reply_counts_today.get(thread_key, 0) >= cfg.goham_reactive_max_replies_per_thread_per_day:
        reasons.append("per_thread_daily_cap_reached")

    recent = [_parse_ts(value) for value in st.recent_reply_times]
    recent = [value for value in recent if value is not None]
    if sum(1 for value in recent if current - value <= timedelta(minutes=15)) >= cfg.goham_reactive_max_replies_per_15m:
        reasons.append("reply_15m_cap_reached")
    if sum(1 for value in recent if current - value <= timedelta(hours=1)) >= cfg.goham_reactive_max_replies_per_hour:
        reasons.append("reply_hour_cap_reached")

    allowed = not reasons
    return ReactiveGovernorDecision(
        allowed=allowed,
        action_tier="reply_candidate" if allowed else ("exception" if policy.route == "exception" else "no_reply"),
        reasons=_dedupe(reasons),
        response_fingerprint=response_fingerprint or None,
    )


def response_fingerprint(text: str) -> str:
    return _fingerprint(text)


def _fingerprint(text: str) -> str:
    normalized = " ".join((text or "").lower().split())
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _cooldown_active(value: str | None, seconds: int, now: datetime) -> bool:
    parsed = _parse_ts(value or "")
    return bool(parsed and now < parsed + timedelta(seconds=seconds))


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
