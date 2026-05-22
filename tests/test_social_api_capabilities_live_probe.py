"""Tests for capabilities endpoint live-probe seeding (M2B).

Verifies that:
- GET /api/social/providers/telegram/capabilities seeds the self-probe cache when
  TELEGRAM_BOT_TOKEN is present and the cache is missing or expired.
- Subsequent calls within the TTL window do NOT invoke a second HTTP request.
- Probe failures are never raised from the endpoint; HTTP 200 is always returned
  with a safe non-ok telegram_self_probe_state.
- Token, raw bot id, raw username, and raw error body never appear in the
  response body or in captured log records.

Assertions covered (see validation-contract.md):
- VAL-M15-M2B-CAPABILITIES-LIVE-PROBE-SEED-001
- VAL-M15-M2B-CAPABILITIES-LIVE-PROBE-CACHED-002
- VAL-M15-M2B-CAPABILITIES-LIVE-PROBE-FAIL-SAFE-003
- VAL-M15-M2B-SNAPSHOT-BYTE-EQUAL-004  (covered by running the pinned tests;
  the snapshot tests are verified in a separate parametrized call from the
  milestone gate — this file only cross-checks the byte-equality invariant
  indirectly via the fresh_probe=False path in the aggregate endpoint)
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.social_telegram_self_probe import (
    _CACHE as _probe_cache,
)
from src.ham.social_telegram_self_probe import (
    TelegramSelfProbeResult,
    _cache_key,
)

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_CAPABILITIES_ROUTE = "/api/social/providers/telegram/capabilities"

_BAIT_TOKEN = "bot1234567890:bait-telegram-token-ABCDEFGHIJKL"  # noqa: S105
_BAIT_BOT_ID = 9_876_543_210
_BAIT_USERNAME = "bait_probe_bot_username_xyz"


def _disable_clerk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)


def _set_telegram_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    token: str = _BAIT_TOKEN,
) -> None:
    """Configure required Telegram env vars with a synthetic bait token."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "1111111111")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "-1001111111111")
    monkeypatch.setenv("TELEGRAM_TEST_GROUP_ID", "-1009999999999")


def _clear_hermes_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HERMES_GATEWAY_BASE_URL", raising=False)
    monkeypatch.delenv("HAM_HERMES_GATEWAY_STATUS_PATH", raising=False)
    monkeypatch.delenv("HAM_HERMES_HOME", raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)


@pytest.fixture(autouse=True)
def _clear_probe_cache() -> Generator[None, None, None]:
    """Clear the module-level TTL cache before and after every test in this
    file to prevent state leakage between tests."""
    _probe_cache.clear()
    yield
    _probe_cache.clear()


def _ok_http_response() -> tuple[int, bytes]:
    """Simulate a successful getMe HTTP response."""
    payload = {
        "ok": True,
        "result": {
            "id": _BAIT_BOT_ID,
            "is_bot": True,
            "first_name": "TestBot",
            "username": _BAIT_USERNAME,
        },
    }
    return (200, json.dumps(payload).encode())


# ---------------------------------------------------------------------------
# VAL-M15-M2B-CAPABILITIES-LIVE-PROBE-SEED-001
# ---------------------------------------------------------------------------


