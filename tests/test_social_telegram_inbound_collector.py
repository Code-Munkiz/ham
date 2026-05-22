"""Tests for src/ham/social_telegram_inbound_collector.py

Covers all 13 collector assertions:
  VAL-M15-M3-COLLECTOR-001 through VAL-M15-M3-COLLECTOR-013
"""

from __future__ import annotations

import datetime
from collections.abc import Iterator
from typing import Any

import pytest

from src.ham.social_telegram_inbound_collector import (
    GetUpdatesTransport,
    run_inbound_poll_once,
)

# ---------------------------------------------------------------------------
# In-memory store helpers
# ---------------------------------------------------------------------------


class InMemoryOffsetStore:
    """Simple in-memory offset store for tests."""

    def __init__(self, initial: int | None = None) -> None:
        self._offset = initial
        self.write_calls: list[tuple[str, int]] = []

    def read_offset(self, bot_digest: str) -> int | None:
        return self._offset

    def write_offset(self, bot_digest: str, update_offset: int) -> None:
        self.write_calls.append((bot_digest, update_offset))
        self._offset = update_offset


class InMemoryTranscriptStore:
    """Simple in-memory transcript store for tests."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def append_row(self, row: dict[str, Any]) -> None:
        self.rows.append(dict(row))

    def iter_rows(self) -> Iterator[dict[str, Any]]:
        return iter(self.rows)


class FailingOnNthAppendTranscriptStore:
    """Transcript store that raises on the Nth append (1-indexed)."""

    def __init__(self, fail_on: int) -> None:
        self.rows: list[dict[str, Any]] = []
        self._fail_on = fail_on
        self._count = 0

    def append_row(self, row: dict[str, Any]) -> None:
        self._count += 1
        if self._count >= self._fail_on:
            raise RuntimeError(f"Simulated append failure on call #{self._count}")
        self.rows.append(dict(row))

    def iter_rows(self) -> Iterator[dict[str, Any]]:
        return iter(self.rows)


class SpyOrderTranscriptStore:
    """Records append order so we can verify append-before-offset-commit."""

    def __init__(self, ops: list[tuple[str, Any]]) -> None:
        self._ops = ops
        self.rows: list[dict[str, Any]] = []

    def append_row(self, row: dict[str, Any]) -> None:
        self._ops.append(("append", dict(row)))
        self.rows.append(dict(row))

    def iter_rows(self) -> Iterator[dict[str, Any]]:
        return iter(self.rows)


class SpyOrderOffsetStore:
    """Records write_offset calls; compatible with InMemoryOffsetStore."""

    def __init__(self, ops: list[tuple[str, Any]], initial: int | None = None) -> None:
        self._ops = ops
        self._offset = initial

    def read_offset(self, bot_digest: str) -> int | None:
        return self._offset

    def write_offset(self, bot_digest: str, update_offset: int) -> None:
        self._ops.append(("write_offset", update_offset))
        self._offset = update_offset


# ---------------------------------------------------------------------------
# Transport helpers
# ---------------------------------------------------------------------------


def _make_update(
    update_id: int = 1,
    message_id: int = 100,
    chat_id: int = -100100100,
    author_id: int = 99887766,
    text: str = "Hello from Telegram",
    date: int = 1700000000,
    chat_type: str = "supergroup",
    **extra_message_fields: Any,
) -> dict[str, Any]:
    """Build a minimal Telegram getUpdates update dict."""
    message: dict[str, Any] = {
        "message_id": message_id,
        "from": {"id": author_id, "first_name": "Test", "username": "testuser"},
        "chat": {"id": chat_id, "type": chat_type, "title": "Test Group"},
        "date": date,
        "text": text,
    }
    message.update(extra_message_fields)
    return {"update_id": update_id, "message": message}


class MockGetUpdatesTransport:
    """Hand-rolled mock transport — no inheritance, no httpx."""

    def __init__(self, updates: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._updates: list[dict[str, Any]] = updates or []

    def get_updates(
        self,
        *,
        bot_token: str,
        offset: int,
        limit: int,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "bot_token": bot_token,
                "offset": offset,
                "limit": limit,
                "timeout_seconds": timeout_seconds,
            }
        )
        return {"ok": True, "result": list(self._updates)}


class RaisingTransport:
    """Transport that raises on call (used to verify it was never called)."""

    def get_updates(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("Transport should not have been called")


# ---------------------------------------------------------------------------
# Shared fixture for a ready environment
# ---------------------------------------------------------------------------

_SYNTHETIC_TOKEN = "synthetic-bot-token-XYZ"


@pytest.fixture()
def ready_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _SYNTHETIC_TOKEN)


# ===========================================================================
# VAL-M15-M3-COLLECTOR-001
# Collector module exists and exports a callable `run_inbound_poll_once`.
# ===========================================================================


def test_collector_module_exports_run_inbound_poll_once() -> None:
    """VAL-M15-M3-COLLECTOR-001: module exports the public callable."""
    from src.ham import social_telegram_inbound_collector as m

    assert callable(getattr(m, "run_inbound_poll_once", None)), (
        "social_telegram_inbound_collector must export 'run_inbound_poll_once'"
    )


# ===========================================================================
# VAL-M15-M3-COLLECTOR-002
# Transport is a Protocol; a hand-rolled mock works without httpx.
# ===========================================================================


def test_mock_transport_satisfies_protocol() -> None:
    """VAL-M15-M3-COLLECTOR-002: MockGetUpdatesTransport satisfies GetUpdatesTransport."""
    transport = MockGetUpdatesTransport()
    assert isinstance(transport, GetUpdatesTransport), (
        "MockGetUpdatesTransport must satisfy GetUpdatesTransport Protocol"
    )


def test_mock_transport_bypasses_httpx(ready_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """VAL-M15-M3-COLLECTOR-002: with mock transport, httpx.Client is never entered."""
    import httpx

    # Patch httpx.Client.__enter__ to raise; if the mock transport correctly
    # bypasses httpx, the test still passes.
    monkeypatch.setattr(
        httpx.Client,
        "__enter__",
        lambda self: (_ for _ in ()).throw(
            AssertionError("httpx must not be called with mock transport")
        ),
    )  # type: ignore[attr-defined]

    transport = MockGetUpdatesTransport(updates=[])
    result = run_inbound_poll_once(
        transport=transport,
        offset_store=InMemoryOffsetStore(),
        transcript_store=InMemoryTranscriptStore(),
    )
    assert result.status == "ok"
    assert result.polled_count == 0


# ===========================================================================
# VAL-M15-M3-COLLECTOR-003
# Offset is read from the M1 offset store before the call.
# ===========================================================================


def test_offset_is_read_from_offset_store_before_call(ready_env: None) -> None:
    """VAL-M15-M3-COLLECTOR-003: pre-seeded offset is passed to transport."""
    offset_store = InMemoryOffsetStore(initial=42)
    transport = MockGetUpdatesTransport(updates=[])

    run_inbound_poll_once(
        transport=transport,
        offset_store=offset_store,
        transcript_store=InMemoryTranscriptStore(),
    )

    assert len(transport.calls) == 1
    assert transport.calls[0]["offset"] == 42, (
        "Collector must pass the stored offset to the transport"
    )


def test_absent_offset_defaults_to_zero(ready_env: None) -> None:
    """VAL-M15-M3-COLLECTOR-003: when offset store is empty, 0 is sent."""
    offset_store = InMemoryOffsetStore(initial=None)
    transport = MockGetUpdatesTransport(updates=[])

    run_inbound_poll_once(
        transport=transport,
        offset_store=offset_store,
        transcript_store=InMemoryTranscriptStore(),
    )

    assert transport.calls[0]["offset"] == 0


# ===========================================================================
# VAL-M15-M3-COLLECTOR-004
# Redacted transcript rows written via the M1 transcript store.
# ===========================================================================


def test_rows_written_to_transcript_store(ready_env: None) -> None:
    """VAL-M15-M3-COLLECTOR-004: updates are normalized and written to transcript store."""
    updates = [_make_update(update_id=1, message_id=10, chat_id=-100100100, author_id=999888)]
    transcript_store = InMemoryTranscriptStore()

    run_inbound_poll_once(
        transport=MockGetUpdatesTransport(updates=updates),
        offset_store=InMemoryOffsetStore(),
        transcript_store=transcript_store,
    )

    assert len(transcript_store.rows) == 1
    row = transcript_store.rows[0]
    assert row["source"] == "telegram"
    assert row["role"] == "user"
    assert "text" in row


# ===========================================================================
# VAL-M15-M3-COLLECTOR-005
# Offset advances to max(update_id) + 1; append precedes offset commit.
# ===========================================================================


def test_offset_advances_to_max_update_id_plus_one(ready_env: None) -> None:
    """VAL-M15-M3-COLLECTOR-005: new offset = max(update_id) + 1."""
    updates = [
        _make_update(update_id=10),
        _make_update(update_id=11, message_id=101),
        _make_update(update_id=12, message_id=102),
    ]
    offset_store = InMemoryOffsetStore(initial=0)

    result = run_inbound_poll_once(
        transport=MockGetUpdatesTransport(updates=updates),
        offset_store=offset_store,
        transcript_store=InMemoryTranscriptStore(),
    )

    assert offset_store._offset == 13, "Offset must be max(update_id) + 1 = 13"
    assert result.new_offset == 13


def test_append_happens_before_offset_commit(ready_env: None) -> None:
    """VAL-M15-M3-COLLECTOR-005: append called before write_offset."""
    ops: list[tuple[str, Any]] = []
    transcript_store = SpyOrderTranscriptStore(ops)
    offset_store = SpyOrderOffsetStore(ops, initial=0)

    updates = [_make_update(update_id=5)]
    run_inbound_poll_once(
        transport=MockGetUpdatesTransport(updates=updates),
        offset_store=offset_store,
        transcript_store=transcript_store,
    )

    # All append ops must come before the write_offset op.
    append_indices = [i for i, (op, _) in enumerate(ops) if op == "append"]
    write_offset_indices = [i for i, (op, _) in enumerate(ops) if op == "write_offset"]
    assert append_indices, "Expected at least one append"
    assert write_offset_indices, "Expected a write_offset"
    assert max(append_indices) < min(write_offset_indices), "All appends must precede write_offset"


# ===========================================================================
# VAL-M15-M3-COLLECTOR-006
# Re-invocation with the same offset is a no-op.
# ===========================================================================


def test_empty_result_is_a_noop(ready_env: None) -> None:
    """VAL-M15-M3-COLLECTOR-006: empty result → no rows written, offset unchanged."""
    offset_store = InMemoryOffsetStore(initial=7)
    transcript_store = InMemoryTranscriptStore()

    # First call: no updates
    result1 = run_inbound_poll_once(
        transport=MockGetUpdatesTransport(updates=[]),
        offset_store=offset_store,
        transcript_store=transcript_store,
    )
    assert result1.polled_count == 0
    assert result1.new_offset is None
    assert offset_store._offset == 7, "Offset must remain unchanged when no updates"
    assert len(transcript_store.rows) == 0

    # Second call: still no updates
    result2 = run_inbound_poll_once(
        transport=MockGetUpdatesTransport(updates=[]),
        offset_store=offset_store,
        transcript_store=transcript_store,
    )
    assert result2.polled_count == 0
    assert offset_store._offset == 7, "Offset must remain unchanged on second no-op call"


# ===========================================================================
# VAL-M15-M3-COLLECTOR-007
# Batch size is hard-capped at 100 updates per call.
# ===========================================================================


def test_transport_receives_limit_of_100(ready_env: None) -> None:
    """VAL-M15-M3-COLLECTOR-007: transport is called with limit=100."""
    transport = MockGetUpdatesTransport(updates=[])
    run_inbound_poll_once(
        transport=transport,
        offset_store=InMemoryOffsetStore(),
        transcript_store=InMemoryTranscriptStore(),
    )
    assert transport.calls[0]["limit"] == 100


def test_batch_capped_when_transport_returns_more_than_100(ready_env: None) -> None:
    """VAL-M15-M3-COLLECTOR-007: when transport returns 150 updates, max 100 rows persisted."""
    # Create 150 updates with unique update_ids
    updates = [_make_update(update_id=i, message_id=i + 1000) for i in range(1, 151)]
    transcript_store = InMemoryTranscriptStore()

    run_inbound_poll_once(
        transport=MockGetUpdatesTransport(updates=updates),
        offset_store=InMemoryOffsetStore(),
        transcript_store=transcript_store,
    )

    assert len(transcript_store.rows) <= 100, (
        "Collector must never persist more than 100 rows per call"
    )


# ===========================================================================
# VAL-M15-M3-COLLECTOR-008
# timeout=0 on Telegram request; transport-level timeout ≤ 6 s.
# ===========================================================================


def test_transport_receives_timeout_seconds_at_most_6(ready_env: None) -> None:
    """VAL-M15-M3-COLLECTOR-008: transport receives timeout_seconds <= 6."""
    transport = MockGetUpdatesTransport(updates=[])
    run_inbound_poll_once(
        transport=transport,
        offset_store=InMemoryOffsetStore(),
        transcript_store=InMemoryTranscriptStore(),
    )
    assert transport.calls[0]["timeout_seconds"] <= 6, "Transport-level timeout must be ≤ 6 s"


def test_collector_module_has_no_timeout_greater_than_6() -> None:
    """VAL-M15-M3-COLLECTOR-008: static check – no hard-coded transport timeout > 6."""
    import ast
    from pathlib import Path

    source = (
        Path(__file__).parent.parent / "src" / "ham" / "social_telegram_inbound_collector.py"
    ).read_text(encoding="utf-8")
    # Ensure the Telegram timeout param is 0 (no long-poll).
    assert "_GETUPDATE_TELEGRAM_TIMEOUT = 0" in source, (
        "Telegram timeout query parameter must be hardcoded to 0"
    )
    # Parse and check all numeric literals that look like a timeout value > 6.
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, float)):
                val = node.value.value
                for target in node.targets:
                    if isinstance(target, ast.Name) and "TIMEOUT" in target.id.upper():
                        # The transport read timeout must be ≤ 6.
                        if "TRANSPORT" in target.id.upper() or "READ" in target.id.upper():
                            assert val <= 6, (
                                f"{target.id} = {val} exceeds the 6 s transport timeout limit"
                            )


# ===========================================================================
# VAL-M15-M3-COLLECTOR-009
# Collector refuses to run without TELEGRAM_BOT_TOKEN.
# ===========================================================================


def test_refuses_to_run_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """VAL-M15-M3-COLLECTOR-009: absent token → blocked result, no transport/store call."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    offset_store = InMemoryOffsetStore(initial=0)
    transcript_store = InMemoryTranscriptStore()
    transport = RaisingTransport()

    result = run_inbound_poll_once(
        transport=transport,  # type: ignore[arg-type]
        offset_store=offset_store,
        transcript_store=transcript_store,
    )

    assert result.status == "blocked"
    assert "telegram_bot_token_missing" in result.reasons
    assert offset_store._offset == 0, "Offset must be unchanged"
    assert len(transcript_store.rows) == 0, "No rows must be written"


