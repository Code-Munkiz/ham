"""Phase 2B live-read/live-model dry-run loop for HAM-on-X.

This module may perform live read-only X search and live xAI drafting, but it
must never call the manual canary executor or any mutating X action.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.action_envelope import SocialActionEnvelope
from src.ham.ham_x.audit import append_audit_event
from src.ham.ham_x.autonomy import AutonomyDecisionResult, decide_autonomy
from src.ham.ham_x.budget import check_budget_guardrail
from src.ham.ham_x.campaign import HamXCampaignConfig, campaign_from_config
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.exception_queue import append_exception_record
from src.ham.ham_x.grok_client import XaiDraftResult, XaiHttpPost, draft_social_action_with_xai
from src.ham.ham_x.hermes_policy_adapter import review_social_action
from src.ham.ham_x.rate_limits import InProcessRateLimiter
from src.ham.ham_x.redaction import redact
from src.ham.ham_x.review_queue import append_review_record
from src.ham.ham_x.target_scoring import CandidateTarget, TargetScoreResult, candidate_from_record, score_candidate
from src.ham.ham_x.x_readonly_client import XDirectReadonlyClient, XDirectSearchResult, XHttpGet

LiveDryRunStatus = Literal["blocked", "completed", "failed"]


class LiveDryRunCandidateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: CandidateTarget
    score_result: TargetScoreResult
    draft_result: dict[str, Any] = Field(default_factory=dict)
    envelope: SocialActionEnvelope | None = None
    autonomy_decision: AutonomyDecisionResult | None = None
    status: str
    review_queue_path: str | None = None
    exception_queue_path: str | None = None
    audit_ids: list[str] = Field(default_factory=list)
    execution_allowed: bool = False
    mutation_attempted: bool = False


class LiveDryRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: LiveDryRunStatus
    ok: bool
    gate_reasons: list[str] = Field(default_factory=list)
    query: str
    search_result: dict[str, Any] = Field(default_factory=dict)
    candidates: list[LiveDryRunCandidateResult] = Field(default_factory=list)
    candidate_count: int = 0
    reviewed_count: int = 0
    exception_count: int = 0
    network_attempted_x: bool = False
    network_attempted_xai: bool = False
    execution_allowed: bool = False
    mutation_attempted: bool = False
    audit_ids: list[str] = Field(default_factory=list)
    review_queue_path: str | None = None
    exception_queue_path: str | None = None
    diagnostic: str = ""

    def redacted_dump(self) -> dict[str, Any]:
        return redact(self.model_dump(mode="json"))


def run_live_read_model_dry_run(
    *,
    config: HamXConfig | None = None,
    campaign: HamXCampaignConfig | None = None,
    x_http_get: XHttpGet | None = None,
    xai_http_post: XaiHttpPost | None = None,
    rate_limiter: InProcessRateLimiter | None = None,
) -> LiveDryRunResult:
    """Run the Phase 2B live read/model dry-run without any execution path."""
    cfg = config or load_ham_x_config()
    camp = campaign or campaign_from_config(cfg)
    limiter = rate_limiter or InProcessRateLimiter()
    gate_reasons = _gate_reasons(cfg)
    if gate_reasons:
        audit_id = append_audit_event(
            "live_dry_run_blocked",
            {
                "gate_reasons": gate_reasons,
                "query": cfg.live_dry_run_query,
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=cfg,
        )
        return LiveDryRunResult(
            status="blocked",
            ok=True,
            gate_reasons=gate_reasons,
            query=cfg.live_dry_run_query,
            audit_ids=[audit_id],
            review_queue_path=str(cfg.review_queue_path),
            exception_queue_path=str(cfg.exception_queue_path),
            diagnostic="Phase 2B live dry-run blocked by safety gates.",
        )

    audit_ids = [
        append_audit_event(
            "live_dry_run_planned",
            {
                "query": cfg.live_dry_run_query,
                "max_results": cfg.live_dry_run_max_results,
                "max_candidates": cfg.live_dry_run_max_candidates,
                "model": cfg.model,
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=cfg,
        )
    ]

    search = XDirectReadonlyClient(config=cfg, http_get=x_http_get).search_recent(
        cfg.live_dry_run_query,
        max_results=cfg.live_dry_run_max_results,
    )
    audit_ids.append(
        append_audit_event(
            "live_dry_run_search_completed",
            {
                "search_result": search.as_dict(),
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=cfg,
        )
    )
    if search.status != "ok":
        return LiveDryRunResult(
            status="failed",
            ok=False,
            query=cfg.live_dry_run_query,
            search_result=search.as_dict(),
            network_attempted_x=search.executed,
            audit_ids=audit_ids,
            review_queue_path=str(cfg.review_queue_path),
            exception_queue_path=str(cfg.exception_queue_path),
            diagnostic=search.diagnostic or search.reason,
        )

    candidates = _candidate_records_from_search(search, config=cfg, campaign=camp)
    max_candidates = max(0, int(cfg.live_dry_run_max_candidates))
    results: list[LiveDryRunCandidateResult] = []
    for candidate in candidates[:max_candidates]:
        results.append(
            _process_candidate(
                candidate,
                config=cfg,
                campaign=camp,
                rate_limiter=limiter,
                xai_http_post=xai_http_post,
            )
        )

    audit_ids.extend(audit_id for result in results for audit_id in result.audit_ids)
    audit_ids.append(
        append_audit_event(
            "live_dry_run_completed",
            {
                "candidate_count": len(results),
                "reviewed_count": sum(1 for result in results if result.review_queue_path),
                "exception_count": sum(1 for result in results if result.exception_queue_path),
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=cfg,
        )
    )
    return LiveDryRunResult(
        status="completed",
        ok=True,
        query=cfg.live_dry_run_query,
        search_result=search.as_dict(),
        candidates=results,
        candidate_count=len(results),
        reviewed_count=sum(1 for result in results if result.review_queue_path),
        exception_count=sum(1 for result in results if result.exception_queue_path),
        network_attempted_x=search.executed,
        network_attempted_xai=any(bool(result.draft_result.get("network_attempted")) for result in results),
        audit_ids=audit_ids,
        review_queue_path=str(cfg.review_queue_path),
        exception_queue_path=str(cfg.exception_queue_path),
    )


def _gate_reasons(config: HamXConfig) -> list[str]:
    reasons: list[str] = []
    if not config.enable_live_read_model_dry_run:
        reasons.append("HAM_X_ENABLE_LIVE_READ_MODEL_DRY_RUN_must_be_true")
    if not config.dry_run:
        reasons.append("HAM_X_DRY_RUN_must_remain_true")
    if config.autonomy_enabled:
        reasons.append("HAM_X_AUTONOMY_ENABLED_must_remain_false")
    if config.enable_live_execution:
        reasons.append("HAM_X_ENABLE_LIVE_EXECUTION_must_remain_false")
    if config.emergency_stop:
        reasons.append("HAM_X_EMERGENCY_STOP_must_remain_false")
    if config.enable_live_smoke:
        reasons.append("HAM_X_ENABLE_LIVE_SMOKE_must_remain_false")
    if (config.readonly_transport or "").strip().lower() != "direct":
        reasons.append("HAM_X_READONLY_TRANSPORT_must_be_direct")
    if not config.x_bearer_token:
        reasons.append("X_BEARER_TOKEN_required")
    if not config.xai_api_key:
        reasons.append("XAI_API_KEY_required")
    return reasons


def _candidate_records_from_search(
    search: XDirectSearchResult,
    *,
    config: HamXConfig,
    campaign: HamXCampaignConfig,
) -> list[CandidateTarget]:
    response = search.response or {}
    data = response.get("data")
    if not isinstance(data, list):
        return []
    records: list[CandidateTarget] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        tweet_id = str(item.get("id") or "").strip() or None
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        record = {
            "source": "live_x_readonly_search",
            "source_post_id": tweet_id,
            "source_url": f"https://x.com/i/web/status/{tweet_id}" if tweet_id else None,
            "text_excerpt": text[:1000],
            "matched_keywords": _matched_keywords(text, campaign),
            "metadata": {
                "phase": "2B",
                "query": config.live_dry_run_query,
                "execution_allowed": False,
                "mutation_attempted": False,
            },
        }
        records.append(candidate_from_record(record, campaign=campaign))
    return records


def _process_candidate(
    candidate: CandidateTarget,
    *,
    config: HamXConfig,
    campaign: HamXCampaignConfig,
    rate_limiter: InProcessRateLimiter,
    xai_http_post: XaiHttpPost | None,
) -> LiveDryRunCandidateResult:
    audit_ids: list[str] = []
    score = score_candidate(candidate, campaign=campaign)
    audit_ids.append(
        append_audit_event(
            "live_dry_run_candidate_scored",
            {
                "candidate": candidate.model_dump(mode="json"),
                "score_result": score.model_dump(mode="json"),
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=config,
        )
    )
    if score.decision in {"ignore", "monitor"}:
        audit_ids.append(
            append_audit_event(
                "live_dry_run_routed",
                {
                    "status": score.decision,
                    "score_result": score.model_dump(mode="json"),
                    "execution_allowed": False,
                    "mutation_attempted": False,
                },
                config=config,
            )
        )
        return LiveDryRunCandidateResult(
            candidate=candidate,
            score_result=score,
            status=score.decision,
            audit_ids=audit_ids,
        )

    draft = draft_social_action_with_xai(
        target_summary=candidate.text_excerpt,
        commentary_goal=f"Relevant {campaign.campaign_id} commentary in {campaign.brand_voice_id} voice",
        input_ref=candidate.source,
        target_url=candidate.source_url,
        target_post_id=candidate.source_post_id,
        config=config,
        http_post=xai_http_post,
    )
    audit_ids.append(
        append_audit_event(
            "live_dry_run_draft_created",
            {
                "candidate": candidate.model_dump(mode="json"),
                "draft_result": draft.as_dict(),
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=config,
        )
    )
    if not draft.ok or draft.envelope is None:
        return LiveDryRunCandidateResult(
            candidate=candidate,
            score_result=score,
            draft_result=draft.as_dict(),
            status="draft_failed" if not draft.blocked else "draft_blocked",
            audit_ids=audit_ids,
        )

    envelope = _prepare_envelope(draft, score=score, config=config, rate_limiter=rate_limiter)
    policy = review_social_action(envelope)
    envelope.policy_result = policy.model_dump(mode="json")
    audit_ids.append(
        append_audit_event(
            "live_dry_run_policy_reviewed",
            {
                "action_id": envelope.action_id,
                "policy_result": envelope.policy_result,
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=config,
        )
    )
    decision = decide_autonomy(
        envelope,
        policy_result=envelope.policy_result,
        budget_result=envelope.budget_result,
        rate_limit_result=envelope.rate_limit_result,
        campaign=campaign,
        config=config,
    )
    envelope.metadata["autonomy_decision"] = decision.model_dump(mode="json")
    envelope.metadata["execution_allowed"] = False
    envelope.metadata["mutation_attempted"] = False
    audit_ids.append(
        append_audit_event(
            "live_dry_run_autonomy_decision",
            {
                "action_id": envelope.action_id,
                "autonomy_decision": decision.model_dump(mode="json"),
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=config,
        )
    )
    return _route_candidate(
        candidate=candidate,
        score=score,
        draft=draft,
        envelope=envelope,
        decision=decision,
        policy_allowed=policy.allowed,
        config=config,
        audit_ids=audit_ids,
    )


def _prepare_envelope(
    draft: XaiDraftResult,
    *,
    score: TargetScoreResult,
    config: HamXConfig,
    rate_limiter: InProcessRateLimiter,
) -> SocialActionEnvelope:
    assert draft.envelope is not None
    envelope = draft.envelope
    envelope.score = score.score
    envelope.reason = "; ".join(score.reasons)
    envelope.budget_result = check_budget_guardrail(config=config).as_dict()
    envelope.rate_limit_result = rate_limiter.check("draft", config=config).as_dict()
    envelope.dry_run = True
    envelope.autonomy_enabled = False
    envelope.metadata.update(
        {
            "score_decision": score.decision,
            "execution_allowed": False,
            "mutation_attempted": False,
        }
    )
    return envelope


def _route_candidate(
    *,
    candidate: CandidateTarget,
    score: TargetScoreResult,
    draft: XaiDraftResult,
    envelope: SocialActionEnvelope,
    decision: AutonomyDecisionResult,
    policy_allowed: bool,
    config: HamXConfig,
    audit_ids: list[str],
) -> LiveDryRunCandidateResult:
    if not policy_allowed or decision.decision in {"auto_reject", "queue_exception"}:
        envelope.status = "queued_exception"
        path = append_exception_record(
            envelope=envelope,
            decision=decision,
            payload={
                "phase": "2B",
                "policy_allowed": policy_allowed,
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=config,
        )
        audit_ids.append(
            append_audit_event(
                "live_dry_run_routed",
                {
                    "action_id": envelope.action_id,
                    "status": "queued_exception",
                    "exception_queue_path": str(path),
                    "execution_allowed": False,
                    "mutation_attempted": False,
                },
                config=config,
            )
        )
        return LiveDryRunCandidateResult(
            candidate=candidate,
            score_result=score,
            draft_result=draft.as_dict(),
            envelope=envelope,
            autonomy_decision=decision,
            status="queued_exception",
            exception_queue_path=str(path),
            audit_ids=audit_ids,
        )

    envelope.status = "queued_review"
    path = append_review_record(envelope, config=config)
    audit_ids.append(
        append_audit_event(
            "live_dry_run_routed",
            {
                "action_id": envelope.action_id,
                "status": "queued_review",
                "review_queue_path": str(path),
                "autonomy_decision": decision.model_dump(mode="json"),
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=config,
        )
    )
    return LiveDryRunCandidateResult(
        candidate=candidate,
        score_result=score,
        draft_result=draft.as_dict(),
        envelope=envelope,
        autonomy_decision=decision,
        status="queued_review",
        review_queue_path=str(path),
        audit_ids=audit_ids,
    )


def _matched_keywords(text: str, campaign: HamXCampaignConfig) -> list[str]:
    low = text.lower()
    return [topic.lower() for topic in campaign.topics if topic.lower() in low][:32]
