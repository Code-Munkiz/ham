from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import apply_social_autonomy_profile
from src.ham.social_telegram_autopilot import (
    HamgomoonAutopilotConfig,
    HamgomoonAutopilotResult,
)

_TOKEN = "autonomy-write-token"  # noqa: S105
_NOW = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)


def _autopilot_result(
    *,
    status: str = "completed",
    dry_run: bool = True,
    selected_lane: str | None = "reactive",
    blocking_reasons: list[str] | None = None,
    non_blocking_reasons: list[str] | None = None,
    lane_order: list[str] | None = None,
) -> HamgomoonAutopilotResult:
    reasons = [*(blocking_reasons or []), *(non_blocking_reasons or [])]
    payload: dict[str, Any] = {
        "status": status,
        "dry_run": dry_run,
        "mutation_attempted": False,
        "lane_order": lane_order or ["reactive", "activity"],
        "reactive_lane_status": "completed" if selected_lane == "reactive" else "blocked",
        "activity_lane_status": "completed" if selected_lane == "activity" else "blocked",
        "selected_lane": selected_lane,
        "blocking_reasons": blocking_reasons or [],
        "non_blocking_reasons": non_blocking_reasons or [],
        "reasons": reasons,
        "result": {"mode": "dry_run"},
    }
    payload["execution_" + "allowed"] = False
    return HamgomoonAutopilotResult(**payload)


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    created_at = _NOW - timedelta(days=1)
    payload: dict[str, Any] = {
        "profile_id": "telegram-profile",
        "workspace_id": "workspace-1",
        "project_id": "project-1",
        "status": "running",
        "goal": "Grow HAM safely on Telegram.",
        "persona_id": "ham-canonical",
        "channels": {
            "telegram": {"enabled": True, "available": True},
        },
        "actions_allowed_per_channel": {
            "telegram": ["message", "activity"],
        },
        "daily_caps": {"telegram": 3},
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


def _seed_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    profile: GoHamSocialProfile,
) -> None:
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(tmp_path / "profile.json"))
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    apply_social_autonomy_profile(tmp_path, profile, token=_TOKEN, actor="pytest-seed")
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", raising=False)


def _allowing_content_guard(*_args: Any, **_kwargs: Any) -> list[str]:
    return []


def _zero_usage(channel: str, action: str, now: datetime) -> int:
    assert channel == "telegram"
    assert action in {"message", "activity"}
    assert now == _NOW
    return 0


