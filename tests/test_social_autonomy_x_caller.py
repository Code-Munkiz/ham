from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import apply_social_autonomy_profile

_TOKEN = "autonomy-write-token"  # noqa: S105
_NOW = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    created_at = _NOW - timedelta(days=1)
    payload: dict[str, Any] = {
        "profile_id": "x-profile",
        "workspace_id": "workspace-1",
        "project_id": "project-1",
        "status": "running",
        "goal": "Grow HAM safely on X.",
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
    assert channel == "x"
    assert action in {"reply", "broadcast"}
    assert now == _NOW
    return 0


def test_delegates_to_reactive_runners(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.ham.ham_x import goham_reactive_batch, goham_reactive_live
    from src.ham.social_autonomy import x_caller

    live_calls: list[dict[str, Any]] = []
    batch_calls: list[dict[str, Any]] = []

    def live_spy(
        prepared: dict[str, Any],
        *,
        config: Any,
        run_reply: Any,
        dry_run: bool,
    ) -> SimpleNamespace:
        live_calls.append(
            {
                "prepared": prepared,
                "dry_run": dry_run,
                "config_dry_run": config.goham_reactive_dry_run,
                "run_reply": run_reply,
            }
        )
        return SimpleNamespace(status="dry_run", reasons=[])

    def batch_spy(
        candidates: list[dict[str, Any]],
        *,
        config: Any,
        run_reply: Any,
        dry_run: bool,
    ) -> SimpleNamespace:
        batch_calls.append(
            {
                "candidates": candidates,
                "dry_run": dry_run,
                "config_dry_run": config.goham_reactive_batch_dry_run,
                "run_reply": run_reply,
            }
        )
        return SimpleNamespace(
            status="completed",
            reasons=[],
            items=[SimpleNamespace(status="dry_run", reasons=[])],
        )

    monkeypatch.setattr(goham_reactive_live, "run_reactive_live_once", live_spy)
    monkeypatch.setattr(goham_reactive_batch, "run_reactive_batch_once", batch_spy)

    live_result = x_caller.dry_run({"channel": "x", "action": "reply", "payload": "HAM"})
    batch_result = x_caller.dry_run({"channel": "x", "action": "broadcast", "payload": "HAM"})

    assert len(live_calls) == 1
    assert live_calls[0]["dry_run"] is True
    assert live_calls[0]["config_dry_run"] is True
    assert live_result["actions_taken"] == ["x:reply"]

    assert len(batch_calls) == 1
    assert batch_calls[0]["dry_run"] is True
    assert batch_calls[0]["config_dry_run"] is True
    assert batch_result["actions_taken"] == ["x:broadcast"]


def test_normalized_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.ham.ham_x import goham_reactive_batch
    from src.ham.social_autonomy import x_caller

    monkeypatch.setattr(
        goham_reactive_batch,
        "run_reactive_batch_once",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="completed",
            reasons=[],
            items=[SimpleNamespace(status="dry_run", reasons=[])],
        ),
    )

    result = x_caller.dry_run({"channel": "x", "action": "broadcast", "payload": "HAM"})

    assert result == {
        "channel": "x",
        "action": "broadcast",
        "actions_taken": ["x:broadcast"],
        "blocked_reasons": [],
        "dry_run": True,
        "execution_allowed": True,
    }


def test_completed_batch_with_all_blocked_items_is_blocked() -> None:
    from src.ham.social_autonomy import x_caller

    result = x_caller._normalize_batch_result(
        SimpleNamespace(
            status="completed",
            reasons=[],
            items=[
                SimpleNamespace(
                    status="blocked",
                    reasons=["reactive_policy_blocked"],
                )
            ],
        ),
        "broadcast",
    )

    assert result["actions_taken"] == []
    assert result["blocked_reasons"] == ["x_reactive_item_blocked:reactive_policy_blocked"]
    assert result["execution_allowed"] is False


def test_completed_batch_with_success_and_blocked_items_preserves_blocked_reasons() -> None:
    from src.ham.social_autonomy import x_caller

    result = x_caller._normalize_batch_result(
        SimpleNamespace(
            status="completed",
            reasons=[],
            items=[
                SimpleNamespace(status="dry_run", reasons=[]),
                SimpleNamespace(
                    status="blocked",
                    reasons=["reactive_policy_blocked"],
                ),
            ],
        ),
        "broadcast",
    )

    assert result["actions_taken"] == ["x:broadcast"]
    assert result["blocked_reasons"] == ["x_reactive_item_blocked:reactive_policy_blocked"]
    assert result["execution_allowed"] is True


def test_no_live_x(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.ham.ham_x import goham_reactive_live
    from src.ham.social_autonomy import x_caller

    def live_spy(
        _prepared: dict[str, Any],
        *,
        config: Any,
        run_reply: Any,
        dry_run: bool,
    ) -> SimpleNamespace:
        assert dry_run is True
        assert config.goham_reactive_dry_run is True
        assert callable(run_reply)
        return SimpleNamespace(status="dry_run", reasons=[])

    monkeypatch.setattr(goham_reactive_live, "run_reactive_live_once", live_spy)

    result = x_caller.dry_run({"channel": "x", "action": "reply", "payload": "HAM"})

    assert result["dry_run"] is True
    assert result["execution_allowed"] is True


def test_runner_errors_surface_as_structured_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.ham.ham_x import goham_reactive_live
    from src.ham.social_autonomy import x_caller

    def fail_runner(*_args: Any, **_kwargs: Any) -> object:
        raise RuntimeError("reactive runner exploded")

    monkeypatch.setattr(goham_reactive_live, "run_reactive_live_once", fail_runner)

    result = x_caller.dry_run({"channel": "x", "action": "reply", "payload": "HAM"})

    assert result["actions_taken"] == []
    assert result["blocked_reasons"] == ["x_reactive_runner_error"]
    assert result["dry_run"] is True
    assert result["execution_allowed"] is False


def test_short_circuit_cap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from src.ham.social_autonomy.tick import AUTONOMY_CAP_EXCEEDED, run_social_autonomy_tick

    calls: list[dict[str, Any]] = []

    class XCallerSpy:
        def dry_run(self, action: dict[str, Any]) -> dict[str, Any]:
            calls.append(action)
            return {
                "actions_taken": ["x:reply"],
                "blocked_reasons": [],
                "dry_run": True,
            }

    _seed_profile(monkeypatch, tmp_path, _profile(daily_caps={"x": 1}))

    result = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_NOW,
        dry_run=True,
        usage_counter=lambda _channel, _action, _now: 1,
        content_guard=_allowing_content_guard,
        x_caller=XCallerSpy(),
    )

    assert result.blocked_reasons == [AUTONOMY_CAP_EXCEEDED]
    assert calls == []


def test_short_circuit_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from src.ham.social_autonomy.tick import AUTONOMY_CHANNEL_DISABLED, run_social_autonomy_tick

    calls: list[dict[str, Any]] = []

    class XCallerSpy:
        def dry_run(self, action: dict[str, Any]) -> dict[str, Any]:
            calls.append(action)
            return {
                "actions_taken": ["x:reply"],
                "blocked_reasons": [],
                "dry_run": True,
            }

    _seed_profile(
        monkeypatch,
        tmp_path,
        _profile(channels={"x": {"enabled": False, "available": True}}),
    )

    result = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_NOW,
        dry_run=True,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
        x_caller=XCallerSpy(),
    )

    assert result.blocked_reasons == [AUTONOMY_CHANNEL_DISABLED]
    assert calls == []