def test_refuses_to_run_with_empty_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """VAL-M15-M3-COLLECTOR-009: empty token string → blocked result."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "   ")

    result = run_inbound_poll_once(
        transport=RaisingTransport(),  # type: ignore[arg-type]
        offset_store=InMemoryOffsetStore(),
        transcript_store=InMemoryTranscriptStore(),
    )

    assert result.status == "blocked"
    assert "telegram_bot_token_missing" in result.reasons


# ===========================================================================
# VAL-M15-M3-COLLECTOR-010
# Token never appears in rows or logs; chat_id/author_id preserved as integers.
# ===========================================================================


def test_token_not_in_transcript_row_or_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-M15-M3-COLLECTOR-010: synthetic token never appears in any persisted row."""
    import json

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _SYNTHETIC_TOKEN)

    updates = [_make_update(update_id=1, text="Hello world")]
    transcript_store = InMemoryTranscriptStore()

    result = run_inbound_poll_once(
        transport=MockGetUpdatesTransport(updates=updates),
        offset_store=InMemoryOffsetStore(),
        transcript_store=transcript_store,
    )

    result_json = result.model_dump_json()
    assert _SYNTHETIC_TOKEN not in result_json, "Token must not appear in result"

    for row in transcript_store.rows:
        row_json = json.dumps(row)
        assert _SYNTHETIC_TOKEN not in row_json, (
            f"Token must not appear in persisted row: {row_json}"
        )


