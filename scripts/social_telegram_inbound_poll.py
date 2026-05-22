#!/usr/bin/env python3
"""Cloud Run Job entrypoint — Telegram inbound poller.

Calls the bounded getUpdates collector once and exits cleanly.

Exit codes
----------
0   Success — no updates available, or updates written successfully.
1   Configuration error — ``TELEGRAM_BOT_TOKEN`` is absent or empty.

Intended to be run as a Cloud Run Job using the existing ``Dockerfile``
with an ``--command`` / ``--args`` override at job-creation time::

    gcloud run jobs create telegram-inbound-poller \\
      --image IMAGE_URL \\
      --command python3 \\
      --args scripts/social_telegram_inbound_poll.py \\
      ...

The bot token is never logged, never printed to stdout or stderr, and
never included in any output line.  Only ``TELEGRAM_BOT_TOKEN`` (the env
variable *name*) and the structured error code ``telegram_bot_token_missing``
appear in output when the token is absent.

See ``docs/M15_TELEGRAM_INBOUND_POLLER_RUNBOOK.md`` for the full operator
runbook.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Make 'src' importable when the script is executed from the repo root via
# ``python scripts/social_telegram_inbound_poll.py`` (PYTHONPATH=/app is
# set in the Dockerfile; pytest.ini adds '.' for tests).
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.ham.ham_x.redaction import redact_text  # noqa: E402
from src.ham.social_telegram_inbound_collector import (  # noqa: E402
    GetUpdatesTransport,
    run_inbound_poll_once,
)
from src.ham.social_telegram_offset_store import (  # noqa: E402
    TelegramOffsetStoreProtocol,
    get_telegram_offset_store,
)
from src.ham.social_telegram_transcript_store import TelegramTranscriptStoreProtocol  # noqa: E402

_LOG = logging.getLogger(__name__)

# Mirrors _POLLER_NUMERIC_ID_RE in src/api/social.py (used by GET /poller/status).
_POLLER_NUMERIC_ID_RE = re.compile(r"(?<![A-Za-z])-?\d{6,}(?![A-Za-z])")
# Maximum length for last_error stored by the poller (mirrors the API read bound).
_POLLER_ERROR_MAX_LEN = 280


def _bound_and_redact_error(exc: BaseException) -> str:
    """Return a bounded, redacted string representation of an exception.

    Applies the same ``redact_text`` + numeric-ID stripping used by
    ``GET /api/social/providers/telegram/poller/status`` before the error
    is persisted to the offset store.
    """
    raw = str(exc)
    cleaned = redact_text(raw)
    cleaned = _POLLER_NUMERIC_ID_RE.sub("", cleaned)
    return cleaned[:_POLLER_ERROR_MAX_LEN]


def main(
    *,
    transport: GetUpdatesTransport | None = None,
    offset_store: TelegramOffsetStoreProtocol | None = None,
    transcript_store: TelegramTranscriptStoreProtocol | None = None,
) -> None:
    """Run one bounded getUpdates poll cycle and exit.

    Parameters
    ----------
    transport, offset_store, transcript_store:
        Injectable seams for unit tests.  Production uses the defaults
        (``HttpxGetUpdatesTransport`` + factory-selected stores).

    Notes
    -----
    Always terminates via :func:`sys.exit`.  The bot token value is never
    included in any output line or log record.

    After each successful poll cycle, writes ``last_run_at`` (UTC ISO-8601
    timestamp) to the offset store via :meth:`write_poller_metadata`.  On
    exception paths, writes ``last_error`` (bounded to 280 chars and
    redacted).  The ``--max-retries=0`` Cloud Run Job guarantee is
    preserved: exceptions are re-raised so the process exits non-zero.
    """
    import os

    # Resolve the offset store up-front so we can write metadata to the same
    # instance that run_inbound_poll_once will use.
    _offset_store: TelegramOffsetStoreProtocol = (
        offset_store if offset_store is not None else get_telegram_offset_store()
    )

    # Compute bot_digest early (before the poll) for metadata writes.
    # If the token is absent, bot_digest is None and metadata writes are skipped.
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    bot_digest: str | None = (
        hashlib.sha256(token.encode("utf-8")).hexdigest()[:16] if token else None
    )

    # Run the poll cycle; catch exceptions so we can write last_error before
    # re-raising (preserving the non-zero exit for Cloud Run Job --max-retries=0).
    try:
        result = run_inbound_poll_once(
            transport=transport,
            offset_store=_offset_store,
            transcript_store=transcript_store,
        )
    except Exception as exc:
        # Write last_error (bounded + redacted) before propagating the exception.
        if bot_digest is not None:
            try:
                error_text = _bound_and_redact_error(exc)
                _offset_store.write_poller_metadata(bot_digest, last_error=error_text)
            except Exception:  # noqa: BLE001
                _LOG.warning("Failed to write last_error poller metadata", exc_info=True)
        raise

    if result.status == "blocked" and "telegram_bot_token_missing" in result.reasons:
        # Write a single structured line to stderr.  The token VALUE is never
        # included — only the env variable name and the error code appear.
        error_payload = json.dumps(
            {
                "level": "error",
                "code": "telegram_bot_token_missing",
                "message": ("TELEGRAM_BOT_TOKEN env is absent or empty; refusing to run"),
            }
        )
        print(error_payload, file=sys.stderr)
        sys.exit(1)

    # Success path — write last_run_at before printing the summary.
    if bot_digest is not None:
        try:
            _offset_store.write_poller_metadata(
                bot_digest, last_run_at=datetime.now(UTC).isoformat()
            )
        except Exception:  # noqa: BLE001
            _LOG.warning("Failed to write last_run_at poller metadata", exc_info=True)

    summary_payload = json.dumps(
        {
            "level": "info",
            "code": "poll_complete",
            "polled_count": result.polled_count,
            "new_offset": result.new_offset,
        }
    )
    print(summary_payload)
    sys.exit(0)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    main()
