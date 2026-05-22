"""Telegram getUpdates offset store — Protocol, file-backend skeleton, and factory.

The Firestore backend is implemented in M1 F4 (telegram-transcript-and-offset-firestore-stores).
This module ships the Protocol and a file-backend skeleton so the M3 poller
(and tests) can use the Protocol surface immediately.

The offset is the ``update_id + 1`` of the last processed Telegram update.
It is keyed by ``sha256(token)[:16]`` (a short hex digest of the bot token)
so different bot tokens do not interfere with each other.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Protocol, TypedDict, runtime_checkable

_LOG = logging.getLogger(__name__)

_TELEGRAM_OFFSET_BACKEND_ENV = "HAM_TELEGRAM_OFFSET_BACKEND"


def _default_offsets_dir() -> Path:
    raw = (os.environ.get("HAM_TELEGRAM_OFFSET_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.cwd() / ".ham" / "telegram_offsets"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class PollerMetadata(TypedDict, total=False):
    """Optional metadata stored alongside the getUpdates offset.

    ``last_run_at`` is an ISO-8601 timestamp reflecting when the poller last
    wrote a successful offset (set by ``write_poller_metadata``). ``last_error``
    is the most recent collector failure message (bounded, redacted by the API
    layer before being surfaced).  Both default to ``None`` when absent.
    """

    last_run_at: str | None
    last_error: str | None


@runtime_checkable
class TelegramOffsetStoreProtocol(Protocol):
    """Backend-agnostic Telegram getUpdates offset store contract.

    ``read_offset(bot_digest)`` returns the last-persisted offset (or ``None``
    when absent). ``write_offset(bot_digest, update_offset)`` persists the
    value atomically so a restart picks up where the poller left off.

    ``read_poller_metadata(bot_digest)`` returns optional metadata stored
    alongside the offset (``last_run_at`` and ``last_error``).  Both fields
    default to ``None`` when absent from the underlying storage.
    """

    def read_offset(self, bot_digest: str) -> int | None: ...
    def write_offset(self, bot_digest: str, update_offset: int) -> None: ...
    def read_poller_metadata(self, bot_digest: str) -> PollerMetadata: ...
    def write_poller_metadata(
        self,
        bot_digest: str,
        *,
        last_run_at: str | None = None,
        last_error: str | None = None,
    ) -> None: ...


# ---------------------------------------------------------------------------
# File-backend skeleton
# ---------------------------------------------------------------------------


class TelegramOffsetFileStore:
    """File-backed Telegram getUpdates offset store.

    Each bot's offset is persisted as a single-key JSON file under
    ``<base_dir>/<bot_digest[:16]>.json``. Writes are atomic (tmp→rename).
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir

    def _resolve_path(self, bot_digest: str) -> Path:
        base = self._base_dir or _default_offsets_dir()
        key = str(bot_digest).strip()[:16] or "default"
        return base / f"{key}.json"

    def read_offset(self, bot_digest: str) -> int | None:
        """Return the stored offset for ``bot_digest``, or ``None`` if absent."""
        path = self._resolve_path(bot_digest)
        if not path.is_file():
            return None
        try:
            data: Any = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                val = data.get("update_offset")
                if val is not None:
                    return int(val)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
        return None

    def write_offset(self, bot_digest: str, update_offset: int) -> None:
        """Atomically persist ``update_offset`` for ``bot_digest``.

        Preserves any existing ``last_run_at`` / ``last_error`` fields stored
        in the same JSON file (written via :meth:`write_poller_metadata`).
        """
        path = self._resolve_path(bot_digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Preserve existing metadata fields while updating the offset.
        existing: dict[str, Any] = {}
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding="utf-8")) or {}
                if not isinstance(existing, dict):
                    existing = {}
            except (OSError, json.JSONDecodeError):
                existing = {}
        existing["update_offset"] = int(update_offset)
        payload = json.dumps(existing, sort_keys=True)
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, path)
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    def read_poller_metadata(self, bot_digest: str) -> PollerMetadata:
        """Return optional metadata stored alongside the offset.

        Reads ``last_run_at`` and ``last_error`` from the same JSON file used
        by :meth:`read_offset` / :meth:`write_offset`.  Both fields default to
        ``None`` when absent.
        """
        path = self._resolve_path(bot_digest)
        if not path.is_file():
            return PollerMetadata(last_run_at=None, last_error=None)
        try:
            data: Any = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return PollerMetadata(last_run_at=None, last_error=None)
        except (OSError, json.JSONDecodeError):
            return PollerMetadata(last_run_at=None, last_error=None)
        raw_run_at = data.get("last_run_at")
        raw_error = data.get("last_error")
        return PollerMetadata(
            last_run_at=str(raw_run_at) if raw_run_at is not None else None,
            last_error=str(raw_error) if raw_error is not None else None,
        )

    def write_poller_metadata(
        self,
        bot_digest: str,
        *,
        last_run_at: str | None = None,
        last_error: str | None = None,
    ) -> None:
        """Merge poller metadata into the existing JSON document.

        Merges only the fields whose values are not ``None`` into the same JSON
        file used by :meth:`read_offset` / :meth:`write_offset`, so the stored
        ``update_offset`` (and any previously written metadata fields) are
        preserved.

        Passing ``last_run_at=None`` (the default) leaves the existing
        ``last_run_at`` field unchanged.  The same applies to ``last_error``.

        Args:
            bot_digest:  Short hex digest of the bot token (``sha256(token)[:16]``).
            last_run_at: ISO-8601 timestamp of the most recent successful poll run.
                         ``None`` means "do not update this field".
            last_error:  Bounded, redacted error message from the most recent
                         failed poll run.  ``None`` means "do not update this field".
        """
        path = self._resolve_path(bot_digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Read existing data to preserve update_offset and other metadata fields.
        existing: dict[str, Any] = {}
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    existing = raw
            except (OSError, json.JSONDecodeError):
                existing = {}
        # Only update fields that were explicitly provided (non-None default).
        if last_run_at is not None:
            existing["last_run_at"] = last_run_at
        if last_error is not None:
            existing["last_error"] = last_error
        # Atomically write back.
        payload = json.dumps(existing, sort_keys=True)
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, path)
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_telegram_offset_store() -> TelegramOffsetStoreProtocol:
    """Pick a Telegram offset store backend based on env.

    Defaults to :class:`TelegramOffsetFileStore`. ``HAM_TELEGRAM_OFFSET_BACKEND
    =firestore`` selects the Firestore backend (lazy-imported).
    """
    backend = (os.environ.get(_TELEGRAM_OFFSET_BACKEND_ENV) or "").strip().lower()
    if backend == "firestore":
        from src.ham.social_telegram_offset_firestore import (  # noqa: PLC0415
            FirestoreTelegramOffsetStore,
        )

        return FirestoreTelegramOffsetStore()
    if backend not in ("", "file"):
        _LOG.warning(
            "Unknown %s=%r; falling back to file backend.",
            _TELEGRAM_OFFSET_BACKEND_ENV,
            backend,
        )
    return TelegramOffsetFileStore()


_telegram_offset_store_singleton: TelegramOffsetStoreProtocol | None = None


def get_telegram_offset_store() -> TelegramOffsetStoreProtocol:
    """Lazy singleton accessor for the configured Telegram offset store."""
    global _telegram_offset_store_singleton
    if _telegram_offset_store_singleton is None:
        _telegram_offset_store_singleton = build_telegram_offset_store()
    return _telegram_offset_store_singleton


def set_telegram_offset_store_for_tests(
    store: TelegramOffsetStoreProtocol | None,
) -> None:
    """Replace the global offset store (``None`` restores lazy default)."""
    global _telegram_offset_store_singleton
    _telegram_offset_store_singleton = store


__all__ = [
    "PollerMetadata",
    "TelegramOffsetStoreProtocol",
    "TelegramOffsetFileStore",
    "build_telegram_offset_store",
    "get_telegram_offset_store",
    "set_telegram_offset_store_for_tests",
]
