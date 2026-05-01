from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from src.ham.social_telegram_activity import (
    TELEGRAM_ACTIVITY_EXECUTION_KIND,
    TelegramActivityCandidate,
    plan_telegram_activity_once,
)


def _iso(ts: datetime) -> str:
    return ts.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_delivery_row(path: Path, **fields: object) -> None:
    row = {
        "provider_id": "telegram",
        "execution_kind": TELEGRAM_ACTIVITY_EXECUTION_KIND,
        "status": "sent",
        "mutation_attempted": True,
        "target_ref": "configured:abc123",
        "executed_at": _iso(datetime.now(UTC)),
    }
    row.update(fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def _ready_env(monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    token = "telegram-token-secret-1234567890"
    test_group = "-1009876543210"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "123456789")
    monkeypatch.setenv("TELEGRAM_TEST_GROUP_ID", test_group)
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "-1001234567890")
    return token, test_group


def test_activity_preview_completed_when_ready_and_governor_allows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    token, test_group = _ready_env(monkeypatch)
    log = tmp_path / "social_delivery_log.jsonl"
    result = plan_telegram_activity_once(
        activity_kind="test_activity",
        readiness="ready",
        gateway_runtime_state="connected",
        delivery_log_path=log,
    )
    data = result.model_dump(mode="json")
    assert data["status"] == "completed"
    assert data["execution_allowed"] is False
    assert data["mutation_attempted"] is False
    assert data["live_apply_available"] is False
    assert data["persona_id"] == "ham-canonical"
    assert data["persona_version"] == 1
    assert len(str(data["persona_digest"])) == 64
    assert len(str(data["proposal_digest"])) == 64
    assert data["target"]["kind"] == "test_group"
    assert data["target"]["masked_id"].startswith("configured:")
    assert data["activity_preview"]["char_count"] == len(data["activity_preview"]["text"])
    assert data["activity_preview"]["char_count"] <= 700
    text = json.dumps(data, sort_keys=True)
    assert token not in text
    assert test_group not in text


def test_activity_candidate_rejects_arbitrary_target_or_text_injection() -> None:
    with pytest.raises(ValueError):
        TelegramActivityCandidate(
            activity_kind="test_activity",
            target_kind="home_channel",  # type: ignore[arg-type]
            target_ref="configured:abc123",
            text="x",
            char_count=1,
        )
    with pytest.raises(TypeError):
        plan_telegram_activity_once(message_text="client supplied final text")  # type: ignore[call-arg]


def test_daily_cap_blocks_based_on_delivery_log_fixture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ready_env(monkeypatch)
    log = tmp_path / "social_delivery_log.jsonl"
    _write_delivery_row(log, executed_at=_iso(datetime.now(UTC) - timedelta(hours=1)))
    result = plan_telegram_activity_once(
        activity_kind="status_update",
        readiness="ready",
        gateway_runtime_state="connected",
        delivery_log_path=log,
    )
    assert result.status == "blocked"
    assert result.proposal_digest is None
    assert "telegram_activity_daily_cap_reached" in result.reasons
    assert result.governor["allowed"] is False


def test_min_spacing_blocks_and_returns_next_allowed_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ready_env(monkeypatch)
    log = tmp_path / "social_delivery_log.jsonl"
    _write_delivery_row(log, executed_at=_iso(datetime.now(UTC) - timedelta(minutes=5)))
    result = plan_telegram_activity_once(
        activity_kind="test_activity",
        readiness="ready",
        gateway_runtime_state="connected",
        delivery_log_path=log,
    )
    assert result.status == "blocked"
    assert "telegram_activity_min_spacing_active" in result.reasons
    assert result.governor["next_allowed_send_time"]


def test_no_delivery_log_append_and_no_telegram_api_or_send_adapter_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ready_env(monkeypatch)
    log = tmp_path / "social_delivery_log.jsonl"
    with patch("urllib.request.urlopen", side_effect=AssertionError("telegram api should not be called")):
        with patch("src.ham.social_telegram_send.send_confirmed_telegram_message") as send:
            result = plan_telegram_activity_once(
                activity_kind="test_activity",
                readiness="ready",
                gateway_runtime_state="connected",
                delivery_log_path=log,
            )
    assert result.status == "completed"
    assert send.call_count == 0
    assert log.exists() is False