def test_capabilities_seeds_cache_on_first_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /capabilities invokes probe_telegram_self() exactly once when
    TELEGRAM_BOT_TOKEN is present and the cache is empty.
    Response must include telegram_self_probe_state == 'ok'.

    VAL-M15-M2B-CAPABILITIES-LIVE-PROBE-SEED-001
    """
    _disable_clerk(monkeypatch)
    _set_telegram_env(monkeypatch)
    _clear_hermes_env(monkeypatch)

    probe_result = TelegramSelfProbeResult(
        state="ok",
        checked_at=datetime.now(UTC),
        error_code=None,
        bot_username_digest=hashlib.sha256(_BAIT_USERNAME.encode()).hexdigest()[:16],
    )

    with patch(
        "src.api.social.probe_telegram_self",
        return_value=probe_result,
    ) as mock_probe:
        response = client.get(_CAPABILITIES_ROUTE)

    assert response.status_code == 200
    body = response.json()

    # probe_telegram_self must have been invoked exactly once
    assert mock_probe.call_count == 1, (
        f"Expected probe_telegram_self called exactly once; got {mock_probe.call_count}"
    )

    # Response must carry the resolved probe state
    assert body.get("telegram_self_probe_state") == "ok", (
        f"Expected telegram_self_probe_state='ok', got: {body.get('telegram_self_probe_state')}"
    )


def test_capabilities_returns_ok_with_no_token_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When TELEGRAM_BOT_TOKEN is absent, capabilities returns 'unknown' probe
    state without making any network call.

    VAL-M15-M2B-CAPABILITIES-LIVE-PROBE-SEED-001 (token-absent variant)
    """
    _disable_clerk(monkeypatch)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    _clear_hermes_env(monkeypatch)

    with patch("src.api.social.probe_telegram_self") as mock_probe:
        response = client.get(_CAPABILITIES_ROUTE)

    assert response.status_code == 200
    body = response.json()
    # No token → no probe call
    assert mock_probe.call_count == 0
    assert body.get("telegram_self_probe_state") == "unknown"


# ---------------------------------------------------------------------------
# VAL-M15-M2B-CAPABILITIES-LIVE-PROBE-CACHED-002
# ---------------------------------------------------------------------------


def test_capabilities_uses_cache_within_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second capabilities call within the TTL window does NOT invoke a
    second HTTP request.  http_get is invoked exactly once across both calls.

    VAL-M15-M2B-CAPABILITIES-LIVE-PROBE-CACHED-002
    """
    _disable_clerk(monkeypatch)
    _set_telegram_env(monkeypatch)
    _clear_hermes_env(monkeypatch)
    # Use a short but non-zero TTL that both requests fit within
    monkeypatch.setenv("HAM_TELEGRAM_SELF_PROBE_TTL_SECONDS", "60")

    http_call_count = 0

    def _mock_http_get(url: str) -> tuple[int, bytes]:
        nonlocal http_call_count
        http_call_count += 1
        return _ok_http_response()

    with patch(
        "src.ham.social_telegram_self_probe._do_http_get",
        side_effect=_mock_http_get,
    ):
        # First call: cache empty → should trigger one HTTP request
        response1 = client.get(_CAPABILITIES_ROUTE)
        # Second call: cache populated → must NOT trigger another HTTP request
        response2 = client.get(_CAPABILITIES_ROUTE)

    assert response1.status_code == 200
    assert response2.status_code == 200

    assert http_call_count == 1, (
        f"Expected exactly 1 HTTP call across two capabilities requests within TTL; "
        f"got {http_call_count}"
    )

    # Both responses should agree on the probe state
    assert response1.json().get("telegram_self_probe_state") == "ok"
    assert response2.json().get("telegram_self_probe_state") == "ok"


def test_capabilities_re_probes_after_ttl_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After the TTL has expired, the next capabilities call re-issues the HTTP
    request to refresh the cache.

    VAL-M15-M2B-CAPABILITIES-LIVE-PROBE-CACHED-002 (TTL-expiry variant)
    """
    _disable_clerk(monkeypatch)
    _set_telegram_env(monkeypatch)
    _clear_hermes_env(monkeypatch)
    monkeypatch.setenv("HAM_TELEGRAM_SELF_PROBE_TTL_SECONDS", "60")

    # Manually seed the cache with an entry that is older than the TTL
    token = _BAIT_TOKEN
    key = _cache_key(token)
    expired_time = datetime.now(UTC) - timedelta(seconds=61)
    _probe_cache[key] = TelegramSelfProbeResult(
        state="ok",
        checked_at=expired_time,
        error_code=None,
        bot_username_digest="staleentry",
    )

    http_call_count = 0

    def _mock_http_get(url: str) -> tuple[int, bytes]:
        nonlocal http_call_count
        http_call_count += 1
        return _ok_http_response()

    with patch(
        "src.ham.social_telegram_self_probe._do_http_get",
        side_effect=_mock_http_get,
    ):
        response = client.get(_CAPABILITIES_ROUTE)

    assert response.status_code == 200
    # TTL expired → new HTTP call must have been made
    assert http_call_count == 1, (
        f"Expected exactly 1 HTTP call after TTL expiry; got {http_call_count}"
    )