def test_chat_id_and_author_id_are_integers(ready_env: None) -> None:
    """VAL-M15-M3-COLLECTOR-010: chat_id and author_id must be integers in the row."""
    updates = [_make_update(update_id=1, chat_id=-100100100, author_id=99887766)]
    transcript_store = InMemoryTranscriptStore()

    run_inbound_poll_once(
        transport=MockGetUpdatesTransport(updates=updates),
        offset_store=InMemoryOffsetStore(),
        transcript_store=transcript_store,
    )

    assert len(transcript_store.rows) == 1
    row = transcript_store.rows[0]
    assert isinstance(row["chat_id"], int), "chat_id must be an integer"
    assert isinstance(row["author_id"], int), "author_id must be an integer"
    assert row["chat_id"] == -100100100
    assert row["author_id"] == 99887766


# ===========================================================================
# VAL-M15-M3-COLLECTOR-011
# Only allow-listed fields on transcript rows.
# ===========================================================================

_ALLOWED_FIELDS = frozenset(
    {
        "source",
        "role",
        "text",
        "chat_id",
        "author_id",
        "message_id",
        "created_at",
        "chat_type",
        "already_answered",
    }
)


def test_only_allowlisted_fields_in_row(ready_env: None) -> None:
    """VAL-M15-M3-COLLECTOR-011: rows contain only the allow-listed fields."""
    # Inject extra fields that should not appear in the row.
    updates = [
        _make_update(
            update_id=1,
            entities=[{"type": "bold", "offset": 0, "length": 5}],
            reply_markup={"inline_keyboard": []},
        )
    ]
    transcript_store = InMemoryTranscriptStore()

    run_inbound_poll_once(
        transport=MockGetUpdatesTransport(updates=updates),
        offset_store=InMemoryOffsetStore(),
        transcript_store=transcript_store,
    )

    assert len(transcript_store.rows) == 1
    row_keys = set(transcript_store.rows[0].keys())
    assert row_keys.issubset(_ALLOWED_FIELDS), (
        f"Unexpected fields in row: {row_keys - _ALLOWED_FIELDS}"
    )


