"""Store tests for HAMgomoon learning records."""
from __future__ import annotations

import json
from pathlib import Path

from src.ham.hamgomoon_learning.models import (
    HermesSocialCritique,
    LearningRecord,
    ReviewOutcome,
    SocialDraftRecord,
)
from src.ham.hamgomoon_learning.store import (
    append_learning_record,
    list_recent_learning_records,
    summarize_learning_hints,
)


def _make_record(
    *,
    channel: str = "x",
    workspace_id: str | None = None,
    project_id: str | None = None,
    draft_text: str = "hello",
    risk_flags: list[str] | None = None,
    reusable_lesson: str | None = "be clear",
    review_decision: str | None = None,
    reason_tags: list[str] | None = None,
) -> LearningRecord:
    draft = SocialDraftRecord(
        channel=channel,  # type: ignore[arg-type]
        proposed_action="reply",
        draft_text=draft_text,
        workspace_id=workspace_id,
        project_id=project_id,
    )
    review = None
    if review_decision:
        review = ReviewOutcome(
            draft_id=draft.draft_id,
            decision=review_decision,  # type: ignore[arg-type]
            reason_tags=reason_tags or [],
        )
    critique = None
    if reusable_lesson is not None or risk_flags is not None:
        critique = HermesSocialCritique(
            draft_id=draft.draft_id,
            brand_fit_score=0.9,
            safety_score=0.9,
            clarity_score=0.9,
            engagement_hypothesis="ok",
            risk_flags=risk_flags or [],
            reusable_lesson=reusable_lesson,
        )
    return LearningRecord(
        channel=channel,  # type: ignore[arg-type]
        draft=draft,
        review=review,
        critique=critique,
        workspace_id=workspace_id,
        project_id=project_id,
    )


def test_append_and_list_recent(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "learn.jsonl"
    rec = _make_record(channel="x", draft_text="hi")
    append_learning_record(rec, path=target)
    assert target.exists()
    out = list_recent_learning_records(path=target)
    assert len(out) == 1
    assert out[0].channel == "x"


def test_append_writes_redacted_form_to_disk(tmp_path: Path) -> None:
    target = tmp_path / "learn.jsonl"
    draft = SocialDraftRecord(
        channel="x",
        proposed_action="post",
        draft_text="leak Bearer abcdef1234567890 here and xai-SuperSecretToken99 too",
    )
    rec = LearningRecord(channel="x", draft=draft)
    append_learning_record(rec, path=target)
    line = target.read_text(encoding="utf-8").strip()
    assert "abcdef1234567890" not in line
    assert "SuperSecretToken99" not in line
    parsed = json.loads(line)
    assert "[REDACTED]" in parsed["draft"]["draft_text"]


def test_list_recent_filters(tmp_path: Path) -> None:
    target = tmp_path / "learn.jsonl"
    append_learning_record(_make_record(channel="x", workspace_id="w1"), path=target)
    append_learning_record(_make_record(channel="telegram", workspace_id="w1"), path=target)
    append_learning_record(_make_record(channel="x", workspace_id="w2"), path=target)

    all_recs = list_recent_learning_records(path=target)
    assert len(all_recs) == 3

    by_ws = list_recent_learning_records(workspace_id="w1", path=target)
    assert len(by_ws) == 2

    by_channel = list_recent_learning_records(channel="x", path=target)
    assert len(by_channel) == 2

    by_both = list_recent_learning_records(workspace_id="w1", channel="x", path=target)
    assert len(by_both) == 1


def test_list_recent_missing_file(tmp_path: Path) -> None:
    target = tmp_path / "missing.jsonl"
    assert list_recent_learning_records(path=target) == []


def test_summarize_learning_hints_buckets(tmp_path: Path) -> None:
    target = tmp_path / "learn.jsonl"
    append_learning_record(
        _make_record(
            draft_text="A",
            reusable_lesson="keep it short",
            risk_flags=["overclaiming"],
            review_decision="approved",
            reason_tags=["voice_fits"],
        ),
        path=target,
    )
    append_learning_record(
        _make_record(
            draft_text="B",
            reusable_lesson="avoid jargon",
            risk_flags=["overclaiming", "regulated-claim"],
            review_decision="approved",
            reason_tags=["voice_fits"],
        ),
        path=target,
    )
    hints = summarize_learning_hints(path=target)
    assert "keep it short" in hints["recent_lessons"]
    assert "overclaiming" in hints["avoid_list"]
    assert "voice_fits" in hints["recurring_preferences"]
    assert any(s.startswith("A") or s.startswith("B") for s in hints["good_examples"])
