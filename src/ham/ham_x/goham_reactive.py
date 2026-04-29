"""Phase 4A dry-run GoHAM reactive engine."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.action_envelope import SocialActionEnvelope
from src.ham.ham_x.audit import append_audit_event
from src.ham.ham_x.autonomy import AutonomyDecisionResult
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.exception_queue import append_exception_record
from src.ham.ham_x.inbound_client import InboundClient, ReactiveInboundItem
from src.ham.ham_x.reactive_governor import (
    ReactiveGovernorDecision,
    ReactiveGovernorState,
    evaluate_reactive_governor,
)
from src.ham.ham_x.reactive_policy import ReactivePolicyDecision, evaluate_reactive_policy
from src.ham.ham_x.redaction import redact
from src.ham.ham_x.review_queue import _cap, append_review_record

ReactiveRunStatus = Literal["blocked", "completed"]
ReactiveItemStatus = Literal["reply_candidate", "ignored", "exception", "blocked"]


class ReactiveItemResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inbound: ReactiveInboundItem
    policy_decision: ReactivePolicyDecision
    governor_decision: ReactiveGovernorDecision
    status: ReactiveItemStatus
    reply_text: str | None = None
    review_queue_path: str | None = None
    exception_queue_path: str | None = None
    audit_ids: list[str] = Field(default_factory=list)
    execution_allowed: bool = False
    mutation_attempted: bool = False


class GohamReactiveResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReactiveRunStatus
    inbound_count: int = 0
    processed_count: int = 0
    reply_candidate_count: int = 0
    ignored_count: int = 0
    exception_count: int = 0
    items: list[ReactiveItemResult] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    audit_ids: list[str] = Field(default_factory=list)
    review_queue_path: str | None = None
    exception_queue_path: str | None = None
    diagnostic: str = "Phase 4A GoHAM reactive engine is dry-run-only and does not call providers."
    execution_allowed: bool = False
    mutation_attempted: bool = False

    def redacted_dump(self) -> dict[str, Any]:
        return redact(_cap(self.model_dump(mode="json")))


def run_reactive_once(
    inbound_items: list[ReactiveInboundItem | dict[str, Any]],
    *,
    config: HamXConfig | None = None,
    state: ReactiveGovernorState | None = None,
    inbound_client: InboundClient | None = None,
) -> GohamReactiveResult:
    """Process bounded inbound engagement into non-mutating reply candidates."""
    cfg = config or load_ham_x_config()
    st = state or ReactiveGovernorState()
    client = inbound_client or InboundClient(config=cfg)
    fetch = client.from_records(inbound_items)
    reasons = _gate_reasons(cfg)
    start_id = append_audit_event(
        "goham_reactive_started",
        {
            "inbound_count": len(fetch.items),
            "max_inbound_per_run": cfg.goham_reactive_max_inbound_per_run,
            "execution_allowed": False,
            "mutation_attempted": False,
        },
        config=cfg,
    )
    audit_ids = [start_id]
    if reasons:
        done_id = append_audit_event(
            "goham_reactive_completed",
            {
                "status": "blocked",
                "reasons": reasons,
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=cfg,
        )
        audit_ids.append(done_id)
        return GohamReactiveResult(
            status="blocked",
            inbound_count=len(fetch.items),
            reasons=reasons,
            audit_ids=audit_ids,
            review_queue_path=str(cfg.review_queue_path),
            exception_queue_path=str(cfg.exception_queue_path),
        )

    results: list[ReactiveItemResult] = []
    actions_this_run = 0
    now = datetime.now(timezone.utc)
    for item in fetch.items[: cfg.goham_reactive_max_inbound_per_run]:
        item_audit_ids: list[str] = []
        seen_id = append_audit_event(
            "goham_reactive_inbound_seen",
            {
                "inbound": item.redacted_dump(),
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=cfg,
        )
        item_audit_ids.append(seen_id)
        audit_ids.append(seen_id)

        policy = evaluate_reactive_policy(item, config=cfg)
        classified_id = append_audit_event(
            "goham_reactive_classified",
            {
                "inbound_id": item.inbound_id,
                "policy": policy.redacted_dump(),
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=cfg,
        )
        item_audit_ids.append(classified_id)
        audit_ids.append(classified_id)

        governor = evaluate_reactive_governor(
            item,
            policy,
            config=cfg,
            state=st,
            actions_this_run=actions_this_run,
            now=now,
        )
        governor_id = append_audit_event(
            "goham_reactive_governor_decision",
            {
                "inbound_id": item.inbound_id,
                "governor": governor.redacted_dump(),
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=cfg,
        )
        item_audit_ids.append(governor_id)
        audit_ids.append(governor_id)

        status: ReactiveItemStatus
        review_path: str | None = None
        exception_path: str | None = None
        if governor.allowed and policy.reply_text:
            status = "reply_candidate"
            review_path = str(_append_reactive_review(item, policy, governor, config=cfg))
            candidate_id = append_audit_event(
                "goham_reactive_reply_candidate_created",
                {
                    "inbound_id": item.inbound_id,
                    "reply_text": policy.reply_text,
                    "execution_allowed": False,
                    "mutation_attempted": False,
                },
                config=cfg,
            )
            item_audit_ids.append(candidate_id)
            audit_ids.append(candidate_id)
            actions_this_run += 1
        elif policy.route == "exception" or governor.action_tier == "exception":
            status = "exception"
            exception_path = str(_append_reactive_exception(item, policy, governor, config=cfg))
        elif policy.route == "ignore":
            status = "ignored"
        else:
            status = "blocked"

        _record_seen_state(item, policy, governor, st=st, now=now, counted=status == "reply_candidate")
        results.append(
            ReactiveItemResult(
                inbound=item,
                policy_decision=policy,
                governor_decision=governor,
                status=status,
                reply_text=policy.reply_text if status == "reply_candidate" else None,
                review_queue_path=review_path,
                exception_queue_path=exception_path,
                audit_ids=item_audit_ids,
            )
        )

    done_id = append_audit_event(
        "goham_reactive_completed",
        {
            "status": "completed",
            "inbound_count": len(fetch.items),
            "processed_count": len(results),
            "reply_candidate_count": sum(1 for item in results if item.status == "reply_candidate"),
            "ignored_count": sum(1 for item in results if item.status == "ignored"),
            "exception_count": sum(1 for item in results if item.status == "exception"),
            "execution_allowed": False,
            "mutation_attempted": False,
        },
        config=cfg,
    )
    audit_ids.append(done_id)
    return GohamReactiveResult(
        status="completed",
        inbound_count=len(fetch.items),
        processed_count=len(results),
        reply_candidate_count=sum(1 for item in results if item.status == "reply_candidate"),
        ignored_count=sum(1 for item in results if item.status == "ignored"),
        exception_count=sum(1 for item in results if item.status == "exception"),
        items=results,
        audit_ids=audit_ids,
        review_queue_path=str(cfg.review_queue_path),
        exception_queue_path=str(cfg.exception_queue_path),
    )


def _gate_reasons(config: HamXConfig) -> list[str]:
    reasons: list[str] = []
    if config.emergency_stop:
        reasons.append("emergency_stop")
    if not config.enable_goham_reactive:
        reasons.append("reactive_disabled")
    if not config.goham_reactive_dry_run:
        reasons.append("reactive_dry_run_required")
    if config.goham_reactive_live_canary:
        reasons.append("reactive_live_canary_disabled_phase4a")
    return reasons


def _append_reactive_review(
    item: ReactiveInboundItem,
    policy: ReactivePolicyDecision,
    governor: ReactiveGovernorDecision,
    *,
    config: HamXConfig,
) -> object:
    return append_review_record(
        {
            "kind": "ham_x_reactive_reply_candidate",
            "proposed_action_type": "reply",
            "inbound": item.redacted_dump(),
            "reply_text": policy.reply_text,
            "policy": policy.redacted_dump(),
            "governor": governor.redacted_dump(),
            "execution_allowed": False,
            "mutation_attempted": False,
        },
        config=config,
    )


def _append_reactive_exception(
    item: ReactiveInboundItem,
    policy: ReactivePolicyDecision,
    governor: ReactiveGovernorDecision,
    *,
    config: HamXConfig,
) -> object:
    envelope = SocialActionEnvelope(
        action_type="draft",
        tenant_id=config.tenant_id,
        agent_id=config.agent_id,
        campaign_id=config.campaign_id,
        account_id=config.account_id,
        profile_id=config.profile_id,
        autonomy_mode="goham",
        policy_profile_id=config.policy_profile_id,
        brand_voice_id=config.brand_voice_id,
        catalog_skill_id=config.catalog_skill_id,
        dry_run=True,
        autonomy_enabled=False,
        input_ref=item.inbound_id,
        target_post_id=item.post_id,
        text=policy.reply_text,
        score=policy.relevance_score,
        reason="phase_4a_reactive_exception",
        status="queued_exception",
        metadata={
            "proposed_action_type": "reply",
            "inbound": item.redacted_dump(),
        },
    )
    decision = AutonomyDecisionResult(
        decision="queue_exception",
        execution_state="blocked",
        execution_allowed=False,
        confidence=policy.relevance_score,
        risk_level="high" if policy.classification in {"toxic_harassing", "price_token_bait"} else "medium",
        reasons=[*policy.reasons, *governor.reasons],
        requires_human_review=True,
        score_100=max(0, min(100, int(round(policy.relevance_score * 100)))),
        raw_score=policy.relevance_score,
        safety_severity=policy.safety.severity,
        tenant_id=config.tenant_id,
        agent_id=config.agent_id,
        campaign_id=config.campaign_id,
        account_id=config.account_id,
        profile_id=config.profile_id,
        policy_profile_id=config.policy_profile_id,
        brand_voice_id=config.brand_voice_id,
        autonomy_mode="goham",
        catalog_skill_id=config.catalog_skill_id,
        action_id=envelope.action_id,
    )
    return append_exception_record(
        envelope=envelope,
        decision=decision,
        payload={"policy": policy.redacted_dump(), "governor": governor.redacted_dump()},
        config=config,
    )


def _record_seen_state(
    item: ReactiveInboundItem,
    policy: ReactivePolicyDecision,
    governor: ReactiveGovernorDecision,
    *,
    st: ReactiveGovernorState,
    now: datetime,
    counted: bool,
) -> None:
    st.handled_inbound_ids.add(item.inbound_id)
    if governor.response_fingerprint:
        st.response_fingerprints.add(governor.response_fingerprint)
    if not counted:
        return
    stamp = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    user_key = item.author_id or item.author_handle or "unknown_user"
    thread_key = item.thread_id or item.conversation_id or item.post_id or item.inbound_id
    st.per_user_last_reply_at[user_key] = stamp
    st.per_thread_last_reply_at[thread_key] = stamp
    st.recent_reply_times.append(stamp)
    st.user_reply_counts_today[user_key] = st.user_reply_counts_today.get(user_key, 0) + 1
    st.thread_reply_counts_today[thread_key] = st.thread_reply_counts_today.get(thread_key, 0) + 1
