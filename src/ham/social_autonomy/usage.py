"""Fail-closed social-autonomy usage counters.

The autonomous runner uses these counters to enforce per-channel action caps.
If the authoritative source for a channel cannot be read or parsed, callers get
``UsageSourceUnavailable`` so the runner can block rather than fail open.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.ham import social_delivery_log
from src.ham.ham_x.config import load_ham_x_config
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.goham_policy import GOHAM_EXECUTION_KIND
from src.ham.ham_x.reactive_governor import GOHAM_REACTIVE_EXECUTION_KIND
from src.ham.social_telegram_activity import TELEGRAM_ACTIVITY_EXECUTION_KIND
from src.ham.social_telegram_reactive import TELEGRAM_REACTIVE_REPLY_EXECUTION_KIND
from src.ham.social_telegram_send import TELEGRAM_EXECUTION_KIND

__all__ = [
    "UsageSourceUnavailable",
    "count_actions_in_window",
    "count_in_window",
]

_X_ACTION_EXECUTION_KINDS = {
    "broadcast": GOHAM_EXECUTION_KIND,
    "reply": GOHAM_REACTIVE_EXECUTION_KIND,
}
_TELEGRAM_ACTION_EXECUTION_KINDS = {
    "activity": TELEGRAM_ACTIVITY_EXECUTION_KIND,
    "message": TELEGRAM_EXECUTION_KIND,
    "reply": TELEGRAM_REACTIVE_REPLY_EXECUTION_KIND,
}


class UsageSourceUnavailable(RuntimeError):  # noqa: N818
    """Raised when a cap-tracking usage source cannot be trusted."""


def count_actions_in_window(
    channel: str,
    action: str,
    now: datetime,
    *,
    window_seconds: int = 86_400,
    journal_path: Path | str | None = None,
    delivery_log_path: Path | str | None = None,
) -> int:
    """Count executed social actions in a backward-looking time window.

    The comparison is inclusive at the lower edge: records with
    ``executed_at == now - window`` are counted. Future records are not counted.
    Missing, unreadable, or corrupt sources raise ``UsageSourceUnavailable``.
    """

    if window_seconds < 0:
        raise ValueError("window_seconds must be non-negative")
    if channel == "discord":
        raise UsageSourceUnavailable("discord usage tracking is unavailable in this mission")

    end = _to_utc(now)
    start = end - timedelta(seconds=window_seconds)

    if channel == "x":
        execution_kind = _execution_kind_for_action(
            action,
            mapping=_X_ACTION_EXECUTION_KINDS,
            channel=channel,
        )
        records = _read_x_records(_path_or_default(journal_path, _default_x_journal_path()))
        return _count_records(
            records,
            execution_kind=execution_kind,
            start=start,
            end=end,
            status="executed",
        )

    if channel == "telegram":
        execution_kind = _execution_kind_for_action(
            action,
            mapping=_TELEGRAM_ACTION_EXECUTION_KINDS,
            channel=channel,
        )
        records = _read_jsonl_records(
            _path_or_default(delivery_log_path, _default_delivery_log_path())
        )
        return _count_records(
            records,
            execution_kind=execution_kind,
            start=start,
            end=end,
            provider_id="telegram",
            status="sent",
        )

    raise UsageSourceUnavailable(f"usage tracking is unavailable for channel {channel!r}")


def count_in_window(
    *,
    channel: str,
    action: str,
    now: datetime,
    window: timedelta | None = None,
    window_seconds: int | None = None,
    journal_path: Path | str | None = None,
    delivery_log_path: Path | str | None = None,
) -> int:
    """Compatibility wrapper for contract-style callers using ``window``."""

    seconds = window_seconds
    if seconds is None:
        seconds = int((window or timedelta(days=1)).total_seconds())
    return count_actions_in_window(
        channel,
        action,
        now,
        window_seconds=seconds,
        journal_path=journal_path,
        delivery_log_path=delivery_log_path,
    )


def _default_x_journal_path() -> Path:
    return load_ham_x_config().execution_journal_path


def _default_delivery_log_path() -> Path:
    return social_delivery_log.default_delivery_log_path()


def _path_or_default(path: Path | str | None, default: Path) -> Path:
    if path is None:
        return default
    return Path(path).expanduser()


def _execution_kind_for_action(
    action: str,
    *,
    mapping: dict[str, str],
    channel: str,
) -> str:
    try:
        return mapping[action]
    except KeyError as exc:
        raise UsageSourceUnavailable(
            f"usage tracking is unavailable for channel {channel!r} action {action!r}"
        ) from exc


def _read_x_records(path: Path) -> list[dict[str, Any]]:
    _read_jsonl_records(path)
    try:
        return ExecutionJournal(path=path).records()
    except OSError as exc:
        raise UsageSourceUnavailable(f"x execution journal is unavailable: {path}") from exc


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise UsageSourceUnavailable(f"usage source is unreadable: {path}") from exc

    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise UsageSourceUnavailable(
                f"usage source contains corrupt JSONL at line {line_number}: {path}"
            ) from exc
        if not isinstance(value, dict):
            raise UsageSourceUnavailable(
                f"usage source contains a non-object record at line {line_number}: {path}"
            )
        _parse_executed_at(value)
        records.append(value)
    return records


def _count_records(
    records: list[dict[str, Any]],
    *,
    execution_kind: str,
    start: datetime,
    end: datetime,
    provider_id: str | None = None,
    status: str,
) -> int:
    count = 0
    for record in records:
        if provider_id is not None and record.get("provider_id") != provider_id:
            continue
        if record.get("status") != status:
            continue
        if record.get("execution_kind") != execution_kind:
            continue
        executed_at = _parse_executed_at(record)
        if start <= executed_at <= end:
            count += 1
    return count


def _parse_executed_at(record: dict[str, Any]) -> datetime:
    raw = record.get("executed_at")
    if not isinstance(raw, str) or not raw.strip():
        raise UsageSourceUnavailable("usage source record is missing executed_at")
    try:
        return _to_utc(datetime.fromisoformat(raw.strip().replace("Z", "+00:00")))
    except ValueError as exc:
        raise UsageSourceUnavailable(
            f"usage source record has invalid executed_at: {raw!r}"
        ) from exc


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
