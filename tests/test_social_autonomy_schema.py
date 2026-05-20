"""Schema-level tests for the GoHAM Social autonomy profile."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from src.ham.social_autonomy.schema import GoHamSocialProfile


def _minimum_payload(**overrides: Any) -> dict[str, Any]:
    created_at = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    payload: dict[str, Any] = {
        "profile_id": "profile-1",
        "status": "draft",
        "goal": "Build a useful, safe social presence for HAM.",
        "persona_id": "ham-canonical",
        "channels": {
            "x": {"enabled": True, "available": True},
            "telegram": {"enabled": False, "available": True},
            "discord": {"enabled": False, "available": False},
        },
        "actions_allowed_per_channel": {
            "x": ["reply", "broadcast"],
            "telegram": ["message", "activity"],
            "discord": [],
        },
        "daily_caps": {"x": 3, "telegram": 1, "discord": 0},
        "cadence": "daily",
        "forbidden_topics": ["politics"],
        "safety_rules": ["no financial advice"],
        "learning_enabled": True,
        "emergency_stop": False,
        "created_at": created_at,
        "updated_at": created_at,
    }
    payload.update(overrides)
    return payload


def test_minimum_valid_payload_round_trips_through_model_dump() -> None:
    profile = GoHamSocialProfile.model_validate(_minimum_payload())

    dumped = profile.model_dump(mode="json")

    assert profile == GoHamSocialProfile.model_validate(dumped)


def test_extra_forbid_rejects_unknown_top_level_fields() -> None:
    payload = _minimum_payload(unknown_field=True)

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        GoHamSocialProfile.model_validate(payload)


@pytest.mark.parametrize("bad_status", ["armed", "off", "", "Running"])
def test_status_literal_rejects_values_outside_allowed_set(bad_status: str) -> None:
    payload = _minimum_payload(status=bad_status)

    with pytest.raises(ValidationError):
        GoHamSocialProfile.model_validate(payload)


def test_channels_keys_reject_unknown_and_accept_discord_unavailable_slot() -> None:
    payload = _minimum_payload(channels={"slack": {"enabled": True, "available": True}})
    with pytest.raises(ValidationError):
        GoHamSocialProfile.model_validate(payload)

    profile = GoHamSocialProfile.model_validate(
        _minimum_payload(
            channels={
                "x": {"enabled": True, "available": True},
                "telegram": {"enabled": True, "available": True},
                "discord": {"enabled": True, "available": True},
            }
        )
    )
    assert set(profile.channels) == {"x", "telegram", "discord"}
    assert profile.channels["discord"].available is False
    assert profile.channels["discord"].enabled is False


def test_action_literals_reject_unknown_actions() -> None:
    payload = _minimum_payload(
        actions_allowed_per_channel={"x": ["reply", "shitpost"], "telegram": ["message"]}
    )

    with pytest.raises(ValidationError):
        GoHamSocialProfile.model_validate(payload)

    profile = GoHamSocialProfile.model_validate(
        _minimum_payload(
            actions_allowed_per_channel={
                "x": ["reply", "broadcast", "reply"],
                "telegram": ["message", "activity"],
            }
        )
    )
    assert profile.actions_allowed_per_channel["x"] == ["reply", "broadcast"]


@pytest.mark.parametrize("bad_cap", [-1, "five", 1.5])
def test_daily_caps_nonnegative_strict_ints_reject_invalid_values(bad_cap: object) -> None:
    payload = _minimum_payload(daily_caps={"x": bad_cap})

    with pytest.raises(ValidationError):
        GoHamSocialProfile.model_validate(payload)


def test_quiet_hours_optional_and_validates_hour_range() -> None:
    without_quiet_hours = GoHamSocialProfile.model_validate(_minimum_payload())
    assert without_quiet_hours.quiet_hours is None

    with_quiet_hours = GoHamSocialProfile.model_validate(
        _minimum_payload(quiet_hours={"start_hour": 22, "end_hour": 6, "timezone": "UTC"})
    )
    assert with_quiet_hours.quiet_hours is not None
    assert with_quiet_hours.quiet_hours.start_hour == 22

    with pytest.raises(ValidationError):
        GoHamSocialProfile.model_validate(
            _minimum_payload(quiet_hours={"start_hour": 24, "end_hour": 6, "timezone": "UTC"})
        )
    with pytest.raises(ValidationError):
        GoHamSocialProfile.model_validate(
            _minimum_payload(quiet_hours={"start_hour": 22, "end_hour": -1, "timezone": "UTC"})
        )


@pytest.mark.parametrize("source_status", ["draft", "running", "paused"])
def test_emergency_stop_status_coerce_forces_stopped(source_status: str) -> None:
    profile = GoHamSocialProfile.model_validate(
        _minimum_payload(status=source_status, emergency_stop=True)
    )

    assert profile.emergency_stop is True
    assert profile.status == "stopped"


def test_timestamps_monotonic_rejects_updated_at_before_created_at() -> None:
    created_at = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)

    with pytest.raises(ValidationError, match="updated_at"):
        GoHamSocialProfile.model_validate(
            _minimum_payload(
                created_at=created_at,
                updated_at=created_at - timedelta(seconds=1),
            )
        )


def test_optional_scoping_defaults_workspace_and_project_to_none() -> None:
    profile = GoHamSocialProfile.model_validate(_minimum_payload())

    assert profile.workspace_id is None
    assert profile.project_id is None
    assert profile.model_dump(mode="json")["workspace_id"] is None
    assert profile.model_dump(mode="json")["project_id"] is None
