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
from typing import Any, Protocol, runtime_checkable

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


@runtime_checkable
class TelegramOffsetStoreProtocol(Protocol):
    """Backend-agnostic Telegram getUpdates offset store contract.

    ``read_offset(bot_digest)`` returns the last-persisted offset (or ``None``
    when absent). ``write_offset(bot_digest, update_offset)`` persists the
    value atomically so a restart picks up where the poller left off.
    """

    def read_offset(self, bot_digest: str) -> int | None: ...
    def write_offset(self, bot_digest: str, update_offset: int) -> None: ...


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
        """Atomically persist ``update_offset`` for ``bot_digest``."""
        path = self._resolve_path(bot_digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"update_offset": int(update_offset)}, sort_keys=True)
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
    "TelegramOffsetStoreProtocol",
    "TelegramOffsetFileStore",
    "build_telegram_offset_store",
    "get_telegram_offset_store",
    "set_telegram_offset_store_for_tests",
]
