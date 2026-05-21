"""Cadence helper tests for the social-autonomy tick service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from src.ham.social_autonomy.tick import (
    cadence_due_state,
    is_cadence_due,
    next_run_at_for,
)


def test_social_autonomy_cadence_manual_requires_run_once_flag() -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)

    assert is_cadence_due("manual", None, now, run_once=False) is False
    assert is_cadence_due("manual", now - timedelta(days=1), now, run_once=True) is True


def test_social_autonomy_cadence_hourly_first_run_is_due() -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)

    assert is_cadence_due("hourly", None, now) is True


def test_social_autonomy_cadence_hourly_boundary_is_inclusive() -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)

    assert is_cadence_due("hourly", now - timedelta(minutes=30), now) is False
    assert is_cadence_due("hourly", now - timedelta(minutes=59), now) is False
    assert is_cadence_due("hourly", now - timedelta(minutes=60), now) is True
    assert is_cadence_due("hourly", now - timedelta(minutes=61), now) is True


def test_social_autonomy_cadence_daily_first_run_is_due() -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)

    assert is_cadence_due("daily", None, now, profile_timezone="America/New_York") is True


def test_social_autonomy_cadence_daily_uses_profile_timezone_dates() -> None:
    last_run_at = datetime.fromisoformat("2026-05-20T23:00:00-04:00")

    assert (
        is_cadence_due(
            "daily",
            last_run_at,
            datetime.fromisoformat("2026-05-20T23:59:00-04:00"),
            profile_timezone="America/New_York",
        )
        is False
    )
    assert (
        is_cadence_due(
            "daily",
            last_run_at,
            datetime.fromisoformat("2026-05-21T00:30:00-04:00"),
            profile_timezone="America/New_York",
        )
        is True
    )


def test_social_autonomy_cadence_unknown_string_fails_closed() -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)

    assert is_cadence_due("bi-monthly", None, now) is False


def test_social_autonomy_next_run_at_for_hourly_and_daily() -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)

    assert next_run_at_for("hourly", now) == now + timedelta(hours=1)
    assert next_run_at_for("manual", now) is None
    assert next_run_at_for("bi-monthly", now) is None
    assert next_run_at_for("daily", now, profile_timezone="America/New_York") == datetime(
        2026,
        5,
        21,
        0,
        0,
        tzinfo=ZoneInfo("America/New_York"),
    )


def test_social_autonomy_cadence_due_state_includes_next_run_at() -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    last_run_at = now - timedelta(minutes=10)

    state = cadence_due_state("hourly", last_run_at, now)

    assert state.due is False
    assert state.next_run_at == last_run_at + timedelta(hours=1)
