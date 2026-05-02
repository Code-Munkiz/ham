from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.ham.social_telegram_activity_runner import TelegramActivityRunResult
from src.ham.social_telegram_autopilot import HamgomoonAutopilotConfig, main, run_hamgomoon_autopilot_once
from src.ham.social_telegram_reactive_runner import TelegramReactiveRunResult
from src.ham.social_telegram_send import TelegramSendResult


class MockTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def send_message(self, *, bot_token: str, chat_id: str, text: str, timeout_seconds: float) -> TelegramSendResult:
        self.calls.append({"bot_token": bot_token, "chat_id": chat_id, "text": text, "timeout_seconds": timeout_seconds})
        return TelegramSendResult(status="sent", execution_allowed=True, mutation_attempted=True)


def _ready_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[str, str, str]:
    token = "telegram-token-secret-1234567890"
    user = "123456789"
    chat = "-1009876543210"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", user)
    monkeypatch.setenv("TELEGRAM_TEST_GROUP_ID", chat)
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "-1001234567890")
    monkeypatch.setenv("HAM_SOCIAL_DELIVERY_LOG_PATH", str(tmp_path / "social_delivery_log.jsonl"))
    return token, user, chat


def _enable_global_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAMGOMOON_AUTOPILOT_ENABLED", "true")
    monkeypatch.setenv("HAMGOMOON_AUTOPILOT_DRY_RUN", "false")


def _enable_lane_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_SOCIAL_TELEGRAM_REACTIVE_AUTONOMY_ENABLED", "true")
    monkeypatch.setenv("HAM_SOCIAL_TELEGRAM_REACTIVE_DRY_RUN", "false")
    monkeypatch.setenv("HAM_SOCIAL_TELEGRAM_ACTIVITY_AUTONOMY_ENABLED", "true")
    monkeypatch.setenv("HAM_SOCIAL_TELEGRAM_ACTIVITY_DRY_RUN", "false")


def _write_transcript(path: Path, *, text: str = "How does Ham work?") -> None:
    row = {
        "source": "telegram",
        "role": "user",
        "text": text,
        "chat_id": "-1009876543210",
        "user_id": "123456789",
        "session_id": "telegram-session-1",
        "message_id": "telegram-message-1",
        "already_answered": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")


def _reactive_result(status: str = "completed", *, mutation: bool = False, reasons: list[str] | None = None) -> TelegramReactiveRunResult:
    return TelegramReactiveRunResult(
        status=status,  # type: ignore[arg-type]
        dry_run=False,
        execution_allowed=mutation,
        mutation_attempted=mutation,
        persona_id="hamgomoon",
        persona_version=1,
        persona_digest="persona-digest",
        selected_inbound_id="inbound_abc123",
        proposal_digest="reply-digest",
        reply_candidate_text="Thanks for asking about Ham.",
        reasons=reasons or [],
    )


def _activity_result(status: str = "completed", *, mutation: bool = False, reasons: list[str] | None = None) -> TelegramActivityRunResult:
    return TelegramActivityRunResult(
        status=status,  # type: ignore[arg-type]
        dry_run=False,
        execution_allowed=mutation,
        mutation_attempted=mutation,
        persona_id="hamgomoon",
        persona_version=1,
        persona_digest="persona-digest",
        proposal_digest="activity-digest",
        target={"kind": "test_group", "configured": True, "masked_id": "configured:abc123"},
        activity_preview={"text": "Ham status check."},
        governor={"allowed": True, "reasons": []},
        reasons=reasons or [],
    )


def _blocked_activity_result(*, reasons: list[str] | None = None) -> TelegramActivityRunResult:
    return TelegramActivityRunResult(
        status="blocked",
        dry_run=True,
        execution_allowed=False,
        mutation_attempted=False,
        persona_id="hamgomoon",
        persona_version=1,
        persona_digest="persona-digest",
        proposal_digest=None,
        target={"kind": "test_group", "configured": True, "masked_id": "configured:abc123"},
        activity_preview={},
        governor={"allowed": False, "reasons": reasons or ["telegram_activity_daily_cap_reached"]},
        reasons=reasons or ["telegram_activity_daily_cap_reached"],
    )


def _blocked_reactive_result(*, reasons: list[str] | None = None) -> TelegramReactiveRunResult:
    return TelegramReactiveRunResult(
        status="blocked",
        dry_run=True,
        execution_allowed=False,
        mutation_attempted=False,
        persona_id="hamgomoon",
        persona_version=1,
        persona_digest="persona-digest",
        selected_inbound_id=None,
        proposal_digest=None,
        reply_candidate_text="",
        reasons=reasons or ["telegram_reactive_no_safe_candidate"],
    )


def test_dry_run_runs_both_lanes_sends_nothing_and_no_log(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    token, user, chat = _ready_env(monkeypatch, tmp_path)
    transcript = tmp_path / "telegram.jsonl"
    _write_transcript(transcript)
    log = tmp_path / "delivery.jsonl"
    reactive_transport = MockTransport()
    activity_transport = MockTransport()

    with patch("urllib.request.urlopen", side_effect=AssertionError("telegram api should not be called")):
        result = run_hamgomoon_autopilot_once(
            HamgomoonAutopilotConfig(
                dry_run=True,
                readiness="ready",
                gateway_runtime_state="connected",
                transcript_paths=[transcript],
                delivery_log_path=log,
            ),
            reactive_transport=reactive_transport,
            activity_transport=activity_transport,
        )

    assert result.status == "completed"
    assert result.dry_run is True
    assert result.lane_order == ["reactive", "activity"]
    assert result.reactive and result.reactive["dry_run"] is True
    assert result.activity and result.activity["dry_run"] is True
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
    assert reactive_transport.calls == []
    assert activity_transport.calls == []
    assert log.exists() is False
    text = result.model_dump_json()
    for raw in (token, user, chat):
        assert raw not in text


def test_dry_run_reactive_candidate_activity_cap_is_partial_not_blocked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch, tmp_path)
    log = tmp_path / "delivery.jsonl"

    with (
        patch("src.ham.social_telegram_autopilot.run_telegram_reactive_once", return_value=_reactive_result("completed", mutation=False)),
        patch("src.ham.social_telegram_autopilot.run_telegram_activity_once", return_value=_blocked_activity_result()),
    ):
        result = run_hamgomoon_autopilot_once(HamgomoonAutopilotConfig(dry_run=True, delivery_log_path=log))

    assert result.status == "partial"
    assert result.selected_lane == "reactive"
    assert result.reactive_lane_status == "completed"
    assert result.activity_lane_status == "blocked"
    assert result.blocking_reasons == []
    assert result.non_blocking_reasons == ["telegram_activity_daily_cap_reached"]
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
    assert log.exists() is False


def test_dry_run_both_lanes_blocked_is_blocked() -> None:
    with (
        patch("src.ham.social_telegram_autopilot.run_telegram_reactive_once", return_value=_blocked_reactive_result()),
        patch("src.ham.social_telegram_autopilot.run_telegram_activity_once", return_value=_blocked_activity_result()),
    ):
        result = run_hamgomoon_autopilot_once(HamgomoonAutopilotConfig(dry_run=True))

    assert result.status == "blocked"
    assert result.selected_lane is None
    assert result.blocking_reasons == ["telegram_reactive_no_safe_candidate", "telegram_activity_daily_cap_reached"]
    assert result.non_blocking_reasons == []


def test_live_mode_blocked_by_default_global_env_gates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch, tmp_path)
    calls: list[str] = []

    with (
        patch("src.ham.social_telegram_autopilot.run_telegram_reactive_once", side_effect=lambda *a, **k: calls.append("reactive")),
        patch("src.ham.social_telegram_autopilot.run_telegram_activity_once", side_effect=lambda *a, **k: calls.append("activity")),
    ):
        result = run_hamgomoon_autopilot_once(HamgomoonAutopilotConfig(dry_run=False, emergency_stop=False))

    assert result.status == "blocked"
    assert "hamgomoon_autopilot_disabled" in result.reasons
    assert "hamgomoon_autopilot_dry_run_enabled" in result.reasons
    assert result.mutation_attempted is False
    assert calls == []


