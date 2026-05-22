"""Tests for fail-closed social-autonomy usage counters."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.ham.ham_x.goham_policy import GOHAM_EXECUTION_KIND
from src.ham.ham_x.reactive_governor import GOHAM_REACTIVE_EXECUTION_KIND
from src.ham.social_autonomy.usage import UsageSourceUnavailable, count_actions_in_window
from src.ham.social_telegram_activity import TELEGRAM_ACTIVITY_EXECUTION_KIND
from src.ham.social_telegram_reactive import TELEGRAM_REACTIVE_REPLY_EXECUTION_KIND
from src.ham.social_telegram_send import TELEGRAM_EXECUTION_KIND


def _append_jsonl(path: Path, *rows: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _x_row(
    *,
    execution_kind: str = GOHAM_REACTIVE_EXECUTION_KIND,
    executed_at: str = "2026-05-20T12:00:00Z",
    status: str = "executed",
) -> dict[str, object]:
    return {
        "action_id": "x-action",
        "action_type": "reply",
        "execution_kind": execution_kind,
        "executed_at": executed_at,
        "status": status,
    }


def _telegram_row(
    *,
    execution_kind: str = TELEGRAM_EXECUTION_KIND,
    executed_at: str = "2026-05-20T12:00:00Z",
    provider_id: str = "telegram",
    status: str = "sent",
) -> dict[str, object]:
    return {
        "provider_id": provider_id,
        "execution_kind": execution_kind,
        "executed_at": executed_at,
        "status": status,
    }


def test_social_autonomy_usage_x_counts_only_matching_kind_and_window(tmp_path: Path) -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    journal = tmp_path / "execution_journal.jsonl"
    _append_jsonl(
        journal,
        _x_row(execution_kind=GOHAM_REACTIVE_EXECUTION_KIND, executed_at="2026-05-20T11:59:00Z"),
        _x_row(execution_kind=GOHAM_EXECUTION_KIND, executed_at="2026-05-20T11:58:00Z"),
        _x_row(execution_kind=GOHAM_REACTIVE_EXECUTION_KIND, executed_at="2026-05-19T11:59:59Z"),
        _x_row(
            execution_kind=GOHAM_REACTIVE_EXECUTION_KIND,
            executed_at="2026-05-20T11:57:00Z",
            status="blocked",
        ),
    )

    assert count_actions_in_window("x", "reply", now, journal_path=journal) == 1


def test_social_autonomy_usage_x_action_discriminator(tmp_path: Path) -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    journal = tmp_path / "execution_journal.jsonl"
    _append_jsonl(
        journal,
        _x_row(execution_kind=GOHAM_REACTIVE_EXECUTION_KIND),
        _x_row(execution_kind=GOHAM_EXECUTION_KIND),
    )

    assert count_actions_in_window("x", "reply", now, journal_path=journal) == 1
    assert count_actions_in_window("x", "broadcast", now, journal_path=journal) == 1


def test_social_autonomy_usage_x_default_path_comes_from_ham_x_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.ham.social_autonomy.usage as usage

    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    journal = tmp_path / "producer-default" / "execution_journal.jsonl"
    _append_jsonl(journal, _x_row(execution_kind=GOHAM_REACTIVE_EXECUTION_KIND))
    monkeypatch.setattr(
        usage,
        "load_ham_x_config",
        lambda: SimpleNamespace(execution_journal_path=journal),
        raising=False,
    )

    assert usage.count_actions_in_window("x", "reply", now) == 1


def test_social_autonomy_usage_telegram_counts_only_sent_matching_provider_kind_and_window(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    delivery_log = tmp_path / "delivery_log.jsonl"
    _append_jsonl(
        delivery_log,
        _telegram_row(execution_kind=TELEGRAM_EXECUTION_KIND, executed_at="2026-05-20T11:59:00Z"),
        _telegram_row(
            execution_kind=TELEGRAM_ACTIVITY_EXECUTION_KIND, executed_at="2026-05-20T11:58:00Z"
        ),
        _telegram_row(execution_kind=TELEGRAM_EXECUTION_KIND, executed_at="2026-05-19T11:59:59Z"),
        _telegram_row(
            execution_kind=TELEGRAM_EXECUTION_KIND,
            executed_at="2026-05-20T11:57:00Z",
            provider_id="slack",
        ),
        _telegram_row(
            execution_kind=TELEGRAM_EXECUTION_KIND,
            executed_at="2026-05-20T11:56:00Z",
            status="blocked",
        ),
    )

    assert count_actions_in_window("telegram", "message", now, delivery_log_path=delivery_log) == 1


@pytest.mark.parametrize(
    ("action", "execution_kind"),
    [
        ("message", TELEGRAM_EXECUTION_KIND),
        ("activity", TELEGRAM_ACTIVITY_EXECUTION_KIND),
        ("reply", TELEGRAM_REACTIVE_REPLY_EXECUTION_KIND),
    ],
)
def test_social_autonomy_usage_telegram_action_discriminator(
    tmp_path: Path,
    action: str,
    execution_kind: str,
) -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    delivery_log = tmp_path / "delivery_log.jsonl"
    _append_jsonl(
        delivery_log,
        _telegram_row(execution_kind=TELEGRAM_EXECUTION_KIND),
        _telegram_row(execution_kind=TELEGRAM_ACTIVITY_EXECUTION_KIND),
        _telegram_row(execution_kind=TELEGRAM_REACTIVE_REPLY_EXECUTION_KIND),
    )

    assert count_actions_in_window("telegram", action, now, delivery_log_path=delivery_log) == 1
    assert execution_kind


def test_social_autonomy_usage_telegram_default_path_comes_from_delivery_log_module(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.ham.social_autonomy.usage as usage

    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    delivery_log = tmp_path / "producer-default" / "delivery_log.jsonl"
    _append_jsonl(delivery_log, _telegram_row(execution_kind=TELEGRAM_EXECUTION_KIND))
    monkeypatch.setattr(
        usage.social_delivery_log,
        "default_delivery_log_path",
        lambda: delivery_log,
        raising=False,
    )

    assert usage.count_actions_in_window("telegram", "message", now) == 1


def test_social_autonomy_usage_timezone_aware_window_and_inclusive_edge(tmp_path: Path) -> None:
    now = datetime.fromisoformat("2026-05-20T00:30:00-04:00")
    journal = tmp_path / "execution_journal.jsonl"
    _append_jsonl(
        journal,
        _x_row(executed_at="2026-05-19T22:00:00-04:00"),
        _x_row(executed_at="2026-05-19T00:30:00-04:00"),
        _x_row(executed_at="2026-05-19T00:29:59-04:00"),
    )

    assert count_actions_in_window("x", "reply", now, journal_path=journal) == 2


def test_social_autonomy_usage_missing_x_source_returns_zero(tmp_path: Path) -> None:
    assert (
        count_actions_in_window(
            "x",
            "reply",
            datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
            journal_path=tmp_path / "missing.jsonl",
        )
        == 0
    )


def test_social_autonomy_usage_missing_telegram_source_returns_zero(tmp_path: Path) -> None:
    assert (
        count_actions_in_window(
            "telegram",
            "message",
            datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
            delivery_log_path=tmp_path / "missing.jsonl",
        )
        == 0
    )


def test_social_autonomy_usage_corrupt_x_record_raises(tmp_path: Path) -> None:
    journal = tmp_path / "execution_journal.jsonl"
    journal.write_text("{not-json\n", encoding="utf-8")

    with pytest.raises(UsageSourceUnavailable):
        count_actions_in_window(
            "x",
            "reply",
            datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
            journal_path=journal,
        )


def test_social_autonomy_usage_corrupt_telegram_record_raises(tmp_path: Path) -> None:
    delivery_log = tmp_path / "delivery_log.jsonl"
    delivery_log.write_text("{not-json\n", encoding="utf-8")

    with pytest.raises(UsageSourceUnavailable):
        count_actions_in_window(
            "telegram",
            "message",
            datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
            delivery_log_path=delivery_log,
        )


@pytest.mark.parametrize(
    ("channel", "action", "path_kwarg"),
    [
        ("x", "reply", "journal_path"),
        ("telegram", "message", "delivery_log_path"),
    ],
)
def test_social_autonomy_usage_non_utf8_source_raises_usage_source_unavailable(
    tmp_path: Path,
    channel: str,
    action: str,
    path_kwarg: str,
) -> None:
    source = tmp_path / f"{channel}.jsonl"
    source.write_bytes(b"\xff\xfe\x00not utf8")

    with pytest.raises(UsageSourceUnavailable):
        count_actions_in_window(
            channel,
            action,
            datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
            **{path_kwarg: source},
        )


def test_social_autonomy_usage_discord_unavailable() -> None:
    with pytest.raises(UsageSourceUnavailable, match="discord usage tracking is unavailable"):
        count_actions_in_window("discord", "message", datetime(2026, 5, 20, 12, 0, tzinfo=UTC))


def test_social_autonomy_usage_custom_window_seconds(tmp_path: Path) -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    delivery_log = tmp_path / "delivery_log.jsonl"
    _append_jsonl(
        delivery_log,
        _telegram_row(executed_at="2026-05-20T11:59:00Z"),
        _telegram_row(executed_at="2026-05-20T11:58:59Z"),
    )

    assert (
        count_actions_in_window(
            "telegram",
            "message",
            now,
            window_seconds=60,
            delivery_log_path=delivery_log,
        )
        == 1
    )
