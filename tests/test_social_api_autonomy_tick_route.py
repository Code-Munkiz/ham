"""HTTP contract tests for the GoHAM Social autonomy tick route."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.clerk_auth import HamActor
from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import save_profile, social_autonomy_path
from src.ham.social_autonomy.tick import (
    AUTONOMY_PROFILE_MISSING,
    AUTONOMY_PROFILE_NOT_RUNNING,
    SocialAutonomyTickResult,
)

client = TestClient(app)


def _actor() -> HamActor:
    return HamActor(
        user_id="user_social_tick_test",
        org_id="org_social_tick_test",
        session_id="session_social_tick_test",
        email="operator@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target = tmp_path / "social_autonomy.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(target))
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)
    return target


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer fake.clerk.jwt"}


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    stamp = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    payload: dict[str, Any] = {
        "profile_id": "route-profile",
        "status": "paused",
        "goal": "Grow HAM safely.",
        "persona_id": "ham-canonical",
        "channels": {
            "x": {"enabled": True, "available": True},
            "telegram": {"enabled": True, "available": True},
            "discord": {"enabled": False, "available": False},
        },
        "actions_allowed_per_channel": {
            "x": ["reply", "broadcast"],
            "telegram": ["message", "activity"],
            "discord": [],
        },
        "daily_caps": {"x": 3, "telegram": 2, "discord": 0},
        "cadence": "manual",
        "quiet_hours": None,
        "forbidden_topics": [],
        "safety_rules": ["no spam", "no mass tagging"],
        "learning_enabled": False,
        "emergency_stop": False,
        "created_at": stamp,
        "updated_at": stamp,
    }
    payload.update(overrides)
    return payload


def _profile(**overrides: Any) -> GoHamSocialProfile:
    return GoHamSocialProfile.model_validate(_profile_payload(**overrides))


def _persist_profile(tmp_path: Path, profile: GoHamSocialProfile) -> None:
    save_profile(tmp_path, profile, actor="pytest")


def _post_tick(json_body: dict[str, Any]) -> Any:
    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=_actor()):
        return client.post(
            "/api/social/autonomy/tick",
            headers=_auth_headers(),
            json=json_body,
        )


def test_tick_route_requires_clerk_authentication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate(monkeypatch, tmp_path)

    response = client.post("/api/social/autonomy/tick", json={})

    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"
    assert "fake.clerk.jwt" not in response.text


def test_tick_route_defaults_to_dry_run_for_missing_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = _isolate(monkeypatch, tmp_path)

    response = _post_tick({})

    assert response.status_code == 200
    body = response.json()
    result = SocialAutonomyTickResult.model_validate(body)
    assert result.dry_run is True
    assert result.ran is False
    assert result.blocked_reasons == [AUTONOMY_PROFILE_MISSING]
    assert not target.exists()
    assert social_autonomy_path(tmp_path) == target


def test_tick_route_explicit_dry_run_returns_blocked_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate(monkeypatch, tmp_path)
    _persist_profile(tmp_path, _profile(status="paused"))

    response = _post_tick({"dry_run": True})

    assert response.status_code == 200
    body = response.json()
    result = SocialAutonomyTickResult.model_validate(body)
    assert result.dry_run is True
    assert result.ran is False
    assert AUTONOMY_PROFILE_NOT_RUNNING in result.blocked_reasons
    assert result.profile_status == "paused"


def test_tick_route_query_dry_run_true_is_respected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate(monkeypatch, tmp_path)

    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=_actor()):
        response = client.post(
            "/api/social/autonomy/tick?dry_run=true",
            headers=_auth_headers(),
            json={},
        )

    assert response.status_code == 200
    assert response.json()["dry_run"] is True


def test_tick_route_live_mode_requires_live_token_before_tick(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate(monkeypatch, tmp_path)
    tick_spy = Mock(side_effect=AssertionError("tick service should not run"))
    monkeypatch.setattr("src.ham.social_autonomy.tick.run_social_autonomy_tick", tick_spy)

    response = _post_tick({"dry_run": False})

    assert response.status_code == 403
    assert response.json()["detail"]["error"]["code"] == "SOCIAL_LIVE_APPLY_DISABLED"
    tick_spy.assert_not_called()


def test_tick_route_rejects_malformed_body_before_tick(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate(monkeypatch, tmp_path)
    tick_spy = Mock(side_effect=AssertionError("tick service should not run"))
    monkeypatch.setattr("src.ham.social_autonomy.tick.run_social_autonomy_tick", tick_spy)

    response = _post_tick({"dry_run": "not-a-bool"})

    assert response.status_code == 422
    tick_spy.assert_not_called()
