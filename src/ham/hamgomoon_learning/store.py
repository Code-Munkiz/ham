"""JSONL store for HAMgomoon learning records (bounded, redacted, append-only)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from src.ham.hamgomoon_learning.models import LearningRecord
from src.ham.hamgomoon_learning.redaction import redact_learning_record

_LOG = logging.getLogger(__name__)

_HAMGOMOON_LEARNING_BACKEND_ENV = "HAM_HAMGOMOON_LEARNING_BACKEND"

_ENV_PATH_KEY = "HAM_HAMGOMOON_LEARNING_PATH"
_DEFAULT_REL = Path(".ham") / "hamgomoon_learning.jsonl"

_MAX_TAIL_BYTES = 2_097_152  # 2 MiB tail scan cap


def _resolve_path(path: Path | None) -> Path:
    if path is not None:
        return path
    env = os.environ.get(_ENV_PATH_KEY, "").strip()
    if env:
        return Path(env)
    return Path.cwd() / _DEFAULT_REL


def append_learning_record(
    record: LearningRecord,
    *,
    path: Path | None = None,
) -> LearningRecord:
    """Defensively redact, then atomically append the record as one JSONL line."""
    redacted = redact_learning_record(record)
    target = _resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = redacted.model_dump()
    line = json.dumps(payload, ensure_ascii=False)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    return redacted


def _read_lines(target: Path) -> list[str]:
    if not target.exists():
        return []
    try:
        size = target.stat().st_size
        with target.open("rb") as fh:
            if size > _MAX_TAIL_BYTES:
                fh.seek(size - _MAX_TAIL_BYTES)
                fh.readline()  # discard partial leading line
            raw = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    return [ln for ln in raw.splitlines() if ln.strip()]


def _matches(
    rec: dict[str, Any],
    *,
    workspace_id: str | None,
    project_id: str | None,
    channel: str | None,
) -> bool:
    if workspace_id is not None and rec.get("workspace_id") != workspace_id:
        return False
    if project_id is not None and rec.get("project_id") != project_id:
        return False
    if channel is not None and rec.get("channel") != channel:
        return False
    return True


def list_recent_learning_records(
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
    channel: str | None = None,
    limit: int = 50,
    path: Path | None = None,
) -> list[LearningRecord]:
    target = _resolve_path(path)
    lines = _read_lines(target)
    clamped = max(1, min(int(limit), 500))
    out: list[LearningRecord] = []
    for line in reversed(lines):
        if len(out) >= clamped:
            break
        try:
            data = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        if not _matches(data, workspace_id=workspace_id, project_id=project_id, channel=channel):
            continue
        try:
            out.append(LearningRecord.model_validate(data))
        except Exception:
            continue
    return list(reversed(out))


def summarize_learning_hints(
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
    channel: str | None = None,
    limit: int = 50,
    path: Path | None = None,
) -> dict[str, list[str]]:
    """Roll recent records into rough buckets of hints for future drafts."""
    records = list_recent_learning_records(
        workspace_id=workspace_id,
        project_id=project_id,
        channel=channel,
        limit=limit,
        path=path,
    )
    recent_lessons: list[str] = []
    avoid_list: list[str] = []
    good_examples: list[str] = []
    recurring_preferences: list[str] = []

    reason_counts: dict[str, int] = {}

    for rec in records:
        critique = rec.critique
        if critique is not None:
            if critique.reusable_lesson:
                recent_lessons.append(critique.reusable_lesson)
            for flag in critique.risk_flags:
                if not flag:
                    continue
                if flag not in avoid_list:
                    avoid_list.append(flag)
        review = rec.review
        if review is not None:
            if review.decision == "approved":
                snippet = (rec.draft.draft_text or "").strip()
                if snippet:
                    snippet_short = snippet if len(snippet) <= 160 else snippet[:157] + "..."
                    good_examples.append(snippet_short)
            for tag in review.reason_tags:
                if not tag:
                    continue
                reason_counts[tag] = reason_counts.get(tag, 0) + 1

    for tag, count in sorted(reason_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if count >= 2:
            recurring_preferences.append(tag)

    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
        return out

    return {
        "recent_lessons": _dedupe(recent_lessons),
        "avoid_list": _dedupe(avoid_list),
        "good_examples": _dedupe(good_examples),
        "recurring_preferences": _dedupe(recurring_preferences),
    }


__all__ = [
    "append_learning_record",
    "list_recent_learning_records",
    "summarize_learning_hints",
    "HamgomoonLearningStoreProtocol",
    "HamgomoonLearningFileStore",
    "build_hamgomoon_learning_store",
    "get_hamgomoon_learning_store",
    "set_hamgomoon_learning_store_for_tests",
]


# ---------------------------------------------------------------------------
# Protocol + file-backend wrapper + factory
# ---------------------------------------------------------------------------


@runtime_checkable
class HamgomoonLearningStoreProtocol(Protocol):
    """Backend-agnostic HAMgomoon learning records store contract."""

    def append_learning_record(
        self,
        record: LearningRecord,
        *,
        path: Path | None = None,
    ) -> LearningRecord: ...

    def list_recent_learning_records(
        self,
        *,
        workspace_id: str | None = None,
        project_id: str | None = None,
        channel: str | None = None,
        limit: int = 50,
        path: Path | None = None,
    ) -> list[LearningRecord]: ...

    def summarize_learning_hints(
        self,
        *,
        workspace_id: str | None = None,
        project_id: str | None = None,
        channel: str | None = None,
        limit: int = 50,
        path: Path | None = None,
    ) -> dict[str, list[str]]: ...


class HamgomoonLearningFileStore:
    """File-backed HAMgomoon learning records store (wraps module-level functions)."""

    def append_learning_record(
        self,
        record: LearningRecord,
        *,
        path: Path | None = None,
    ) -> LearningRecord:
        return append_learning_record(record, path=path)

    def list_recent_learning_records(
        self,
        *,
        workspace_id: str | None = None,
        project_id: str | None = None,
        channel: str | None = None,
        limit: int = 50,
        path: Path | None = None,
    ) -> list[LearningRecord]:
        return list_recent_learning_records(
            workspace_id=workspace_id,
            project_id=project_id,
            channel=channel,
            limit=limit,
            path=path,
        )

    def summarize_learning_hints(
        self,
        *,
        workspace_id: str | None = None,
        project_id: str | None = None,
        channel: str | None = None,
        limit: int = 50,
        path: Path | None = None,
    ) -> dict[str, list[str]]:
        return summarize_learning_hints(
            workspace_id=workspace_id,
            project_id=project_id,
            channel=channel,
            limit=limit,
            path=path,
        )


def build_hamgomoon_learning_store() -> HamgomoonLearningStoreProtocol:
    """Pick a HAMgomoon learning store backend based on env.

    Defaults to :class:`HamgomoonLearningFileStore`. ``HAM_HAMGOMOON_LEARNING_BACKEND
    =firestore`` selects the Firestore backend (lazy-imported).
    """
    backend = (os.environ.get(_HAMGOMOON_LEARNING_BACKEND_ENV) or "").strip().lower()
    if backend == "firestore":
        from src.ham.hamgomoon_learning.firestore_store import (  # noqa: PLC0415
            FirestoreHamgomoonLearningStore,
        )

        return FirestoreHamgomoonLearningStore()
    if backend not in ("", "file"):
        _LOG.warning(
            "Unknown %s=%r; falling back to file backend.",
            _HAMGOMOON_LEARNING_BACKEND_ENV,
            backend,
        )
    return HamgomoonLearningFileStore()


_hamgomoon_learning_store_singleton: HamgomoonLearningStoreProtocol | None = None


def get_hamgomoon_learning_store() -> HamgomoonLearningStoreProtocol:
    """Lazy singleton accessor for the configured HAMgomoon learning store."""
    global _hamgomoon_learning_store_singleton
    if _hamgomoon_learning_store_singleton is None:
        _hamgomoon_learning_store_singleton = build_hamgomoon_learning_store()
    return _hamgomoon_learning_store_singleton


def set_hamgomoon_learning_store_for_tests(
    store: HamgomoonLearningStoreProtocol | None,
) -> None:
    """Replace the global learning store (``None`` restores lazy default)."""
    global _hamgomoon_learning_store_singleton
    _hamgomoon_learning_store_singleton = store