def test_live_mode_blocked_when_global_dry_run_gate_true(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch, tmp_path)
    monkeypatch.setenv("HAMGOMOON_AUTOPILOT_ENABLED", "true")
    monkeypatch.setenv("HAMGOMOON_AUTOPILOT_DRY_RUN", "true")

    result = run_hamgomoon_autopilot_once(HamgomoonAutopilotConfig(dry_run=False, emergency_stop=False))

    assert result.status == "blocked"
    assert result.reasons == ["hamgomoon_autopilot_dry_run_enabled"]
    assert result.reactive is None
    assert result.activity is None


def test_live_mode_respects_lane_specific_gates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch, tmp_path)
    _enable_global_gates(monkeypatch)
    transcript = tmp_path / "telegram.jsonl"
    _write_transcript(transcript)

    result = run_hamgomoon_autopilot_once(
        HamgomoonAutopilotConfig(
            dry_run=False,
            readiness="ready",
            gateway_runtime_state="connected",
            transcript_paths=[transcript],
            delivery_log_path=tmp_path / "delivery.jsonl",
            emergency_stop=False,
        )
    )

    assert result.status == "blocked"
    assert "telegram_reactive_autonomy_disabled" in result.reasons
    assert "telegram_activity_autonomy_disabled" in result.reasons
    assert result.mutation_attempted is False


