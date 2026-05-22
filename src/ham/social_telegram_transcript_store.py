"""Telegram inbound transcript store — Protocol, file-backend skeleton, and factory.

The Firestore backend is implemented in M1 F4 (telegram-transcript-and-offset-firestore-stores).
This module ships the Protocol and a file-backend skeleton so tests and the
reactive lane can use the Protocol surface immediately.

Row contract (matches existing JSONL format in ``social_telegram_inbound.py``):
    {
        "source": "telegram",
        "role":   "user",
        "text":   <redacted>,
        "chat_id":    <int>,
        "author_id":  <int>,
        "message_id": <int>,
        "created_at": <ISO-8601 string>,
        # optional
        "chat_type":       <str | None>,
        "already_answered": <bool | None>,
    }
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

_LOG = logging.getLogger(__name__)

_TELEGRAM_TRANSCRIPT_BACKEND_ENV = "HAM_TELEGRAM_TRANSCRIPT_BACKEND"

_TRANSCRIPT_ROW_FIELDS = frozenset(
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


def _default_transcript_path() -> Path:
    raw = (os.environ.get("HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.cwd() / ".ham" / "telegram_inbound_transcript.jsonl"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class TelegramTranscriptStoreProtocol(Protocol):
    """Backend-agnostic Telegram inbound transcript store contract.

    ``append_row`` writes one redacted, allow-listed row; ``iter_rows``
    yields all stored rows. Both the file-backend skeleton and the
    Firestore backend satisfy this Protocol.
    """

    def append_row(self, row: dict[str, Any]) -> None: ...
    def iter_rows(self) -> Iterator[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# File-backend skeleton
# ---------------------------------------------------------------------------


class TelegramTranscriptFileStore:
    """File-backed Telegram inbound transcript store.

    Writes/reads JSONL at ``HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH`` (or the
    default ``.ham/telegram_inbound_transcript.jsonl``).  The M3 poller is
    the only writer; the reactive lane reads via ``iter_rows``.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    def _resolve(self) -> Path:
        if self._path is not None:
            return self._path
        return _default_transcript_path()

    def append_row(self, row: dict[str, Any]) -> None:
        """Write one allow-listed row as a JSONL line (atomic append)."""
        safe = {k: v for k, v in row.items() if k in _TRANSCRIPT_ROW_FIELDS}
        target = self._resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(safe, sort_keys=True) + "\n")

    def iter_rows(self) -> Iterator[dict[str, Any]]:
        """Yield all rows from the JSONL transcript file."""
        target = self._resolve()
        if not target.is_file():
            return
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_telegram_transcript_store() -> TelegramTranscriptStoreProtocol:
    """Pick a Telegram transcript store backend based on env.

    Defaults to :class:`TelegramTranscriptFileStore`. ``HAM_TELEGRAM_TRANSCRIPT_BACKEND
    =firestore`` selects the Firestore backend (lazy-imported so the SDK is not
    required for file-mode usage).
    """
    backend = (os.environ.get(_TELEGRAM_TRANSCRIPT_BACKEND_ENV) or "").strip().lower()
    if backend == "firestore":
        from src.ham.social_telegram_transcript_firestore import (  # noqa: PLC0415
            FirestoreTelegramTranscriptStore,
        )

        return FirestoreTelegramTranscriptStore()
    if backend not in ("", "file"):
        _LOG.warning(
            "Unknown %s=%r; falling back to file backend.",
            _TELEGRAM_TRANSCRIPT_BACKEND_ENV,
            backend,
        )
    return TelegramTranscriptFileStore()


_telegram_transcript_store_singleton: TelegramTranscriptStoreProtocol | None = None


def get_telegram_transcript_store() -> TelegramTranscriptStoreProtocol:
    """Lazy singleton accessor for the configured Telegram transcript store."""
    global _telegram_transcript_store_singleton
    if _telegram_transcript_store_singleton is None:
        _telegram_transcript_store_singleton = build_telegram_transcript_store()
    return _telegram_transcript_store_singleton


def set_telegram_transcript_store_for_tests(
    store: TelegramTranscriptStoreProtocol | None,
) -> None:
    """Replace the global transcript store (``None`` restores lazy default)."""
    global _telegram_transcript_store_singleton
    _telegram_transcript_store_singleton = store


__all__ = [
    "TelegramTranscriptStoreProtocol",
    "TelegramTranscriptFileStore",
    "build_telegram_transcript_store",
    "get_telegram_transcript_store",
    "set_telegram_transcript_store_for_tests",
]
