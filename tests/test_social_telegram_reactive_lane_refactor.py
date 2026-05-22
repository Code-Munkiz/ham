"""Tests for M3 F13 reactive-lane transcript-iterable refactor.

Covers VAL-M15-M3-REACTIVE-001 through VAL-M15-M3-REACTIVE-005:

- 001: ``discover_telegram_inbound_once`` accepts a ``transcripts`` iterable.
- 002: Existing JSONL fixture tests remain green (verified by sibling test files).
- 003: Emits ``telegram_inbound_source_not_configured`` when neither source is set.
- 004: Path-only mode preserves ``hermes_transcript_source_unavailable`` when file missing.
- 005: M14 reactive-lane fixture tests still green when only file path is configured
      (verified by running sibling test files; this file adds the runner-level check).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from src.ham.social_telegram_inbound import discover_telegram_inbound_once
from src.ham.social_telegram_reactive import preview_telegram_reactive_replies_once
from src.ham.social_telegram_reactive_runner import (
    TelegramReactiveRunConfig,
    run_telegram_reactive_once,
)
from src.ham.social_telegram_transcript_store import (
    TelegramTranscriptStoreProtocol,
    set_telegram_transcript_store_for_tests,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _telegram_rows(*texts: str, chat_id: str = "-1009876543210", author_id: str = "123456789") -> list[dict[str, Any]]:
    """Build minimal Telegram transcript rows (matching M1 JSONL contract)."""
    return [
        {
            "source": "telegram",
            "role": "user",
            "text": text,
            "chat_id": int(chat_id),
            "author_id": int(author_id),
            "message_id": idx + 1,
            "created_at": f"2026-05-01T00:0{idx}:00Z",
        }
        for idx, text in enumerate(texts)
    ]


class InMemoryTranscriptStore:
    """Minimal in-memory transcript store satisfying TelegramTranscriptStoreProtocol."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows: list[dict[str, Any]] = rows or []

    def append_row(self, row: dict[str, Any]) -> None:
        self._rows.append(row)

    def iter_rows(self) -> Iterator[dict[str, Any]]:
        return iter(list(self._rows))


assert isinstance(InMemoryTranscriptStore(), TelegramTranscriptStoreProtocol)


# ---------------------------------------------------------------------------
# VAL-M15-M3-REACTIVE-001: discover_telegram_inbound_once accepts transcripts iterable
# ---------------------------------------------------------------------------


def test_discover_from_transcript_iterable_two_rows() -> None:
    """VAL-M15-M3-REACTIVE-001: iterable of two rows → items length 2, redactions applied."""
    rows = _telegram_rows("How does Ham work?", "Thanks, this is awesome")
    result = discover_telegram_inbound_once(transcripts=iter(rows))

    assert result.status == "completed"
    assert result.inbound_count == 2
    assert len(result.items) == 2

    serialised = result.model_dump_json()
    # Raw IDs must be redacted
    assert "-1009876543210" not in serialised
    assert "123456789" not in serialised

    # Each item must carry a masked ref
    for item in result.items:
        assert item.chat_ref.startswith("configured:")
        assert item.author_ref.startswith("configured:")


def test_discover_from_transcript_iterable_repliable_flag() -> None:
    """VAL-M15-M3-REACTIVE-001: rows with chat_id + author_id → repliable=True."""
    rows = _telegram_rows("Hello")
    result = discover_telegram_inbound_once(transcripts=iter(rows))

    assert result.status == "completed"
    assert len(result.items) == 1
    assert result.items[0].repliable is True


def test_discover_from_transcript_iterable_respects_max_items() -> None:
    """VAL-M15-M3-REACTIVE-001: cap is respected when iterable exceeds MAX_INBOUND_ITEMS."""
    rows = _telegram_rows(*[f"msg {i}" for i in range(25)])
    result = discover_telegram_inbound_once(transcripts=iter(rows), max_items=5)

    assert result.inbound_count == 5
    assert len(result.items) == 5


def test_discover_from_transcript_iterable_empty_yields_source_unavailable() -> None:
    """VAL-M15-M3-REACTIVE-001: empty iterable → hermes_transcript_source_unavailable.

    The iterable represents a configured source that has no rows yet.
    """
    result = discover_telegram_inbound_once(transcripts=iter([]))

    assert result.status == "blocked"
    assert "hermes_transcript_source_unavailable" in result.reasons


