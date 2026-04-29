"""Phase 4B one-shot GoHAM reactive live reply canary."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.audit import append_audit_event
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.goham_reactive import ReactiveItemResult
from src.ham.ham_x.inbound_client import ReactiveInboundItem
from src.ham.ham_x.reactive_governor import (
    GOHAM_REACTIVE_EXECUTION_KIND,
    ReactiveGovernorDecision,
    ReactiveGovernorState,
    evaluate_reactive_governor,
)
from src.ham.ham_x.reactive_policy import ReactivePolicyDecision, evaluate_reactive_policy
from src.ham.ham_x.reactive_reply_executor import (
    ReactiveReplyExecutor,
    ReactiveReplyRequest,
    ReactiveReplyResult,
)
from src.ham.ham_x.redaction import redact
from src.ham.ham_x.review_queue import _cap

GohamReactiveLiveStatus = Literal["blocked", "executed", "failed"]
RunReply = Callable[[ReactiveReplyRequest], ReactiveReplyResult]
_LINK_RE = re.compile(r"(?i)(https?://|\bt\.co/|\[[^\]]+\]\([^\)]+\))")
_MAX_REPLY_CHARS = 280


class GohamReactiveLiveResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: GohamReactiveLiveStatus
    inbound: ReactiveInboundItem | None = None
    policy_decision: ReactivePolicyDecision | None = None
    governor_decision: ReactiveGovernorDecision | None = None
    execution_request: ReactiveReplyRequest | None = None
    execution_result: ReactiveReplyResult | None = None
    audit_ids: list[str] = Field(default_factory=list)
    journal_path: str
    audit_path: str
    reasons: list[str] = Field(default_factory=list)
    diagnostic: str = ""
    execution_allowed: bool = False
    mutation_attempted: bool = False

    def redacted_dump(self) -> dict[str, Any]:
        return redact(_cap(self.model_dump(mode="json")))


def run_reactive_live_once(
    prepared: ReactiveInboundItem | ReactiveItemResult | dict[str, Any],
    *,
    config: HamXConfig | None = None,
    state: ReactiveGovernorState | None = None,
    journal: ExecutionJournal | None = None,
    run_reply: RunReply | None = None,
) -> GohamReactiveLiveResult:
    """Execute at most one prepared reactive reply, then stop."""
    cfg = config or load_ham_x_config()
    st = state or ReactiveGovernorState()
    jrnl = journal or ExecutionJournal(config=cfg)
    audit_ids: list[str] = []
    inbound, phase4a_reasons = _coerce_prepared(prepared)

    start_id = append_audit_event(
        "goham_reactive_reply_requested",
        {
            "inbound": inbound.redacted_dump() if inbound else None,
            "phase4a_reasons": phase4a_reasons,
            "execution_kind": GOHAM_REACTIVE_EXECUTION_KIND,
            "execution_allowed": False,
            "mutation_attempted": False,
        },
        config=cfg,
    )
    audit_ids.append(start_id)

    gate_reasons = _gate_reasons(cfg)
    if phase4a_reasons or gate_reasons or inbound is None:
        return _finish(
            cfg,
            jrnl,
            status="blocked",
            audit_ids=audit_ids,
            reasons=[*(phase4a_reasons or ["invalid_prepared_inbound"]), *gate_reasons],
            diagnostic="Reactive live canary blocked before policy/governor evaluation.",
            inbound=inbound,
        )

    policy = evaluate_reactive_policy(inbound, config=cfg)
    governor = evaluate_reactive_governor(
        inbound,
        policy,
        config=cfg,
        state=st,
        actions_this_run=0,
        now=datetime.now(timezone.utc),
        live_canary=True,
    )
    candidate_reasons = _candidate_reasons(inbound, policy, governor, cfg)
    decision_id = append_audit_event(
        "goham_reactive_governor_decision",
        {
            "inbound_id": inbound.inbound_id,
            "policy": policy.redacted_dump(),
            "governor": governor.redacted_dump(),
            "candidate_reasons": candidate_reasons,
            "execution_allowed": False,
            "mutation_attempted": False,
        },
        config=cfg,
    )
    audit_ids.append(decision_id)

    if candidate_reasons:
        _record_blocked_state(policy, st=st)
        block_id = append_audit_event(
            "goham_reactive_reply_blocked",
            {
                "inbound_id": inbound.inbound_id,
                "reasons": candidate_reasons,
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=cfg,
        )
        audit_ids.append(block_id)
        return _finish(
            cfg,
            jrnl,
            status="blocked",
            audit_ids=audit_ids,
            reasons=candidate_reasons,
            diagnostic="Reactive live canary blocked before provider call.",
            inbound=inbound,
            policy_decision=policy,
            governor_decision=governor,
        )

    request = _request_from_inbound(inbound, policy, cfg)
    if jrnl.has_executed(action_id=request.action_id, idempotency_key=request.idempotency_key):
        return _finish(
            cfg,
            jrnl,
            status="blocked",
            audit_ids=audit_ids,
            reasons=["duplicate_execution"],
            diagnostic="Reactive live canary duplicate execution blocked.",
            inbound=inbound,
            policy_decision=policy,
            governor_decision=governor,
            execution_request=request,
        )

    reply_once = run_reply or ReactiveReplyExecutor(config=cfg).execute
    result = reply_once(request)
    event_type = "goham_reactive_reply_executed" if result.status == "executed" else "goham_reactive_reply_failed"
    event_id = append_audit_event(
        event_type,
        {
            "inbound_id": inbound.inbound_id,
            "request": request.redacted_dump(),
            "result": result.redacted_dump(),
            "execution_allowed": result.execution_allowed,
            "mutation_attempted": result.mutation_attempted,
        },
        config=cfg,
    )
    result.audit_event_id = event_id
    audit_ids.append(event_id)

    _record_provider_state(inbound, policy, governor, result, st=st)
    if result.status == "executed":
        jrnl.append_executed(
            action_id=request.action_id,
            idempotency_key=request.idempotency_key,
            action_type="reply",
            provider_post_id=result.provider_post_id,
            execution_kind=GOHAM_REACTIVE_EXECUTION_KIND,
            source_action_id=request.inbound_id,
        )

    return _finish(
        cfg,
        jrnl,
        status=result.status,
        audit_ids=audit_ids,
        reasons=result.reasons,
        diagnostic=result.diagnostic,
        inbound=inbound,
        policy_decision=policy,
        governor_decision=governor,
        execution_request=request,
        execution_result=result,
        execution_allowed=result.execution_allowed,
        mutation_attempted=result.mutation_attempted,
    )


def _coerce_prepared(
    prepared: ReactiveInboundItem | ReactiveItemResult | dict[str, Any],
) -> tuple[ReactiveInboundItem | None, list[str]]:
    if isinstance(prepared, ReactiveItemResult):
        reasons: list[str] = []
        if prepared.status != "reply_candidate":
            reasons.append("phase4a_result_not_reply_candidate")
        if not prepared.reply_text:
            reasons.append("phase4a_reply_text_missing")
        return prepared.inbound, reasons
    if isinstance(prepared, ReactiveInboundItem):
        return prepared, []
    try:
        return ReactiveInboundItem.model_validate(prepared), []
    except Exception:
        return None, ["invalid_prepared_inbound"]


def _gate_reasons(config: HamXConfig) -> list[str]:
    reasons: list[str] = []
    if config.emergency_stop:
        reasons.append("emergency_stop")
    if not config.enable_goham_reactive:
        reasons.append("reactive_disabled")
    if config.goham_reactive_dry_run:
        reasons.append("reactive_dry_run_enabled")
    if not config.goham_reactive_live_canary:
        reasons.append("reactive_live_canary_required")
    if config.goham_reactive_max_replies_per_run != 1:
        reasons.append("reactive_max_replies_per_run_must_equal_one")
    if not config.goham_reactive_block_links:
        reasons.append("reactive_link_blocking_required")
    return _dedupe(reasons)


def _candidate_reasons(
    inbound: ReactiveInboundItem,
    policy: ReactivePolicyDecision,
    governor: ReactiveGovernorDecision,
    config: HamXConfig,
) -> list[str]:
    reasons = [*policy.reasons, *governor.reasons]
    if not policy.allowed or policy.route != "reply_candidate":
        reasons.append(f"policy_route_{policy.route}")
    if not governor.allowed:
        reasons.append("governor_not_allowed")
    if governor.action_tier != "reply_candidate":
        reasons.append("governor_tier_not_reply_candidate")
    if inbound.inbound_type == "dm":
        reasons.append("dm_reply_not_allowed")
    if not _reply_target_id(inbound):
        reasons.append("reply_target_required")
    reply_text = policy.reply_text or ""
    if not reply_text.strip():
        reasons.append("reply_text_required")
    if len(reply_text) > _MAX_REPLY_CHARS:
        reasons.append("reply_text_too_long")
    if config.goham_reactive_block_links and _LINK_RE.search(reply_text):
        reasons.append("reply_link_present")
    return _dedupe(reasons)


def _request_from_inbound(
    inbound: ReactiveInboundItem,
    policy: ReactivePolicyDecision,
    config: HamXConfig,
) -> ReactiveReplyRequest:
    reply_target_id = _reply_target_id(inbound) or ""
    idempotency_key = _idempotency_key(
        campaign_id=config.campaign_id,
        inbound_id=inbound.inbound_id,
        reply_target_id=reply_target_id,
        text=policy.reply_text or "",
    )
    return ReactiveReplyRequest(
        action_id="goham-reactive-" + idempotency_key.removeprefix("goham-reactive-reply-"),
        inbound_id=inbound.inbound_id,
        source_post_id=inbound.post_id or reply_target_id,
        reply_target_id=reply_target_id,
        author_id=inbound.author_id,
        thread_id=inbound.thread_id or inbound.conversation_id,
        text=policy.reply_text or "",
        idempotency_key=idempotency_key,
    )


def _reply_target_id(inbound: ReactiveInboundItem) -> str | None:
    return (inbound.post_id or inbound.in_reply_to_post_id or "").strip() or None


def _idempotency_key(*, campaign_id: str, inbound_id: str, reply_target_id: str, text: str) -> str:
    raw = f"{campaign_id}:{inbound_id}:{reply_target_id}:{' '.join(text.lower().split())}"
    return "goham-reactive-reply-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _record_blocked_state(policy: ReactivePolicyDecision, *, st: ReactiveGovernorState) -> None:
    if not policy.allowed:
        st.policy_rejection_count += 1


def _record_provider_state(
    inbound: ReactiveInboundItem,
    policy: ReactivePolicyDecision,
    governor: ReactiveGovernorDecision,
    result: ReactiveReplyResult,
    *,
    st: ReactiveGovernorState,
) -> None:
    if result.status == "executed":
        stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        user_key = inbound.author_id or inbound.author_handle or "unknown_user"
        thread_key = inbound.thread_id or inbound.conversation_id or inbound.post_id or inbound.inbound_id
        st.handled_inbound_ids.add(inbound.inbound_id)
        if governor.response_fingerprint:
            st.response_fingerprints.add(governor.response_fingerprint)
        st.per_user_last_reply_at[user_key] = stamp
        st.per_thread_last_reply_at[thread_key] = stamp
        st.recent_reply_times.append(stamp)
        st.user_reply_counts_today[user_key] = st.user_reply_counts_today.get(user_key, 0) + 1
        st.thread_reply_counts_today[thread_key] = st.thread_reply_counts_today.get(thread_key, 0) + 1
        st.consecutive_provider_failures = 0
        st.last_provider_status_code = result.provider_status_code
        return
    st.consecutive_provider_failures += 1
    st.last_provider_status_code = result.provider_status_code


def _finish(
    config: HamXConfig,
    journal: ExecutionJournal,
    *,
    status: GohamReactiveLiveStatus,
    audit_ids: list[str],
    reasons: list[str],
    diagnostic: str,
    inbound: ReactiveInboundItem | None = None,
    policy_decision: ReactivePolicyDecision | None = None,
    governor_decision: ReactiveGovernorDecision | None = None,
    execution_request: ReactiveReplyRequest | None = None,
    execution_result: ReactiveReplyResult | None = None,
    execution_allowed: bool = False,
    mutation_attempted: bool = False,
) -> GohamReactiveLiveResult:
    return GohamReactiveLiveResult(
        status=status,
        inbound=inbound,
        policy_decision=policy_decision,
        governor_decision=governor_decision,
        execution_request=execution_request,
        execution_result=execution_result,
        audit_ids=audit_ids,
        journal_path=str(journal.path),
        audit_path=str(config.audit_log_path),
        reasons=_dedupe(reasons),
        diagnostic=diagnostic,
        execution_allowed=execution_allowed,
        mutation_attempted=mutation_attempted,
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
