from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.ham_x.goham_live_controller import GohamExecutionResult, run_live_controller_once
from src.ham.ham_x.goham_reactive_batch import run_reactive_batch_once
from src.ham.ham_x.goham_reactive_live import run_reactive_live_once
from src.ham.ham_x.reactive_reply_executor import ReactiveReplyRequest, ReactiveReplyResult
from src.ham.social_autonomy.enforcement import (
    autonomy_reasons_for_apply,
    preview_autonomy_runner_tick,
)
from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_telegram_activity_runner import (
    TelegramActivityRunConfig,
    run_telegram_activity_once,
)
from src.ham.social_telegram_reactive_runner import (
    TelegramReactiveRunConfig,
    run_telegram_reactive_once,
)
from src.ham.social_telegram_send import TelegramSendResult
from tests.test_ham_x_goham_live_controller import _candidate
from tests.test_ham_x_goham_live_controller import _test_config as _live_controller_config
from tests.test_ham_x_goham_reactive import _item, _test_config
from tests.test_ham_x_goham_reactive_batch import _batch_config

client = TestClient(app)


class MockTelegramTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def send_message(
        self,
        *,
        bot_token: str,
        chat_id: str,
        text: str,
        timeout_seconds: float,
    ) -> TelegramSendResult:
        self.calls.append(
            {
                "bot_token": bot_token,
                "chat_id": chat_id,
                "text": text,
                "timeout_seconds": timeout_seconds,
            }
        )
        return TelegramSendResult(status="sent", execution_allowed=True, mutation_attempted=True)


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    stamp = datetime(2026, 5, 20, 12, 0, tzinfo=UTC).isoformat().replace("+00:00", "Z")
    payload: dict[str, Any] = {
        "profile_id": "runner-profile",
        "status": "running",
        "goal": "Run GoHAM Social inside the configured envelope.",
        "persona_id": "ham-canonical",
        "channels": {
            "x": {"enabled": True, "available": True},
            "telegram": {"enabled": True, "available": True},
            "discord": {"enabled": False, "available": False},
        },
        "actions_allowed_per_channel": {
            "x": ["reply", "broadcast"],
            "telegram": ["reply", "message", "activity"],
            "discord": [],
        },
        "daily_caps": {"x": 5, "telegram": 5, "discord": 0},
        "cadence": "manual",
        "quiet_hours": None,
        "forbidden_topics": [],
        "safety_rules": ["no spam", "no credential requests"],
        "learning_enabled": True,
        "emergency_stop": False,
        "created_at": stamp,
        "updated_at": stamp,
    }
    payload.update(overrides)
    return payload


def _profile(**overrides: Any) -> GoHamSocialProfile:
    return GoHamSocialProfile.model_validate(_profile_payload(**overrides))


def _write_profile(path: Path, **overrides: Any) -> GoHamSocialProfile:
    profile = _profile(**overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile.model_dump(mode="json"), sort_keys=True), encoding="utf-8")
    return profile


def _isolate_autonomy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target = tmp_path / "social_autonomy.json"
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(target))
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
    return target


def _ready_telegram(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "********************************")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "123456789")
    monkeypatch.setenv("TELEGRAM_TEST_GROUP_ID", "-1009876543210")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "-1001234567890")
    monkeypatch.setenv("HAM_SOCIAL_DELIVERY_LOG_PATH", str(tmp_path / "social_delivery_log.jsonl"))


def _enable_telegram_reactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_SOCIAL_TELEGRAM_REACTIVE_AUTONOMY_ENABLED", "true")
    monkeypatch.setenv("HAM_SOCIAL_TELEGRAM_REACTIVE_DRY_RUN", "false")


def _enable_telegram_activity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_SOCIAL_TELEGRAM_ACTIVITY_AUTONOMY_ENABLED", "true")
    monkeypatch.setenv("HAM_SOCIAL_TELEGRAM_ACTIVITY_DRY_RUN", "false")


def _write_transcript(path: Path) -> None:
    row = {
        "source": "telegram",
        "role": "user",
        "text": "How does Ham work?",
        "chat_id": "-1009876543210",
        "user_id": "123456789",
        "session_id": "telegram-session-1",
        "message_id": "telegram-message-1",
        "already_answered": False,
    }
    path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")


