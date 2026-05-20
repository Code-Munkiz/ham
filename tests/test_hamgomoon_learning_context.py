"""Tests for the HAMgomoon learning context renderer."""
from __future__ import annotations

from pathlib import Path

from src.ham.hamgomoon_learning.context import render_hamgomoon_learning_hints
from src.ham.hamgomoon_learning.models import (
    HermesSocialCritique,
    LearningRecord,
    ReviewOutcome,
    SocialDraftRecord,
)
from src.ham.hamgomoon_learning.store import append_learning_record


def test_render_empty_path(tmp_path: Path) -> None:
    target = tmp_path / "learn.jsonl"
    block = render_hamgomoon_learning_hints(path=target)
    assert block.startswith("# HAMgomoon learning hints\n")
    assert "no learning hints yet" in block


def test_render_with_records(tmp_path: Path) -> None:
    target = tmp_path / "learn.jsonl"
    draft = SocialDraftRecord(channel="x", proposed_action="reply", draft_text="hi")
    critique = HermesSocialCritique(
        draft_id=draft.draft_id,
        brand_fit_score=0.8,
        safety_score=0.9,
        clarity_score=0.85,
        engagement_hypothesis="ok",
        risk_flags=["overclaiming"],
        reusable_lesson="keep it short",
    )
    review = ReviewOutcome(
        draft_id=draft.draft_id,
        decision="approved",
        reason_tags=["voice_fits"],
    )
    rec = LearningRecord(channel="x", draft=draft, review=review, critique=critique)
    # add a second record so the recurring preference threshold is met
    draft2 = SocialDraftRecord(channel="x", proposed_action="reply", draft_text="hello")
    rec2 = LearningRecord(
        channel="x",
        draft=draft2,
        review=ReviewOutcome(draft_id=draft2.draft_id, decision="approved", reason_tags=["voice_fits"]),
        critique=critique.model_copy(update={"draft_id": draft2.draft_id}),
    )
    append_learning_record(rec, path=target)
    append_learning_record(rec2, path=target)

    block = render_hamgomoon_learning_hints(path=target)
    assert "Recent lessons:" in block
    assert "keep it short" in block
    assert "Avoid:" in block
    assert "overclaiming" in block
    assert "Recurring preferences:" in block
    assert "voice_fits" in block


def test_render_does_not_leak_external_ids(tmp_path: Path) -> None:
    target = tmp_path / "learn.jsonl"
    draft = SocialDraftRecord(channel="x", proposed_action="post", draft_text="hi")
    rec = LearningRecord(channel="x", draft=draft)
    append_learning_record(rec, path=target)
    block = render_hamgomoon_learning_hints(path=target)
    assert "draft_id" not in block
    assert "external_platform_id" not in block
