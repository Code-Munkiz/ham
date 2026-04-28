"""Supervised HAM-on-X social opportunity pipeline for Phase 1B."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.action_envelope import SocialActionEnvelope
from src.ham.ham_x.audit import append_audit_event
from src.ham.ham_x.budget import check_budget_guardrail
from src.ham.ham_x.campaign import HamXCampaignConfig, campaign_from_config
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
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
    queued: bool = False
    status: str
    audit_ids: list[str] = Field(default_factory=list)
    review_queue_path: str | None = None


class PipelineRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search_plan: dict[str, Any]
    candidates: list[PipelineCandidateResult]
    queued_count: int
    ignored_count: int
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
        return PipelineCandidateResult(
            candidate=candidate,
            score_result=score,
            queued=False,
            status="ignored",
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
    if not policy.allowed:
        envelope.status = "rejected"
        audit_ids.append(
            append_audit_event(
                "policy_rejected",
                {
                    "action_id": envelope.action_id,
                    "policy_result": policy.model_dump(mode="json"),
                },
                config=config,
            )
        )
        return PipelineCandidateResult(
            candidate=candidate,
            score_result=score,
            envelope=envelope,
            queued=False,
            status="policy_rejected",
            audit_ids=audit_ids,
        )

    envelope.status = "queued"
    audit_ids.append(
        append_audit_event(
            "policy_allowed",
            {
                "action_id": envelope.action_id,
                "policy_result": policy.model_dump(mode="json"),
            },
            config=config,
        )
    )
    queue_path = append_review_record(envelope, config=config)
    audit_ids.append(
        append_audit_event(
            "queued_for_review",
            {
                "action_id": envelope.action_id,
                "review_queue_path": str(queue_path),
            },
            config=config,
        )
    )
    return PipelineCandidateResult(
        candidate=candidate,
        score_result=score,
        envelope=envelope,
        queued=True,
        status="queued",
        audit_ids=audit_ids,
        review_queue_path=str(queue_path),
    )
