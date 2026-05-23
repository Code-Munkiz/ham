"""Mission 16 Milestone 5b: Telegram activity live-apply readiness alignment."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import src.api.social as social_api
from src.api.server import app
from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import apply_social_autonomy_profile
from src.ham.social_telegram_send import TelegramSendResult

client = TestClient(app)

_SOCIAL_TOKEN = "social-live-apply-readiness-token"  # noqa: S105
_APPLY_ROUTE = "/api/social/providers/telegram/activity/apply"
_CONFIRM = "SEND ONE TELEGRAM ACTIVITY"
_NOW = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)


def _now_iso(offset_seconds: int = 0) -> str:
    base = datetime.now(UTC) - timedelta(seconds=offset_seconds)
    return base.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _disable_clerk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith(("TELEGRAM_", "HERMES_", "HAM_SOCIAL_", "HAM_HERMES_")):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", _SOCIAL_TOKEN)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", "write-token")
    monkeypatch.setenv("HAM_SOCIAL_DELIVERY_LOG_PATH", str(tmp_path / "social_delivery.jsonl"))
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(tmp_path / "social_autonomy.json"))
    monkeypatch.setenv("HAM_HERMES_HOME", str(tmp_path / "hermes-home"))
    _disable_clerk(monkeypatch)
    return tmp_path / "social_autonomy.json"


def _seed_probe_cache(token: str) -> None:
    import hashlib

    from src.ham.social_telegram_self_probe import (
        TelegramSelfProbeResult,
        _CACHE as probe_cache,
    )

    cache_key = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    probe_cache[cache_key] = TelegramSelfProbeResult(
        state="ok",
        checked_at=datetime.now(UTC),
        error_code=None,
        bot_username_digest="test",
    )


def _seed_probe_cache_state(token: str, state: str) -> None:
    import hashlib

    from src.ham.social_telegram_self_probe import (
        TelegramSelfProbeResult,
        _CACHE as probe_cache,
    )

    cache_key = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    probe_cache[cache_key] = TelegramSelfProbeResult(
        state=state,  # type: ignore[arg-type]
        checked_at=datetime.now(UTC),
        error_code="probe_failed" if state == "not_ok" else None,
        bot_username_digest="test",
    )


def _write_hermes_gateway(path: Path, *, telegram_state: str = "unknown") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "gateway_state": "running",
                "active_agents": 0,
                "platforms": {"telegram": {"state": telegram_state}},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _enable_telegram_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    telegram_state: str = "unknown",
    probe_state: str = "ok",
) -> str:
    token = "telegram-token-secret-1234567890"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "123456789")
    monkeypatch.setenv("TELEGRAM_TEST_GROUP_ID", "-1009876543210")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "-1001234567890")
    monkeypatch.setenv("HAM_HERMES_HOME", str(tmp_path / "hermes-home"))
    gateway_path = tmp_path / "hermes-home" / "gateway_state.json"
    monkeypatch.setenv("HAM_HERMES_GATEWAY_STATUS_PATH", str(gateway_path))
    _write_hermes_gateway(
        gateway_path,
        telegram_state=telegram_state,
    )
    if probe_state == "ok":
        _seed_probe_cache(token)
    else:
        _seed_probe_cache_state(token, probe_state)
    return token


def _activity_preview_digest() -> str:
    res = client.post("/api/social/providers/telegram/activity/preview", json={})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "completed", body
    digest = body.get("proposal_digest")
    assert isinstance(digest, str) and len(digest) == 64
    return digest


def _write_running_profile(
    profile_path: Path,
    *,
    activity_requires_hermes_gateway: bool = False,
    emergency_stop: bool = False,
) -> None:
    profile = GoHamSocialProfile.model_validate(
        {
            "profile_id": "m16-apply-profile",
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
            "forbidden_topics": [],
            "safety_rules": [],
            "learning_enabled": False,
            "emergency_stop": emergency_stop,
            "activity_requires_hermes_gateway": activity_requires_hermes_gateway,
            "created_at": _NOW,
            "updated_at": _NOW,
        }
    )
    apply_social_autonomy_profile(
        profile_path.parent,
        profile,
        token="write-token",
        actor="pytest",
    )


def test_activity_readiness_helper_skips_hermes_when_self_probe_ok(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _enable_telegram_env(monkeypatch, tmp_path, telegram_state="unknown", probe_state="ok")
    reasons = social_api._telegram_activity_readiness_apply_reasons(
        activity_requires_hermes_gateway=False,
    )
    assert reasons == []
    assert "telegram_gateway_not_connected" not in reasons
    assert "telegram_platform_not_connected" not in reasons


def test_activity_readiness_helper_requires_hermes_when_flag_true(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _enable_telegram_env(monkeypatch, tmp_path, telegram_state="unknown", probe_state="ok")
    reasons = social_api._telegram_activity_readiness_apply_reasons(
        activity_requires_hermes_gateway=True,
    )
    assert "telegram_gateway_not_connected" in reasons
    assert "telegram_platform_not_connected" in reasons


def test_activity_readiness_helper_blocks_on_failed_self_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _enable_telegram_env(monkeypatch, tmp_path, telegram_state="unknown", probe_state="not_ok")
    reasons = social_api._telegram_activity_readiness_apply_reasons(
        activity_requires_hermes_gateway=False,
    )
    assert reasons == ["telegram_self_probe_not_ok"]


def test_activity_apply_allows_send_when_hermes_disconnected_but_self_probe_ok(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    profile_path = _isolate(monkeypatch, tmp_path)
    _enable_telegram_env(monkeypatch, tmp_path, telegram_state="unknown", probe_state="ok")
    _write_running_profile(profile_path, activity_requires_hermes_gateway=False)
    digest = _activity_preview_digest()
    send_result = TelegramSendResult(
        status="sent",
        execution_allowed=True,
        mutation_attempted=True,
        provider_message_id="telegram-activity-message-m16",
    )
    with patch("src.api.social.send_confirmed_telegram_message", return_value=send_result) as send:
        body = client.post(
            _APPLY_ROUTE,
            headers={"X-Ham-Operator-Authorization": f"Bearer {_SOCIAL_TOKEN}"},
            json={"proposal_digest": digest, "confirmation_phrase": _CONFIRM},
        ).json()
    assert send.call_count == 1
    assert body["status"] == "sent"
    assert body["mutation_attempted"] is True
    assert "telegram_gateway_not_connected" not in body["reasons"]
    assert "telegram_platform_not_connected" not in body["reasons"]


def test_activity_apply_blocked_when_self_probe_not_ok_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    profile_path = _isolate(monkeypatch, tmp_path)
    _enable_telegram_env(monkeypatch, tmp_path, telegram_state="connected", probe_state="not_ok")
    _write_running_profile(profile_path)
    with patch("src.api.social.send_confirmed_telegram_message") as send:
        body = client.post(
            _APPLY_ROUTE,
            headers={"X-Ham-Operator-Authorization": f"Bearer {_SOCIAL_TOKEN}"},
            json={"proposal_digest": "a" * 64, "confirmation_phrase": _CONFIRM},
        ).json()
    assert send.call_count == 0
    assert body["status"] == "blocked"
    assert "telegram_self_probe_not_ok" in body["reasons"]


def test_activity_apply_still_blocks_on_proposal_digest_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate(monkeypatch, tmp_path)
    _enable_telegram_env(monkeypatch, tmp_path, telegram_state="unknown", probe_state="ok")
    with patch("src.api.social.send_confirmed_telegram_message") as send:
        body = client.post(
            _APPLY_ROUTE,
            headers={"X-Ham-Operator-Authorization": f"Bearer {_SOCIAL_TOKEN}"},
            json={"proposal_digest": "0" * 64, "confirmation_phrase": _CONFIRM},
        ).json()
    assert send.call_count == 0
    assert body["status"] == "blocked"
    assert "proposal_digest_mismatch" in body["reasons"]


def test_activity_apply_still_blocks_on_missing_confirmation_phrase(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate(monkeypatch, tmp_path)
    _enable_telegram_env(monkeypatch, tmp_path, telegram_state="unknown", probe_state="ok")
    digest = _activity_preview_digest()
    with patch("src.api.social.send_confirmed_telegram_message") as send:
        body = client.post(
            _APPLY_ROUTE,
            headers={"X-Ham-Operator-Authorization": f"Bearer {_SOCIAL_TOKEN}"},
            json={"proposal_digest": digest, "confirmation_phrase": "wrong phrase"},
        ).json()
    assert send.call_count == 0
    assert body["status"] == "blocked"
    assert "confirmation_phrase_required" in body["reasons"]


def test_activity_apply_still_blocks_when_cap_exceeded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate(monkeypatch, tmp_path)
    _enable_telegram_env(monkeypatch, tmp_path, telegram_state="unknown", probe_state="ok")
    digest = _activity_preview_digest()
    delivery_path = Path(os.environ["HAM_SOCIAL_DELIVERY_LOG_PATH"])
    delivery_path.parent.mkdir(parents=True, exist_ok=True)
    with delivery_path.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "provider_id": "telegram",
                    "execution_kind": "social_telegram_activity",
                    "status": "sent",
                    "mutation_attempted": True,
                    "target_ref": "configured:abc123",
                    "executed_at": _now_iso(offset_seconds=60),
                },
                sort_keys=True,
            )
            + "\n"
        )
    with patch("src.api.social.send_confirmed_telegram_message") as send:
        body = client.post(
            _APPLY_ROUTE,
            headers={"X-Ham-Operator-Authorization": f"Bearer {_SOCIAL_TOKEN}"},
            json={"proposal_digest": digest, "confirmation_phrase": _CONFIRM},
        ).json()
    assert send.call_count == 0
    assert body["status"] == "blocked"
    assert "telegram_activity_governor_blocked" in body["reasons"]
    assert "telegram_activity_daily_cap_reached" in body["reasons"]


def test_activity_apply_still_blocks_on_emergency_stop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    profile_path = _isolate(monkeypatch, tmp_path)
    _enable_telegram_env(monkeypatch, tmp_path, telegram_state="unknown", probe_state="ok")
    _write_running_profile(profile_path, emergency_stop=True)
    digest = _activity_preview_digest()
    with patch("src.api.social.send_confirmed_telegram_message") as send:
        body = client.post(
            _APPLY_ROUTE,
            headers={"X-Ham-Operator-Authorization": f"Bearer {_SOCIAL_TOKEN}"},
            json={"proposal_digest": digest, "confirmation_phrase": _CONFIRM},
        ).json()
    assert send.call_count == 0
    assert body["status"] == "blocked"
    assert "autonomy_emergency_stop" in body["reasons"]


def test_legacy_telegram_readiness_still_requires_hermes_for_message_apply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _enable_telegram_env(monkeypatch, tmp_path, telegram_state="unknown", probe_state="ok")
    legacy = social_api._telegram_readiness_apply_reasons()
    activity = social_api._telegram_activity_readiness_apply_reasons(
        activity_requires_hermes_gateway=False,
    )
    assert "telegram_gateway_not_connected" in legacy
    assert "telegram_platform_not_connected" in legacy
    assert "telegram_gateway_not_connected" not in activity
    assert "telegram_platform_not_connected" not in activity
