"""Learning-store wiring for GoHAM Social autonomy ticks.

This module is intentionally deterministic and offline-only. It never reads
the legacy HAMgomoon env toggle and never imports live LLM or transport
clients; opt-in is controlled solely by ``GoHamSocialProfile.learning_enabled``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from src.ham.hamgomoon_learning.hermes_critic import StubSocialCritic, get_default_social_critic
from src.ham.hamgomoon_learning.models import LearningRecord
from src.ham.hamgomoon_learning.redaction import (
    redact_external_id,
    redact_learning_record,
    redact_text,
)
from src.ham.hamgomoon_learning.store import append_learning_record
from src.ham.social_autonomy.schema import GoHamSocialProfile

_EXTERNAL_ID_RE = re.compile(r"(?<![\w-])-?\d{18,}(?![\w-])")
_BANNED_SECRET_NAMES = (
    "HAM_" + "SOCIAL_LIVE_APPLY_TOKEN",
    "TELEGRAM" + "_BOT_TOKEN",
    "XAI" + "_API_KEY",
)


class TickLearningCritic(Protocol):
    """Minimal critic surface needed by the autonomy learning hook."""

    def review(self, tick_result: Any) -> LearningRecord:  # pragma: no cover - protocol
        ...


LearningStore = Path | str | Callable[[LearningRecord], LearningRecord | None] | Any


def append_tick_learning(
    profile: GoHamSocialProfile,
    tick_result: Any,
    *,
    critic: TickLearningCritic | None = None,
    learning_store: LearningStore | None = None,
) -> LearningRecord | None:
    """Append one redacted HAMgomoon learning record for an autonomy tick.

    ``learning_enabled=False`` is a no-op. When enabled, the deterministic
    ``StubSocialCritic.review(tick_result)`` path creates a learning record,
    profile workspace/project context is attached, and the record is redacted
    before being appended through the existing HAMgomoon learning-store API.
    """

    if not profile.learning_enabled:
        return None

    active_critic = critic if critic is not None else get_default_social_critic()
    record = active_critic.review(tick_result)
    record = _attach_profile_context(record, profile)
    record = _sanitize_learning_record(record)
    return _append_record(record, learning_store)


def _attach_profile_context(
    record: LearningRecord,
    profile: GoHamSocialProfile,
) -> LearningRecord:
    draft = record.draft.model_copy(
        update={
            "workspace_id": profile.workspace_id,
            "project_id": profile.project_id,
            "persona_id": profile.persona_id,
        }
    )
    return record.model_copy(
        update={
            "workspace_id": profile.workspace_id,
            "project_id": profile.project_id,
            "draft": draft,
        }
    )


def _sanitize_learning_record(record: LearningRecord) -> LearningRecord:
    redacted = redact_learning_record(record)
    payload = redacted.model_dump(mode="json")
    return LearningRecord.model_validate(_scrub_value(payload))


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return _scrub_text(value)
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _scrub_value(item) for key, item in value.items()}
    return value


def _scrub_text(text: str) -> str:
    scrubbed = redact_text(text)
    for name in _BANNED_SECRET_NAMES:
        scrubbed = re.sub(rf"\b{re.escape(name)}\s*=\s*[^\s,;)]+", "[REDACTED]", scrubbed)
        scrubbed = scrubbed.replace(name, "[REDACTED]")
    return _EXTERNAL_ID_RE.sub(
        lambda match: redact_external_id(match.group(0)) or "[REDACTED]",
        scrubbed,
    )


def _append_record(
    record: LearningRecord,
    learning_store: LearningStore | None,
) -> LearningRecord:
    if learning_store is None:
        return append_learning_record(record)

    if isinstance(learning_store, str | Path):
        target = Path(learning_store)
        if target.exists() and target.is_dir():
            target = target / "hamgomoon_learning.jsonl"
        return append_learning_record(record, path=target)

    append_method = getattr(learning_store, "append_learning_record", None)
    if callable(append_method):
        appended = append_method(record)
        return record if appended is None else appended

    if callable(learning_store):
        appended = learning_store(record)
        return record if appended is None else appended

    raise TypeError(
        "learning_store must be a path, callable, or object with append_learning_record"
    )


__all__ = ["append_tick_learning"]
