from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from src.ham.social_telegram_reactive import TELEGRAM_REACTIVE_REPLY_EXECUTION_KIND
from src.ham.social_telegram_reactive_runner import TelegramReactiveRunConfig, run_telegram_reactive_once
from src.ham.social_telegram_send import TelegramSendResult


class MockTransport:
    def __init__(self, result: TelegramSendResult | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.result = result or TelegramSendResult(
            status="sent",
            execution_allowed=True,
            mutation_attempted=True,
            provider_message_id="telegram-reactive-message-1",
        )

    def send_message(self, *, bot_token: str, chat_id: str, text: str, timeout_seconds: float) -> TelegramSendResult:
        self.calls.append({"bot_token": bot_token, "chat_id": chat_id, "text": text, "timeout_seconds": timeout_seconds})
        return self.result


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


def _enable_live_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_SOCIAL_TELEGRAM_REACTIVE_AUTONOMY_ENABLED", "true")
    monkeypatch.setenv("HAM_SOCIAL_TELEGRAM_REACTIVE_DRY_RUN", "false")


def _write_transcript(path: Path, *, text: str = "How does Ham work?", chat: str = "-1009876543210", user: str = "123456789", answered: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "source": "telegram",
        "role": "user",
        "text": text,
        "chat_id": chat,
        "user_id": user,
        "session_id": "telegram-session-1",
        "message_id": "telegram-message-1",
        "already_answered": answered,
    }
    path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")


def _live_config(transcript: Path, log: Path, **overrides: object) -> TelegramReactiveRunConfig:
    data = {
        "dry_run": False,
        "readiness": "ready",
        "gateway_runtime_state": "connected",
        "transcript_paths": [transcript],
        "delivery_log_path": log,
    }
    data.update(overrides)
    return TelegramReactiveRunConfig(**data)


def _iso(ts: datetime) -> str:
    return ts.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_delivery_row(path: Path, **fields: object) -> None:
    row = {
        "provider_id": "telegram",
        "execution_kind": TELEGRAM_REACTIVE_REPLY_EXECUTION_KIND,
        "action_type": "reactive_reply",
        "status": "sent",
        "mutation_attempted": True,
        "target_ref": "configured:abc123",
        "executed_at": _iso(datetime.now(UTC)),
    }
    row.update(fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def test_dry_run_sends_nothing_selects_one_and_no_log(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    token, _user, chat = _ready_env(monkeypatch, tmp_path)
    transcript = tmp_path / "telegram.jsonl"
    _write_transcript(transcript)
    log = tmp_path / "delivery.jsonl"
    transport = MockTransport()

    with patch("urllib.request.urlopen", side_effect=AssertionError("telegram api should not be called")):
        result = run_telegram_reactive_once(
            TelegramReactiveRunConfig(dry_run=True, readiness="ready", gateway_runtime_state="connected", transcript_paths=[transcript], delivery_log_path=log),
            transport=transport,
        )

    assert result.status == "completed"
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
    assert result.proposal_digest
    assert result.selected_inbound_id
    assert result.reply_candidate_text
    assert transport.calls == []
    assert log.exists() is False
    out = result.model_dump_json()
    assert token not in out
    assert chat not in out


def test_live_mode_blocked_by_default_env_gates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch, tmp_path)
    transcript = tmp_path / "telegram.jsonl"
    _write_transcript(transcript)
    log = tmp_path / "delivery.jsonl"
    transport = MockTransport()

    result = run_telegram_reactive_once(_live_config(transcript, log), transport=transport)

    assert result.status == "blocked"
    assert "telegram_reactive_autonomy_disabled" in result.reasons
    assert "telegram_reactive_dry_run_enabled" in result.reasons
    assert result.mutation_attempted is False
    assert transport.calls == []


def test_live_mode_blocked_when_dry_run_env_still_true(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch, tmp_path)
    monkeypatch.setenv("HAM_SOCIAL_TELEGRAM_REACTIVE_AUTONOMY_ENABLED", "true")
    monkeypatch.setenv("HAM_SOCIAL_TELEGRAM_REACTIVE_DRY_RUN", "true")
    transcript = tmp_path / "telegram.jsonl"
    _write_transcript(transcript)
    transport = MockTransport()

    result = run_telegram_reactive_once(_live_config(transcript, tmp_path / "delivery.jsonl"), transport=transport)

    assert "telegram_reactive_dry_run_enabled" in result.reasons
    assert transport.calls == []


def test_live_mode_blocked_when_readiness_not_ready_or_no_candidate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch, tmp_path)
    _enable_live_gates(monkeypatch)
    transcript = tmp_path / "telegram.jsonl"
    _write_transcript(transcript, text="banana sandwich weather")
    transport = MockTransport()

    not_ready = run_telegram_reactive_once(_live_config(transcript, tmp_path / "a.jsonl", readiness="setup_required"), transport=transport)
    no_candidate = run_telegram_reactive_once(_live_config(transcript, tmp_path / "b.jsonl"), transport=transport)

    assert "telegram_readiness_not_ready" in not_ready.reasons
    assert "telegram_reactive_no_safe_candidate" in no_candidate.reasons
    assert transport.calls == []


def test_live_blocks_already_handled_inbound_duplicate_fingerprint_and_caps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch, tmp_path)
    _enable_live_gates(monkeypatch)
    transcript = tmp_path / "telegram.jsonl"
    _write_transcript(transcript)
    log = tmp_path / "delivery.jsonl"
    preview = run_telegram_reactive_once(TelegramReactiveRunConfig(dry_run=True, readiness="ready", gateway_runtime_state="connected", transcript_paths=[transcript], delivery_log_path=log))
    assert preview.selected_inbound_id and preview.proposal_digest
    import hashlib

    idempotency = f"telegram-reactive-reply-{hashlib.sha256(f'telegram-reactive-reply:{preview.selected_inbound_id}'.encode('utf-8')).hexdigest()[:32]}"
    _write_delivery_row(log, idempotency_key=idempotency, proposal_digest=preview.proposal_digest)
    for i in range(2):
        _write_delivery_row(log, idempotency_key=f"other-{i}", proposal_digest=f"{i}" * 64)
    transport = MockTransport()

    result = run_telegram_reactive_once(_live_config(transcript, log), transport=transport)

    assert "telegram_reactive_inbound_already_handled" in result.reasons
    assert "telegram_reactive_response_fingerprint_duplicate" in result.reasons
    assert "telegram_reactive_hourly_cap_reached" in result.reasons
    assert result.mutation_attempted is False
    assert transport.calls == []


