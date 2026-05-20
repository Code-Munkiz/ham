"""Pydantic models for the HAMgomoon learning loop."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Channel = Literal["x", "telegram", "discord", "other"]
ProposedAction = Literal["post", "reply", "thread", "message"]
SafetyState = Literal["unreviewed", "preview_ok", "preview_blocked", "live_blocked"]
ReviewDecision = Literal["approved", "rejected", "edited", "needs_changes"]
DeliveryStatus = Literal["not_sent", "dry_run", "sent", "failed"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _new_uuid() -> str:
    return str(uuid.uuid4())


class SocialDraftRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str = Field(default_factory=_new_uuid)
    workspace_id: str | None = None
    project_id: str | None = None
    channel: Channel
    campaign_id: str | None = None
    persona_id: str | None = None
    prompt: str = ""
    draft_text: str = ""
    proposed_action: ProposedAction
    safety_state: SafetyState = "unreviewed"
    created_at: str = Field(default_factory=_utc_now_iso)


class ReviewOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str
    decision: ReviewDecision
    reviewer_note: str | None = None
    edited_text: str | None = None
    reason_tags: list[str] = Field(default_factory=list)
    at: str = Field(default_factory=_utc_now_iso)


class DeliveryOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str
    status: DeliveryStatus
    external_platform_id: str | None = None
    error_category: str | None = None
    at: str = Field(default_factory=_utc_now_iso)


class HermesSocialCritique(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str
    brand_fit_score: float = Field(ge=0.0, le=1.0)
    safety_score: float = Field(ge=0.0, le=1.0)
    clarity_score: float = Field(ge=0.0, le=1.0)
    engagement_hypothesis: str
    risk_flags: list[str] = Field(default_factory=list)
    suggested_improvement: str | None = None
    reusable_lesson: str | None = None
    policy_suggestion: str | None = None
    should_update_strategy: bool = False
    at: str = Field(default_factory=_utc_now_iso)


class LearningRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(default_factory=_new_uuid)
    workspace_id: str | None = None
    project_id: str | None = None
    channel: Channel
    draft: SocialDraftRecord
    review: ReviewOutcome | None = None
    delivery: DeliveryOutcome | None = None
    critique: HermesSocialCritique | None = None
    safe_future_hint: str | None = None
    created_at: str = Field(default_factory=_utc_now_iso)


__all__ = [
    "Channel",
    "ProposedAction",
    "SafetyState",
    "ReviewDecision",
    "DeliveryStatus",
    "SocialDraftRecord",
    "ReviewOutcome",
    "DeliveryOutcome",
    "HermesSocialCritique",
    "LearningRecord",
]