def test_telegram_reactive_runner_autonomy_channel_disabled_blocks_transport(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = _isolate_autonomy(monkeypatch, tmp_path)
    _write_profile(target, channels={"telegram": {"enabled": False, "available": True}})
    _ready_telegram(monkeypatch, tmp_path)
    _enable_telegram_reactive(monkeypatch)
    transcript = tmp_path / "telegram.jsonl"
    _write_transcript(transcript)
    transport = MockTelegramTransport()

    result = run_telegram_reactive_once(
        TelegramReactiveRunConfig(
            dry_run=False,
            readiness="ready",
            gateway_runtime_state="connected",
            transcript_paths=[transcript],
            delivery_log_path=tmp_path / "delivery.jsonl",
        ),
        transport=transport,
    )

    assert result.status == "blocked"
    assert result.reasons[0] == "autonomy_channel_disabled"
    assert result.mutation_attempted is False
    assert transport.calls == []


def test_telegram_activity_runner_autonomy_channel_disabled_blocks_transport(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = _isolate_autonomy(monkeypatch, tmp_path)
    _write_profile(target, channels={"telegram": {"enabled": False, "available": True}})
    _ready_telegram(monkeypatch, tmp_path)
    _enable_telegram_activity(monkeypatch)
    transport = MockTelegramTransport()

    result = run_telegram_activity_once(
        TelegramActivityRunConfig(
            dry_run=False,
            readiness="ready",
            gateway_runtime_state="connected",
            delivery_log_path=tmp_path / "delivery.jsonl",
        ),
        transport=transport,
    )

    assert result.status == "blocked"
    assert result.reasons[0] == "autonomy_channel_disabled"
    assert result.mutation_attempted is False
    assert transport.calls == []


def test_reactive_live_runner_autonomy_action_not_allowed_blocks_transport(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = _isolate_autonomy(monkeypatch, tmp_path)
    _write_profile(target, actions_allowed_per_channel={"x": ["broadcast"]})
    calls = 0

    def run_reply(_: ReactiveReplyRequest) -> ReactiveReplyResult:
        nonlocal calls
        calls += 1
        return ReactiveReplyResult(
            status="executed", execution_allowed=True, mutation_attempted=True
        )

    result = run_reactive_live_once(
        _item().model_dump(mode="json"),
        config=_test_config(tmp_path, dry_run=False, live_canary=True),
        run_reply=run_reply,
    )

    assert result.status == "blocked"
    assert result.reasons[0] == "autonomy_action_not_allowed"
    assert result.mutation_attempted is False
    assert calls == 0


def test_reactive_batch_runner_autonomy_channel_disabled_blocks_transport(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = _isolate_autonomy(monkeypatch, tmp_path)
    _write_profile(target, channels={"x": {"enabled": False, "available": True}})
    calls = 0

    def run_reply(_: ReactiveReplyRequest) -> ReactiveReplyResult:
        nonlocal calls
        calls += 1
        return ReactiveReplyResult(
            status="executed", execution_allowed=True, mutation_attempted=True
        )

    result = run_reactive_batch_once(
        [_item().model_dump(mode="json")],
        config=_batch_config(
            tmp_path, dry_run=False, batch_overrides={"goham_reactive_batch_dry_run": False}
        ),
        run_reply=run_reply,
    )

    assert result.status == "blocked"
    assert result.reasons[0] == "autonomy_channel_disabled"
    assert result.mutation_attempted is False
    assert calls == 0


def test_live_controller_runner_autonomy_channel_disabled_blocks_transport(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = _isolate_autonomy(monkeypatch, tmp_path)
    _write_profile(target, channels={"x": {"enabled": False, "available": True}})
    calls = 0

    def run_post(*_args: Any, **_kwargs: Any) -> GohamExecutionResult:
        nonlocal calls
        calls += 1
        raise AssertionError("autonomy block must prevent live controller transport")

    result = run_live_controller_once(
        [_candidate()],
        config=_live_controller_config(tmp_path),
        run_post=run_post,
    )

    assert result.status == "blocked"
    assert result.reasons[0] == "autonomy_channel_disabled"
    assert result.mutation_attempted is False
    assert calls == 0


def test_permissive_profile_preserves_legacy_runner_reasons(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = _isolate_autonomy(monkeypatch, tmp_path)
    _ready_telegram(monkeypatch, tmp_path)
    transcript = tmp_path / "telegram.jsonl"
    _write_transcript(transcript)

    reactive_cfg = TelegramReactiveRunConfig(
        dry_run=False,
        readiness="setup_required",
        gateway_runtime_state="unknown",
        transcript_paths=[transcript],
        delivery_log_path=tmp_path / "reactive-delivery.jsonl",
    )
    activity_cfg = TelegramActivityRunConfig(
        dry_run=False,
        readiness="setup_required",
        gateway_runtime_state="unknown",
        delivery_log_path=tmp_path / "activity-delivery.jsonl",
    )
    x_live_cfg = _test_config(tmp_path / "x-live", dry_run=True, live_canary=False)
    x_batch_cfg = _batch_config(
        tmp_path / "x-batch", batch_overrides={"goham_reactive_batch_max_replies_per_run": 0}
    )
    x_controller_cfg = _live_controller_config(tmp_path / "x-controller", controller_dry_run=True)

    legacy = {
        "telegram_reactive": run_telegram_reactive_once(reactive_cfg).reasons,
        "telegram_activity": run_telegram_activity_once(activity_cfg).reasons,
        "x_reactive_live": run_reactive_live_once(
            _item().model_dump(mode="json"), config=x_live_cfg
        ).reasons,
        "x_reactive_batch": run_reactive_batch_once(
            [_item().model_dump(mode="json")], config=x_batch_cfg
        ).reasons,
        "x_live_controller": run_live_controller_once(
            [_candidate()], config=x_controller_cfg
        ).reasons,
    }

    _write_profile(target)

    assert run_telegram_reactive_once(reactive_cfg).reasons == legacy["telegram_reactive"]
    assert run_telegram_activity_once(activity_cfg).reasons == legacy["telegram_activity"]
    assert (
        run_reactive_live_once(_item().model_dump(mode="json"), config=x_live_cfg).reasons
        == legacy["x_reactive_live"]
    )
    assert (
        run_reactive_batch_once([_item().model_dump(mode="json")], config=x_batch_cfg).reasons
        == legacy["x_reactive_batch"]
    )
    assert (
        run_live_controller_once([_candidate()], config=x_controller_cfg).reasons
        == legacy["x_live_controller"]
    )


def test_autonomy_preview_tick_blocking_profile_would_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    profile = _profile(status="paused")

    result = preview_autonomy_runner_tick(profile, channel="telegram", action="activity")

    assert result["channel"] == "telegram"
    assert result["action"] == "activity"
    assert result["would_run"] is False
    assert result["reasons"] == autonomy_reasons_for_apply(
        profile, channel="telegram", action="activity"
    )
    assert not (tmp_path / ".ham").exists()


def test_autonomy_preview_tick_permissive_profile_would_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = preview_autonomy_runner_tick(_profile(), channel="x", action="broadcast")

    assert result == {
        "channel": "x",
        "action": "broadcast",
        "would_run": True,
        "reasons": [],
        "next_run_summary": "x:broadcast would run on the next one-shot tick.",
    }
    assert not (tmp_path / ".ham").exists()


def test_social_autonomy_api_preview_tick_endpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _isolate_autonomy(monkeypatch, tmp_path)
    _write_profile(target, status="paused")

    response = client.post(
        "/api/social/autonomy/preview-tick", json={"channel": "telegram", "action": "activity"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["channel"] == "telegram"
    assert body["action"] == "activity"
    assert body["would_run"] is False
    assert "autonomy_profile_not_running" in body["reasons"]


def test_social_autonomy_api_preview_tick_validation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _isolate_autonomy(monkeypatch, tmp_path)
    _write_profile(target)
    before = target.read_text(encoding="utf-8")

    missing_channel = client.post("/api/social/autonomy/preview-tick", json={"action": "activity"})
    bad_channel = client.post("/api/social/autonomy/preview-tick", json={"channel": "slack"})
    bad_action = client.post(
        "/api/social/autonomy/preview-tick", json={"channel": "telegram", "action": "shitpost"}
    )

    assert missing_channel.status_code == 422
    assert bad_channel.status_code == 422
    assert bad_action.status_code == 422
    assert target.read_text(encoding="utf-8") == before
