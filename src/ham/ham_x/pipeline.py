"""Supervised HAM-on-X social opportunity pipeline for Phase 1B."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.action_envelope import SocialActionEnvelope
from src.ham.ham_x.audit import append_audit_event
from src.ham.ham_x.autonomy import AutonomyDecisionResult, decide_autonomy
from src.ham.ham_x.budget import check_budget_guardrail
from src.ham.ham_x.campaign import HamXCampaignConfig, campaign_from_config
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.exception_queue import append_exception_record
from src.ham.ham_x.grok_client import draft_social_action
from src.ham.ham_x.hermes_policy_adapter import review_social_action
from src.ham.ham_x.rate_limits import InProcessRateLimiter
from src.ham.ham_x.review_queue import append_review_record
from src.ham.ham_x.target_scoring import (
    CandidateTarget,
    TargetScoreResult,
    candidate_from_record,
    score_candidate,
)
from src.ham.ham_x.xurl_wrapper import XurlWrapper


class PipelineCandidateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: CandidateTarget
    score_result: TargetScoreResult
    envelope: SocialActionEnvelope | None = None
    autonomy_decision: AutonomyDecisionResult | None = None
    queued: bool = False
    status: str
    audit_ids: list[str] = Field(default_factory=list)
    review_queue_path: str | None = None
    exception_queue_path: str | None = None


class PipelineRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search_plan: dict[str, Any]
    candidates: list[PipelineCandidateResult]
    queued_count: int
    ignored_count: int
    exception_count: int = 0
    auto_approved_candidate_count: int = 0
    audit_ids: list[str] = Field(default_factory=list)


def run_supervised_opportunity_loop(
    records: list[dict[str, Any]],
    *,
    query: str = "base ecosystem builders",
    config: HamXConfig | None = None,
    campaign: HamXCampaignConfig | None = None,
    rate_limiter: InProcessRateLimiter | None = None,
) -> PipelineRunResult:
    """Run the non-mutating Phase 1B opportunity loop over candidate records."""
    cfg = config or load_ham_x_config()
    camp = campaign or campaign_from_config(cfg)
    limiter = rate_limiter or InProcessRateLimiter()
    xurl = XurlWrapper(config=cfg, rate_limiter=limiter)
    search_plan = xurl.plan_search(query).as_dict()
    audit_ids = [
        append_audit_event(
            "search_plan_created",
            {
                "query": query,
                "search_plan": search_plan,
            },
            config=cfg,
        )
    ]

    results: list[PipelineCandidateResult] = []
    for record in records:
        candidate = candidate_from_record(record, campaign=camp)
        item = _process_candidate(candidate, config=cfg, campaign=camp, rate_limiter=limiter)
        results.append(item)

    return PipelineRunResult(
        search_plan=search_plan,
        candidates=results,
        queued_count=sum(1 for item in results if item.queued),
        ignored_count=sum(1 for item in results if item.status in {"ignored", "policy_rejected"}),
        exception_count=sum(1 for item in results if item.status == "queued_exception"),
        auto_approved_candidate_count=sum(
            1 for item in results if item.status == "auto_approved_candidate"
        ),
        audit_ids=audit_ids,
    )


def _process_candidate(
    candidate: CandidateTarget,
    *,
    config: HamXConfig,
    campaign: HamXCampaignConfig,
    rate_limiter: InProcessRateLimiter,
) -> PipelineCandidateResult:
    audit_ids: list[str] = []
    score = score_candidate(candidate, campaign=campaign)
    audit_ids.append(
        append_audit_event(
            "candidate_scored",
            {
                "candidate": candidate.model_dump(mode="json"),
                "score_result": score.model_dump(mode="json"),
            },
            config=config,
        )
    )

    if score.decision in {"ignore", "monitor"}:
        event = "action_ignored" if score.decision == "ignore" else "action_monitored"
        audit_ids.append(
            append_audit_event(
                "candidate_ignored",
                {
                    "candidate": candidate.model_dump(mode="json"),
                    "score_result": score.model_dump(mode="json"),
                },
                config=config,
            )
        )
        audit_ids.append(
            append_audit_event(
                event,
                {
                    "candidate": candidate.model_dump(mode="json"),
                    "score_result": score.model_dump(mode="json"),
                },
                config=config,
            )
        )
        return PipelineCandidateResult(
            candidate=candidate,
            score_result=score,
            queued=False,
            status="ignored" if score.decision == "ignore" else "monitored",
            audit_ids=audit_ids,
        )

    envelope = draft_social_action(
        target_summary=candidate.text_excerpt,
        commentary_goal=f"Relevant {campaign.campaign_id} commentary in {campaign.brand_voice_id} voice",
        input_ref=candidate.source,
        target_url=candidate.source_url,
        target_post_id=candidate.source_post_id,
        config=config,
    )
    envelope.score = score.score
    envelope.reason = "; ".join(score.reasons)
    envelope.metadata.update(
        {
            "candidate": candidate.model_dump(mode="json"),
            "score_decision": score.decision,
        }
    )
    envelope.budget_result = check_budget_guardrail(config=config).as_dict()
    envelope.rate_limit_result = rate_limiter.check("draft", config=config).as_dict()
    audit_ids.append(
        append_audit_event(
            "draft_created",
            {"action_id": envelope.action_id, "envelope": envelope.redacted_dump()},
            config=config,
        )
    )

    policy = review_social_action(envelope)
    envelope.policy_result = policy.model_dump(mode="json")
    decision = decide_autonomy(
        envelope,
        policy_result=policy.model_dump(mode="json"),
        budget_result=envelope.budget_result,
        rate_limit_result=envelope.rate_limit_result,
        campaign=campaign,
        config=config,
    )
    envelope.metadata["autonomy_decision"] = decision.model_dump(mode="json")
    audit_ids.append(
        append_audit_event(
            "autonomy_decision_created",
            {
                "action_id": envelope.action_id,
                "autonomy_decision": decision.model_dump(mode="json"),
            },
            config=config,
        )
    )
    return _route_autonomy_decision(
        candidate=candidate,
        score=score,
        envelope=envelope,
        decision=decision,
        policy_allowed=policy.allowed,
        config=config,
        audit_ids=audit_ids,
    )


def _route_autonomy_decision(
    *,
    candidate: CandidateTarget,
    score: TargetScoreResult,
    envelope: SocialActionEnvelope,
    decision: AutonomyDecisionResult,
    policy_allowed: bool,
    config: HamXConfig,
    audit_ids: list[str],
) -> PipelineCandidateResult:
    if not policy_allowed:
        audit_ids.append(
            append_audit_event(
                "policy_rejected",
                {
                    "action_id": envelope.action_id,
                    "policy_result": envelope.policy_result,
                },
                config=config,
            )
        )
    else:
        audit_ids.append(
            append_audit_event(
                "policy_allowed",
                {
                    "action_id": envelope.action_id,
                    "policy_result": envelope.policy_result,
                },
                config=config,
            )
        )

    if decision.decision == "auto_reject":
        envelope.status = "auto_rejected"
        audit_ids.append(
            append_audit_event(
                "action_auto_rejected",
                {"action_id": envelope.action_id, "autonomy_decision": decision.model_dump(mode="json")},
                config=config,
            )
        )
        return PipelineCandidateResult(
            candidate=candidate,
            score_result=score,
            envelope=envelope,
            autonomy_decision=decision,
            status="auto_rejected",
            audit_ids=audit_ids,
        )

    if decision.decision == "draft_only":
        envelope.status = "draft_only"
        audit_ids.append(
            append_audit_event(
                "action_draft_only",
                {"action_id": envelope.action_id, "autonomy_decision": decision.model_dump(mode="json")},
                config=config,
            )
        )
        return PipelineCandidateResult(
            candidate=candidate,
            score_result=score,
            envelope=envelope,
            autonomy_decision=decision,
            status="draft_only",
            audit_ids=audit_ids,
        )

    if decision.decision == "queue_exception":
        envelope.status = "queued_exception"
        exception_path = append_exception_record(envelope=envelope, decision=decision, config=config)
        if "emergency_stop" in decision.reasons:
            audit_ids.append(
                append_audit_event(
                    "emergency_stop_blocked",
                    {
                        "action_id": envelope.action_id,
                        "autonomy_decision": decision.model_dump(mode="json"),
                    },
                    config=config,
                )
            )
        audit_ids.append(
            append_audit_event(
                "action_queued_exception",
                {
                    "action_id": envelope.action_id,
                    "exception_queue_path": str(exception_path),
                    "autonomy_decision": decision.model_dump(mode="json"),
                },
                config=config,
            )
        )
        return PipelineCandidateResult(
            candidate=candidate,
            score_result=score,
            envelope=envelope,
            autonomy_decision=decision,
            status="queued_exception",
            audit_ids=audit_ids,
            exception_queue_path=str(exception_path),
        )

    if decision.decision == "queue_review":
        envelope.status = "queued_review"
        queue_path = append_review_record(envelope, config=config)
        audit_ids.append(
            append_audit_event(
                "action_queued_review",
                {
                    "action_id": envelope.action_id,
                    "review_queue_path": str(queue_path),
                    "autonomy_decision": decision.model_dump(mode="json"),
                },
                config=config,
            )
        )
        return PipelineCandidateResult(
            candidate=candidate,
            score_result=score,
            envelope=envelope,
            autonomy_decision=decision,
            queued=True,
            status="queued_review",
            audit_ids=audit_ids,
            review_queue_path=str(queue_path),
        )

    if decision.decision == "auto_approve":
        envelope.status = "auto_approved_candidate"
        queue_path = append_review_record(envelope, config=config)
        audit_ids.append(
            append_audit_event(
                "action_auto_approved_candidate",
                {
                    "action_id": envelope.action_id,
                    "review_queue_path": str(queue_path),
                    "autonomy_decision": decision.model_dump(mode="json"),
                },
                config=config,
            )
        )
        audit_ids.append(
            append_audit_event(
                "execution_blocked_phase1c",
                {
                    "action_id": envelope.action_id,
                    "execution_allowed": decision.execution_allowed,
                    "execution_state": decision.execution_state,
                },
                config=config,
            )
        )
        return PipelineCandidateResult(
            candidate=candidate,
            score_result=score,
            envelope=envelope,
            autonomy_decision=decision,
            status="auto_approved_candidate",
            audit_ids=audit_ids,
            review_queue_path=str(queue_path),
        )

    envelope.status = "monitored" if decision.decision == "monitor" else "ignored"
    audit_ids.append(
        append_audit_event(
            "action_monitored" if decision.decision == "monitor" else "action_ignored",
            {"action_id": envelope.action_id, "autonomy_decision": decision.model_dump(mode="json")},
            config=config,
        )
    )
    return PipelineCandidateResult(
        candidate=candidate,
        score_result=score,
        envelope=envelope,
        autonomy_decision=decision,
        status=envelope.status,
        audit_ids=audit_ids,
    )