# ===========================================================================
# VAL-M15-M3-COLLECTOR-012
# Text is redacted via the canonical pipeline; ≥12-digit numbers stripped.
# ===========================================================================


def test_numeric_id_stripped_from_text(ready_env: None) -> None:
    """VAL-M15-M3-COLLECTOR-012: 12-digit number in text is stripped."""
    twelve_digit_number = "123456789012"
    updates = [_make_update(update_id=1, text=f"Ref {twelve_digit_number} end")]
    transcript_store = InMemoryTranscriptStore()

    run_inbound_poll_once(
        transport=MockGetUpdatesTransport(updates=updates),
        offset_store=InMemoryOffsetStore(),
        transcript_store=transcript_store,
    )

    assert len(transcript_store.rows) == 1
    assert twelve_digit_number not in transcript_store.rows[0]["text"], (
        "12-digit number must be stripped from persisted text"
    )


def test_text_redaction_via_canonical_pipeline(ready_env: None) -> None:
    """VAL-M15-M3-COLLECTOR-012: text passes through redact_text before persisting."""
    # A bearer token in the message text should be redacted.
    updates = [_make_update(update_id=1, text="Bearer ABCDEFGHIJKLMNOPQRSTUVWXYZ12345678 here")]
    transcript_store = InMemoryTranscriptStore()

    run_inbound_poll_once(
        transport=MockGetUpdatesTransport(updates=updates),
        offset_store=InMemoryOffsetStore(),
        transcript_store=transcript_store,
    )

    assert len(transcript_store.rows) == 1
    text = transcript_store.rows[0]["text"]
    # The raw bearer token must not appear verbatim.
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ12345678" not in text, "Bearer token in text must be redacted"


