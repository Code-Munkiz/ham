"""Phase 3B live governed GoHAM controller for one prepared original post."""
from __future__ import annotations

import hashlib
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.audit import append_audit_event
from src.ham.ham_x.autonomy import AutonomyDecisionResult
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.goham_bridge import (
    GohamExecutionRequest,
    GohamExecutionResult,
    run_goham_guarded_post,
)
from src.ham.ham_x.goham_campaign import GohamCampaignProfile, campaign_profile_from_config
from src.ham.ham_x.goham_governor import (
    GohamGovernorCandidate,
    GohamGovernorDecision,
    GohamGovernorState,
    evaluate_goham_governor,
)
from src.ham.ham_x.goham_ops import GohamStatus, show_goham_status
from src.ham.ham_x.redaction import redact

GohamLiveStatus = Literal["blocked", "executed", "failed"]
RunPost = Callable[..., GohamExecutionResult]
MAX_SUMMARY_CHARS = 1000


class GohamLiveCandidateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: GohamGovernorCandidate
    governor_decision: GohamGovernorDecision
    audit_id: str
    selected: bool = False
    reasons: list[str] = Field(default_factory=list)
    execution_allowed: bool = False
    mutation_attempted: bool = False


class GohamLiveControllerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status_before: GohamStatus
    status_after: GohamStatus
    candidate_count: int = 0
    processed_count: int = 0
    governor_decisions: list[GohamLiveCandidateDecision] = Field(default_factory=list)
    selected_candidate: GohamGovernorCandidate | None = None
    execution_request: GohamExecutionRequest | None = None
    execution_result: GohamExecutionResult | None = None
    status: GohamLiveStatus
    provider_post_id: str | None = None
    provider_status_code: int | None = None
    execution_allowed: bool = False
    mutation_attempted: bool = False
    audit_ids: list[str] = Field(default_factory=list)
    journal_path: str
    audit_path: str
    reasons: list[str] = Field(default_factory=list)
    diagnostic: str = ""

    def redacted_dump(self) -> dict[str, Any]:
        return redact(_bound_value(self.model_dump(mode="json")))


