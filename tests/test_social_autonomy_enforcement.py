"""Pure enforcement-helper tests for GoHAM Social autonomy profiles."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import src.ham.social_autonomy.enforcement as enforcement
from src.ham.social_autonomy.enforcement import (
    AUTONOMY_ACTION_NOT_ALLOWED,
    AUTONOMY_APPLY_REASON_CODES,
    AUTONOMY_CHANNEL_DISABLED,
    AUTONOMY_DAILY_CAP_EXCEEDED,
    AUTONOMY_EMERGENCY_STOP,
    AUTONOMY_PROFILE_NOT_RUNNING,
    AUTONOMY_QUIET_HOURS_ACTIVE,
    autonomy_reasons_for_apply,
)
from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import read_social_autonomy_profile


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    created_at = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    payload: dict[str, Any] = {
        "profile_id": "profile-1",
        "status": "running",
        "goal": "Grow awareness for HAM safely.",
        "persona_id": "ham-canonical",
        "channels": {
            "x": {"enabled": True, "available": True},
            "telegram": {"enabled": True, "available": True},
            "discord": {"enabled": False, "available": False},
        },
        "actions_allowed_per_channel": {
            "x": ["reply", "broadcast"],
            "telegram": ["message", "activity"],
            "discord": [],
        },
        "daily_caps": {"x": 3, "telegram": 2, "discord": 0},
        "cadence": "daily",
        "quiet_hours": None,
        "forbidden_topics": ["politics"],
        "safety_rules": ["no spam", "no financial promises"],
        "learning_enabled": True,
        "emergency_stop": False,
        "created_at": created_at,
        "updated_at": created_at,
    }
    payload.update(overrides)
    return payload


def _profile(**overrides: Any) -> GoHamSocialProfile:
    return GoHamSocialProfile.model_validate(_profile_payload(**overrides))


def test_permissive_returns_empty() -> None:
    reasons = autonomy_reasons_for_apply(_profile(), channel="x", action="reply")

    assert reasons == []


@pytest.mark.parametrize("status", ["draft", "paused", "stopped"])
def test_not_running_returns_profile_not_running(status: str) -> None:
    reasons = autonomy_reasons_for_apply(_profile(status=status), channel="x", action="reply")

    assert AUTONOMY_PROFILE_NOT_RUNNING in reasons


@pytest.mark.parametrize(
    "channels",
    [
        {"x": {"enabled": False, "available": True}},
        {"telegram": {"enabled": True, "available": True}},
    ],
)
def test_channel_disabled_returns_channel_disabled(channels: dict[str, Any]) -> None:
    profile = _profile(channels=channels)

    reasons = autonomy_reasons_for_apply(profile, channel="x", action="reply")

    assert AUTONOMY_CHANNEL_DISABLED in reasons


def test_action_not_allowed_returns_action_not_allowed() -> None:
    profile = _profile(actions_allowed_per_channel={"x": ["broadcast"]})

    reasons = autonomy_reasons_for_apply(profile, channel="x", action="reply")

    assert AUTONOMY_ACTION_NOT_ALLOWED in reasons


def test_emergency_stop_returns_emergency_stop_first() -> None:
    profile = _profile(
        status="running",
        emergency_stop=True,
        channels={"x": {"enabled": False, "available": True}},
        actions_allowed_per_channel={"x": []},
        daily_caps={"x": 0},
    )

    reasons = autonomy_reasons_for_apply(profile, channel="x", action="reply")

    assert reasons[0] == AUTONOMY_EMERGENCY_STOP
    assert AUTONOMY_PROFILE_NOT_RUNNING in reasons
    assert AUTONOMY_CHANNEL_DISABLED in reasons
    assert AUTONOMY_ACTION_NOT_ALLOWED in reasons
    assert AUTONOMY_DAILY_CAP_EXCEEDED in reasons


def test_daily_cap_exceeded_returns_daily_cap_exceeded() -> None:
    reasons = autonomy_reasons_for_apply(_profile(daily_caps={"x": 0}), channel="x", action="reply")

    assert AUTONOMY_DAILY_CAP_EXCEEDED in reasons


def test_quiet_hours_active_returns_quiet_hours_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        enforcement,
        "_now_utc",
        lambda: datetime(2026, 5, 20, 23, 0, tzinfo=UTC),
    )
    profile = _profile(quiet_hours={"start_hour": 22, "end_hour": 6, "timezone": "UTC"})

    reasons = autonomy_reasons_for_apply(profile, channel="x", action="reply")

    assert AUTONOMY_QUIET_HOURS_ACTIVE in reasons


def test_quiet_hours_inactive_does_not_block(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        enforcement,
        "_now_utc",
        lambda: datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
    )
    profile = _profile(quiet_hours={"start_hour": 22, "end_hour": 6, "timezone": "UTC"})

    reasons = autonomy_reasons_for_apply(profile, channel="x", action="reply")

    assert AUTONOMY_QUIET_HOURS_ACTIVE not in reasons
    assert reasons == []


def test_order_and_dedup_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        enforcement,
        "_now_utc",
        lambda: datetime(2026, 5, 20, 23, 0, tzinfo=UTC),
    )
    profile = _profile(
        status="running",
        emergency_stop=True,
        channels={"x": {"enabled": False, "available": True}},
        actions_allowed_per_channel={"x": []},
        daily_caps={"x": 0},
        quiet_hours={"start_hour": 22, "end_hour": 6, "timezone": "UTC"},
    )

    reasons_a = autonomy_reasons_for_apply(profile, channel="x", action="reply")
    reasons_b = autonomy_reasons_for_apply(profile, channel="x", action="reply")

    assert reasons_a == reasons_b
    assert reasons_a == [
        AUTONOMY_EMERGENCY_STOP,
        AUTONOMY_PROFILE_NOT_RUNNING,
        AUTONOMY_CHANNEL_DISABLED,
        AUTONOMY_ACTION_NOT_ALLOWED,
        AUTONOMY_DAILY_CAP_EXCEEDED,
        AUTONOMY_QUIET_HOURS_ACTIVE,
    ]
    assert len(reasons_a) == len(set(reasons_a))
    assert set(reasons_a).issubset(set(AUTONOMY_APPLY_REASON_CODES))


@pytest.mark.parametrize(
    ("channel", "action"),
    [
        ("x", "reply"),
        ("telegram", "message"),
        ("discord", "message"),
    ],
)
def test_draft_default_safe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    channel: str,
    action: str,
) -> None:
    target = tmp_path / "profile.json"
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(target))

    profile = read_social_autonomy_profile(tmp_path)
    reasons = autonomy_reasons_for_apply(profile, channel=channel, action=action)  # type: ignore[arg-type]

    assert not target.exists()
    assert reasons[0] == AUTONOMY_PROFILE_NOT_RUNNING


def test_helper_source_has_no_env_file_or_transport_imports() -> None:
    source_path = Path(enforcement.__file__).resolve()
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden_roots = {
        "dotenv",
        "httpx",
        "os",
        "pathlib",
        "requests",
        "socket",
        "urllib",
    }

    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.partition(".")[0])

    assert imported_roots.isdisjoint(forbidden_roots)
