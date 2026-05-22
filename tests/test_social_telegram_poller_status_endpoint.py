"""Tests for GET /api/social/providers/telegram/poller/status.

Covers:
- VAL-M15-M4-POLLERSTATUS-001: Endpoint exists at canonical path and returns
  200 with expected keys when stores are seeded.
- VAL-M15-M4-POLLERSTATUS-002: Reads only from M1 stores — no live Telegram
  (httpx / urllib) calls are issued.
- VAL-M15-M4-POLLERSTATUS-003: Response body contains no secrets, no chat ids,
  no 18+-digit numeric sequences.
- VAL-M15-M4-POLLERSTATUS-004: `last_error_code` is bounded (≤ 280 chars) and
  redacted (12-digit phone-number-like sequence is masked).
- VAL-M15-M4-POLLERSTATUS-005: Auth surface is consistent with adjacent Clerk-
  gated social GET routes.
- VAL-M15-CROSS-INBOUND-E2E-001 (partial — the E2E assertion requires live
  operator activation; this test verifies that `transcript_count_today` reflects
  seeded rows and `last_run_at` / `last_error_code` are null when absent).
"""

from __future__ import annotations

import datetime
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.ham.social_telegram_offset_store import (
    set_telegram_offset_store_for_tests,
)
from src.ham.social_telegram_transcript_store import (
    set_telegram_transcript_store_for_tests,
)

# ---------------------------------------------------------------------------
# In-memory fake stores for tests
# ---------------------------------------------------------------------------


class _FakeOffsetStore:
    """In-memory offset store that supports read_poller_metadata for tests."""

    def __init__(
        self,
        update_offset: int | None = None,
        last_run_at: str | None = None,
        last_error: str | None = None,
    ) -> None:
        self._update_offset = update_offset
        self._last_run_at = last_run_at
        self._last_error = last_error
        self._writes: list[tuple[str, int]] = []

    def read_offset(self, bot_digest: str) -> int | None:
        return self._update_offset

    def write_offset(self, bot_digest: str, update_offset: int) -> None:
        self._update_offset = update_offset
        self._writes.append((bot_digest, update_offset))

    def read_poller_metadata(self, bot_digest: str) -> dict[str, Any]:
        return {
            "last_run_at": self._last_run_at,
            "last_error": self._last_error,
        }


