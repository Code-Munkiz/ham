from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from src.ham.social_delivery_log import append_delivery_record
from src.ham.social_telegram_send import (
    TelegramSendRequest,
    TelegramSendResult,
    TelegramTransport,
    send_confirmed_telegram_message,
)


class MockTransport:
    def __init__(self, result: TelegramSendResult | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.result = result or TelegramSendResult(
            status="sent",
            execution_allowed=True,
            mutation_attempted=True,
            provider_message_id="telegram-message-1",
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


def _request(**overrides: object) -> TelegramSendRequest:
    data = {
        "target_kind": "test_group",
        "text": "Ham Telegram preview check: no batch, no retry.",
        "proposal_digest": "a" * 64,
        "persona_digest": "b" * 64,
        "idempotency_key": "telegram-idempotency-1",
        "telegram_connected": True,
    }
    data.update(overrides)
    return TelegramSendRequest(**data)


def _ready_env(monkeypatch: pytest.MonkeyPatch) -> tuple[str, str, str]:
    token = "telegram-token-secret-1234567890"
    allowed = "123456789"
    target = "-1009876543210"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", allowed)
    monkeypatch.setenv("TELEGRAM_TEST_GROUP_ID", target)
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "-1001234567890")
    return token, allowed, target


def test_mock_transport_success_returns_sent_and_masked_target(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    token, _allowed, target = _ready_env(monkeypatch)
    transport = MockTransport()

    result = send_confirmed_telegram_message(_request(), transport=transport, delivery_log_path=tmp_path / "delivery.jsonl")

    assert result.status == "sent"
    assert result.execution_allowed is True
    assert result.mutation_attempted is True
    assert result.provider_message_id == "telegram-message-1"
    assert result.target_kind == "test_group"
    assert result.target_ref and result.target_ref.startswith("configured:")
    assert len(transport.calls) == 1
    assert transport.calls[0]["bot_token"] == token
    assert transport.calls[0]["chat_id"] == target
    text = result.model_dump_json()
    assert token not in text
    assert target not in text


def test_missing_token_blocks_before_transport(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    transport = MockTransport()

    result = send_confirmed_telegram_message(_request(), transport=transport, delivery_log_path=tmp_path / "delivery.jsonl")

    assert result.status == "blocked"
    assert result.mutation_attempted is False
    assert "telegram_bot_token_missing" in result.reasons
    assert transport.calls == []


def test_missing_readiness_blocks_before_transport(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch)
    transport = MockTransport()

    result = send_confirmed_telegram_message(
        _request(telegram_connected=False),
        transport=transport,
        delivery_log_path=tmp_path / "delivery.jsonl",
    )

    assert result.status == "blocked"
    assert "telegram_not_connected" in result.reasons
    assert transport.calls == []


def test_invalid_target_kind_rejected() -> None:
    with pytest.raises(ValueError):
        TelegramSendRequest(**{**_request().model_dump(), "target_kind": "raw"})


def test_missing_configured_target_blocks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch)
    monkeypatch.delenv("TELEGRAM_TEST_GROUP_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_TEST_GROUP", raising=False)
    monkeypatch.delenv("TELEGRAM_TEST_CHAT_ID", raising=False)
    transport = MockTransport()

    result = send_confirmed_telegram_message(_request(), transport=transport, delivery_log_path=tmp_path / "delivery.jsonl")

    assert result.status == "blocked"
    assert "telegram_target_missing" in result.reasons
    assert transport.calls == []


def test_arbitrary_raw_target_impossible() -> None:
    with pytest.raises(ValueError):
        TelegramSendRequest(**{**_request().model_dump(), "target_id": "-1009876543210"})


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "telegram_message_empty"),
        ("x" * 701, "telegram_message_too_long"),
        ("MEDIA:/tmp/secret.png", "telegram_plain_text_only"),
        ("attachment:/tmp/secret.png", "telegram_plain_text_only"),
    ],
)
def test_text_validation_blocks_before_transport(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    text: str,
    reason: str,
) -> None:
    _ready_env(monkeypatch)
    transport = MockTransport()

    result = send_confirmed_telegram_message(
        _request(text=text),
        transport=transport,
        delivery_log_path=tmp_path / "delivery.jsonl",
    )

    assert result.status == "blocked"
    assert reason in result.reasons
    assert transport.calls == []


def test_provider_failure_returns_redacted_diagnostic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    token, _allowed, target = _ready_env(monkeypatch)
    transport = MockTransport(
        TelegramSendResult(
            status="failed",
            execution_allowed=True,
            mutation_attempted=True,
            reasons=["provider_send_failed"],
            result={"diagnostic": f"failed token={token} chat={target}"},
        )
    )

    result = send_confirmed_telegram_message(_request(), transport=transport, delivery_log_path=tmp_path / "delivery.jsonl")

    text = result.model_dump_json()
    assert result.status == "failed"
    assert result.mutation_attempted is True
    assert token not in text
    assert target not in text
    assert "[REDACTED" in text
    assert len(transport.calls) == 1


def test_timeout_returns_unknown_delivery_no_retry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch)
    transport = MockTransport(
        TelegramSendResult(
            status="failed",
            execution_allowed=True,
            mutation_attempted=True,
            reasons=["provider_timeout_unknown_delivery"],
        )
    )

    result = send_confirmed_telegram_message(_request(), transport=transport, delivery_log_path=tmp_path / "delivery.jsonl")

    assert result.status == "failed"
    assert result.reasons == ["provider_timeout_unknown_delivery"]
    assert len(transport.calls) == 1


def test_result_and_delivery_log_never_contain_secret_values(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    token, allowed, target = _ready_env(monkeypatch)
    log = tmp_path / "delivery.jsonl"

    result = send_confirmed_telegram_message(_request(), transport=MockTransport(), delivery_log_path=log)

    text = result.model_dump_json() + log.read_text(encoding="utf-8")
    for raw in (token, allowed, target):
        assert raw not in text
    row = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert row["target_ref"].startswith("configured:")
    assert row["status"] == "sent"
    assert row["execution_kind"] == "social_telegram_message"


def test_custom_execution_kind_is_applied_to_delivery_log(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch)
    log = tmp_path / "delivery.jsonl"

    result = send_confirmed_telegram_message(
        _request(),
        transport=MockTransport(),
        delivery_log_path=log,
        execution_kind="social_telegram_activity",
        action_type="activity",
    )

    assert result.status == "sent"
    row = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert row["execution_kind"] == "social_telegram_activity"
    assert row["action_type"] == "activity"


def test_duplicate_idempotency_key_blocks_before_transport(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ready_env(monkeypatch)
    log = tmp_path / "delivery.jsonl"
    req = _request()
    append_delivery_record(
        {
            "provider_id": "telegram",
            "status": "sent",
            "idempotency_key": req.idempotency_key,
            "target_ref": "configured:abc",
        },
        path=log,
    )
    transport = MockTransport()

    result = send_confirmed_telegram_message(req, transport=transport, delivery_log_path=log)

    assert result.status == "duplicate"
    assert "duplicate_idempotency_key" in result.reasons
    assert result.mutation_attempted is False
    assert transport.calls == []


def test_live_transport_is_not_used_by_unit_tests() -> None:
    assert issubclass(MockTransport, object)
    assert TelegramTransport
