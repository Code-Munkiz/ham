"""Redaction tests for HAMgomoon learning records."""
from __future__ import annotations

from src.ham.hamgomoon_learning.models import (
    DeliveryOutcome,
    HermesSocialCritique,
    LearningRecord,
    ReviewOutcome,
    SocialDraftRecord,
)
from src.ham.hamgomoon_learning.redaction import (
    redact_external_id,
    redact_learning_record,
    redact_text,
)


def test_redact_text_bearer() -> None:
    out = redact_text("Authorization: Bearer abcdef1234567890")
    assert "abcdef1234567890" not in out
    assert "[REDACTED]" in out


def test_redact_text_xai_key() -> None:
    out = redact_text("here is a key xai-superLongTokenString12345")
    assert "xai-superLongTokenString12345" not in out
    assert "[REDACTED]" in out


def test_redact_text_xoxb_key() -> None:
    out = redact_text("slack: xoxb-1234abcdEFGH-foo")
    assert "xoxb-1234abcdEFGH-foo" not in out


def test_redact_text_telegram_bot_token() -> None:
    out = redact_text("bot12345678:AAEEFFggHHiiJjkk-token_value")
    assert "AAEEFFggHHiiJjkk-token_value" not in out
    assert "[REDACTED]" in out


def test_redact_text_ham_env_token() -> None:
    out = redact_text("export HAM_SOCIAL_LIVE_APPLY_TOKEN=supersecret123")
    assert "supersecret123" not in out
    assert "HAM_SOCIAL_LIVE_APPLY_TOKEN" in out


def test_redact_text_url_query_token() -> None:
    out = redact_text("hit https://api.example.com/x?token=abc123&foo=bar now")
    assert "abc123" not in out
    assert "foo=bar" in out


def test_redact_text_benign_unchanged() -> None:
    text = "Just a friendly message about our launch."
    assert redact_text(text) == text


def test_redact_external_id_short() -> None:
    assert redact_external_id("abc") == "…abc"


def test_redact_external_id_long() -> None:
    assert redact_external_id("1234567890abcdef") == "…abcdef"


def test_redact_external_id_none() -> None:
    assert redact_external_id(None) is None
    assert redact_external_id("") is None


def test_redact_learning_record_full() -> None:
    draft = SocialDraftRecord(
        draft_id="d1",
        channel="x",
        proposed_action="reply",
        prompt="auth Bearer abcdef1234567890 here",
        draft_text="and xai-ZZZsecretTokenABCDEF should not leak",
    )
    review = ReviewOutcome(
        draft_id="d1",
        decision="rejected",
        reviewer_note="we leaked HAM_SOCIAL_LIVE_APPLY_TOKEN=topsecret somehow",
        edited_text=None,
        reason_tags=["xai-LeakyTagSecretToken"],
    )
    delivery = DeliveryOutcome(
        draft_id="d1",
        status="sent",
        external_platform_id="1234567890abcdef",
        error_category=None,
    )
    critique = HermesSocialCritique(
        draft_id="d1",
        brand_fit_score=0.5,
        safety_score=0.5,
        clarity_score=0.5,
        engagement_hypothesis="hypo with xai-SECRET-foo present",
        risk_flags=["Bearer abcdef1234567890"],
        suggested_improvement="drop link with ?token=qqq",
        reusable_lesson="lesson with xoxb-AbCdEf1234",
        policy_suggestion=None,
        should_update_strategy=False,
    )
    rec = LearningRecord(
        channel="x",
        draft=draft,
        review=review,
        delivery=delivery,
        critique=critique,
        safe_future_hint="hint with HAM_TOKEN=secret123",
    )
    redacted = redact_learning_record(rec)
    blob = redacted.model_dump_json()
    assert "abcdef1234567890" not in blob
    assert "ZZZsecretTokenABCDEF" not in blob
    assert "topsecret" not in blob
    assert "LeakyTagSecretToken" not in blob
    assert "SECRET-foo" not in blob
    assert "AbCdEf1234" not in blob
    assert "qqq" not in blob
    assert "secret123" not in blob
    assert redacted.delivery is not None
    assert redacted.delivery.external_platform_id == "…abcdef"


def test_redact_learning_record_none_branches() -> None:
    draft = SocialDraftRecord(channel="x", proposed_action="post")
    rec = LearningRecord(channel="x", draft=draft)
    redacted = redact_learning_record(rec)
    assert redacted.review is None
    assert redacted.delivery is None
    assert redacted.critique is None
    assert redacted.safe_future_hint is None
