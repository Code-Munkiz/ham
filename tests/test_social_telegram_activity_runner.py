from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from src.ham.social_telegram_activity import TELEGRAM_ACTIVITY_EXECUTION_KIND
from src.ham.social_telegram_activity_runner import (
    TelegramActivityRunConfig,
    run_telegram_activity_once,
)
from src.ham.social_telegram_send import TelegramSendResult


class MockTransport:
    def __init__(self, result: TelegramSendResult | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.result = result or TelegramSendResult(
            status="sent",
            execution_allowed=True,
            mutation_attempted=True,
            provider_message_id="telegram-activity-message-1",
        )

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
        return self.result


def _ready_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[str, str, str]:
    token = "telegram-token-secret-1234567890"
    allowed = "123456789"
    test_group = "-1009876543210"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", allowed)
    monkeypatch.setenv("TELEGRAM_TEST_GROUP_ID", test_group)
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "-1001234567890")
    monkeypatch.setenv("HAM_SOCIAL_DELIVERY_LOG_PATH", str(tmp_path / "social_delivery_log.jsonl"))
    return token, allowed, test_group


def _enable_live_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_SOCIAL_TELEGRAM_ACTIVITY_AUTONOMY_ENABLED", "true")
    monkeypatch.setenv("HAM_SOCIAL_TELEGRAM_ACTIVITY_DRY_RUN", "false")


def _live_config(log: Path, **overrides: object) -> TelegramActivityRunConfig:
    data = {
        "dry_run": False,
        "readiness": "ready",
        "gateway_runtime_state": "connected",
        "delivery_log_path": log,
    }
    data.update(overrides)
    return TelegramActivityRunConfig(**data)


def _iso(ts: datetime) -> str:
    return ts.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_delivery_row(path: Path, **fields: object) -> None:
    row = {
        "provider_id": "telegram",
        "status": "sent",
        "mutation_attempted": True,
        "target_ref": "configured:abc123",
        "executed_at": _iso(datetime.now(UTC)),
    }
    row.update(fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def test_dry_run_run_once_sends_nothing_and_returns_planned_activity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    token, _allowed, test_group = _ready_env(monkeypatch, tmp_path)
    log = tmp_path / "dry-run.jsonl"
    transport = MockTransport()

    with patch("urllib.request.urlopen", side_effect=AssertionError("telegram api should not be called")):
        result = run_telegram_activity_once(
            TelegramActivityRunConfig(
                dry_run=True,
                readiness="ready",
                gateway_runtime_state="connected",
                delivery_log_path=log,
            ),
            transport=transport,
        )

    data = result.model_dump(mode="json")
    assert data["status"] == "completed"
    assert data["dry_run"] is True
    assert data["execution_allowed"] is False
    assert data["mutation_attempted"] is False
    assert data["proposal_digest"]
    assert data["persona_digest"]
    assert data["governor"]["allowed"] is True
    assert data["activity_preview"]["text"]
    assert transport.calls == []
    assert log.exists() is False
    text = json.dumps(data, sort_keys=True)
    assert token not in text
    assert test_group not in text


def test_live_mode_blocked_by_default_env_gates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch, tmp_path)
    log = tmp_path / "live-default-blocked.jsonl"
    transport = MockTransport()

    result = run_telegram_activity_once(_live_config(log), transport=transport)

    assert result.status == "blocked"
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
    assert "telegram_activity_autonomy_disabled" in result.reasons
    assert "telegram_activity_dry_run_enabled" in result.reasons
    assert transport.calls == []
    assert log.exists() is False


