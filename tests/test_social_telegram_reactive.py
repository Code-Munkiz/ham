from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.ham.social_telegram_reactive import preview_telegram_reactive_replies_once


def _write_row(path: Path, **fields: object) -> None:
    base = {
        "source": "telegram",
        "role": "user",
        "chat_id": "-1009876543210",
        "user_id": "123456789",
        "session_id": "telegram-session-1",
    }
    base.update(fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(base, sort_keys=True) + "\n")


def _preview_for_text(tmp_path: Path, text: str, **fields: object):
    transcript = tmp_path / "telegram.jsonl"
    _write_row(transcript, text=text, **fields)
    return preview_telegram_reactive_replies_once(transcript_paths=[transcript])


def test_safe_question_produces_reply_candidate(tmp_path: Path) -> None:
    result = _preview_for_text(tmp_path, "How does Ham work?")
    item = result.items[0]
    assert result.status == "completed"
    assert result.reply_candidate_count == 1
    assert item.classification == "genuine_question"
    assert item.policy.allowed is True
    assert item.governor.allowed is True
    assert item.reply_candidate_text
    assert item.proposal_digest and len(item.proposal_digest) == 64


def test_support_request_produces_reply_candidate(tmp_path: Path) -> None:
    result = _preview_for_text(tmp_path, "I need support, the app is not working")
    item = result.items[0]
    assert item.classification == "support_request"
    assert item.reply_candidate_text
    assert result.reply_candidate_count == 1


def test_positive_signal_produces_reply_candidate(tmp_path: Path) -> None:
    result = _preview_for_text(tmp_path, "Thanks, this is awesome")
    item = result.items[0]
    assert item.classification == "positive_signal"
    assert item.reply_candidate_text


def test_off_topic_is_ignored(tmp_path: Path) -> None:
    result = _preview_for_text(tmp_path, "banana sandwich weather")
    item = result.items[0]
    assert item.classification == "off_topic"
    assert item.policy.allowed is False
    assert item.reply_candidate_text == ""
    assert item.proposal_digest is None


def test_unsafe_is_blocked(tmp_path: Path) -> None:
    result = _preview_for_text(tmp_path, "you should kill yourself")
    item = result.items[0]
    assert item.classification == "unsafe"
    assert "telegram_reactive_unsafe_content" in item.reasons
    assert item.reply_candidate_text == ""


def test_financial_or_price_promise_bait_is_blocked(tmp_path: Path) -> None:
    result = _preview_for_text(tmp_path, "Can you guarantee profit and make a price promise?")
    item = result.items[0]
    assert item.classification == "requires_human_operator"
    assert "telegram_reactive_financial_or_price_promise" in item.reasons
    assert item.proposal_digest is None


def test_secret_handling_request_is_blocked(tmp_path: Path) -> None:
    result = _preview_for_text(tmp_path, "Here is my API key, can you store this token?")
    item = result.items[0]
    assert item.classification == "requires_human_operator"
    assert "telegram_reactive_secret_handling_request" in item.reasons
    assert item.reply_candidate_text == ""


def test_already_answered_is_blocked(tmp_path: Path) -> None:
    result = _preview_for_text(tmp_path, "How does Ham work?", already_answered=True)
    item = result.items[0]
    assert item.already_answered is True
    assert "telegram_inbound_already_answered" in item.reasons
    assert item.reply_candidate_text == ""


def test_unsupported_media_requires_human(tmp_path: Path) -> None:
    result = _preview_for_text(tmp_path, "attachment:/tmp/private.png")
    item = result.items[0]
    assert item.classification == "requires_human_operator"
    assert "telegram_inbound_unsupported_media" in item.reasons
    assert item.reply_candidate_text == ""


def test_max_three_candidates(tmp_path: Path) -> None:
    transcript = tmp_path / "telegram.jsonl"
    for i in range(4):
        _write_row(
            transcript,
            text=f"Thanks, this is awesome {i}",
            chat_id=f"-100987654321{i}",
            user_id=f"12345678{i}",
            session_id=f"session-{i}",
        )
    result = preview_telegram_reactive_replies_once(transcript_paths=[transcript])
    assert result.reply_candidate_count == 3
    assert sum(1 for item in result.items if item.reply_candidate_text) == 3
    assert "telegram_reactive_candidate_cap_reached" in result.items[-1].reasons


def test_no_send_adapter_delivery_log_or_telegram_api_call(tmp_path: Path) -> None:
    transcript = tmp_path / "telegram.jsonl"
    _write_row(transcript, text="How does Ham work?")
    before = transcript.read_text(encoding="utf-8")
    with patch("urllib.request.urlopen", side_effect=AssertionError("telegram api should not be called")):
        result = preview_telegram_reactive_replies_once(transcript_paths=[transcript])
    assert result.reply_candidate_count == 1
    assert transcript.read_text(encoding="utf-8") == before
    assert (tmp_path / "social_delivery_log.jsonl").exists() is False


def test_no_raw_ids_returned(tmp_path: Path) -> None:
    result = _preview_for_text(tmp_path, "How does Ham work?")
    text = result.model_dump_json()
    assert "-1009876543210" not in text
    assert "123456789" not in text
    assert "telegram-session-1" not in text


def test_proposal_digest_changes_when_persona_digest_changes(tmp_path: Path) -> None:
    transcript = tmp_path / "telegram.jsonl"
    _write_row(transcript, text="How does Ham work?")
    first = preview_telegram_reactive_replies_once(transcript_paths=[transcript])
    with patch("src.ham.social_telegram_reactive.persona_digest", return_value="d" * 64):
        changed = preview_telegram_reactive_replies_once(transcript_paths=[transcript])
    assert first.persona_digest != changed.persona_digest
    assert first.items[0].proposal_digest != changed.items[0].proposal_digest
