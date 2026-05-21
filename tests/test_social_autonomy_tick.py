"""End-to-end tests for the GoHAM Social autonomy tick service."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import (
    apply_social_autonomy_profile,
    read_social_autonomy_profile,
    social_autonomy_path,
)
from src.ham.social_autonomy.usage import UsageSourceUnavailable

_TOKEN = "autonomy-write-token"  # noqa: S105
_NOW = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    created_at = _NOW - timedelta(days=1)
    payload: dict[str, Any] = {
        "profile_id": "profile-1",
        "workspace_id": "workspace-1",
        "project_id": "project-1",
        "status": "running",
        "goal": "Grow awareness for HAM safely.",
        "persona_id": "ham-canonical",
        "channels": {
            "x": {"enabled": True, "available": True},
        },
        "actions_allowed_per_channel": {
            "x": ["reply", "broadcast"],
        },
        "daily_caps": {"x": 3},
        "cadence": "hourly",
        "quiet_hours": None,
        "forbidden_topics": [],
        "safety_rules": [],
        "learning_enabled": False,
        "emergency_stop": False,
        "created_at": created_at,
        "updated_at": created_at,
    }
    payload.update(overrides)
    return payload


def _profile(**overrides: Any) -> GoHamSocialProfile:
    return GoHamSocialProfile.model_validate(_profile_payload(**overrides))


def _zero_usage(channel: str, action: str, now: datetime) -> int:
    assert channel
    assert action
    assert now == _NOW
    return 0


def _allowing_content_guard(*_args: Any, **_kwargs: Any) -> list[str]:
    return []


def _production_content_guard(
    profile: GoHamSocialProfile,
    *,
    channel: str,
    action: str,
    payload: str,
    now: datetime,
) -> list[str]:
    from src.ham.social_autonomy.content_guards import collect_content_guard_reasons

    return collect_content_guard_reasons(
        payload,
        topic=f"{channel}:{action}",
        payload_summary=payload,
        forbidden_topics=profile.forbidden_topics,
        safety_rules=profile.safety_rules,
        now=now,
    )


def _configure_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target = tmp_path / "profile.json"
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(target))
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    return target


def _seed_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    profile: GoHamSocialProfile,
) -> Path:
    target = _configure_store(monkeypatch, tmp_path)
    apply_social_autonomy_profile(tmp_path, profile, token=_TOKEN, actor="pytest-seed")
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", raising=False)
    return target


def _audit_files(tmp_path: Path) -> list[Path]:
    audit_dir = tmp_path / "_audit" / "social_autonomy"
    return sorted(audit_dir.glob("*.json")) if audit_dir.exists() else []


def test_all_blocked_reason_constants_are_exported() -> None:
    import src.ham.social_autonomy.tick as tick

    expected = {
        "AUTONOMY_PROFILE_MISSING": "autonomy_profile_missing",
        "AUTONOMY_PROFILE_NOT_RUNNING": "autonomy_profile_not_running",
        "AUTONOMY_EMERGENCY_STOP": "autonomy_emergency_stop",
        "AUTONOMY_CHANNEL_DISABLED": "autonomy_channel_disabled",
        "AUTONOMY_CHANNEL_UNAVAILABLE": "autonomy_channel_unavailable",
        "AUTONOMY_ACTION_NOT_ALLOWED": "autonomy_action_not_allowed",
        "AUTONOMY_QUIET_HOURS_ACTIVE": "autonomy_quiet_hours_active",
        "AUTONOMY_CADENCE_NOT_DUE": "autonomy_cadence_not_due",
        "AUTONOMY_CAP_ZERO": "autonomy_cap_zero",
        "AUTONOMY_CAP_EXCEEDED": "autonomy_cap_exceeded",
        "AUTONOMY_CAP_TRACKING_UNAVAILABLE": "autonomy_cap_tracking_unavailable",
        "AUTONOMY_FORBIDDEN_TOPIC_MATCHED": "autonomy_forbidden_topic_matched",
        "AUTONOMY_SAFETY_RULE_VIOLATION": "autonomy_safety_rule_violation",
        "AUTONOMY_SAFETY_RULE_UNENFORCED": "autonomy_safety_rule_unenforced",
        "AUTONOMY_PAYLOAD_EMPTY_OR_TOO_SHORT": "autonomy_payload_empty_or_too_short",
    }

    assert {name: getattr(tick, name) for name in expected} == expected
    assert tick.BLOCKED_REASON_CODES == tuple(expected.values())


def test_plan_is_pure_and_missing_profile_default_denies(tmp_path: Path) -> None:
    from src.ham.social_autonomy.tick import (
        AUTONOMY_PROFILE_MISSING,
        plan_social_autonomy_tick,
    )

    before = sorted(tmp_path.rglob("*"))

    result = plan_social_autonomy_tick(
        None,
        now=_NOW,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
    )

    assert result.ran is False
    assert result.actions_taken == []
    assert result.blocked_reasons == [AUTONOMY_PROFILE_MISSING]
    assert sorted(tmp_path.rglob("*")) == before


@pytest.mark.parametrize("status", ["draft", "paused", "stopped"])
def test_status_not_running_blocks(status: str) -> None:
    from src.ham.social_autonomy.tick import (
        AUTONOMY_PROFILE_NOT_RUNNING,
        plan_social_autonomy_tick,
    )

    result = plan_social_autonomy_tick(
        _profile(status=status),
        now=_NOW,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
    )

    assert result.ran is False
    assert result.blocked_reasons == [AUTONOMY_PROFILE_NOT_RUNNING]
    assert result.profile_status == status


def test_emergency_stop_preempts_status_gate() -> None:
    from src.ham.social_autonomy.tick import (
        AUTONOMY_EMERGENCY_STOP,
        plan_social_autonomy_tick,
    )

    result = plan_social_autonomy_tick(
        _profile(emergency_stop=True),
        now=_NOW,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
    )

    assert result.ran is False
    assert result.blocked_reasons == [AUTONOMY_EMERGENCY_STOP]
    assert result.profile_status == "stopped"


def test_channel_disabled_blocks_without_usage_call() -> None:
    from src.ham.social_autonomy.tick import (
        AUTONOMY_CHANNEL_DISABLED,
        plan_social_autonomy_tick,
    )

    calls: list[tuple[str, str]] = []

    def usage_counter(channel: str, action: str, now: datetime) -> int:
        calls.append((channel, action))
        assert now
        return 0

    result = plan_social_autonomy_tick(
        _profile(channels={"x": {"enabled": False, "available": True}}),
        now=_NOW,
        usage_counter=usage_counter,
        content_guard=_allowing_content_guard,
    )

    assert result.ran is False
    assert result.blocked_reasons == [AUTONOMY_CHANNEL_DISABLED]
    assert calls == []


def test_discord_channel_unavailable_is_distinct_from_disabled() -> None:
    from src.ham.social_autonomy.tick import (
        AUTONOMY_CHANNEL_DISABLED,
        AUTONOMY_CHANNEL_UNAVAILABLE,
        plan_social_autonomy_tick,
    )

    profile = _profile(
        channels={"discord": {"enabled": True, "available": True}},
        actions_allowed_per_channel={"discord": ["message"]},
        daily_caps={"discord": 1},
    )

    result = plan_social_autonomy_tick(
        profile,
        now=_NOW,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
    )

    assert result.ran is False
    assert result.blocked_reasons == [AUTONOMY_CHANNEL_UNAVAILABLE]
    assert AUTONOMY_CHANNEL_DISABLED not in result.blocked_reasons


def test_action_not_allowed_blocks_candidate_actions() -> None:
    from src.ham.social_autonomy.tick import (
        AUTONOMY_ACTION_NOT_ALLOWED,
        plan_social_autonomy_tick,
    )

    result = plan_social_autonomy_tick(
        _profile(actions_allowed_per_channel={"x": []}),
        now=_NOW,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
    )

    assert result.ran is False
    assert result.blocked_reasons == [AUTONOMY_ACTION_NOT_ALLOWED]
    assert "x:reply" in result.actions_considered
    assert "x:broadcast" in result.actions_considered


def test_quiet_hours_and_cadence_gates_block_before_caps() -> None:
    from src.ham.social_autonomy.tick import (
        AUTONOMY_CADENCE_NOT_DUE,
        AUTONOMY_QUIET_HOURS_ACTIVE,
        plan_social_autonomy_tick,
    )

    calls = 0

    def usage_counter(channel: str, action: str, now: datetime) -> int:
        nonlocal calls
        calls += 1
        assert channel
        assert action
        assert now
        return 0

    quiet = plan_social_autonomy_tick(
        _profile(quiet_hours={"start_hour": 11, "end_hour": 13, "timezone": "UTC"}),
        now=_NOW,
        usage_counter=usage_counter,
        content_guard=_allowing_content_guard,
    )
    cadence = plan_social_autonomy_tick(
        _profile(last_run_at=_NOW - timedelta(minutes=10), updated_at=_NOW),
        now=_NOW,
        usage_counter=usage_counter,
        content_guard=_allowing_content_guard,
    )

    assert quiet.blocked_reasons == [AUTONOMY_QUIET_HOURS_ACTIVE]
    assert cadence.blocked_reasons == [AUTONOMY_CADENCE_NOT_DUE]
    assert calls == 0


def test_plan_requires_injected_usage_counter_and_content_guard() -> None:
    from src.ham.social_autonomy.tick import plan_social_autonomy_tick

    with pytest.raises(TypeError, match="usage_counter"):
        plan_social_autonomy_tick(
            _profile(),
            now=_NOW,
            usage_counter=None,
            content_guard=_allowing_content_guard,
        )

    with pytest.raises(TypeError, match="content_guard"):
        plan_social_autonomy_tick(
            _profile(),
            now=_NOW,
            usage_counter=_zero_usage,
            content_guard=None,
        )


def test_plan_with_counter_spy_never_falls_back_to_filesystem_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.ham.social_autonomy import usage
    from src.ham.social_autonomy.tick import plan_social_autonomy_tick

    def forbidden_filesystem_counter(*_args: Any, **_kwargs: Any) -> int:
        raise AssertionError("filesystem usage counter was invoked")

    monkeypatch.setattr(usage, "count_actions_in_window", forbidden_filesystem_counter)
    calls: list[tuple[str, str]] = []

    def counter_spy(channel: str, action: str, now: datetime) -> int:
        calls.append((channel, action))
        assert now == _NOW
        return 0

    result = plan_social_autonomy_tick(
        _profile(),
        now=_NOW,
        usage_counter=counter_spy,
        content_guard=_allowing_content_guard,
    )

    assert result.ran is True
    assert calls == [("x", "reply"), ("x", "broadcast")]


def test_caps_zero_exceeded_and_source_unavailable_block() -> None:
    from src.ham.social_autonomy.tick import (
        AUTONOMY_CAP_EXCEEDED,
        AUTONOMY_CAP_TRACKING_UNAVAILABLE,
        AUTONOMY_CAP_ZERO,
        plan_social_autonomy_tick,
    )

    cap_zero_calls: list[tuple[str, str]] = []

    def cap_zero_counter(channel: str, action: str, now: datetime) -> int:
        cap_zero_calls.append((channel, action))
        assert now
        return 0

    cap_zero = plan_social_autonomy_tick(
        _profile(daily_caps={"x": 0}),
        now=_NOW,
        usage_counter=cap_zero_counter,
        content_guard=_allowing_content_guard,
    )
    cap_exceeded = plan_social_autonomy_tick(
        _profile(daily_caps={"x": 3}),
        now=_NOW,
        usage_counter=lambda _channel, _action, _now: 3,
        content_guard=_allowing_content_guard,
    )

    def unavailable(_channel: str, _action: str, _now: datetime) -> int:
        raise UsageSourceUnavailable("missing usage source")

    cap_source = plan_social_autonomy_tick(
        _profile(daily_caps={"x": 3}),
        now=_NOW,
        usage_counter=unavailable,
        content_guard=_allowing_content_guard,
    )

    assert cap_zero.blocked_reasons == [AUTONOMY_CAP_ZERO]
    assert cap_zero_calls == []
    assert cap_exceeded.blocked_reasons == [AUTONOMY_CAP_EXCEEDED]
    assert cap_source.blocked_reasons == [AUTONOMY_CAP_TRACKING_UNAVAILABLE]


@pytest.mark.parametrize(
    ("profile", "reason"),
    [
        (
            _profile(forbidden_topics=["alpha leak"], goal="Discuss Alpha Leak prerelease."),
            "autonomy_forbidden_topic_matched",
        ),
        (
            _profile(safety_rules=["mass_tagging"], goal="@a @b @c @d @e @f hello"),
            "autonomy_safety_rule_violation",
        ),
        (
            _profile(safety_rules=["warning_about_thursday"]),
            "autonomy_safety_rule_unenforced",
        ),
        (
            _profile(safety_rules=["payload_min_length"], goal="hi"),
            "autonomy_payload_empty_or_too_short",
        ),
    ],
)
def test_content_guards_block(profile: GoHamSocialProfile, reason: str) -> None:
    from src.ham.social_autonomy.tick import plan_social_autonomy_tick

    result = plan_social_autonomy_tick(
        profile,
        now=_NOW,
        usage_counter=_zero_usage,
        content_guard=_production_content_guard,
    )

    assert result.ran is False
    assert result.blocked_reasons == [reason]


def test_happy_path_result_shape_and_deduped_reasons() -> None:
    from src.ham.social_autonomy.tick import SocialAutonomyTickResult, plan_social_autonomy_tick

    result = plan_social_autonomy_tick(
        _profile(),
        now=_NOW,
        usage_counter=_zero_usage,
        content_guard=lambda *_args, **_kwargs: [
            "autonomy_cap_exceeded",
            "autonomy_cap_exceeded",
        ],
    )

    assert result.ran is False
    assert result.blocked_reasons == ["autonomy_cap_exceeded"]
    assert SocialAutonomyTickResult.model_validate(result.model_dump()) == result
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SocialAutonomyTickResult.model_validate(
            {**result.model_dump(mode="json"), "extra_key": "not-allowed"}
        )

    happy = plan_social_autonomy_tick(
        _profile(),
        now=_NOW,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
    )
    assert happy.ran is True
    assert happy.dry_run is True
    assert happy.actions_taken == ["x:reply", "x:broadcast"]
    assert happy.blocked_reasons == []


def test_run_persists_profile_summary_and_learning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.ham.social_autonomy.tick import run_social_autonomy_tick

    target = _seed_profile(
        monkeypatch,
        tmp_path,
        _profile(learning_enabled=True),
    )
    audits_before = _audit_files(tmp_path)
    learning_path = tmp_path / "learning.jsonl"

    result = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_NOW,
        dry_run=True,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
        learning_store=learning_path,
    )

    persisted = read_social_autonomy_profile(tmp_path)
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert result.ran is True
    assert persisted.last_run_at == _NOW
    assert persisted.next_run_at == _NOW + timedelta(hours=1)
    assert persisted.last_tick_summary is not None
    assert persisted.last_tick_summary.blocked_reasons == result.blocked_reasons
    assert on_disk["last_tick_summary"]["actions_taken"] == ["x:reply", "x:broadcast"]
    assert len(_audit_files(tmp_path)) == len(audits_before) + 1
    assert learning_path.is_file()


def test_run_constructs_default_usage_counter_at_io_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.ham.social_autonomy import usage
    from src.ham.social_autonomy.tick import run_social_autonomy_tick

    journal = tmp_path / "producer-default" / "execution_journal.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        usage,
        "load_ham_x_config",
        lambda: SimpleNamespace(execution_journal_path=journal),
        raising=False,
    )
    _seed_profile(monkeypatch, tmp_path, _profile())

    result = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_NOW,
        dry_run=True,
        content_guard=_allowing_content_guard,
    )

    assert result.ran is True
    assert result.actions_taken == ["x:reply", "x:broadcast"]


def test_run_repeated_immediately_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.ham.social_autonomy.tick import AUTONOMY_CADENCE_NOT_DUE, run_social_autonomy_tick

    _seed_profile(monkeypatch, tmp_path, _profile())

    first = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_NOW,
        dry_run=True,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
    )
    second = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_NOW,
        dry_run=True,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
    )

    assert first.ran is True
    assert second.ran is False
    assert second.blocked_reasons == [AUTONOMY_CADENCE_NOT_DUE]


def test_corrupt_profile_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.ham.social_autonomy.tick import run_social_autonomy_tick

    target = _configure_store(monkeypatch, tmp_path)
    target.write_text("{not-json\n", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        run_social_autonomy_tick(store_path=tmp_path, now=_NOW)


def test_run_missing_profile_does_not_create_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.ham.social_autonomy.tick import (
        AUTONOMY_PROFILE_MISSING,
        run_social_autonomy_tick,
    )

    target = _configure_store(monkeypatch, tmp_path)
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", raising=False)

    result = run_social_autonomy_tick(store_path=tmp_path, now=_NOW)

    assert result.ran is False
    assert result.blocked_reasons == [AUTONOMY_PROFILE_MISSING]
    assert social_autonomy_path(tmp_path) == target
    assert not target.exists()