def test_discover_from_transcript_iterable_filters_non_telegram_rows() -> None:
    """VAL-M15-M3-REACTIVE-001: non-telegram rows are filtered; status still completed."""
    rows = [
        {"source": "discord", "role": "user", "text": "discord msg", "chat_id": 1, "author_id": 2, "message_id": 1, "created_at": "2026-01-01T00:00:00Z"},
        {"source": "telegram", "role": "user", "text": "telegram msg", "chat_id": 1, "author_id": 2, "message_id": 2, "created_at": "2026-01-01T00:00:01Z"},
    ]
    result = discover_telegram_inbound_once(transcripts=iter(rows))

    assert result.status == "completed"
    assert result.inbound_count == 1
    assert result.items[0].text == "telegram msg"


# ---------------------------------------------------------------------------
# VAL-M15-M3-REACTIVE-003: telegram_inbound_source_not_configured
# ---------------------------------------------------------------------------


def test_emits_inbound_source_not_configured_when_neither_source_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """VAL-M15-M3-REACTIVE-003: all transcript env vars unset and no transcripts → not_configured.

    Also satisfies VAL-M15-M2-READINESS-REACTIVE-INBOUND-MISSING-004.
    """
    for var in (
        "HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH",
        "HAM_TELEGRAM_TRANSCRIPT_BACKEND",
        "HAM_HERMES_HOME",
        "HERMES_HOME",
    ):
        monkeypatch.delenv(var, raising=False)

    result = discover_telegram_inbound_once()

    assert result.status == "blocked"
    assert "telegram_inbound_source_not_configured" in result.reasons


def test_runner_emits_inbound_source_not_configured_when_neither_source_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """VAL-M15-M3-REACTIVE-003 via runner: run_telegram_reactive_once propagates the blocked reason."""
    for var in (
        "HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH",
        "HAM_TELEGRAM_TRANSCRIPT_BACKEND",
        "HAM_HERMES_HOME",
        "HERMES_HOME",
    ):
        monkeypatch.delenv(var, raising=False)

    result = run_telegram_reactive_once(TelegramReactiveRunConfig())

    assert result.status in ("blocked", "completed")
    assert "telegram_inbound_source_not_configured" in result.reasons


# ---------------------------------------------------------------------------
# VAL-M15-M3-REACTIVE-004: hermes_transcript_source_unavailable for missing file
# ---------------------------------------------------------------------------


def test_path_only_mode_emits_source_unavailable_for_missing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M3-REACTIVE-004: file path configured but absent → hermes_transcript_source_unavailable."""
    missing = tmp_path / "no_such_file.jsonl"
    monkeypatch.setenv("HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH", str(missing))
    # No transcript backend set
    monkeypatch.delenv("HAM_TELEGRAM_TRANSCRIPT_BACKEND", raising=False)

    result = discover_telegram_inbound_once()

    assert result.status == "blocked"
    assert "hermes_transcript_source_unavailable" in result.reasons
    # Must NOT emit the "not configured" reason — a path IS configured
    assert "telegram_inbound_source_not_configured" not in result.reasons


def test_explicit_transcript_paths_missing_emits_source_unavailable(tmp_path: Path) -> None:
    """VAL-M15-M3-REACTIVE-004: explicit missing path → hermes_transcript_source_unavailable."""
    result = discover_telegram_inbound_once(transcript_paths=[tmp_path / "missing.jsonl"])

    assert result.status == "blocked"
    assert "hermes_transcript_source_unavailable" in result.reasons
    assert "telegram_inbound_source_not_configured" not in result.reasons


# ---------------------------------------------------------------------------
# VAL-M15-M3-REACTIVE-005: runner + preview pass-through with file path only
# ---------------------------------------------------------------------------


def test_runner_uses_file_path_when_explicit_transcript_paths_provided(tmp_path: Path) -> None:
    """VAL-M15-M3-REACTIVE-005: explicit transcript_paths → file-path mode unchanged."""
    transcript = tmp_path / "telegram.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "source": "telegram",
                "role": "user",
                "text": "How does Ham work?",
                "chat_id": "-1009876543210",
                "user_id": "123456789",
                "session_id": "s1",
                "message_id": "m1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_telegram_reactive_once(
        TelegramReactiveRunConfig(
            dry_run=True,
            transcript_paths=[transcript],
        )
    )

    assert result.status == "completed"
    assert result.proposal_digest is not None


def test_preview_uses_transcript_iterable_when_provided(tmp_path: Path) -> None:
    """VAL-M15-M3-REACTIVE-005: preview with transcripts iterable works end-to-end."""
    rows = _telegram_rows("How does Ham work?")
    result = preview_telegram_reactive_replies_once(transcripts=iter(rows))

    assert result.status == "completed"
    assert result.reply_candidate_count == 1
    assert result.items[0].classification == "genuine_question"
    assert result.items[0].reply_candidate_text


# ---------------------------------------------------------------------------
# Runner: transcript_store injectable wires iter_rows to discover
# ---------------------------------------------------------------------------


def test_runner_with_injectable_transcript_store(tmp_path: Path) -> None:
    """Runner's transcript_store kwarg wires store.iter_rows() to discover."""
    rows = _telegram_rows("How does Ham work?")
    store = InMemoryTranscriptStore(rows)

    result = run_telegram_reactive_once(
        TelegramReactiveRunConfig(dry_run=True),
        transcript_store=store,
    )

    assert result.status == "completed"
    assert result.inbound_count == 1
    assert result.proposal_digest is not None