# ---------------------------------------------------------------------------
# VAL-M15-M2B-CAPABILITIES-LIVE-PROBE-FAIL-SAFE-003
# ---------------------------------------------------------------------------


def test_capabilities_fail_safe_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the probe raises TimeoutError, capabilities returns HTTP 200 with a
    safe (non-ok) telegram_self_probe_state.  The bait token must not appear in
    the response body or any log record.

    VAL-M15-M2B-CAPABILITIES-LIVE-PROBE-FAIL-SAFE-003 (timeout variant)
    """
    _disable_clerk(monkeypatch)
    _set_telegram_env(monkeypatch, token=_BAIT_TOKEN)
    _clear_hermes_env(monkeypatch)

    def _raise_timeout(url: str) -> tuple[int, bytes]:
        raise TimeoutError("synthetic timeout")

    with caplog.at_level(logging.DEBUG):
        with patch(
            "src.ham.social_telegram_self_probe._do_http_get",
            side_effect=_raise_timeout,
        ):
            response = client.get(_CAPABILITIES_ROUTE)

    assert response.status_code == 200, (
        f"Expected HTTP 200 on probe timeout; got {response.status_code}"
    )
    body = response.json()
    probe_state = body.get("telegram_self_probe_state")
    assert probe_state in ("not_ok", "unknown"), (
        f"Expected safe non-ok probe state on timeout; got {probe_state!r}"
    )

    # Bait token must never appear in the response body
    response_text = response.text
    assert _BAIT_TOKEN not in response_text, (
        "Bait token appeared in capabilities response body on timeout"
    )

    # Bait token must never appear in any captured log record
    for record in caplog.records:
        assert _BAIT_TOKEN not in record.getMessage(), (
            f"Bait token appeared in log record: {record.getMessage()!r}"
        )


def test_capabilities_fail_safe_on_http_401(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the probe receives HTTP 401, capabilities returns HTTP 200 with a
    safe (non-ok) telegram_self_probe_state.  The bait token must not appear in
    the response body or any log record.

    VAL-M15-M2B-CAPABILITIES-LIVE-PROBE-FAIL-SAFE-003 (HTTP 401 variant)
    """
    _disable_clerk(monkeypatch)
    _set_telegram_env(monkeypatch, token=_BAIT_TOKEN)
    _clear_hermes_env(monkeypatch)

    def _return_401(url: str) -> tuple[int, bytes]:
        return (401, b'{"ok": false, "error_code": 401, "description": "Unauthorized"}')

    with caplog.at_level(logging.DEBUG):
        with patch(
            "src.ham.social_telegram_self_probe._do_http_get",
            side_effect=_return_401,
        ):
            response = client.get(_CAPABILITIES_ROUTE)

    assert response.status_code == 200, (
        f"Expected HTTP 200 on probe 401; got {response.status_code}"
    )
    body = response.json()
    probe_state = body.get("telegram_self_probe_state")
    assert probe_state in ("not_ok", "unknown"), (
        f"Expected safe non-ok probe state on HTTP 401; got {probe_state!r}"
    )

    response_text = response.text
    assert _BAIT_TOKEN not in response_text, (
        "Bait token appeared in capabilities response body on HTTP 401"
    )

    for record in caplog.records:
        assert _BAIT_TOKEN not in record.getMessage(), (
            f"Bait token appeared in log record: {record.getMessage()!r}"
        )


