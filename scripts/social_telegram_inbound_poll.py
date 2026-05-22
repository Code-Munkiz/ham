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

import json
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Make 'src' importable when the script is executed from the repo root via
# ``python scripts/social_telegram_inbound_poll.py`` (PYTHONPATH=/app is
# set in the Dockerfile; pytest.ini adds '.' for tests).
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.ham.social_telegram_inbound_collector import (  # noqa: E402
    GetUpdatesTransport,
    run_inbound_poll_once,
)
from src.ham.social_telegram_offset_store import TelegramOffsetStoreProtocol  # noqa: E402
from src.ham.social_telegram_transcript_store import TelegramTranscriptStoreProtocol  # noqa: E402

_LOG = logging.getLogger(__name__)


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
    """
    result = run_inbound_poll_once(
        transport=transport,
        offset_store=offset_store,
        transcript_store=transcript_store,
    )

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

    # Success path — status is "ok" (polled_count may be 0 or > 0).
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
