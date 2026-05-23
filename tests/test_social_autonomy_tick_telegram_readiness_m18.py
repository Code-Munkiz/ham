"""Mission 18 regression tests for Telegram tick readiness alignment."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import apply_social_autonomy_profile
from src.ham.social_autonomy.tick import (
    AUTONOMY_CHANNEL_DISABLED,
    run_social_autonomy_tick,
)
from src.ham.social_persona import load_social_persona
from src.ham.social_telegram_activity import _activity_text, plan_telegram_activity_once
from src.ham.social_telegram_activity_runner import TelegramActivityRunResult

_TOKEN = "autonomy-write-token"  # noqa: S105
_NOW = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)


def _telegram_only_profile(**overrides: Any) -> GoHamSocialProfile:
    created_at = _NOW - timedelta(days=1)
    payload: dict[str, Any] = {
        "profile_id": "m18-profile",
        "workspace_id": "workspace-1",
        "project_id": "project-1",
        "status": "running",
        "goal": "Mission 16 controlled Telegram proof.",
        "persona_id": "ham-canonical",
        "channels": {
            "telegram": {"enabled": True, "available": True},
            "x": {"enabled": False, "available": True},
            "discord": {"enabled": False, "available": False},
        },
        "actions_allowed_per_channel": {
            "telegram": ["activity"],
            "x": [],
            "discord": [],
        },
        "daily_caps": {"telegram": 1, "x": 0, "discord": 0},
        "cadence": "manual",
        "quiet_hours": None,
        "forbidden_topics": [],
        "safety_rules": [],
        "learning_enabled": False,
        "emergency_stop": False,
        "created_at": created_at,
        "updated_at": created_at,
    }
    payload.update(overrides)
    return GoHamSocialProfile.model_validate(payload)


def _seed_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    profile: GoHamSocialProfile,
) -> None:
    target = tmp_path / "profile.json"
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(target))
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    apply_social_autonomy_profile(tmp_path, profile, token=_TOKEN, actor="pytest-seed")
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", raising=False)


def _ready_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token-secret-1234567890")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "123456789")
    monkeypatch.setenv("TELEGRAM_TEST_GROUP_ID", "-1009876543210")
    monkeypatch.setenv("HAM_SOCIAL_DELIVERY_LOG_PATH", str(tmp_path / "delivery.jsonl"))


def _pin_ready_status(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.api.social as social_mod

    monkeypatch.setattr(
        social_mod,
        "_telegram_status_for_autonomy_tick",
        lambda: SimpleNamespace(
            overall_readiness="ready",
            hermes_gateway=SimpleNamespace(provider_runtime_state="unknown"),
            telegram_self_probe_state="ok",
        ),
    )


def _zero_usage(channel: str, action: str, now: datetime) -> int:
    assert channel and action and now
    return 0


def _allowing_content_guard(*_args: Any, **_kwargs: Any) -> list[str]:
    return []


def test_telegram_enabled_profile_does_not_emit_channel_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_profile(monkeypatch, tmp_path, _telegram_only_profile())
    _pin_ready_status(monkeypatch)
    monkeypatch.delenv("HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH", raising=False)

    result = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_NOW,
        dry_run=True,
        run_once=True,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
    )

    assert AUTONOMY_CHANNEL_DISABLED not in result.blocked_reasons
    assert "autonomy_channel_unavailable" not in result.blocked_reasons


def test_self_probe_ok_clears_telegram_readiness_blockers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ready_env(monkeypatch, tmp_path)
    _seed_profile(monkeypatch, tmp_path, _telegram_only_profile())
    _pin_ready_status(monkeypatch)
    monkeypatch.delenv("HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH", raising=False)
    monkeypatch.delenv("HAM_HERMES_HOME", raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)

    result = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_NOW,
        dry_run=True,
        run_once=True,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
    )

    assert "telegram_self_probe_not_ok" not in result.blocked_reasons
    assert "telegram_readiness_not_ready" not in result.blocked_reasons


def test_self_probe_not_ok_surfaces_explicit_blocker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.api.social as social_mod

    _seed_profile(monkeypatch, tmp_path, _telegram_only_profile())
    monkeypatch.setattr(
        social_mod,
        "_telegram_status_for_autonomy_tick",
        lambda: SimpleNamespace(
            overall_readiness="ready",
            hermes_gateway=SimpleNamespace(provider_runtime_state="unknown"),
            telegram_self_probe_state="not_ok",
        ),
    )
    monkeypatch.delenv("HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH", raising=False)

    result = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_NOW,
        dry_run=True,
        run_once=True,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
    )

    assert "telegram_self_probe_not_ok" in result.blocked_reasons


def test_autonomy_tick_self_probe_refreshes_on_cache_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.api.social as social_mod

    fresh_calls: list[str] = []
    monkeypatch.setattr(
        social_mod,
        "_get_telegram_self_probe_state_cached_only",
        lambda: "unknown",
    )
    monkeypatch.setattr(
        social_mod,
        "_get_telegram_self_probe_state",
        lambda: fresh_calls.append("fresh") or "ok",
    )

    assert social_mod._telegram_self_probe_state_for_autonomy_tick() == "ok"
    assert fresh_calls == ["fresh"]


def test_autonomy_tick_self_probe_uses_cache_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.api.social as social_mod

    def _fail_fresh() -> str:
        raise AssertionError("fresh probe should not run when cache is populated")

    monkeypatch.setattr(
        social_mod,
        "_get_telegram_self_probe_state_cached_only",
        lambda: "ok",
    )
    monkeypatch.setattr(social_mod, "_get_telegram_self_probe_state", _fail_fresh)

    assert social_mod._telegram_self_probe_state_for_autonomy_tick() == "ok"


def test_reactive_transcript_missing_does_not_block_activity_lane(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ready_env(monkeypatch, tmp_path)
    _seed_profile(monkeypatch, tmp_path, _telegram_only_profile())
    _pin_ready_status(monkeypatch)
    monkeypatch.delenv("HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH", raising=False)
    monkeypatch.delenv("HAM_HERMES_HOME", raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)

    result = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_NOW,
        dry_run=True,
        run_once=True,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
    )

    assert "telegram:activity" in result.actions_taken
    assert "hermes_transcript_source_unavailable" not in result.blocked_reasons
    assert "telegram_reactive_preview_not_available" not in result.blocked_reasons


def test_dry_run_reaches_exact_activity_text_without_live_transport(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ready_env(monkeypatch, tmp_path)
    _seed_profile(monkeypatch, tmp_path, _telegram_only_profile())
    _pin_ready_status(monkeypatch)
    monkeypatch.delenv("HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH", raising=False)
    monkeypatch.delenv("HAM_HERMES_HOME", raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)

    persona = load_social_persona("ham-canonical", 1)
    expected_text = _activity_text(
        activity_kind="test_activity",
        display_name=persona.display_name,
    )
    captured: list[TelegramActivityRunResult] = []

    import src.ham.social_telegram_autopilot as autopilot_mod

    original = autopilot_mod.run_telegram_activity_once

    def _capture_activity(*args: Any, **kwargs: Any) -> TelegramActivityRunResult:
        result = original(*args, **kwargs)
        captured.append(result)
        return result

    with patch(
        "urllib.request.urlopen",
        side_effect=AssertionError("live Telegram transport must not be called"),
    ):
        with patch.object(autopilot_mod, "run_telegram_activity_once", side_effect=_capture_activity):
            result = run_social_autonomy_tick(
                store_path=tmp_path,
                now=_NOW,
                dry_run=True,
                run_once=True,
                usage_counter=_zero_usage,
                content_guard=_allowing_content_guard,
            )

    assert result.ran is True
    assert "telegram:activity" in result.actions_taken
    assert captured, "activity lane should run during dry-run tick"
    preview = captured[0].activity_preview
    assert preview["text"] == expected_text
    assert preview["text"] == plan_telegram_activity_once(
        readiness="ready",
        gateway_runtime_state="unknown",
        telegram_self_probe_state="ok",
    ).activity_preview["text"]