def run_live_controller_once(
    candidates: list[GohamGovernorCandidate | dict[str, Any]],
    *,
    config: HamXConfig | None = None,
    journal: ExecutionJournal | None = None,
    profile: GohamCampaignProfile | None = None,
    state: GohamGovernorState | None = None,
    run_post: RunPost | None = None,
) -> GohamLiveControllerResult:
    """Evaluate prepared candidates, execute at most one original post, then stop."""
    cfg = config or load_ham_x_config()
    jrnl = journal or ExecutionJournal(config=cfg)
    prof = profile or campaign_profile_from_config(cfg)
    st = state or GohamGovernorState()
    status_before = show_goham_status(config=cfg, journal=jrnl)
    start_id = append_audit_event(
        "goham_live_controller_started",
        {
            "candidate_count": len(candidates),
            "max_candidates_per_run": cfg.goham_max_candidates_per_run,
            "max_actions_per_run": cfg.goham_live_max_actions_per_run,
            "execution_allowed": False,
            "mutation_attempted": False,
        },
        config=cfg,
    )
    audit_ids = [start_id]
    candidate_decisions: list[GohamLiveCandidateDecision] = []
    reasons = _controller_gate_reasons(cfg)

    if reasons:
        return _finish(
            cfg,
            jrnl,
            status_before=status_before,
            candidate_count=len(candidates),
            processed_count=0,
            governor_decisions=candidate_decisions,
            audit_ids=audit_ids,
            status="blocked",
            reasons=reasons,
            diagnostic="GoHAM live controller blocked before candidate evaluation.",
        )

    processed_count = 0
    execution_request: GohamExecutionRequest | None = None
    execution_result: GohamExecutionResult | None = None
    selected_candidate: GohamGovernorCandidate | None = None
    attempts_this_run = 0
    max_candidates = min(cfg.goham_max_candidates_per_run, len(candidates))
    for raw in candidates[:max_candidates]:
        if attempts_this_run >= cfg.goham_live_max_actions_per_run:
            break
        candidate = raw if isinstance(raw, GohamGovernorCandidate) else GohamGovernorCandidate.model_validate(raw)
        candidate = _with_deterministic_idempotency(candidate, campaign_id=prof.campaign_id)
        decision = evaluate_goham_governor(
            candidate,
            config=cfg,
            journal=jrnl,
            profile=prof,
            state=st,
            actions_this_run=attempts_this_run,
        )
        candidate_reasons = _candidate_bridge_reasons(candidate, decision, cfg)
        audit_id = append_audit_event(
            "goham_live_controller_candidate_decision",
            {
                "candidate": candidate.model_dump(mode="json"),
                "governor_decision": decision.model_dump(mode="json"),
                "candidate_reasons": candidate_reasons,
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=cfg,
        )
        audit_ids.append(audit_id)
        item = GohamLiveCandidateDecision(
            candidate=candidate,
            governor_decision=decision,
            audit_id=audit_id,
            reasons=candidate_reasons or decision.reasons or decision.provider_block_reasons,
        )
        candidate_decisions.append(item)
        processed_count += 1

        if candidate_reasons:
            reasons = candidate_reasons
            continue

        request = _request_from_candidate(candidate, cfg, campaign_id=prof.campaign_id)
        duplicate = jrnl.has_executed(action_id=request.action_id, idempotency_key=request.idempotency_key)
        if duplicate:
            item.reasons = _dedupe([*item.reasons, "duplicate_execution"])
            reasons = item.reasons
            continue

        selected_candidate = candidate
        item.selected = True
        execution_request = request
        attempts_this_run += 1
        post_once = run_post or run_goham_guarded_post
        execution_result = post_once(
            request,
            decision=_decision_from_candidate(candidate, cfg, campaign_id=prof.campaign_id),
            config=cfg,
            journal=jrnl,
            per_run_count=0,
        )
        reasons = execution_result.reasons
        break

    if execution_result is None:
        diagnostic = "No prepared candidate passed live-governed execution gates."
        return _finish(
            cfg,
            jrnl,
            status_before=status_before,
            candidate_count=len(candidates),
            processed_count=processed_count,
            governor_decisions=candidate_decisions,
            selected_candidate=selected_candidate,
            execution_request=execution_request,
            audit_ids=audit_ids,
            status="blocked",
            reasons=reasons or ["no_live_candidate_selected"],
            diagnostic=diagnostic,
        )

    return _finish(
        cfg,
        jrnl,
        status_before=status_before,
        candidate_count=len(candidates),
        processed_count=processed_count,
        governor_decisions=candidate_decisions,
        selected_candidate=selected_candidate,
        execution_request=execution_request,
        execution_result=execution_result,
        audit_ids=audit_ids,
        status=execution_result.status,
        provider_post_id=execution_result.provider_post_id,
        provider_status_code=execution_result.provider_status_code,
        execution_allowed=execution_result.execution_allowed,
        mutation_attempted=execution_result.mutation_attempted,
        reasons=reasons,
        diagnostic=execution_result.diagnostic,
    )


def _finish(
    config: HamXConfig,
    journal: ExecutionJournal,
    *,
    status_before: GohamStatus,
    candidate_count: int,
    processed_count: int,
    governor_decisions: list[GohamLiveCandidateDecision],
    audit_ids: list[str],
    status: GohamLiveStatus,
    reasons: list[str],
    diagnostic: str,
    selected_candidate: GohamGovernorCandidate | None = None,
    execution_request: GohamExecutionRequest | None = None,
    execution_result: GohamExecutionResult | None = None,
    provider_post_id: str | None = None,
    provider_status_code: int | None = None,
    execution_allowed: bool = False,
    mutation_attempted: bool = False,
) -> GohamLiveControllerResult:
    status_after = show_goham_status(config=config, journal=journal)
    done_id = append_audit_event(
        "goham_live_controller_completed",
        {
            "status": status,
            "candidate_count": candidate_count,
            "processed_count": processed_count,
            "selected_action_id": selected_candidate.action_id if selected_candidate else None,
            "provider_post_id": provider_post_id,
            "provider_status_code": provider_status_code,
            "execution_allowed": execution_allowed,
            "mutation_attempted": mutation_attempted,
            "reasons": reasons,
        },
        config=config,
    )
    audit_ids.append(done_id)
    return GohamLiveControllerResult(
        status_before=status_before,
        status_after=status_after,
        candidate_count=candidate_count,
        processed_count=processed_count,
        governor_decisions=governor_decisions,
        selected_candidate=selected_candidate,
        execution_request=execution_request,
        execution_result=execution_result,
        status=status,
        provider_post_id=provider_post_id,
        provider_status_code=provider_status_code,
        execution_allowed=execution_allowed,
        mutation_attempted=mutation_attempted,
        audit_ids=audit_ids,
        journal_path=str(journal.path),
        audit_path=str(config.audit_log_path),
        reasons=_dedupe(reasons),
        diagnostic=diagnostic,
    )


def _controller_gate_reasons(config: HamXConfig) -> list[str]:
    reasons: list[str] = []
    if config.emergency_stop:
        reasons.append("emergency_stop")
    if not config.enable_goham_live_controller:
        reasons.append("live_controller_disabled")
    if not config.enable_goham_controller:
        reasons.append("controller_disabled")
    if config.goham_controller_dry_run:
        reasons.append("controller_dry_run_enabled")
    if not config.enable_goham_execution:
        reasons.append("goham_execution_disabled")
    if not config.autonomy_enabled:
        reasons.append("autonomy_disabled")
    if config.dry_run:
        reasons.append("dry_run_enabled")
    if not config.enable_live_execution:
        reasons.append("live_execution_disabled")
    if not config.goham_live_controller_original_posts_only:
        reasons.append("original_posts_only_gate_disabled")
    if config.goham_live_max_actions_per_run != 1:
        reasons.append("live_max_actions_per_run_must_equal_one")
    return reasons


def _candidate_bridge_reasons(
    candidate: GohamGovernorCandidate,
    decision: GohamGovernorDecision,
    config: HamXConfig,
) -> list[str]:
    reasons = [*decision.reasons, *decision.provider_block_reasons]
    if not decision.allowed:
        reasons.append("governor_not_allowed")
    if decision.action_tier != "auto_original_post":
        reasons.append("governor_tier_not_auto_original_post")
    if not decision.provider_call_allowed:
        reasons.append("governor_provider_call_not_allowed")
    if candidate.action_type != "post":
        reasons.append("unsupported_action_type")
    if candidate.target_post_id:
        reasons.append("target_post_not_allowed")
    if candidate.quote_target_id:
        reasons.append("quote_target_not_allowed")
    if str(candidate.metadata.get("reply_target_id") or "").strip():
        reasons.append("reply_target_not_allowed")
    if config.goham_controller_dry_run:
        reasons.append("controller_dry_run_enabled")
    if not config.enable_goham_live_controller:
        reasons.append("live_controller_disabled")
    if not config.goham_live_controller_original_posts_only:
        reasons.append("original_posts_only_gate_disabled")
    if config.goham_live_max_actions_per_run != 1:
        reasons.append("live_max_actions_per_run_must_equal_one")
    return _dedupe(reasons)


def _request_from_candidate(
    candidate: GohamGovernorCandidate,
    config: HamXConfig,
    *,
    campaign_id: str,
) -> GohamExecutionRequest:
    return GohamExecutionRequest(
        tenant_id=config.tenant_id,
        agent_id=config.agent_id,
        campaign_id=campaign_id,
        account_id=config.account_id,
        action_type="post",
        text=candidate.text,
        source_action_id=candidate.source_action_id,
        idempotency_key=candidate.idempotency_key,
        reason="phase_3b_live_governed_controller",
        action_id=candidate.action_id,
    )


def _decision_from_candidate(
    candidate: GohamGovernorCandidate,
    config: HamXConfig,
    *,
    campaign_id: str,
) -> AutonomyDecisionResult:
    score_100 = max(0, min(100, int(round(candidate.score * 100))))
    return AutonomyDecisionResult(
        decision="auto_approve",
        execution_state="candidate_only",
        execution_allowed=False,
        confidence=max(0.0, min(1.0, candidate.score)),
        risk_level="low",
        reasons=["phase_3b_live_governed_candidate"],
        requires_human_review=False,
        score_100=score_100,
        raw_score=candidate.score,
        safety_severity="low",
        tenant_id=config.tenant_id,
        agent_id=config.agent_id,
        campaign_id=campaign_id,
        account_id=config.account_id,
        profile_id=config.profile_id,
        policy_profile_id=config.policy_profile_id,
        brand_voice_id=config.brand_voice_id,
        autonomy_mode="goham",
        catalog_skill_id=config.catalog_skill_id,
        action_id=candidate.action_id,
    )


def _with_deterministic_idempotency(
    candidate: GohamGovernorCandidate,
    *,
    campaign_id: str,
) -> GohamGovernorCandidate:
    key = _deterministic_idempotency_key(
        campaign_id=campaign_id,
        source_action_id=candidate.source_action_id,
        text_key=candidate.text_key(),
    )
    return candidate.model_copy(update={"idempotency_key": key})


def _deterministic_idempotency_key(*, campaign_id: str, source_action_id: str, text_key: str) -> str:
    raw = f"{campaign_id}:{source_action_id}:{text_key}"
    return "goham-live-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = item.strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _bound_value(value: Any) -> Any:
    if isinstance(value, str):
        return value[: MAX_SUMMARY_CHARS - 3] + "..." if len(value) > MAX_SUMMARY_CHARS else value
    if isinstance(value, list):
        return [_bound_value(item) for item in value[:25]]
    if isinstance(value, dict):
        return {str(key)[:128]: _bound_value(item) for key, item in list(value.items())[:50]}
    return value