def test_live_mode_blocked_when_autonomy_enabled_but_dry_run_env_true(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ready_env(monkeypatch, tmp_path)
    monkeypatch.setenv("HAM_SOCIAL_TELEGRAM_ACTIVITY_AUTONOMY_ENABLED", "true")
    monkeypatch.setenv("HAM_SOCIAL_TELEGRAM_ACTIVITY_DRY_RUN", "true")
    log = tmp_path / "live-dry-run-env-blocked.jsonl"
    transport = MockTransport()

    result = run_telegram_activity_once(_live_config(log), transport=transport)

    assert result.status == "blocked"
    assert result.mutation_attempted is False
    assert "telegram_activity_dry_run_enabled" in result.reasons
    assert transport.calls == []
    assert log.exists() is False


def test_live_mode_blocked_when_readiness_not_ready(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch, tmp_path)
    _enable_live_gates(monkeypatch)
    log = tmp_path / "readiness-blocked.jsonl"
    transport = MockTransport()

    result = run_telegram_activity_once(
        _live_config(log, readiness="setup_required", gateway_runtime_state="connected"),
        transport=transport,
    )

    assert result.status == "blocked"
    assert "telegram_activity_preview_not_available" in result.reasons
    assert "telegram_readiness_not_ready" in result.reasons
    assert result.mutation_attempted is False
    assert transport.calls == []
    assert log.exists() is False


def test_live_mode_blocked_when_governor_blocks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch, tmp_path)
    _enable_live_gates(monkeypatch)
    log = tmp_path / "governor-blocked.jsonl"
    _write_delivery_row(
        log,
        execution_kind=TELEGRAM_ACTIVITY_EXECUTION_KIND,
        executed_at=_iso(datetime.now(UTC) - timedelta(hours=1)),
    )
    transport = MockTransport()

    result = run_telegram_activity_once(_live_config(log), transport=transport)

    assert result.status == "blocked"
    assert "telegram_activity_governor_blocked" in result.reasons
    assert "telegram_activity_daily_cap_reached" in result.reasons
    assert result.mutation_attempted is False
    assert transport.calls == []


def test_live_mode_calls_narrow_adapter_once_and_logs_activity_kind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    token, allowed, test_group = _ready_env(monkeypatch, tmp_path)
    _enable_live_gates(monkeypatch)
    log = tmp_path / "live-success.jsonl"
    transport = MockTransport()

    result = run_telegram_activity_once(_live_config(log), transport=transport)

    assert result.status == "sent"
    assert result.execution_allowed is True
    assert result.mutation_attempted is True
    assert result.provider_message_id == "telegram-activity-message-1"
    assert len(transport.calls) == 1
    row = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert row["execution_kind"] == TELEGRAM_ACTIVITY_EXECUTION_KIND
    assert row["action_type"] == "activity"
    assert row["target_ref"].startswith("configured:")
    assert row["provider_message_id"]
    text = result.model_dump_json() + log.read_text(encoding="utf-8")
    for raw in (token, allowed, test_group):
        assert raw not in text


def test_duplicate_idempotency_blocks_before_transport(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch, tmp_path)
    _enable_live_gates(monkeypatch)
    log = tmp_path / "duplicate.jsonl"
    preview = run_telegram_activity_once(
        TelegramActivityRunConfig(
            dry_run=True,
            readiness="ready",
            gateway_runtime_state="connected",
            delivery_log_path=log,
        )
    )
    assert preview.proposal_digest
    import hashlib

    digest = hashlib.sha256(f"telegram-activity-run-once:{preview.proposal_digest}".encode("utf-8")).hexdigest()
    _write_delivery_row(
        log,
        execution_kind="social_telegram_message",
        idempotency_key=f"telegram-activity-run-once-{digest[:32]}",
    )
    transport = MockTransport()

    result = run_telegram_activity_once(_live_config(log), transport=transport)

    assert result.status == "duplicate"
    assert "duplicate_idempotency_key" in result.reasons
    assert result.mutation_attempted is False
    assert transport.calls == []


def test_provider_failure_does_not_retry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    token, _allowed, test_group = _ready_env(monkeypatch, tmp_path)
    _enable_live_gates(monkeypatch)
    log = tmp_path / "provider-failure.jsonl"
    transport = MockTransport(
        TelegramSendResult(
            status="failed",
            execution_allowed=True,
            mutation_attempted=True,
            reasons=["provider_send_failed"],
            result={"diagnostic": f"token={token} chat={test_group}"},
        )
    )

    result = run_telegram_activity_once(_live_config(log), transport=transport)

    assert result.status == "failed"
    assert result.mutation_attempted is True
    assert result.reasons == ["provider_send_failed"]
    assert len(transport.calls) == 1
    text = result.model_dump_json() + log.read_text(encoding="utf-8")
    assert token not in text
    assert test_group not in text
    assert "[REDACTED" in text


def test_no_scheduler_loop_daemon_or_reactive_surface_created() -> None:
    source = Path("src/ham/social_telegram_activity_runner.py").read_text(encoding="utf-8")
    forbidden = ["while True", "schedule.", "sched.", "daemon", "threading", "asyncio.create_task", "inbound"]
    for needle in forbidden:
        assert needle not in source
