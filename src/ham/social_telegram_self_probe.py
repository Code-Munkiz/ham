"""HAM-side Telegram self-probe (getMe) with TTL cache.

Implements a single GET to api.telegram.org/bot<token>/getMe via stdlib
urllib.request, matching the social_telegram_send.py transport precedent.

Design invariants:
- Never raises: the entire probe is wrapped in a try/except.
- Never logs or returns raw token, bot_id, or username.
- TTL-cached (default 60 s, override via HAM_TELEGRAM_SELF_PROBE_TTL_SECONDS).
- Cache key derived from sha256(token)[:16] — tokens are never stored.
- Returns TelegramSelfProbeResult with state/checked_at/error_code fields only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

_logger = logging.getLogger(__name__)

# Maximum wall-clock time (seconds) for a single getMe HTTP call.
_GETME_TIMEOUT_SEC: float = 6.0

# URL template; token is substituted at call time, never logged.
_GETME_URL_TEMPLATE = "https://api.telegram.org/bot{token}/getMe"

# Module-level TTL cache: {sha256(token)[:16] -> TelegramSelfProbeResult}
# Only digest keys are stored here — raw tokens never appear.
_CACHE: dict[str, TelegramSelfProbeResult] = {}


@dataclass
class TelegramSelfProbeResult:
    """Result of a Telegram self-probe.

    Invariant: token, raw bot_id, and raw username never appear in any field.
    ``bot_username_digest`` is a sha256[:16] hex digest of the username, never
    the username itself.
    """

    state: str  # "ok" | "auth_failed" | "timeout" | "network_error" | "unknown"
    checked_at: datetime
    error_code: str | None = None
    bot_username_digest: str | None = None  # sha256[:16] of username; never raw value


def _cache_key(token: str) -> str:
    """Return a 16-char lowercase hex digest derived from sha256(token)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _probe_ttl_seconds() -> int:
    """Read TTL from env at call time so tests can monkeypatch.setenv()."""
    raw = os.environ.get("HAM_TELEGRAM_SELF_PROBE_TTL_SECONDS", "60")
    try:
        return max(1, int(raw))
    except (ValueError, TypeError):
        return 60


def _do_http_get(url: str) -> tuple[int, bytes]:
    """Default HTTP GET via stdlib urllib.request.

    Returns ``(status_code, response_body_bytes)`` for all HTTP responses,
    including error statuses. Raises for network/timeout errors.

    urllib.error.HTTPError (non-2xx) is converted to a ``(code, body)`` return
    value so callers can inspect 401 and similar statuses without catching that
    specific exception class.

    The URL (which embeds the bot token) is never logged here or by callers.
    """
    req = urllib.request.Request(url, method="GET")  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=_GETME_TIMEOUT_SEC) as resp:  # noqa: S310
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:  # noqa: BLE001
            body = b""
        return exc.code, body


def probe_telegram_self(
    token: str,
    *,
    now: datetime,
    http_get: Callable[[str], tuple[int, bytes]] | None = None,
) -> TelegramSelfProbeResult:
    """Probe the Telegram getMe endpoint. TTL-cached. Never raises.

    Checks the module-level TTL cache keyed by ``sha256(token)[:16]`` before
    issuing a new HTTP request.  On success, caches the result for the TTL
    duration.  On failure of any kind returns a result with a non-null
    ``error_code`` — the exception is never propagated.

    Args:
        token: Telegram bot token.  Never logged, never stored in the cache.
        now: Current timestamp, used for TTL calculations and result
             ``checked_at`` field.  Pass ``datetime.now(timezone.utc)`` from
             callers; injectable for testing.
        http_get: Optional injectable HTTP GET callable for tests.  Receives the
                  fully-formed getMe URL and must return ``(status_code,
                  body_bytes)``.  Defaults to the stdlib urllib implementation.

    Returns:
        TelegramSelfProbeResult — always returned, never raises.
    """
    key = _cache_key(token)
    ttl = _probe_ttl_seconds()

    # ---- TTL cache check ------------------------------------------------
    cached = _CACHE.get(key)
    if cached is not None:
        age = (now - cached.checked_at).total_seconds()
        if age < ttl:
            return cached

    # ---- HTTP probe (fully wrapped; never raises) ------------------------
    getter = http_get if http_get is not None else _do_http_get
    url = _GETME_URL_TEMPLATE.format(token=token)

    result: TelegramSelfProbeResult
    try:
        status, raw = getter(url)
        payload = json.loads(raw)
        result = _build_result_from_response(status, payload, now=now)
    except TimeoutError:
        result = TelegramSelfProbeResult(
            state="timeout",
            checked_at=now,
            error_code="timeout",
        )
    except (ConnectionError, urllib.error.URLError):
        result = TelegramSelfProbeResult(
            state="network_error",
            checked_at=now,
            error_code="network_error",
        )
    except json.JSONDecodeError:
        result = TelegramSelfProbeResult(
            state="unknown",
            checked_at=now,
            error_code="parse_error",
        )
    except Exception:  # noqa: BLE001  # defensive transport boundary; all errors become ok=False
        result = TelegramSelfProbeResult(
            state="unknown",
            checked_at=now,
            error_code="unknown",
        )

    _CACHE[key] = result
    return result


def _build_result_from_response(
    status: int,
    payload: object,
    *,
    now: datetime,
) -> TelegramSelfProbeResult:
    """Build a probe result from a parsed HTTP response.

    Raw bot_id and username are NEVER stored in the returned object.
    Only a sha256[:16] digest of the username is retained.
    """
    if not isinstance(payload, dict):
        return TelegramSelfProbeResult(
            state="unknown",
            checked_at=now,
            error_code="parse_error",
        )

    if status == 200 and payload.get("ok") is True:
        result_obj = payload.get("result")
        bot_username_digest: str | None = None
        if isinstance(result_obj, dict):
            raw_username = result_obj.get("username") or ""
            if raw_username:
                # Digest only — raw username is never retained in any field.
                bot_username_digest = hashlib.sha256(
                    str(raw_username).encode("utf-8")
                ).hexdigest()[:16]
        return TelegramSelfProbeResult(
            state="ok",
            checked_at=now,
            error_code=None,
            bot_username_digest=bot_username_digest,
        )

    if status == 401:
        return TelegramSelfProbeResult(
            state="auth_failed",
            checked_at=now,
            error_code="auth_failed",
            bot_username_digest=None,
        )

    # Other HTTP error status (403, 404, 429, 500, etc.)
    return TelegramSelfProbeResult(
        state="unknown",
        checked_at=now,
        error_code=f"http_{status}",
        bot_username_digest=None,
    )
