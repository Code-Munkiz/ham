from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.ham.social_telegram_inbound import discover_telegram_inbound_once


def _write_row(path: Path, **fields: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(fields, sort_keys=True) + "\n")


def test_reads_temp_hermes_session_fixture_and_bounds_user_messages(tmp_path: Path) -> None:
    transcript = tmp_path / "telegram.jsonl"
    raw_chat = "-1009876543210"
    raw_author = "123456789"
    raw_session = "telegram-session-1"
    _write_row(
        transcript,
        source="telegram",
        role="user",
        text="hello from telegram" + ("x" * 600),
        chat_id=raw_chat,
        user_id=raw_author,
        session_id=raw_session,
        created_at="2026-05-01T00:00:00Z",
        chat_type="group",
    )

    result = discover_telegram_inbound_once(transcript_paths=[transcript])

    assert result.status == "completed"
    assert result.inbound_count == 1
    item = result.items[0]
    assert len(item.text) == 500
    assert item.author_ref.startswith("configured:")
    assert item.chat_ref.startswith("configured:")
    assert item.session_ref.startswith("configured:")
    assert item.created_at == "2026-05-01T00:00:00Z"
    assert item.chat_type == "group"
    assert item.repliable is True
    text = result.model_dump_json()
    for raw in (raw_chat, raw_author, raw_session):
        assert raw not in text


def test_excludes_assistant_system_and_non_telegram_messages(tmp_path: Path) -> None:
    transcript = tmp_path / "telegram.jsonl"
    _write_row(transcript, source="telegram", role="assistant", text="assistant reply", chat_id="c1", user_id="u1")
    _write_row(transcript, source="telegram", role="system", text="system note", chat_id="c1", user_id="u1")
    _write_row(transcript, source="discord", role="user", text="discord msg", chat_id="c1", user_id="u1")
    _write_row(transcript, source="telegram", role="user", text="telegram user", chat_id="c1", user_id="u1")

    result = discover_telegram_inbound_once(transcript_paths=[transcript])

    assert result.status == "completed"
    assert result.inbound_count == 1
    assert result.items[0].text == "telegram user"


def test_missing_source_blocks_safely(tmp_path: Path) -> None:
    result = discover_telegram_inbound_once(transcript_paths=[tmp_path / "missing.jsonl"])

    assert result.status == "blocked"
    assert "hermes_transcript_source_unavailable" in result.reasons
    assert result.execution_allowed is False
    assert result.mutation_attempted is False


def test_malformed_transcript_warns_without_failure(tmp_path: Path) -> None:
    transcript = tmp_path / "telegram.jsonl"
    transcript.write_text("{bad json\n", encoding="utf-8")

    result = discover_telegram_inbound_once(transcript_paths=[transcript])

    assert result.status == "completed"
    assert result.inbound_count == 0
    assert "hermes_transcript_row_malformed" in result.warnings


def test_missing_reply_metadata_is_not_repliable(tmp_path: Path) -> None:
    transcript = tmp_path / "telegram.jsonl"
    _write_row(transcript, source="telegram", role="user", text="metadata missing", session_id="s1")

    result = discover_telegram_inbound_once(transcript_paths=[transcript])

    assert result.inbound_count == 1
    item = result.items[0]
    assert item.repliable is False
    assert "telegram_reply_target_unavailable" in item.reasons


def test_no_telegram_api_calls_or_state_mutation(tmp_path: Path) -> None:
    transcript = tmp_path / "telegram.jsonl"
    _write_row(transcript, source="telegram", role="user", text="hello", chat_id="c1", user_id="u1")
    before = transcript.read_text(encoding="utf-8")

    with patch("urllib.request.urlopen", side_effect=AssertionError("telegram api should not be called")):
        result = discover_telegram_inbound_once(transcript_paths=[transcript])

    assert result.status == "completed"
    assert transcript.read_text(encoding="utf-8") == before


def test_max_items_is_bounded(tmp_path: Path) -> None:
    transcript = tmp_path / "telegram.jsonl"
    for i in range(25):
        _write_row(transcript, source="telegram", role="user", text=f"message {i}", chat_id=f"c{i}", user_id=f"u{i}")

    result = discover_telegram_inbound_once(transcript_paths=[transcript], max_items=50)

    assert result.inbound_count == 20
    assert len(result.items) == 20
