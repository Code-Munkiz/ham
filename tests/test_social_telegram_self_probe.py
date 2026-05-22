"""Tests for src/ham/social_telegram_self_probe.py.

Assertion coverage:
  VAL-M15-M2-SELFPROBE-OK-001      — success path (getMe 200)
  VAL-M15-M2-SELFPROBE-FAILURE-002 — auth failure (getMe 401)
  VAL-M15-M2-SELFPROBE-NEVER-RAISES-003 — never raises on transport failures
  VAL-M15-M2-SELFPROBE-TTL-CACHE-004   — TTL cache skips HTTP within window
  VAL-M15-M2-SELFPROBE-CACHE-KEY-005   — cache key = sha256(token)[:16]
  VAL-M15-M2-SELFPROBE-NO-LOG-006      — no secrets/identifiers in logs

All HTTP calls are mocked at the http_get callable boundary.
No live api.telegram.org traffic.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, timedelta

import pytest

from src.ham.social_telegram_self_probe import (
    _CACHE,
    TelegramSelfProbeResult,
    probe_telegram_self,
)

# ---------------------------------------------------------------------------
# Shared test fixtures / helpers
# ---------------------------------------------------------------------------

_T0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

# Synthetic values for bait-string checks — never real credentials.
_BOT_TOKEN = "9999:synth-token-for-self-probe-test"
_BOT_ID = 123456789
_BOT_USERNAME = "myspecialsynthbot"


def _ok_response_bytes() -> bytes:
    return json.dumps(
        {
            "ok": True,
            "result": {
                "id": _BOT_ID,
                "is_bot": True,
                "username": _BOT_USERNAME,
                "first_name": "MyBot",
            },
        }
    ).encode()


def _ok_http_get(url: str) -> tuple[int, bytes]:
    return 200, _ok_response_bytes()


def _auth_failed_http_get(url: str) -> tuple[int, bytes]:
    body = json.dumps({"ok": False, "error_code": 401, "description": "Unauthorized"}).encode()
    return 401, body


@pytest.fixture(autouse=True)
def _clear_probe_cache() -> None:
    """Ensure a clean TTL cache before and after every test."""
    _CACHE.clear()
    yield  # type: ignore[misc]
    _CACHE.clear()


# ---------------------------------------------------------------------------
# VAL-M15-M2-SELFPROBE-OK-001
# ---------------------------------------------------------------------------


def test_getme_success_returns_ok() -> None:
    """VAL-M15-M2-SELFPROBE-OK-001: mocked getMe 200 → state=ok, no raw identifiers."""
    result = probe_telegram_self(_BOT_TOKEN, now=_T0, http_get=_ok_http_get)

    assert result.state == "ok"
    assert result.checked_at == _T0
    assert result.error_code is None

    # bot_username_digest must be a 16-char lowercase hex string (sha256[:16])
    assert result.bot_username_digest is not None
    assert len(result.bot_username_digest) == 16
    assert re.match(r"^[0-9a-f]{16}$", result.bot_username_digest)

    # Raw username, bot_id, and token must NOT appear in any field value.
    dumped = repr(result)
    assert _BOT_USERNAME not in dumped, "Raw username leaked into result repr"
    assert str(_BOT_ID) not in dumped, "Raw bot_id leaked into result repr"
    assert _BOT_TOKEN not in dumped, "Token leaked into result repr"

    # Also check the dataclass fields individually.
    assert _BOT_USERNAME not in (result.bot_username_digest or "")
    assert str(_BOT_ID) not in (result.bot_username_digest or "")


# ---------------------------------------------------------------------------
# VAL-M15-M2-SELFPROBE-FAILURE-002
# ---------------------------------------------------------------------------


def test_getme_auth_failed_returns_error_code() -> None:
    """VAL-M15-M2-SELFPROBE-FAILURE-002: mocked getMe 401 → state=auth_failed."""
    result = probe_telegram_self(_BOT_TOKEN, now=_T0, http_get=_auth_failed_http_get)

    assert result.state == "auth_failed"
    assert result.error_code == "auth_failed"
    assert result.checked_at is not None
    assert result.bot_username_digest is None


# ---------------------------------------------------------------------------
# VAL-M15-M2-SELFPROBE-NEVER-RAISES-003
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc,expected_state",
    [
        (TimeoutError("timed out"), "timeout"),
        (ConnectionError("connection refused"), "network_error"),
        (json.JSONDecodeError("bad json", "", 0), "unknown"),
        (RuntimeError("unexpected sentinel"), "unknown"),
    ],
)
def test_probe_never_raises_on_transport_failures(exc: Exception, expected_state: str) -> None:
    """VAL-M15-M2-SELFPROBE-NEVER-RAISES-003: all transport exceptions yield a result,
    never propagate out of probe_telegram_self."""

    def raising_http_get(url: str) -> tuple[int, bytes]:
        raise exc

    # Must not raise under any circumstance.
    result = probe_telegram_self(_BOT_TOKEN, now=_T0, http_get=raising_http_get)

    assert isinstance(result, TelegramSelfProbeResult)
    assert result.state == expected_state, (
        f"Expected state={expected_state!r} for {type(exc).__name__}, got {result.state!r}"
    )
    assert result.error_code is not None, "error_code must be non-empty on failure"
    assert result.checked_at == _T0


# ---------------------------------------------------------------------------
# VAL-M15-M2-SELFPROBE-TTL-CACHE-004
# ---------------------------------------------------------------------------


def test_ttl_cache_skips_http_within_ok_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """VAL-M15-M2-SELFPROBE-TTL-CACHE-004: second call within TTL uses cache;
    third call past TTL re-issues http_get.  http_get call count == 2 total."""
    monkeypatch.setenv("HAM_TELEGRAM_SELF_PROBE_TTL_SECONDS", "60")

    call_count = 0

    def counting_http_get(url: str) -> tuple[int, bytes]:
        nonlocal call_count
        call_count += 1
        return 200, _ok_response_bytes()

    # First call at T0 — HTTP must be issued.
    r1 = probe_telegram_self(_BOT_TOKEN, now=_T0, http_get=counting_http_get)
    assert r1.state == "ok"
    assert call_count == 1

    # Second call at T0+30 s — within 60 s TTL, must use cache (no HTTP).
    r2 = probe_telegram_self(
        _BOT_TOKEN,
        now=_T0 + timedelta(seconds=30),
        http_get=counting_http_get,
    )
    assert r2.state == "ok"
    assert call_count == 1, "Expected no new HTTP call within TTL window"

    # Third call at T0+301 s — past TTL (60 s), must re-issue HTTP.
    r3 = probe_telegram_self(
        _BOT_TOKEN,
        now=_T0 + timedelta(seconds=301),
        http_get=counting_http_get,
    )
    assert r3.state == "ok"
    assert call_count == 2, "Expected exactly one new HTTP call after TTL expiry"


# ---------------------------------------------------------------------------
# VAL-M15-M2-SELFPROBE-CACHE-KEY-005
# ---------------------------------------------------------------------------


def test_cache_keyed_by_sha256_of_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """VAL-M15-M2-SELFPROBE-CACHE-KEY-005: different tokens get separate cache entries;
    cache keys are sha256[:16] hex and never contain raw token bytes."""
    monkeypatch.setenv("HAM_TELEGRAM_SELF_PROBE_TTL_SECONDS", "300")

    calls: list[str] = []

    def tracking_http_get(url: str) -> tuple[int, bytes]:
        calls.append(url)
        return 200, _ok_response_bytes()

    token_a = "aaaa:aaaaaaaaaa-distinct-a"
    token_b = "bbbb:bbbbbbbbbb-distinct-b"

    # First call with token_a — HTTP issued.
    probe_telegram_self(token_a, now=_T0, http_get=tracking_http_get)
    assert len(calls) == 1

    # Second call with token_a within TTL — must hit cache.
    probe_telegram_self(
        token_a,
        now=_T0 + timedelta(seconds=30),
        http_get=tracking_http_get,
    )
    assert len(calls) == 1, "token_a result should be served from cache"

    # First call with token_b — different key, must issue HTTP.
    probe_telegram_self(
        token_b,
        now=_T0 + timedelta(seconds=30),
        http_get=tracking_http_get,
    )
    assert len(calls) == 2, "token_b must trigger a new HTTP call (different cache entry)"

    # Verify all cache keys are 16-char hex and never contain raw token bytes.
    assert len(_CACHE) == 2, "Expected exactly two cache entries (one per token)"
    for cache_key in _CACHE:
        assert re.match(r"^[0-9a-f]{16}$", cache_key), f"Cache key not a 16-char hex: {cache_key!r}"
        # Raw token bytes must never appear in the cache key.
        assert "aaaa" not in cache_key, "token_a literal leaked into cache key"
        assert "bbbb" not in cache_key, "token_b literal leaked into cache key"
        assert "distinct" not in cache_key, "token content leaked into cache key"


# ---------------------------------------------------------------------------
# VAL-M15-M2-SELFPROBE-NO-LOG-006
# ---------------------------------------------------------------------------


def test_probe_never_logs_secrets_or_identifiers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """VAL-M15-M2-SELFPROBE-NO-LOG-006: token, raw bot_id, and raw username never
    appear in any log record across success / auth-failure / network-error /
    parse-error paths."""

    def _network_err(url: str) -> tuple[int, bytes]:
        raise ConnectionError("network failure")

    def _parse_err(url: str) -> tuple[int, bytes]:
        raise json.JSONDecodeError("bad", "", 0)

    scenarios: list[tuple[str, object]] = [
        ("success", _ok_http_get),
        ("auth_fail", _auth_failed_http_get),
        ("network_error", _network_err),
        ("parse_error", _parse_err),
    ]

    bait_strings = [
        _BOT_TOKEN,
        str(_BOT_ID),
        _BOT_USERNAME,
    ]

    for scenario_name, getter in scenarios:
        _CACHE.clear()
        with caplog.at_level(logging.DEBUG, logger="src.ham.social_telegram_self_probe"):
            probe_telegram_self(_BOT_TOKEN, now=_T0, http_get=getter)  # type: ignore[arg-type]

        for record in caplog.records:
            msg = record.getMessage()
            for bait in bait_strings:
                assert bait not in msg, (
                    f"Bait string {bait!r} leaked into log record "
                    f"(scenario={scenario_name!r}): {msg!r}"
                )

        caplog.clear()
