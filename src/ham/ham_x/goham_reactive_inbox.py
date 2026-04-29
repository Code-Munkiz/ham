"""Phase 4B.1 read-only reactive inbox discovery and target selection."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.inbound_client import InboundClient, ReactiveInboundItem
from src.ham.ham_x.reactive_governor import (
    GOHAM_REACTIVE_EXECUTION_KIND,
    ReactiveGovernorDecision,
    ReactiveGovernorState,
    evaluate_reactive_governor,
)
from src.ham.ham_x.reactive_policy import ReactivePolicyDecision, evaluate_reactive_policy
from src.ham.ham_x.redaction import redact
from src.ham.ham_x.review_queue import _cap

ReactiveInboxStatus = Literal["blocked", "completed"]
ReactiveInboxCandidateStatus = Literal["selected", "eligible", "ignored", "exception", "blocked"]

_PRIORITY = {
    "genuine_question": 0,
    "support_request": 1,
    "positive_comment": 2,
    "criticism": 3,
}


class ReactiveInboxCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inbound: ReactiveInboundItem
    policy_decision: ReactivePolicyDecision
    governor_decision: ReactiveGovernorDecision
    status: ReactiveInboxCandidateStatus
    reply_target_id: str | None = None
    priority: int = 99
    reasons: list[str] = Field(default_factory=list)
    execution_allowed: bool = False
    mutation_attempted: bool = False

    def redacted_dump(self) -> dict[str, Any]:
        return redact(_cap(self.model_dump(mode="json")))


class ReactiveInboxDiscoveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReactiveInboxStatus
    query: str = ""
    inbound_count: int = 0
    processed_count: int = 0
    candidates: list[ReactiveInboxCandidate] = Field(default_factory=list)
    selected_candidate: ReactiveInboxCandidate | None = None
    selected_inbound: ReactiveInboundItem | None = None
    reply_target_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
    journal_path: str
    audit_path: str
    diagnostic: str = "Phase 4B.1 inbox discovery is read-only and does not execute replies."
    execution_allowed: bool = False
    mutation_attempted: bool = False

    def redacted_dump(self) -> dict[str, Any]:
        return redact(_cap(self.model_dump(mode="json")))


def discover_reactive_inbox_once(
    *,
    config: HamXConfig | None = None,
    inbound_client: InboundClient | None = None,
    journal: ExecutionJournal | None = None,
    state: ReactiveGovernorState | None = None,
) -> ReactiveInboxDiscoveryResult:
    """Discover inbound X items, evaluate them, and return at most one reply target."""
    cfg = config or load_ham_x_config()
    jrnl = journal or ExecutionJournal(config=cfg)
    query = _discovery_query(cfg)
    reasons = _gate_reasons(cfg, query=query)
    if reasons:
        return _finish(cfg, jrnl, status="blocked", query=query, reasons=reasons)

    st = state or state_from_journal(jrnl)
    client = inbound_client or InboundClient(config=cfg)
    fetch = client.fetch_mentions(query=query, max_results=cfg.reactive_inbox_max_results)
    if fetch.status != "ok":
        return _finish(
            cfg,
            jrnl,
            status="blocked",
            query=query,
            reasons=[fetch.reason or fetch.status],
            diagnostic=fetch.diagnostic or "Reactive inbox discovery fetch did not return items.",
        )

    known_handled = set(st.handled_inbound_ids)
    known_reply_ids = _provider_reply_ids(jrnl)
    candidates: list[ReactiveInboxCandidate] = []
    now = datetime.now(timezone.utc)
    items = _within_lookback(fetch.items, cfg.reactive_inbox_lookback_hours, now)
    for item in items[: cfg.reactive_inbox_max_results]:
        enriched = _mark_already_answered(item, handled_ids=known_handled, provider_reply_ids=known_reply_ids)
        policy = evaluate_reactive_policy(enriched, config=cfg)
        governor = evaluate_reactive_governor(
            enriched,
            policy,
            config=cfg,
            state=st,
            actions_this_run=0,
            now=now,
            live_canary=False,
        )
        candidate = _candidate_from_decision(enriched, policy, governor)
        candidates.append(candidate)

    selected = _select_candidate(candidates)
    if selected:
        selected.status = "selected"
    return _finish(
        cfg,
        jrnl,
        status="completed",
        query=query,
        inbound_count=len(fetch.items),
        processed_count=len(candidates),
        candidates=candidates,
        selected_candidate=selected,
        selected_inbound=selected.inbound if selected else None,
        reply_target_id=selected.reply_target_id if selected else None,
        reasons=[] if selected else ["no_reply_candidate_selected"],
    )


def state_from_journal(journal: ExecutionJournal) -> ReactiveGovernorState:
    state = ReactiveGovernorState()
    for row in journal.records():
        if row.get("status") != "executed":
            continue
        if row.get("execution_kind") != GOHAM_REACTIVE_EXECUTION_KIND:
            continue
        source_action_id = str(row.get("source_action_id") or "").strip()
        if source_action_id:
            state.handled_inbound_ids.add(source_action_id)
        executed_at = str(row.get("executed_at") or "").strip()
        if executed_at:
            state.recent_reply_times.append(executed_at)
    return state


def _gate_reasons(config: HamXConfig, *, query: str) -> list[str]:
    reasons: list[str] = []
    if not config.enable_reactive_inbox_discovery:
        reasons.append("reactive_inbox_discovery_disabled")
    if not config.x_bearer_token:
        reasons.append("x_bearer_token_missing")
    if not query:
        reasons.append("reactive_inbox_query_or_handle_required")
    return reasons


def _discovery_query(config: HamXConfig) -> str:
    if config.reactive_inbox_query.strip():
        return config.reactive_inbox_query.strip()
    handle = config.reactive_handle.strip().lstrip("@")
    return f"@{handle} -is:retweet" if handle else ""


def _candidate_from_decision(
    item: ReactiveInboundItem,
    policy: ReactivePolicyDecision,
    governor: ReactiveGovernorDecision,
) -> ReactiveInboxCandidate:
    reasons = _dedupe([*policy.reasons, *governor.reasons])
    target = _reply_target_id(item)
    if target is None:
        reasons.append("reply_target_required")
    priority = _PRIORITY.get(policy.classification, 99)
    if policy.route == "exception":
        status: ReactiveInboxCandidateStatus = "exception"
    elif policy.route == "ignore":
        status = "ignored"
    elif governor.allowed and target and priority < 99:
        status = "eligible"
    else:
        status = "blocked"
    return ReactiveInboxCandidate(
        inbound=item,
        policy_decision=policy,
        governor_decision=governor,
        status=status,
        reply_target_id=target,
        priority=priority,
        reasons=_dedupe(reasons),
    )


def _select_candidate(candidates: list[ReactiveInboxCandidate]) -> ReactiveInboxCandidate | None:
    eligible = [item for item in candidates if item.status == "eligible" and item.reply_target_id]
    if not eligible:
        return None
    return sorted(
        eligible,
        key=lambda item: (
            item.priority,
            -item.policy_decision.relevance_score,
            _sort_timestamp(item.inbound.created_at),
        ),
    )[0]


def _sort_timestamp(value: str | None) -> float:
    parsed = _parse_ts(value)
    return -parsed.timestamp() if parsed else 0.0


def _within_lookback(
    items: list[ReactiveInboundItem],
    lookback_hours: int,
    now: datetime,
) -> list[ReactiveInboundItem]:
    if lookback_hours <= 0:
        return items
    cutoff = now - timedelta(hours=lookback_hours)
    out: list[ReactiveInboundItem] = []
    for item in items:
        parsed = _parse_ts(item.created_at or "")
        if parsed is None or parsed >= cutoff:
            out.append(item)
    return out


def _mark_already_answered(
    item: ReactiveInboundItem,
    *,
    handled_ids: set[str],
    provider_reply_ids: set[str],
) -> ReactiveInboundItem:
    answered = (
        item.already_answered
        or item.inbound_id in handled_ids
        or bool(item.post_id and item.post_id in provider_reply_ids)
        or bool(item.thread_id and item.thread_id in provider_reply_ids)
        or bool(item.conversation_id and item.conversation_id in provider_reply_ids)
    )
    return item.model_copy(update={"already_answered": answered}) if answered != item.already_answered else item


def _provider_reply_ids(journal: ExecutionJournal) -> set[str]:
    ids: set[str] = set()
    for row in journal.records():
        if row.get("status") == "executed" and row.get("execution_kind") == GOHAM_REACTIVE_EXECUTION_KIND:
            provider_post_id = str(row.get("provider_post_id") or "").strip()
            if provider_post_id:
                ids.add(provider_post_id)
    return ids


def _reply_target_id(item: ReactiveInboundItem) -> str | None:
    return (item.post_id or item.in_reply_to_post_id or "").strip() or None


def _parse_ts(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _finish(
    config: HamXConfig,
    journal: ExecutionJournal,
    *,
    status: ReactiveInboxStatus,
    query: str,
    reasons: list[str],
    diagnostic: str | None = None,
    inbound_count: int = 0,
    processed_count: int = 0,
    candidates: list[ReactiveInboxCandidate] | None = None,
    selected_candidate: ReactiveInboxCandidate | None = None,
    selected_inbound: ReactiveInboundItem | None = None,
    reply_target_id: str | None = None,
) -> ReactiveInboxDiscoveryResult:
    return ReactiveInboxDiscoveryResult(
        status=status,
        query=query,
        inbound_count=inbound_count,
        processed_count=processed_count,
        candidates=candidates or [],
        selected_candidate=selected_candidate,
        selected_inbound=selected_inbound,
        reply_target_id=reply_target_id,
        reasons=_dedupe(reasons),
        journal_path=str(journal.path),
        audit_path=str(config.audit_log_path),
        diagnostic=diagnostic or "Phase 4B.1 inbox discovery is read-only and does not execute replies.",
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
