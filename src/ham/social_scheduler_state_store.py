"""Social scheduler state store — model, Protocol, file-backend skeleton, and factory.

The Firestore backend is implemented in M1 F5 (scheduler-state-firestore-store).
This module ships the Pydantic model, the Protocol, and a file-backend skeleton
so the M4 scheduler route and tests can use the Protocol surface immediately.

Scheduler state is a singleton document per deployment:
    {
        "scheduler_enabled":       <bool>,       # default False
        "last_scheduled_tick_at":  <ISO-8601>,   # or None
        "last_tick_summary":       <dict | None>,
    }
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

_LOG = logging.getLogger(__name__)

_SOCIAL_SCHEDULER_STATE_BACKEND_ENV = "HAM_SOCIAL_SCHEDULER_STATE_BACKEND"


def _default_scheduler_state_path() -> Path:
    raw = (os.environ.get("HAM_SOCIAL_SCHEDULER_STATE_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.cwd() / ".ham" / "social_scheduler_state.json"


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class SocialSchedulerState(BaseModel):
    """Persisted scheduler state snapshot."""

    model_config = ConfigDict(extra="forbid")

    scheduler_enabled: bool = False
    last_scheduled_tick_at: datetime | None = None
    last_tick_summary: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SocialSchedulerStateStoreProtocol(Protocol):
    """Backend-agnostic social scheduler state store contract.

    ``read_state()`` returns the current state (or safe defaults when absent).
    ``write_state(state)`` persists the new state. The M4 scheduled-tick route
    is the only writer; the SocialStatusPanel reads via ``read_state``.
    """

    def read_state(self) -> SocialSchedulerState: ...
    def write_state(self, state: SocialSchedulerState) -> None: ...


# ---------------------------------------------------------------------------
# File-backend skeleton
# ---------------------------------------------------------------------------


class SocialSchedulerStateFileStore:
    """File-backed social scheduler state store.

    State is persisted as a single JSON file at the path determined by
    ``HAM_SOCIAL_SCHEDULER_STATE_PATH`` (or the default ``.ham/social_scheduler_state.json``).
    Writes are atomic (tmp→rename). ``scheduler_enabled`` defaults to ``False``
    and ``last_scheduled_tick_at`` defaults to ``None`` when the file is absent.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    def _resolve(self) -> Path:
        if self._path is not None:
            return self._path
        return _default_scheduler_state_path()

    def read_state(self) -> SocialSchedulerState:
        """Return current state; returns safe defaults when the file is absent."""
        path = self._resolve()
        if not path.is_file():
            return SocialSchedulerState()
        try:
            data: Any = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return SocialSchedulerState.model_validate(data)
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        return SocialSchedulerState()

    def write_state(self, state: SocialSchedulerState) -> None:
        """Atomically persist the scheduler state."""
        path = self._resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            state.model_dump(mode="json", exclude_none=True),
            indent=2,
            sort_keys=True,
        )
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


def build_social_scheduler_state_store() -> SocialSchedulerStateStoreProtocol:
    """Pick a social scheduler state store backend based on env.

    Defaults to :class:`SocialSchedulerStateFileStore`. ``HAM_SOCIAL_SCHEDULER_STATE_BACKEND
    =firestore`` selects the Firestore backend (lazy-imported).
    """
    backend = (os.environ.get(_SOCIAL_SCHEDULER_STATE_BACKEND_ENV) or "").strip().lower()
    if backend == "firestore":
        from src.ham.social_scheduler_state_firestore import (  # noqa: PLC0415
            FirestoreSocialSchedulerStateStore,
        )

        return FirestoreSocialSchedulerStateStore()
    if backend not in ("", "file"):
        _LOG.warning(
            "Unknown %s=%r; falling back to file backend.",
            _SOCIAL_SCHEDULER_STATE_BACKEND_ENV,
            backend,
        )
    return SocialSchedulerStateFileStore()


_social_scheduler_state_store_singleton: SocialSchedulerStateStoreProtocol | None = None


def get_social_scheduler_state_store() -> SocialSchedulerStateStoreProtocol:
    """Lazy singleton accessor for the configured social scheduler state store."""
    global _social_scheduler_state_store_singleton
    if _social_scheduler_state_store_singleton is None:
        _social_scheduler_state_store_singleton = build_social_scheduler_state_store()
    return _social_scheduler_state_store_singleton


def set_social_scheduler_state_store_for_tests(
    store: SocialSchedulerStateStoreProtocol | None,
) -> None:
    """Replace the global scheduler state store (``None`` restores lazy default)."""
    global _social_scheduler_state_store_singleton
    _social_scheduler_state_store_singleton = store


__all__ = [
    "SocialSchedulerState",
    "SocialSchedulerStateStoreProtocol",
    "SocialSchedulerStateFileStore",
    "build_social_scheduler_state_store",
    "get_social_scheduler_state_store",
    "set_social_scheduler_state_store_for_tests",
]
