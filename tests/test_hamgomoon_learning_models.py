"""Schema tests for HAMgomoon learning models."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.ham.hamgomoon_learning.models import (
    DeliveryOutcome,
    HermesSocialCritique,
    LearningRecord,
    ReviewOutcome,
    SocialDraftRecord,
)


def test_social_draft_record_happy_path() -> None:
    rec = SocialDraftRecord(
        channel="x",
        proposed_action="post",
        prompt="Test prompt",
        draft_text="Hello world.",
    )
    assert rec.draft_id
    assert rec.channel == "x"
    assert rec.safety_state == "unreviewed"
    assert rec.created_at.endswith("Z")


def test_social_draft_record_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        SocialDraftRecord(
            channel="x",
            proposed_action="post",
            extra_field="nope",  # type: ignore[call-arg]
        )


def test_review_outcome_happy() -> None:
    out = ReviewOutcome(draft_id="d", decision="approved")
    assert out.draft_id == "d"
    assert out.decision == "approved"
    assert out.reason_tags == []


def test_review_outcome_rejects_extra() -> None:
    with pytest.raises(ValidationError):
        ReviewOutcome(draft_id="d", decision="approved", x=1)  # type: ignore[call-arg]


def test_delivery_outcome_happy() -> None:
    out = DeliveryOutcome(draft_id="d", status="dry_run")
    assert out.status == "dry_run"


def test_delivery_outcome_rejects_extra() -> None:
    with pytest.raises(ValidationError):
        DeliveryOutcome(draft_id="d", status="dry_run", boom=True)  # type: ignore[call-arg]


def test_critique_score_bounds() -> None:
    HermesSocialCritique(
        draft_id="d",
        brand_fit_score=0.5,
        safety_score=1.0,
        clarity_score=0.0,
        engagement_hypothesis="ok",
    )
    with pytest.raises(ValidationError):
        HermesSocialCritique(
            draft_id="d",
            brand_fit_score=1.5,
            safety_score=1.0,
            clarity_score=0.0,
            engagement_hypothesis="ok",
        )


def test_learning_record_happy() -> None:
    draft = SocialDraftRecord(channel="telegram", proposed_action="message")
    rec = LearningRecord(channel="telegram", draft=draft)
    assert rec.record_id
    assert rec.channel == "telegram"
    assert rec.draft.proposed_action == "message"


def test_learning_record_rejects_extra() -> None:
    draft = SocialDraftRecord(channel="x", proposed_action="post")
    with pytest.raises(ValidationError):
        LearningRecord(channel="x", draft=draft, oops=True)  # type: ignore[call-arg]