def test_live_calls_send_adapter_once_and_logs_reactive_reply(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    token, user, chat = _ready_env(monkeypatch, tmp_path)
    _enable_live_gates(monkeypatch)
    transcript = tmp_path / "telegram.jsonl"
    _write_transcript(transcript, user=user, chat=chat)
    log = tmp_path / "delivery.jsonl"
    transport = MockTransport()

    result = run_telegram_reactive_once(_live_config(transcript, log), transport=transport)

    assert result.status == "sent"
    assert result.execution_allowed is True
    assert result.mutation_attempted is True
    assert len(transport.calls) == 1
    row = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert row["execution_kind"] == TELEGRAM_REACTIVE_REPLY_EXECUTION_KIND
    assert row["action_type"] == "reactive_reply"
    assert result.provider_message_id == "telegram-reactive-message-1"
    text = result.model_dump_json() + log.read_text(encoding="utf-8")
    for raw in (token, user, chat):
        assert raw not in text


def test_provider_failure_does_not_retry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch, tmp_path)
    _enable_live_gates(monkeypatch)
    transcript = tmp_path / "telegram.jsonl"
    _write_transcript(transcript)
    transport = MockTransport(TelegramSendResult(status="failed", execution_allowed=True, mutation_attempted=True, reasons=["provider_send_failed"]))

    result = run_telegram_reactive_once(_live_config(transcript, tmp_path / "delivery.jsonl"), transport=transport)

    assert result.status == "failed"
    assert result.mutation_attempted is True
    assert result.reasons == ["provider_send_failed"]
    assert len(transport.calls) == 1


def test_no_scheduler_loop_daemon_or_api_surface_created() -> None:
    source = Path("src/ham/social_telegram_reactive_runner.py").read_text(encoding="utf-8")
    forbidden = ["while True", "schedule.", "sched.", "daemon", "threading", "asyncio.create_task", "@router"]
    for needle in forbidden:
        assert needle not in source
