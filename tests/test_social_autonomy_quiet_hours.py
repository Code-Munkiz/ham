"""Quiet-hours helper tests for the social-autonomy tick service."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.ham.social_autonomy.schema import QuietHours
from src.ham.social_autonomy.tick import is_quiet_hours_active


def test_social_autonomy_quiet_hours_none_never_active() -> None:
    assert is_quiet_hours_active(None, datetime(2026, 5, 20, 12, 0, tzinfo=UTC)) is False


def test_social_autonomy_quiet_hours_non_wrap_window_active() -> None:
    quiet_hours = {"start_hour": 9, "end_hour": 17, "timezone": "UTC"}

    assert is_quiet_hours_active(quiet_hours, datetime(2026, 5, 20, 12, 0, tzinfo=UTC)) is True


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 5, 20, 9, 0, tzinfo=UTC), True),
        (datetime(2026, 5, 20, 16, 59, tzinfo=UTC), True),
        (datetime(2026, 5, 20, 17, 0, tzinfo=UTC), False),
    ],
)
def test_social_autonomy_quiet_hours_half_open_interval(now: datetime, expected: bool) -> None:
    quiet_hours = QuietHours(start_hour=9, end_hour=17, timezone="UTC")

    assert is_quiet_hours_active(quiet_hours, now) is expected


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (23, True),
        (3, True),
        (6, False),
        (7, False),
        (21, False),
        (22, True),
    ],
)
def test_social_autonomy_quiet_hours_wrap_midnight(hour: int, expected: bool) -> None:
    quiet_hours = {"start_hour": 22, "end_hour": 6, "timezone": "UTC"}

    assert (
        is_quiet_hours_active(quiet_hours, datetime(2026, 5, 20, hour, 0, tzinfo=UTC)) is expected
    )


def test_social_autonomy_quiet_hours_uses_profile_timezone() -> None:
    quiet_hours = {"start_hour": 22, "end_hour": 6, "timezone": "America/New_York"}

    assert is_quiet_hours_active(quiet_hours, datetime(2026, 5, 20, 5, 0, tzinfo=UTC)) is True
    assert is_quiet_hours_active(quiet_hours, datetime(2026, 5, 20, 12, 0, tzinfo=UTC)) is False