def test_runner_injectable_store_overrides_file_path(tmp_path: Path) -> None:
    """Injected transcript_store takes priority over cfg.transcript_paths."""
    # transcript_paths points to a file that doesn't exist — if used, would block
    missing = tmp_path / "no_such.jsonl"
    rows = _telegram_rows("How does Ham work?")
    store = InMemoryTranscriptStore(rows)

    result = run_telegram_reactive_once(
        TelegramReactiveRunConfig(dry_run=True, transcript_paths=[missing]),
        transcript_store=store,
    )

    # Store has data → should complete, not block on missing file
    assert result.status == "completed"
    assert result.inbound_count == 1


def test_runner_auto_wires_firestore_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Runner auto-detects HAM_TELEGRAM_TRANSCRIPT_BACKEND=firestore and uses store."""
    rows = _telegram_rows("How does Ham work?")
    store = InMemoryTranscriptStore(rows)

    monkeypatch.setenv("HAM_TELEGRAM_TRANSCRIPT_BACKEND", "firestore")
    set_telegram_transcript_store_for_tests(store)
    try:
        result = run_telegram_reactive_once(TelegramReactiveRunConfig(dry_run=True))
    finally:
        set_telegram_transcript_store_for_tests(None)
        monkeypatch.delenv("HAM_TELEGRAM_TRANSCRIPT_BACKEND", raising=False)

    assert result.status == "completed"
    assert result.inbound_count == 1
    assert result.proposal_digest is not None


def test_runner_firestore_backend_empty_store_emits_source_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """When Firestore backend configured but store is empty → hermes_transcript_source_unavailable."""
    store = InMemoryTranscriptStore([])

    monkeypatch.setenv("HAM_TELEGRAM_TRANSCRIPT_BACKEND", "firestore")
    set_telegram_transcript_store_for_tests(store)
    try:
        result = run_telegram_reactive_once(TelegramReactiveRunConfig(dry_run=True))
    finally:
        set_telegram_transcript_store_for_tests(None)
        monkeypatch.delenv("HAM_TELEGRAM_TRANSCRIPT_BACKEND", raising=False)

    assert result.status == "blocked"
    assert "hermes_transcript_source_unavailable" in result.reasons


def test_no_safe_candidate_emits_reactive_no_safe_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    """When rows exist but no safe candidate: emits telegram_reactive_no_safe_candidate."""
    # "banana sandwich" is off_topic → policy blocked → no safe candidate
    rows = _telegram_rows("banana sandwich weather")
    store = InMemoryTranscriptStore(rows)

    monkeypatch.setenv("HAM_TELEGRAM_TRANSCRIPT_BACKEND", "firestore")
    set_telegram_transcript_store_for_tests(store)
    try:
        result = run_telegram_reactive_once(TelegramReactiveRunConfig(dry_run=True))
    finally:
        set_telegram_transcript_store_for_tests(None)
        monkeypatch.delenv("HAM_TELEGRAM_TRANSCRIPT_BACKEND", raising=False)

    assert "telegram_reactive_no_safe_candidate" in result.reasons