def test_capabilities_fail_safe_on_parse_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the probe response body is not valid JSON, capabilities returns
    HTTP 200 with a safe (non-ok) telegram_self_probe_state.

    VAL-M15-M2B-CAPABILITIES-LIVE-PROBE-FAIL-SAFE-003 (parse error variant)
    """
    _disable_clerk(monkeypatch)
    _set_telegram_env(monkeypatch, token=_BAIT_TOKEN)
    _clear_hermes_env(monkeypatch)

    def _return_garbage(url: str) -> tuple[int, bytes]:
        return (200, b"not-valid-json-at-all {{{{")

    with caplog.at_level(logging.DEBUG):
        with patch(
            "src.ham.social_telegram_self_probe._do_http_get",
            side_effect=_return_garbage,
        ):
            response = client.get(_CAPABILITIES_ROUTE)

    assert response.status_code == 200, (
        f"Expected HTTP 200 on probe parse error; got {response.status_code}"
    )
    body = response.json()
    probe_state = body.get("telegram_self_probe_state")
    assert probe_state in ("not_ok", "unknown"), (
        f"Expected safe non-ok probe state on parse error; got {probe_state!r}"
    )

    response_text = response.text
    assert _BAIT_TOKEN not in response_text, (
        "Bait token appeared in capabilities response body on parse error"
    )

    for record in caplog.records:
        assert _BAIT_TOKEN not in record.getMessage(), (
            f"Bait token appeared in log record: {record.getMessage()!r}"
        )


def test_capabilities_fail_safe_on_generic_exception(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When probe_telegram_self raises a generic exception, the endpoint must
    NOT propagate it.  HTTP 200 with safe state must be returned.

    VAL-M15-M2B-CAPABILITIES-LIVE-PROBE-FAIL-SAFE-003 (generic exception variant)
    """
    _disable_clerk(monkeypatch)
    _set_telegram_env(monkeypatch, token=_BAIT_TOKEN)
    _clear_hermes_env(monkeypatch)

    def _raise_generic(url: str) -> tuple[int, bytes]:
        raise RuntimeError("unexpected internal failure")

    with caplog.at_level(logging.DEBUG):
        with patch(
            "src.ham.social_telegram_self_probe._do_http_get",
            side_effect=_raise_generic,
        ):
            response = client.get(_CAPABILITIES_ROUTE)

    assert response.status_code == 200, (
        f"Expected HTTP 200 on generic probe exception; got {response.status_code}"
    )
    body = response.json()
    probe_state = body.get("telegram_self_probe_state")
    assert probe_state in ("not_ok", "unknown"), (
        f"Expected safe non-ok state on generic exception; got {probe_state!r}"
    )

    response_text = response.text
    assert _BAIT_TOKEN not in response_text, (
        "Bait token appeared in capabilities response body on generic exception"
    )

    for record in caplog.records:
        assert _BAIT_TOKEN not in record.getMessage(), (
            f"Bait token appeared in log record: {record.getMessage()!r}"
        )


