"""Dry-run GoHAM Firehose controller foundation."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.audit import append_audit_event
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.goham_campaign import GohamCampaignProfile, campaign_profile_from_config
from src.ham.ham_x.goham_governor import (
    GohamActionBudget,
    GohamGovernorCandidate,
    GohamGovernorDecision,
    GohamGovernorState,
    build_action_budget,
    evaluate_goham_governor,
)
from src.ham.ham_x.redaction import redact
from src.ham.ham_x.review_queue import _cap

ControllerStatus = Literal["blocked", "completed"]


class GohamControllerCandidateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: GohamGovernorCandidate
    governor_decision: GohamGovernorDecision
    audit_id: str
    execution_allowed: bool = False
    mutation_attempted: bool = False


class GohamControllerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ControllerStatus
    allowed_dry_run: list[GohamControllerCandidateDecision] = Field(default_factory=list)
    blocked: list[GohamControllerCandidateDecision] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    budget: GohamActionBudget
    candidate_count: int = 0
    processed_count: int = 0
    max_candidates_per_run: int
    max_actions_per_run: int
    audit_ids: list[str] = Field(default_factory=list)
    execution_allowed: bool = False
    mutation_attempted: bool = False
    diagnostic: str = "Phase 3A GoHAM controller is dry-run-only and does not call providers."

    def redacted_dump(self) -> dict[str, Any]:
        return redact(_cap(self.model_dump(mode="json")))


def run_controller_once(
    candidates: list[GohamGovernorCandidate | dict[str, Any]],
    *,
    config: HamXConfig | None = None,
    journal: ExecutionJournal | None = None,
    profile: GohamCampaignProfile | None = None,
    state: GohamGovernorState | None = None,
) -> GohamControllerResult:
    """Evaluate a bounded candidate bank without executing provider calls."""
    cfg = config or load_ham_x_config()
    jrnl = journal or ExecutionJournal(config=cfg)
    prof = profile or campaign_profile_from_config(cfg)
    st = state or GohamGovernorState()
    budget = build_action_budget(config=cfg, journal=jrnl, profile=prof, state=st)
    start_id = append_audit_event(
        "goham_controller_started",
        {
            "candidate_count": len(candidates),
            "max_candidates_per_run": cfg.goham_max_candidates_per_run,
            "execution_allowed": False,
            "mutation_attempted": False,
        },
        config=cfg,
    )
    audit_ids = [start_id]

    if cfg.emergency_stop or not cfg.enable_goham_controller:
        reasons = []
        if cfg.emergency_stop:
            reasons.append("emergency_stop")
        if not cfg.enable_goham_controller:
            reasons.append("controller_disabled")
        done_id = append_audit_event(
            "goham_controller_completed",
            {
                "status": "blocked",
                "reasons": reasons,
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=cfg,
        )
        audit_ids.append(done_id)
        return GohamControllerResult(
            status="blocked",
            reasons=reasons,
            budget=budget,
            candidate_count=len(candidates),
            processed_count=0,
            max_candidates_per_run=cfg.goham_max_candidates_per_run,
            max_actions_per_run=cfg.goham_max_actions_per_run,
            audit_ids=audit_ids,
        )

    allowed: list[GohamControllerCandidateDecision] = []
    blocked: list[GohamControllerCandidateDecision] = []
    processed_count = 0
    for raw in candidates[: cfg.goham_max_candidates_per_run]:
        if len(allowed) >= cfg.goham_max_actions_per_run:
            break
        candidate = raw if isinstance(raw, GohamGovernorCandidate) else GohamGovernorCandidate.model_validate(raw)
        decision = evaluate_goham_governor(
            candidate,
            config=cfg,
            journal=jrnl,
            profile=prof,
            state=st,
            actions_this_run=len(allowed),
        )
        audit_id = append_audit_event(
            "goham_controller_candidate_decision",
            {
                "candidate": candidate.model_dump(mode="json"),
                "governor_decision": decision.model_dump(mode="json"),
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=cfg,
        )
        audit_ids.append(audit_id)
        item = GohamControllerCandidateDecision(
            candidate=candidate,
            governor_decision=decision,
            audit_id=audit_id,
        )
        processed_count += 1
        if decision.allowed:
            allowed.append(item)
        else:
            blocked.append(item)

    done_id = append_audit_event(
        "goham_controller_completed",
        {
            "status": "completed",
            "candidate_count": len(candidates),
            "processed_count": processed_count,
            "allowed_dry_run_count": len(allowed),
            "blocked_count": len(blocked),
            "execution_allowed": False,
            "mutation_attempted": False,
        },
        config=cfg,
    )
    audit_ids.append(done_id)
    return GohamControllerResult(
        status="completed",
        allowed_dry_run=allowed,
        blocked=blocked,
        budget=build_action_budget(config=cfg, journal=jrnl, profile=prof, state=st),
        candidate_count=len(candidates),
        processed_count=processed_count,
        max_candidates_per_run=cfg.goham_max_candidates_per_run,
        max_actions_per_run=cfg.goham_max_actions_per_run,
        audit_ids=audit_ids,
    )
