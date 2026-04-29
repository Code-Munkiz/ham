"""Phase 4C bounded reactive batch runner."""
from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.audit import append_audit_event
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.goham_reactive_inbox import ReactiveInboxCandidate, state_from_journal
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

ReactiveBatchStatus = Literal["blocked", "completed", "stopped"]
ReactiveBatchItemStatus = Literal["executed", "dry_run", "blocked", "failed", "skipped"]
RunReply = Callable[[ReactiveReplyRequest], ReactiveReplyResult]
_LINK_RE = re.compile(r"(?i)(https?://|\bt\.co/|\[[^\]]+\]\([^\)]+\))")
_MAX_REPLY_CHARS = 280


class ReactiveBatchItemResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inbound: ReactiveInboundItem
    policy_decision: ReactivePolicyDecision | None = None
    governor_decision: ReactiveGovernorDecision | None = None
    execution_request: ReactiveReplyRequest | None = None
    execution_result: ReactiveReplyResult | None = None
    status: ReactiveBatchItemStatus
    reasons: list[str] = Field(default_factory=list)
    audit_ids: list[str] = Field(default_factory=list)
    execution_allowed: bool = False
    mutation_attempted: bool = False


class GohamReactiveBatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReactiveBatchStatus
    inbound_count: int = 0
    processed_count: int = 0
    attempted_count: int = 0
    executed_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    items: list[ReactiveBatchItemResult] = Field(default_factory=list)
    stop_reason: str = ""
    reasons: list[str] = Field(default_factory=list)
    audit_ids: list[str] = Field(default_factory=list)
    journal_path: str
    audit_path: str
    execution_allowed: bool = False
    mutation_attempted: bool = False

    def redacted_dump(self) -> dict[str, Any]:
        return redact(_cap(self.model_dump(mode="json")))