class _FakeTranscriptStore:
    """In-memory transcript store with configurable rows for tests."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows: list[dict[str, Any]] = rows or []

    def append_row(self, row: dict[str, Any]) -> None:
        self._rows.append(row)

    def iter_rows(self) -> Iterator[dict[str, Any]]:
        yield from self._rows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TODAY_ISO = datetime.datetime.now(datetime.UTC).date().isoformat()
_TODAY_DT = f"{_TODAY_ISO}T10:00:00+00:00"
_YESTERDAY_DT = (
    (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1))
    .replace(hour=10, minute=0, second=0, microsecond=0)
    .isoformat()
)


def _make_row(created_at: str = _TODAY_DT) -> dict[str, Any]:
    return {
        "source": "telegram",
        "role": "user",
        "text": "hello world",
        "chat_id": 111,
        "author_id": 222,
        "message_id": 333,
        "created_at": created_at,
    }


@pytest.fixture()
def _client() -> Iterator[TestClient]:
    """Fresh TestClient with Clerk auth disabled."""
    from src.api.server import app

    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# VAL-M15-M4-POLLERSTATUS-001: Endpoint exists at canonical path
# ---------------------------------------------------------------------------


class TestPollerStatusEndpointExists:
    """VAL-M15-M4-POLLERSTATUS-001"""

    def test_endpoint_returns_200_with_expected_keys(self, _client: TestClient) -> None:
        """GET /api/social/providers/telegram/poller/status returns 200 with required keys."""
        fake_offset = _FakeOffsetStore(update_offset=42, last_run_at=_TODAY_DT)
        fake_transcript = _FakeTranscriptStore(rows=[_make_row()])

        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        try:
            resp = _client.get("/api/social/providers/telegram/poller/status")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert "last_run_at" in body
            assert "last_offset" in body
            assert "transcript_count_today" in body
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)

    def test_last_offset_reflects_stored_offset(self, _client: TestClient) -> None:
        """last_offset matches the value stored in the offset store."""
        fake_offset = _FakeOffsetStore(update_offset=99)
        fake_transcript = _FakeTranscriptStore()

        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        try:
            resp = _client.get("/api/social/providers/telegram/poller/status")
            assert resp.status_code == 200
            assert resp.json()["last_offset"] == 99
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)

    def test_last_offset_null_when_never_set(self, _client: TestClient) -> None:
        """last_offset is null when the offset store has no entry."""
        fake_offset = _FakeOffsetStore(update_offset=None)
        fake_transcript = _FakeTranscriptStore()

        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        try:
            resp = _client.get("/api/social/providers/telegram/poller/status")
            assert resp.status_code == 200
            assert resp.json()["last_offset"] is None
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)

    def test_transcript_count_today_integer(self, _client: TestClient) -> None:
        """transcript_count_today is an integer (0 when no rows today)."""
        fake_offset = _FakeOffsetStore()
        fake_transcript = _FakeTranscriptStore(rows=[])

        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        try:
            resp = _client.get("/api/social/providers/telegram/poller/status")
            assert resp.status_code == 200
            count = resp.json()["transcript_count_today"]
            assert isinstance(count, int)
            assert count == 0
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)

    def test_transcript_count_today_counts_todays_rows(self, _client: TestClient) -> None:
        """transcript_count_today counts only today's rows (UTC), ignoring yesterday."""
        rows = [_make_row(_TODAY_DT), _make_row(_TODAY_DT), _make_row(_YESTERDAY_DT)]
        fake_offset = _FakeOffsetStore()
        fake_transcript = _FakeTranscriptStore(rows=rows)

        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        try:
            resp = _client.get("/api/social/providers/telegram/poller/status")
            assert resp.status_code == 200
            assert resp.json()["transcript_count_today"] == 2
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)

    def test_last_run_at_returned_when_set(self, _client: TestClient) -> None:
        """last_run_at is returned when the offset store has it."""
        fake_offset = _FakeOffsetStore(last_run_at=_TODAY_DT)
        fake_transcript = _FakeTranscriptStore()

        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        try:
            resp = _client.get("/api/social/providers/telegram/poller/status")
            assert resp.status_code == 200
            assert resp.json()["last_run_at"] == _TODAY_DT
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)


# ---------------------------------------------------------------------------
# VAL-M15-M4-POLLERSTATUS-002: Reads only from M1 stores, no live Telegram calls
# ---------------------------------------------------------------------------


class TestPollerStatusNoLiveTelegramCalls:
    """VAL-M15-M4-POLLERSTATUS-002"""

    def test_no_httpx_call_made(self, _client: TestClient) -> None:
        """httpx.Client.__init__ is never invoked by the status endpoint."""
        fake_offset = _FakeOffsetStore(update_offset=42)
        fake_transcript = _FakeTranscriptStore(rows=[_make_row()])

        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        try:
            with patch("httpx.Client.__init__", side_effect=AssertionError("httpx was called")):
                resp = _client.get("/api/social/providers/telegram/poller/status")
                assert resp.status_code == 200
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)

    def test_no_urllib_call_made(self, _client: TestClient) -> None:
        """urllib.request.urlopen is never invoked by the status endpoint."""
        fake_offset = _FakeOffsetStore(update_offset=42)
        fake_transcript = _FakeTranscriptStore(rows=[_make_row()])

        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        try:
            with patch("urllib.request.urlopen", side_effect=AssertionError("urllib was called")):
                resp = _client.get("/api/social/providers/telegram/poller/status")
                assert resp.status_code == 200
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)

    def test_response_matches_seeded_store_values(self, _client: TestClient) -> None:
        """Response body matches values seeded into the in-memory stores."""
        fake_offset = _FakeOffsetStore(update_offset=77, last_run_at=_TODAY_DT)
        fake_transcript = _FakeTranscriptStore(rows=[_make_row(), _make_row()])

        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        try:
            with patch("httpx.Client.__init__", side_effect=AssertionError("httpx called")):
                with patch(
                    "urllib.request.urlopen",
                    side_effect=AssertionError("urllib called"),
                ):
                    resp = _client.get("/api/social/providers/telegram/poller/status")
                    assert resp.status_code == 200
                    body = resp.json()
                    assert body["last_offset"] == 77
                    assert body["last_run_at"] == _TODAY_DT
                    assert body["transcript_count_today"] == 2
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)