def test_capabilities_token_bait_never_in_response_on_success(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """On a successful probe, the bait token, raw bot id, and raw username must
    never appear in the response body or any log record.

    VAL-M15-M2B-CAPABILITIES-LIVE-PROBE-FAIL-SAFE-003 (secret hygiene on success)
    """
    _disable_clerk(monkeypatch)
    _set_telegram_env(monkeypatch, token=_BAIT_TOKEN)
    _clear_hermes_env(monkeypatch)

    def _return_success(url: str) -> tuple[int, bytes]:
        return _ok_http_response()

    with caplog.at_level(logging.DEBUG):
        with patch(
            "src.ham.social_telegram_self_probe._do_http_get",
            side_effect=_return_success,
        ):
            response = client.get(_CAPABILITIES_ROUTE)

    assert response.status_code == 200
    response_text = response.text

    # Raw bait token must not appear in response
    assert _BAIT_TOKEN not in response_text, (
        "Bait token appeared in capabilities response body on success"
    )
    # Raw bot id must not appear in response
    assert str(_BAIT_BOT_ID) not in response_text, (
        f"Raw bot id {_BAIT_BOT_ID} appeared in capabilities response body"
    )
    # Raw username must not appear in response
    assert _BAIT_USERNAME not in response_text, (
        "Raw username appeared in capabilities response body"
    )

    for record in caplog.records:
        msg = record.getMessage()
        assert _BAIT_TOKEN not in msg, f"Bait token appeared in log: {msg!r}"
        assert _BAIT_USERNAME not in msg, f"Raw username appeared in log: {msg!r}"


# ---------------------------------------------------------------------------
# Hermes decoupling (supplementary)
# ---------------------------------------------------------------------------


def test_capabilities_hermes_absent_does_not_block_telegram_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing Hermes does NOT block the Telegram self-probe or the readiness
    fields in the capabilities response.

    VAL-M15-M2B-CAPABILITIES-LIVE-PROBE-SEED-001 (Hermes-decoupled variant)
    """
    _disable_clerk(monkeypatch)
    _set_telegram_env(monkeypatch)
    _clear_hermes_env(monkeypatch)  # Hermes entirely absent

    probe_result = TelegramSelfProbeResult(
        state="ok",
        checked_at=datetime.now(UTC),
        error_code=None,
        bot_username_digest="d1a2b3c4d5e6f7a8",
    )

    with patch(
        "src.api.social.probe_telegram_self",
        return_value=probe_result,
    ):
        response = client.get(_CAPABILITIES_ROUTE)

    assert response.status_code == 200
    body = response.json()

    # Self-probe state must reflect the probe result — Hermes absence irrelevant
    assert body.get("telegram_self_probe_state") == "ok"
    # Hermes gateway must be reported as not_configured
    assert body.get("hermes_gateway_readiness") == "not_configured"
    # Telegram readiness must be ready (all envs set + probe ok + Hermes absent)
    assert body.get("telegram_readiness") == "ready"


# ---------------------------------------------------------------------------
# VAL-M15-M2B-SNAPSHOT-BYTE-EQUAL-004 (inline coverage check)
# ---------------------------------------------------------------------------


def test_aggregate_endpoint_still_uses_cached_only_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The aggregate GET /api/social endpoint continues to use the cached-only
    probe path (fresh_probe=False) so that snapshot tests remain byte-equal.
    When the cache is empty, telegram_self_probe_state is 'unknown' in the
    aggregate response but any value in the dedicated capabilities response.

    VAL-M15-M2B-SNAPSHOT-BYTE-EQUAL-004 (invariant inline check)
    """
    _disable_clerk(monkeypatch)
    _set_telegram_env(monkeypatch)
    _clear_hermes_env(monkeypatch)
    # Patch non-social endpoints to avoid irrelevant side effects
    monkeypatch.delenv("HAM_HERMES_HOME", raising=False)

    # Cache is empty at this point; aggregate must NOT call probe_telegram_self
    with patch("src.api.social.probe_telegram_self") as mock_probe:
        aggregate_response = client.get("/api/social")

    # probe_telegram_self must NOT have been called by the aggregate endpoint
    assert mock_probe.call_count == 0, (
        f"Aggregate endpoint called probe_telegram_self {mock_probe.call_count} time(s); "
        "expected 0 (cached-only path must be used)"
    )

    assert aggregate_response.status_code == 200
    aggregate_body = aggregate_response.json()
    # telegramCapabilities inside the aggregate must show 'unknown' (cache empty, no probe)
    telegram_caps = aggregate_body.get("telegramCapabilities") or {}
    assert telegram_caps.get("telegram_self_probe_state") == "unknown", (
        f"Expected 'unknown' in aggregate telegramCapabilities (cached-only); "
        f"got {telegram_caps.get('telegram_self_probe_state')!r}"
    )
