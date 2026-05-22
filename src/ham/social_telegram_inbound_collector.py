"""Bounded Telegram getUpdates inbound poller / collector.

Reads the persisted getUpdates offset from the M1 offset store, issues one
bounded ``GET getUpdates`` call, normalises each returned update into an
allow-listed JSONL row, appends rows to the M1 transcript store, and
atomically advances the offset.

Design invariants
-----------------
- ``timeout=0`` is hardcoded on the getUpdates request (no long-poll).
- ``limit=100`` caps the batch size per call.
- The offset is committed **only** if ALL rows are appended successfully.
  A failure on any row leaves the offset unchanged so the next call
  re-fetches the same batch idempotently.
- The bot token is never logged, never included in any row, and never
  passed to the transcript store.
- :func:`run_inbound_poll_once` refuses to run when ``TELEGRAM_BOT_TOKEN``
  is absent.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import os
import re
from typing import Any, Literal, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.redaction import redact_text
from src.ham.social_telegram_offset_store import (
    TelegramOffsetStoreProtocol,
    get_telegram_offset_store,
)
from src.ham.social_telegram_transcript_store import (
    TelegramTranscriptStoreProtocol,
    get_telegram_transcript_store,
)

_LOG = logging.getLogger(__name__)

_GETUPDATE_LIMIT = 100
_GETUPDATE_TELEGRAM_TIMEOUT = 0  # no long-poll; must remain 0
_TRANSPORT_READ_TIMEOUT_SECONDS = 6.0
_TELEGRAM_API_BASE = "https://api.telegram.org"

# Strip ≥6-digit numeric IDs from free-form message text
# Mirrors the `_RAW_NUMERIC_ID_RE` precedent in social_telegram_send.py
_RAW_NUMERIC_ID_RE = re.compile(r"(?<![A-Za-z])-?\d{6,}(?![A-Za-z])")

_ALLOWED_ROW_FIELDS = frozenset(
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


# ---------------------------------------------------------------------------
# Transport Protocol (injectable for tests)
# ---------------------------------------------------------------------------


@runtime_checkable
class GetUpdatesTransport(Protocol):
    """Minimal Telegram getUpdates transport contract.

    Implementations receive the bot token, offset, limit, and transport-level
    timeout.  They return the parsed JSON body from
    ``api.telegram.org/bot<token>/getUpdates`` as a Python dict.

    Tests substitute a hand-rolled mock; no inheritance required.
    """

    def get_updates(
        self,
        *,
        bot_token: str,
        offset: int,
        limit: int,
        timeout_seconds: float,
    ) -> dict[str, Any]: ...  # noqa: D102


class HttpxGetUpdatesTransport:
    """Default httpx-backed Telegram getUpdates transport.

    Uses ``httpx.Client`` with a ≤6 s read timeout.  The Telegram-level
    ``timeout`` query parameter is always ``0`` (no long-poll).
    """

    api_base: str = _TELEGRAM_API_BASE

    def get_updates(
        self,
        *,
        bot_token: str,
        offset: int,
        limit: int,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        url = f"{self.api_base}/bot{bot_token}/getUpdates"
        params: dict[str, Any] = {
            "offset": offset,
            "timeout": _GETUPDATE_TELEGRAM_TIMEOUT,
            "allowed_updates": '["message"]',
            "limit": limit,
        }
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

InboundPollStatus = Literal["ok", "blocked", "failed"]


class InboundPollResult(BaseModel):
    """Result of a single bounded getUpdates poll cycle."""

    model_config = ConfigDict(extra="forbid")

    status: InboundPollStatus = "ok"
    polled_count: int = 0
    new_offset: int | None = None
    reasons: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_inbound_poll_once(
    *,
    transport: GetUpdatesTransport | None = None,
    offset_store: TelegramOffsetStoreProtocol | None = None,
    transcript_store: TelegramTranscriptStoreProtocol | None = None,
) -> InboundPollResult:
    """Run one bounded getUpdates poll cycle.

    Parameters
    ----------
    transport:
        Injectable transport (default: :class:`HttpxGetUpdatesTransport`).
        Tests pass a ``MockGetUpdatesTransport``; production uses the default.
    offset_store:
        Injectable offset store (default: ``get_telegram_offset_store()``).
    transcript_store:
        Injectable transcript store (default: ``get_telegram_transcript_store()``).

    Returns
    -------
    InboundPollResult
        ``status="blocked"`` with ``reasons=["telegram_bot_token_missing"]``
        when ``TELEGRAM_BOT_TOKEN`` is absent or empty.
        ``status="ok"`` with ``polled_count=0`` when there are no new updates.
        ``status="ok"`` with ``polled_count=N`` after writing N rows.
    """
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        return InboundPollResult(
            status="blocked",
            reasons=["telegram_bot_token_missing"],
        )

    _transport = transport if transport is not None else HttpxGetUpdatesTransport()
    _offset_store = offset_store if offset_store is not None else get_telegram_offset_store()
    _transcript_store = (
        transcript_store if transcript_store is not None else get_telegram_transcript_store()
    )

    bot_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    current_offset = _offset_store.read_offset(bot_digest) or 0

    # Issue exactly one bounded getUpdates call.
    # The Telegram `timeout` parameter is always 0 (no long-poll).
    response = _transport.get_updates(
        bot_token=token,
        offset=current_offset,
        limit=_GETUPDATE_LIMIT,
        timeout_seconds=_TRANSPORT_READ_TIMEOUT_SECONDS,
    )

    updates: list[Any] = response.get("result", [])
    if not isinstance(updates, list):
        updates = []
    # Hard-cap: never process more than 100 updates per call.
    updates = updates[:_GETUPDATE_LIMIT]

    if not updates:
        # Idempotent: no new updates → no change to offset or transcript store.
        return InboundPollResult(status="ok", polled_count=0, new_offset=None)

    # Normalize all updates to allow-listed rows.
    rows: list[dict[str, Any]] = []
    for update in updates:
        row = _normalize_update(update)
        if row is not None:
            rows.append(row)

    # Write all rows BEFORE committing the offset.
    # If any append raises, the exception propagates; offset is NOT advanced.
    for row in rows:
        _transcript_store.append_row(row)

    # Persist new offset: highest update_id across the batch + 1.
    max_update_id = max(
        int(u["update_id"]) for u in updates if isinstance(u, dict) and "update_id" in u
    )
    new_offset = max_update_id + 1
    _offset_store.write_offset(bot_digest, new_offset)

    return InboundPollResult(
        status="ok",
        polled_count=len(rows),
        new_offset=new_offset,
    )


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _normalize_update(update: Any) -> dict[str, Any] | None:
    """Normalize one Telegram update dict to the JSONL row contract.

    Returns ``None`` for non-message updates or structurally invalid payloads.
    """
    if not isinstance(update, dict):
        return None
    message = update.get("message")
    if not isinstance(message, dict):
        return None

    # Required integer fields — skip update if any are missing / unparseable.
    try:
        chat_id = int(message["chat"]["id"])
        author_id = int(message["from"]["id"])
        message_id = int(message["message_id"])
    except (KeyError, TypeError, ValueError):
        return None

    # Text — run through canonical redaction pipeline.
    raw_text = message.get("text", "") or ""
    text = _redact_message_text(str(raw_text))

    # Timestamp → ISO-8601.
    created_at: str | None = None
    date_ts = message.get("date")
    if date_ts is not None:
        try:
            created_at = datetime.datetime.fromtimestamp(int(date_ts), tz=datetime.UTC).isoformat()
        except (TypeError, ValueError, OSError):
            created_at = None

    # Optional: chat type.
    chat_type: str | None = None
    chat_obj = message.get("chat")
    if isinstance(chat_obj, dict):
        raw_type = chat_obj.get("type")
        if raw_type is not None:
            chat_type = str(raw_type)[:64]

    row: dict[str, Any] = {
        "source": "telegram",
        "role": "user",
        "text": text,
        "chat_id": chat_id,
        "author_id": author_id,
        "message_id": message_id,
        "created_at": created_at,
        "chat_type": chat_type,
        "already_answered": False,
    }
    # Allow-list: drop any key not in the documented contract.
    return {k: v for k, v in row.items() if k in _ALLOWED_ROW_FIELDS}


def _redact_message_text(text: str) -> str:
    """Apply canonical redaction and strip ≥6-digit numeric IDs from message text."""
    redacted = redact_text(text)
    # Strip bare ≥6-digit numbers (chat IDs, phone numbers, etc.)
    return _RAW_NUMERIC_ID_RE.sub("", redacted)


__all__ = [
    "GetUpdatesTransport",
    "HttpxGetUpdatesTransport",
    "InboundPollResult",
    "InboundPollStatus",
    "run_inbound_poll_once",
]