# ===========================================================================
# VAL-M15-M3-COLLECTOR-013
# Crash safety: failure mid-batch leaves offset unchanged.
# ===========================================================================


def test_transcript_store_failure_leaves_offset_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-M15-M3-COLLECTOR-013: mid-batch failure → offset not committed."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _SYNTHETIC_TOKEN)

    updates = [
        _make_update(update_id=10, message_id=100),
        _make_update(update_id=11, message_id=101),
        _make_update(update_id=12, message_id=102),
        _make_update(update_id=13, message_id=103),
        _make_update(update_id=14, message_id=104),
    ]
    offset_store = InMemoryOffsetStore(initial=5)
    # Fail on the 3rd append
    failing_store = FailingOnNthAppendTranscriptStore(fail_on=3)

    with pytest.raises(RuntimeError, match="Simulated append failure"):
        run_inbound_poll_once(
            transport=MockGetUpdatesTransport(updates=updates),
            offset_store=offset_store,
            transcript_store=failing_store,
        )

    # Offset must not have advanced
    assert offset_store._offset == 5, (
        "Offset must remain at pre-call value when a mid-batch append fails"
    )
    assert len(offset_store.write_calls) == 0, (
        "write_offset must not have been called after the transcript store raised"
    )


def test_subsequent_call_replays_all_rows_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-M15-M3-COLLECTOR-013: after failure, next call with non-raising store succeeds."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _SYNTHETIC_TOKEN)

    updates = [
        _make_update(update_id=10, message_id=100),
        _make_update(update_id=11, message_id=101),
        _make_update(update_id=12, message_id=102),
    ]
    offset_store = InMemoryOffsetStore(initial=10)

    # First call: fails mid-batch
    failing_store = FailingOnNthAppendTranscriptStore(fail_on=2)
    with pytest.raises(RuntimeError):
        run_inbound_poll_once(
            transport=MockGetUpdatesTransport(updates=updates),
            offset_store=offset_store,
            transcript_store=failing_store,
        )
    assert offset_store._offset == 10, "Offset must remain unchanged after failure"

    # Second call: non-raising store processes all rows
    good_store = InMemoryTranscriptStore()
    result = run_inbound_poll_once(
        transport=MockGetUpdatesTransport(updates=updates),
        offset_store=offset_store,
        transcript_store=good_store,
    )
    assert result.status == "ok"
    assert result.polled_count == 3
    assert offset_store._offset == 13, "Offset must advance to 13 after successful replay"