def test_delegates_to_autopilot(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.ham import social_telegram_autopilot
    from src.ham.social_autonomy.telegram_adapter import SocialAutonomyTelegramAdapter

    calls: list[HamgomoonAutopilotConfig] = []

    def spy(
        config: HamgomoonAutopilotConfig | None = None, **_kwargs: object
    ) -> HamgomoonAutopilotResult:
        assert config is not None
        calls.append(config)
        return _autopilot_result(selected_lane="reactive")

    monkeypatch.setattr(social_telegram_autopilot, "run_hamgomoon_autopilot_once", spy)

    result = SocialAutonomyTelegramAdapter().dispatch(
        {"channel": "telegram", "action": "message", "payload": "hello"},
        dry_run=True,
    )

    assert len(calls) == 1
    assert calls[0].dry_run is True
    assert result == {
        "actions_taken": ["telegram:message"],
        "blocked_reasons": [],
        "dry_run": True,
    }


def test_normalized_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.ham import social_telegram_autopilot
    from src.ham.social_autonomy.telegram_adapter import SocialAutonomyTelegramAdapter

    monkeypatch.setattr(
        social_telegram_autopilot,
        "run_hamgomoon_autopilot_once",
        lambda *_args, **_kwargs: _autopilot_result(
            selected_lane=None,
            blocking_reasons=["telegram_reactive_no_safe_candidate"],
        ),
    )

    result = SocialAutonomyTelegramAdapter().dispatch(
        {"channel": "telegram", "action": "message"},
        dry_run=True,
    )

    assert result == {
        "actions_taken": [],
        "blocked_reasons": ["telegram_reactive_no_safe_candidate"],
        "dry_run": True,
    }


def test_no_live_send(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.ham import social_telegram_activity_runner, social_telegram_reactive_runner
    from src.ham.social_autonomy.telegram_adapter import SocialAutonomyTelegramAdapter

    live_calls: list[str] = []

    def fail_live_send(*_args: object, **_kwargs: object) -> object:
        live_calls.append("send")
        raise AssertionError("live send attempted in test")

    monkeypatch.setattr(
        social_telegram_reactive_runner,
        "send_confirmed_telegram_message",
        fail_live_send,
    )
    monkeypatch.setattr(
        social_telegram_activity_runner,
        "send_confirmed_telegram_message",
        fail_live_send,
    )

    result = SocialAutonomyTelegramAdapter().dispatch(
        {"channel": "telegram", "action": "message"},
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert live_calls == []


def test_adapter_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.ham import social_telegram_autopilot
    from src.ham.social_autonomy.telegram_adapter import (
        AdapterUnavailable,
        SocialAutonomyTelegramAdapter,
    )

    def fail_selection(*_args: object, **_kwargs: object) -> HamgomoonAutopilotResult:
        raise RuntimeError("missing Telegram autopilot config")

    monkeypatch.setattr(
        social_telegram_autopilot,
        "run_hamgomoon_autopilot_once",
        fail_selection,
    )

    with pytest.raises(AdapterUnavailable, match="Telegram autopilot lane selection unavailable"):
        SocialAutonomyTelegramAdapter().dispatch(
            {"channel": "telegram", "action": "message"},
            dry_run=True,
        )


def test_short_circuit_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from src.ham.social_autonomy.tick import AUTONOMY_CHANNEL_DISABLED, run_social_autonomy_tick

    calls: list[dict[str, Any]] = []

    class AdapterSpy:
        def dispatch(self, action: dict[str, Any], *, dry_run: bool = True) -> dict[str, Any]:
            calls.append(action)
            return {
                "actions_taken": ["telegram:message"],
                "blocked_reasons": [],
                "dry_run": dry_run,
            }

    _seed_profile(
        monkeypatch,
        tmp_path,
        _profile(channels={"telegram": {"enabled": False, "available": True}}),
    )

    result = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_NOW,
        dry_run=True,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
        telegram_adapter=AdapterSpy(),
    )

    assert result.blocked_reasons == [AUTONOMY_CHANNEL_DISABLED]
    assert calls == []


def test_short_circuit_action(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from src.ham.social_autonomy.tick import AUTONOMY_ACTION_NOT_ALLOWED, run_social_autonomy_tick

    calls: list[str] = []

    class AdapterSpy:
        def dispatch(self, action: dict[str, Any], *, dry_run: bool = True) -> dict[str, Any]:
            calls.append(str(action["action"]))
            return {
                "actions_taken": [f"telegram:{action['action']}"],
                "blocked_reasons": [],
                "dry_run": dry_run,
            }

    _seed_profile(
        monkeypatch,
        tmp_path,
        _profile(actions_allowed_per_channel={"telegram": ["message"]}),
    )

    result = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_NOW,
        dry_run=True,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
        telegram_adapter=AdapterSpy(),
    )

    assert calls == ["message"]
    assert result.actions_taken == ["telegram:message"]
    assert result.blocked_reasons == [AUTONOMY_ACTION_NOT_ALLOWED]


def test_short_circuit_cap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from src.ham.social_autonomy.tick import AUTONOMY_CAP_EXCEEDED, run_social_autonomy_tick

    calls: list[dict[str, Any]] = []

    class AdapterSpy:
        def dispatch(self, action: dict[str, Any], *, dry_run: bool = True) -> dict[str, Any]:
            calls.append(action)
            return {
                "actions_taken": ["telegram:message"],
                "blocked_reasons": [],
                "dry_run": dry_run,
            }

    _seed_profile(monkeypatch, tmp_path, _profile(daily_caps={"telegram": 1}))

    result = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_NOW,
        dry_run=True,
        usage_counter=lambda _channel, _action, _now: 1,
        content_guard=_allowing_content_guard,
        telegram_adapter=AdapterSpy(),
    )

    assert result.blocked_reasons == [AUTONOMY_CAP_EXCEEDED]
    assert calls == []


def test_tick_returns_structured_block_when_adapter_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.ham.social_autonomy.telegram_adapter import AdapterUnavailable
    from src.ham.social_autonomy.tick import (
        AUTONOMY_ACTION_NOT_ALLOWED,
        AUTONOMY_CHANNEL_UNAVAILABLE,
        run_social_autonomy_tick,
    )

    class UnavailableAdapter:
        def dispatch(self, action: dict[str, Any], *, dry_run: bool = True) -> dict[str, Any]:
            assert action["action"] == "message"
            assert dry_run is True
            raise AdapterUnavailable("missing config")

    _seed_profile(
        monkeypatch,
        tmp_path,
        _profile(actions_allowed_per_channel={"telegram": ["message"]}),
    )

    result = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_NOW,
        dry_run=True,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
        telegram_adapter=UnavailableAdapter(),
    )

    assert result.ran is False
    assert result.actions_taken == []
    assert result.blocked_reasons == [AUTONOMY_ACTION_NOT_ALLOWED, AUTONOMY_CHANNEL_UNAVAILABLE]