# ---------------------------------------------------------------------------
# VAL-M15-M4-POLLERSTATUS-003: No secrets / chat ids / raw 18+-digit IDs
# ---------------------------------------------------------------------------


class TestPollerStatusNoSecretsInResponse:
    """VAL-M15-M4-POLLERSTATUS-003"""

    def test_no_18_digit_sequence_in_response(self, _client: TestClient) -> None:
        """18+-digit numeric sequence does not appear in the response."""
        raw_error = "error involving 123456789012345678"  # 18-digit number
        fake_offset = _FakeOffsetStore(update_offset=1, last_error=raw_error)
        fake_transcript = _FakeTranscriptStore()

        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        try:
            resp = _client.get("/api/social/providers/telegram/poller/status")
            assert resp.status_code == 200
            assert "123456789012345678" not in resp.text
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)

    def test_no_bot_token_value_in_response(self, _client: TestClient) -> None:
        """TELEGRAM_BOT_TOKEN value does not appear in response body."""
        import os

        fake_token = "synthetic-bot-token-secret-XYZ"
        fake_offset = _FakeOffsetStore(update_offset=1)
        fake_transcript = _FakeTranscriptStore()

        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        try:
            with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": fake_token}):
                resp = _client.get("/api/social/providers/telegram/poller/status")
                assert resp.status_code == 200
                assert fake_token not in resp.text
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)


# ---------------------------------------------------------------------------
# VAL-M15-M4-POLLERSTATUS-004: last_error_code bounded and redacted
# ---------------------------------------------------------------------------


class TestPollerStatusLastErrorBoundedAndRedacted:
    """VAL-M15-M4-POLLERSTATUS-004"""

    def test_last_error_code_bounded_to_280_chars(self, _client: TestClient) -> None:
        """last_error_code is truncated to ≤ 280 characters."""
        long_error = "e" * 4000
        fake_offset = _FakeOffsetStore(last_error=long_error)
        fake_transcript = _FakeTranscriptStore()

        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        try:
            resp = _client.get("/api/social/providers/telegram/poller/status")
            assert resp.status_code == 200
            body = resp.json()
            error_code = body.get("last_error_code")
            if error_code is not None:
                assert len(error_code) <= 280
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)

    def test_last_error_code_digit_sequence_masked(self, _client: TestClient) -> None:
        """12-digit numeric sequence in last_error is masked/stripped in the response."""
        error_with_digits = "error code 123456789012 occurred"  # 12-digit
        fake_offset = _FakeOffsetStore(last_error=error_with_digits)
        fake_transcript = _FakeTranscriptStore()

        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        try:
            resp = _client.get("/api/social/providers/telegram/poller/status")
            assert resp.status_code == 200
            assert "123456789012" not in resp.text
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)

    def test_last_error_code_null_when_no_error(self, _client: TestClient) -> None:
        """last_error_code is null when offset store has no error recorded."""
        fake_offset = _FakeOffsetStore(last_error=None)
        fake_transcript = _FakeTranscriptStore()

        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        try:
            resp = _client.get("/api/social/providers/telegram/poller/status")
            assert resp.status_code == 200
            assert resp.json().get("last_error_code") is None
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)


# ---------------------------------------------------------------------------
# VAL-M15-M4-POLLERSTATUS-005: Auth surface consistent with adjacent routes
# ---------------------------------------------------------------------------