def test_live_mode_calls_reactive_then_activity_when_no_reactive_send(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_global_gates(monkeypatch)
    order: list[str] = []

    def reactive(*_args: object, **_kwargs: object) -> TelegramReactiveRunResult:
        order.append("reactive")
        return _reactive_result("completed", mutation=False)

    def activity(*_args: object, **_kwargs: object) -> TelegramActivityRunResult:
        order.append("activity")
        return _activity_result("sent", mutation=True)

    with (
        patch("src.ham.social_telegram_autopilot.run_telegram_reactive_once", side_effect=reactive),
        patch("src.ham.social_telegram_autopilot.run_telegram_activity_once", side_effect=activity),
    ):
        result = run_hamgomoon_autopilot_once(HamgomoonAutopilotConfig(dry_run=False, emergency_stop=False))

    assert order == ["reactive", "activity"]
    assert result.lane_order == ["reactive", "activity"]
    assert result.status == "sent"
    assert result.activity and result.activity["status"] == "sent"


def test_live_mode_can_select_reactive_when_activity_is_blocked_by_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_global_gates(monkeypatch)
    order: list[str] = []

    def reactive(*_args: object, **_kwargs: object) -> TelegramReactiveRunResult:
        order.append("reactive")
        return _reactive_result("completed", mutation=False)

    def activity(*_args: object, **_kwargs: object) -> TelegramActivityRunResult:
        order.append("activity")
        return _blocked_activity_result()

    with (
        patch("src.ham.social_telegram_autopilot.run_telegram_reactive_once", side_effect=reactive),
        patch("src.ham.social_telegram_autopilot.run_telegram_activity_once", side_effect=activity),
    ):
        result = run_hamgomoon_autopilot_once(HamgomoonAutopilotConfig(dry_run=False, emergency_stop=False))

    assert order == ["reactive", "activity"]
    assert result.status == "partial"
    assert result.selected_lane == "reactive"
    assert result.blocking_reasons == []
    assert result.non_blocking_reasons == ["telegram_activity_daily_cap_reached"]
    assert result.execution_allowed is False
    assert result.mutation_attempted is False


def test_reactive_live_send_skips_activity_by_default_unless_allow_both(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_global_gates(monkeypatch)
    order: list[str] = []

    def reactive(*_args: object, **_kwargs: object) -> TelegramReactiveRunResult:
        order.append("reactive")
        return _reactive_result("sent", mutation=True)

    def activity(*_args: object, **_kwargs: object) -> TelegramActivityRunResult:
        order.append("activity")
        return _activity_result("sent", mutation=True)

    with (
        patch("src.ham.social_telegram_autopilot.run_telegram_reactive_once", side_effect=reactive),
        patch("src.ham.social_telegram_autopilot.run_telegram_activity_once", side_effect=activity),
    ):
        skipped = run_hamgomoon_autopilot_once(HamgomoonAutopilotConfig(dry_run=False, emergency_stop=False))
        both = run_hamgomoon_autopilot_once(HamgomoonAutopilotConfig(dry_run=False, allow_both_live_lanes=True, emergency_stop=False))

    assert skipped.status == "sent"
    assert skipped.selected_lane == "reactive"
    assert skipped.skipped_lanes == ["activity"]
    assert "activity_skipped_after_reactive_send" in skipped.non_blocking_reasons
    assert both.status == "sent"
    assert both.skipped_lanes == []
    assert order == ["reactive", "reactive", "activity"]


def test_emergency_stop_blocks_live_before_lanes(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_global_gates(monkeypatch)
    calls: list[str] = []

    with (
        patch("src.ham.social_telegram_autopilot.run_telegram_reactive_once", side_effect=lambda *a, **k: calls.append("reactive")),
        patch("src.ham.social_telegram_autopilot.run_telegram_activity_once", side_effect=lambda *a, **k: calls.append("activity")),
    ):
        result = run_hamgomoon_autopilot_once(HamgomoonAutopilotConfig(dry_run=False, emergency_stop=True))

    assert result.status == "blocked"
    assert result.reasons == ["emergency_stop"]
    assert result.mutation_attempted is False
    assert calls == []


def test_cli_summary_is_bounded_and_defaults_dry_run(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    fake = _reactive_result("completed", mutation=False)
    with patch(
        "src.ham.social_telegram_autopilot.run_hamgomoon_autopilot_once",
        return_value=fake_model_result(),
    ) as run:
        code = main(["--dry-run"])

    assert code == 0
    assert run.call_args.args[0].dry_run is True
    out = json.loads(capsys.readouterr().out)
    assert out["run_kind"] == "hamgomoon_autopilot_run_once"
    assert "reactive_status" in out
    assert "reply_candidate_text" not in out
    assert fake.reply_candidate_text not in json.dumps(out)


def fake_model_result():
    from src.ham.social_telegram_autopilot import HamgomoonAutopilotResult

    return HamgomoonAutopilotResult(
        status="completed",
        dry_run=True,
        lane_order=["reactive", "activity"],
        selected_lane="reactive",
        reactive_lane_status="completed",
        activity_lane_status="completed",
        reactive={"status": "completed", "reply_candidate_text": "secret-looking candidate text"},
        activity={"status": "completed", "activity_preview": {"text": "activity text"}},
        result={"mode": "dry_run"},
    )


def test_no_scheduler_loop_daemon_or_direct_api_surface_created() -> None:
    source = Path("src/ham/social_telegram_autopilot.py").read_text(encoding="utf-8")
    forbidden = ["while True", "schedule.", "sched.", "daemon", "threading", "asyncio.create_task", "@router", "urlopen("]
    for needle in forbidden:
        assert needle not in source