def run_reactive_batch_once(
    candidates: list[ReactiveInboxCandidate | ReactiveInboundItem | dict[str, Any]],
    *,
    config: HamXConfig | None = None,
    journal: ExecutionJournal | None = None,
    state: ReactiveGovernorState | None = None,
    run_reply: RunReply | None = None,
) -> GohamReactiveBatchResult:
    """Process bounded reactive candidates; live replies require explicit opt-in."""
    cfg = config or load_ham_x_config()
    jrnl = journal or ExecutionJournal(config=cfg)
    st = state or state_from_journal(jrnl)
    reasons = _gate_reasons(cfg)
    start_id = append_audit_event(
        "goham_reactive_started",
        {
            "mode": "batch",
            "candidate_count": len(candidates),
            "dry_run": cfg.goham_reactive_batch_dry_run,
            "max_replies_per_run": cfg.goham_reactive_batch_max_replies_per_run,
            "execution_allowed": False,
            "mutation_attempted": False,
        },
        config=cfg,
    )
    if reasons:
        done_id = append_audit_event(
            "goham_reactive_completed",
            {
                "mode": "batch",
                "status": "blocked",
                "reasons": reasons,
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=cfg,
        )
        return _finish(
            cfg,
            jrnl,
            status="blocked",
            items=[],
            reasons=reasons,
            audit_ids=[start_id, done_id],
        )

    eval_cfg = replace(
        cfg,
        goham_reactive_dry_run=True,
        goham_reactive_live_canary=False,
        goham_reactive_max_replies_per_run=cfg.goham_reactive_batch_max_replies_per_run,
    )
    items: list[ReactiveBatchItemResult] = []
    attempted_count = 0
    executed_count = 0
    failed_count = 0
    stop_reason = ""
    provider_failures = 0
    now = datetime.now(timezone.utc)

    for raw in candidates:
        if stop_reason:
            items.append(_skipped_item(raw, reason=stop_reason))
            continue
        if attempted_count >= cfg.goham_reactive_batch_max_replies_per_run:
            items.append(_skipped_item(raw, reason="max_replies_per_run_reached"))
            continue

        item = _inbound_from_candidate(raw)
        item_audit_ids: list[str] = []
        seen_id = append_audit_event(
            "goham_reactive_inbound_seen",
            {
                "mode": "batch",
                "inbound": item.redacted_dump(),
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=cfg,
        )
        item_audit_ids.append(seen_id)

        policy = evaluate_reactive_policy(item, config=eval_cfg)
        governor = evaluate_reactive_governor(
            item,
            policy,
            config=eval_cfg,
            state=st,
            actions_this_run=attempted_count,
            now=now,
            live_canary=False,
        )
        request = _request_from_item(item, policy, eval_cfg)
        reasons_item = _candidate_reasons(item, policy, governor, request, jrnl, st, eval_cfg)
        decision_id = append_audit_event(
            "goham_reactive_governor_decision",
            {
                "mode": "batch",
                "inbound_id": item.inbound_id,
                "policy": policy.redacted_dump(),
                "governor": governor.redacted_dump(),
                "candidate_reasons": reasons_item,
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=cfg,
        )
        item_audit_ids.append(decision_id)

        if reasons_item:
            block_id = append_audit_event(
                "goham_reactive_reply_blocked",
                {
                    "mode": "batch",
                    "inbound_id": item.inbound_id,
                    "reasons": reasons_item,
                    "execution_allowed": False,
                    "mutation_attempted": False,
                },
                config=cfg,
            )
            item_audit_ids.append(block_id)
            items.append(
                ReactiveBatchItemResult(
                    inbound=item,
                    policy_decision=policy,
                    governor_decision=governor,
                    execution_request=request,
                    status="blocked",
                    reasons=reasons_item,
                    audit_ids=item_audit_ids,
                )
            )
            continue

        attempted_count += 1
        if cfg.goham_reactive_batch_dry_run:
            _record_simulated_state(item, governor, st=st, now=now)
            items.append(
                ReactiveBatchItemResult(
                    inbound=item,
                    policy_decision=policy,
                    governor_decision=governor,
                    execution_request=request,
                    status="dry_run",
                    audit_ids=item_audit_ids,
                )
            )
            continue

        result = (run_reply or ReactiveReplyExecutor(config=cfg).execute)(request)
        result = result.model_copy(update={"diagnostic": redact(result.diagnostic)})
        event_type = "goham_reactive_reply_executed" if result.status == "executed" else "goham_reactive_reply_failed"
        event_id = append_audit_event(
            event_type,
            {
                "mode": "batch",
                "inbound_id": item.inbound_id,
                "request": request.redacted_dump(),
                "result": result.redacted_dump(),
                "execution_allowed": result.execution_allowed,
                "mutation_attempted": result.mutation_attempted,
            },
            config=cfg,
        )
        result.audit_event_id = event_id
        item_audit_ids.append(event_id)
        if result.status == "executed":
            executed_count += 1
            provider_failures = 0
            jrnl.append_executed(
                action_id=request.action_id,
                idempotency_key=request.idempotency_key,
                action_type="reply",
                provider_post_id=result.provider_post_id,
                execution_kind=GOHAM_REACTIVE_EXECUTION_KIND,
                source_action_id=request.inbound_id,
            )
            _record_simulated_state(item, governor, st=st, now=now)
        else:
            failed_count += 1
            provider_failures += 1
            st.consecutive_provider_failures += 1
            st.last_provider_status_code = result.provider_status_code
            if cfg.goham_reactive_batch_stop_on_auth_failure and result.provider_status_code in {401, 403}:
                stop_reason = "provider_auth_stop"
            elif provider_failures >= cfg.goham_reactive_batch_stop_on_provider_failures:
                stop_reason = "provider_failure_stop"
        items.append(
            ReactiveBatchItemResult(
                inbound=item,
                policy_decision=policy,
                governor_decision=governor,
                execution_request=request,
                execution_result=result,
                status=result.status,
                reasons=result.reasons,
                audit_ids=item_audit_ids,
                execution_allowed=result.execution_allowed,
                mutation_attempted=result.mutation_attempted,
            )
        )

    status: ReactiveBatchStatus = "stopped" if stop_reason else "completed"
    done_id = append_audit_event(
        "goham_reactive_completed",
        {
            "mode": "batch",
            "status": status,
            "stop_reason": stop_reason,
            "processed_count": len(items),
            "attempted_count": attempted_count,
            "executed_count": executed_count,
            "failed_count": failed_count,
            "execution_allowed": not cfg.goham_reactive_batch_dry_run,
            "mutation_attempted": any(item.mutation_attempted for item in items),
        },
        config=cfg,
    )
    return _finish(
        cfg,
        jrnl,
        status=status,
        items=items,
        stop_reason=stop_reason,
        attempted_count=attempted_count,
        executed_count=executed_count,
        failed_count=failed_count,
        audit_ids=[start_id, done_id],
    )


def _gate_reasons(config: HamXConfig) -> list[str]:
    reasons: list[str] = []
    if config.emergency_stop:
        reasons.append("emergency_stop")
    if not config.enable_goham_reactive:
        reasons.append("reactive_disabled")
    if not config.enable_goham_reactive_batch:
        reasons.append("reactive_batch_disabled")
    if config.goham_reactive_batch_max_replies_per_run <= 0:
        reasons.append("reactive_batch_max_replies_required")
    return reasons


def _inbound_from_candidate(raw: ReactiveInboxCandidate | ReactiveInboundItem | dict[str, Any]) -> ReactiveInboundItem:
    if isinstance(raw, ReactiveInboxCandidate):
        return raw.inbound
    if isinstance(raw, ReactiveInboundItem):
        return raw
    if "inbound" in raw:
        return ReactiveInboxCandidate.model_validate(raw).inbound
    return ReactiveInboundItem.model_validate(raw)


def _request_from_item(
    item: ReactiveInboundItem,
    policy: ReactivePolicyDecision,
    config: HamXConfig,
) -> ReactiveReplyRequest | None:
    target = _reply_target_id(item)
    text = policy.reply_text or ""
    if not target or not text:
        return None
    key = _idempotency_key(
        campaign_id=config.campaign_id,
        inbound_id=item.inbound_id,
        reply_target_id=target,
        text=text,
    )
    return ReactiveReplyRequest(
        action_id="goham-reactive-batch-" + key.removeprefix("goham-reactive-reply-"),
        inbound_id=item.inbound_id,
        source_post_id=item.post_id or target,
        reply_target_id=target,
        author_id=item.author_id,
        thread_id=item.thread_id or item.conversation_id,
        text=text,
        idempotency_key=key,
    )


def _candidate_reasons(
    item: ReactiveInboundItem,
    policy: ReactivePolicyDecision,
    governor: ReactiveGovernorDecision,
    request: ReactiveReplyRequest | None,
    journal: ExecutionJournal,
    state: ReactiveGovernorState,
    config: HamXConfig,
) -> list[str]:
    reasons = [*policy.reasons, *governor.reasons]
    if item.inbound_type == "dm":
        reasons.append("dm_not_supported")
    if policy.route != "reply_candidate" or not policy.allowed:
        reasons.append(f"policy_route_{policy.route}")
    if not governor.allowed:
        reasons.append("governor_not_allowed")
    if not request:
        reasons.append("reply_request_required")
    else:
        if journal.has_executed(action_id=request.action_id, idempotency_key=request.idempotency_key):
            reasons.append("duplicate_execution")
        if not request.text.strip():
            reasons.append("reply_text_required")
        if len(request.text) > _MAX_REPLY_CHARS:
            reasons.append("reply_text_too_long")
        if config.goham_reactive_block_links and _LINK_RE.search(request.text):
            reasons.append("reply_link_present")
    if item.inbound_id in state.handled_inbound_ids:
        reasons.append("duplicate_inbound")
    if governor.response_fingerprint and governor.response_fingerprint in state.response_fingerprints:
        reasons.append("duplicate_response_text")
    return _dedupe(reasons)


def _record_simulated_state(
    item: ReactiveInboundItem,
    governor: ReactiveGovernorDecision,
    *,
    st: ReactiveGovernorState,
    now: datetime,
) -> None:
    stamp = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    user_key = item.author_id or item.author_handle or "unknown_user"
    thread_key = item.thread_id or item.conversation_id or item.post_id or item.inbound_id
    st.handled_inbound_ids.add(item.inbound_id)
    if governor.response_fingerprint:
        st.response_fingerprints.add(governor.response_fingerprint)
    st.per_user_last_reply_at[user_key] = stamp
    st.per_thread_last_reply_at[thread_key] = stamp
    st.recent_reply_times.append(stamp)
    st.user_reply_counts_today[user_key] = st.user_reply_counts_today.get(user_key, 0) + 1
    st.thread_reply_counts_today[thread_key] = st.thread_reply_counts_today.get(thread_key, 0) + 1
    st.consecutive_provider_failures = 0


def _skipped_item(
    raw: ReactiveInboxCandidate | ReactiveInboundItem | dict[str, Any],
    *,
    reason: str,
) -> ReactiveBatchItemResult:
    return ReactiveBatchItemResult(
        inbound=_inbound_from_candidate(raw),
        status="skipped",
        reasons=[reason],
    )


def _reply_target_id(item: ReactiveInboundItem) -> str | None:
    return (item.post_id or item.in_reply_to_post_id or "").strip() or None


def _idempotency_key(*, campaign_id: str, inbound_id: str, reply_target_id: str, text: str) -> str:
    raw = f"{campaign_id}:{inbound_id}:{reply_target_id}:{' '.join(text.lower().split())}"
    return "goham-reactive-reply-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _finish(
    config: HamXConfig,
    journal: ExecutionJournal,
    *,
    status: ReactiveBatchStatus,
    items: list[ReactiveBatchItemResult],
    reasons: list[str] | None = None,
    stop_reason: str = "",
    attempted_count: int | None = None,
    executed_count: int | None = None,
    failed_count: int | None = None,
    audit_ids: list[str] | None = None,
) -> GohamReactiveBatchResult:
    attempted = attempted_count if attempted_count is not None else sum(1 for item in items if item.status in {"dry_run", "executed", "failed"})
    executed = executed_count if executed_count is not None else sum(1 for item in items if item.status == "executed")
    failed = failed_count if failed_count is not None else sum(1 for item in items if item.status == "failed")
    blocked = sum(1 for item in items if item.status == "blocked")
    return GohamReactiveBatchResult(
        status=status,
        inbound_count=len(items),
        processed_count=len(items),
        attempted_count=attempted,
        executed_count=executed,
        failed_count=failed,
        blocked_count=blocked,
        items=items,
        stop_reason=stop_reason,
        reasons=_dedupe(reasons or []),
        journal_path=str(journal.path),
        audit_path=str(config.audit_log_path),
        execution_allowed=not config.goham_reactive_batch_dry_run and attempted > 0,
        mutation_attempted=any(item.mutation_attempted for item in items),
        audit_ids=audit_ids or [],
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