class TestPollerStatusAuthSurface:
    """VAL-M15-M4-POLLERSTATUS-005

    The endpoint follows the same Clerk-gate pattern as adjacent GET routes in
    /api/social/... When HAM_CLERK_REQUIRE_AUTH is not set, the endpoint is
    accessible without a bearer token (consistent with dev-mode behavior of
    adjacent routes). When auth is enforced, behavior matches adjacent routes.
    """

    def test_endpoint_accessible_in_dev_mode(self, _client: TestClient) -> None:
        """In dev mode (no HAM_CLERK_REQUIRE_AUTH), endpoint returns 200 without auth header."""
        import os

        fake_offset = _FakeOffsetStore()
        fake_transcript = _FakeTranscriptStore()

        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        env_before = os.environ.get("HAM_CLERK_REQUIRE_AUTH")
        os.environ.pop("HAM_CLERK_REQUIRE_AUTH", None)
        try:
            resp = _client.get("/api/social/providers/telegram/poller/status")
            # Dev mode: accessible without Bearer token
            assert resp.status_code == 200
        finally:
            if env_before is not None:
                os.environ["HAM_CLERK_REQUIRE_AUTH"] = env_before
            else:
                os.environ.pop("HAM_CLERK_REQUIRE_AUTH", None)
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)

    def test_consistent_with_telegram_status_route(self, _client: TestClient) -> None:
        """Poller status uses same Depends(get_ham_clerk_actor) pattern as telegram/status."""
        import os

        fake_offset = _FakeOffsetStore()
        fake_transcript = _FakeTranscriptStore()

        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        # Both routes should behave identically in the same auth environment.
        env_before = os.environ.get("HAM_CLERK_REQUIRE_AUTH")
        os.environ.pop("HAM_CLERK_REQUIRE_AUTH", None)
        try:
            status_resp = _client.get("/api/social/providers/telegram/status")
            poller_resp = _client.get("/api/social/providers/telegram/poller/status")
            # Both should succeed (or both fail with the same status code)
            assert status_resp.status_code == poller_resp.status_code
        finally:
            if env_before is not None:
                os.environ["HAM_CLERK_REQUIRE_AUTH"] = env_before
            else:
                os.environ.pop("HAM_CLERK_REQUIRE_AUTH", None)
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)


# ---------------------------------------------------------------------------
# VAL-M15-CROSS-INBOUND-E2E-001 (partial — testable portion)
# ---------------------------------------------------------------------------


class TestPollerStatusCrossE2EPartial:
    """VAL-M15-CROSS-INBOUND-E2E-001 (partial)

    The full E2E assertion requires live operator activation of the Cloud Run
    Job. This test covers the portion that can be verified locally:
    - transcript_count_today reflects seeded transcript rows
    - last_run_at is returned when set in the offset store
    - last_error_code is absent when no error
    """

    def test_transcript_count_reflects_seeded_rows(self, _client: TestClient) -> None:
        """transcript_count_today >= 1 when offset store has rows from today."""
        rows = [_make_row(_TODAY_DT), _make_row(_TODAY_DT)]
        fake_offset = _FakeOffsetStore(update_offset=10, last_run_at=_TODAY_DT)
        fake_transcript = _FakeTranscriptStore(rows=rows)

        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        try:
            resp = _client.get("/api/social/providers/telegram/poller/status")
            assert resp.status_code == 200
            body = resp.json()
            assert body["transcript_count_today"] >= 1
            assert body["last_run_at"] is not None
            assert body.get("last_error_code") is None
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)

    def test_last_run_at_advances_with_new_offset(self, _client: TestClient) -> None:
        """last_run_at reflects the stored last_run_at from the offset store."""
        ts_earlier = "2026-05-22T08:00:00+00:00"
        ts_later = "2026-05-22T09:00:00+00:00"

        # First "run" state
        fake_offset = _FakeOffsetStore(update_offset=5, last_run_at=ts_earlier)
        fake_transcript = _FakeTranscriptStore()
        set_telegram_offset_store_for_tests(fake_offset)
        set_telegram_transcript_store_for_tests(fake_transcript)
        try:
            resp1 = _client.get("/api/social/providers/telegram/poller/status")
            assert resp1.status_code == 200
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)

        # Second "run" state — offset advanced, last_run_at advanced
        fake_offset2 = _FakeOffsetStore(update_offset=15, last_run_at=ts_later)
        fake_transcript2 = _FakeTranscriptStore(rows=[_make_row(_TODAY_DT)])
        set_telegram_offset_store_for_tests(fake_offset2)
        set_telegram_transcript_store_for_tests(fake_transcript2)
        try:
            resp2 = _client.get("/api/social/providers/telegram/poller/status")
            assert resp2.status_code == 200
            body2 = resp2.json()
            assert body2["last_offset"] == 15
            assert body2["last_run_at"] == ts_later
            assert body2["transcript_count_today"] == 1
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)