# ---------------------------------------------------------------------------
# Additional integration-style tests (cover edge cases)
# ---------------------------------------------------------------------------


def test_non_message_updates_are_skipped(ready_env: None) -> None:
    """Non-message updates (e.g. edited_message) are not written to transcript."""
    non_message_update = {"update_id": 1, "edited_message": {"message_id": 1, "text": "edit"}}
    transcript_store = InMemoryTranscriptStore()

    result = run_inbound_poll_once(
        transport=MockGetUpdatesTransport(updates=[non_message_update]),
        offset_store=InMemoryOffsetStore(),
        transcript_store=transcript_store,
    )

    # Update is still processed for offset purposes, but no row written.
    # (The update_id is still in the list, so offset should advance.)
    assert result.status == "ok"
    assert len(transcript_store.rows) == 0, "Non-message updates must not produce rows"


def test_created_at_is_iso8601(ready_env: None) -> None:
    """created_at field is an ISO-8601 string."""
    ts = int(datetime.datetime(2024, 1, 15, 12, 0, 0, tzinfo=datetime.UTC).timestamp())
    updates = [_make_update(update_id=1, date=ts)]
    transcript_store = InMemoryTranscriptStore()

    run_inbound_poll_once(
        transport=MockGetUpdatesTransport(updates=updates),
        offset_store=InMemoryOffsetStore(),
        transcript_store=transcript_store,
    )

    assert len(transcript_store.rows) == 1
    created_at = transcript_store.rows[0]["created_at"]
    assert created_at is not None
    # Must be parseable as ISO-8601
    parsed = datetime.datetime.fromisoformat(created_at)
    assert parsed.tzinfo is not None, "created_at must include timezone"
