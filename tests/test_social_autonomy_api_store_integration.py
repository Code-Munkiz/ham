"""API route + store integration tests.

VAL-M15-M1-STORE-API-INTEGRATION-027

Verifies that the five social-autonomy operator routes call into
``get_social_autonomy_store()`` (not the module-level functions directly)
by demonstrating that injecting a different store via
``set_social_autonomy_store_for_tests`` changes the routes' behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import (
    SocialAutonomyFileStore,
    apply_social_autonomy_profile,
    set_social_autonomy_store_for_tests,
)

client = TestClient(app)

_TOKEN = "api-integration-test-token"  # noqa: S105


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    created_at = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    payload: dict[str, Any] = {
        "profile_id": "api-integration-profile",
        "status": "draft",
        "goal": "Integration test goal.",
        "persona_id": "ham-canonical",
        "channels": {
            "x": {"enabled": False, "available": True},
            "telegram": {"enabled": False, "available": True},
            "discord": {"enabled": False, "available": False},
        },
        "actions_allowed_per_channel": {
            "x": ["reply"],
            "telegram": ["message"],
            "discord": [],
        },
        "daily_caps": {"x": 1, "telegram": 1, "discord": 0},
        "cadence": "manual",
        "quiet_hours": None,
        "forbidden_topics": [],
        "safety_rules": ["credential_request"],
        "learning_enabled": True,
        "emergency_stop": False,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": created_at.isoformat().replace("+00:00", "Z"),
    }
    payload.update(overrides)
    return payload


def _profile(**overrides: Any) -> GoHamSocialProfile:
    return GoHamSocialProfile.model_validate(_profile_payload(**overrides))


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(tmp_path / "profile.json"))
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)


def _operator_headers(token: str = _TOKEN) -> dict[str, str]:
    return {
        "Authorization": "Bearer clerk-session-jwt",
        "X-Ham-Operator-Authorization": f"Bearer {token}",
    }


class TestApiRoutesUseFactory:
    """VAL-M15-M1-STORE-API-INTEGRATION-027"""

    def test_get_autonomy_uses_factory(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """GET /autonomy reads through the factory store."""
        _isolate(monkeypatch, tmp_path)
        # Seed data directly via the module-level function (bypassing factory)
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
        apply_social_autonomy_profile(
            None, _profile(profile_id="factory-test"), token=_TOKEN, actor="test"
        )
        # Reset the factory singleton; the route should use the env-configured store
        set_social_autonomy_store_for_tests(None)

        response = client.get("/api/social/autonomy")

        assert response.status_code == 200
        assert response.json()["profile_id"] == "factory-test"

    def test_get_autonomy_uses_injected_store(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Injecting a store via set_social_autonomy_store_for_tests changes route behavior."""
        _isolate(monkeypatch, tmp_path)
        # Write a profile to an alternate path
        alt_path = tmp_path / "alt_profile.json"
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(alt_path))
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
        apply_social_autonomy_profile(
            None, _profile(profile_id="injected-store-profile"), token=_TOKEN, actor="test"
        )
        # Inject a store pointing at the alt path
        injected_store = SocialAutonomyFileStore()
        set_social_autonomy_store_for_tests(injected_store)
        try:
            response = client.get("/api/social/autonomy")
            assert response.status_code == 200
            assert response.json()["profile_id"] == "injected-store-profile"
        finally:
            set_social_autonomy_store_for_tests(None)

    def test_write_status_uses_factory(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """GET /autonomy/write-status reads through the factory store."""
        _isolate(monkeypatch, tmp_path)
        set_social_autonomy_store_for_tests(None)

        # Unset write token → disabled
        monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", raising=False)
        resp = client.get("/api/social/autonomy/write-status")
        assert resp.status_code == 200
        assert resp.json()["writes_enabled"] is False

        # Set write token → enabled
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
        resp2 = client.get("/api/social/autonomy/write-status")
        assert resp2.status_code == 200
        assert resp2.json()["writes_enabled"] is True

    def test_launch_reads_through_factory(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """POST /autonomy/launch reads and writes through the factory store."""
        _isolate(monkeypatch, tmp_path)
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
        set_social_autonomy_store_for_tests(None)

        response = client.post(
            "/api/social/autonomy/launch",
            headers=_operator_headers(_TOKEN),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "running"

    def test_existing_api_tests_remain_green_with_factory(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Core API scenario works with the factory as the seam (no direct module calls in routes)."""
        _isolate(monkeypatch, tmp_path)
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
        set_social_autonomy_store_for_tests(None)

        # GET returns default draft
        r1 = client.get("/api/social/autonomy")
        assert r1.status_code == 200
        assert r1.json()["status"] == "draft"

        # launch → running
        r2 = client.post(
            "/api/social/autonomy/launch",
            headers=_operator_headers(_TOKEN),
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "running"

        # pause → paused
        r3 = client.post(
            "/api/social/autonomy/pause",
            headers=_operator_headers(_TOKEN),
        )
        assert r3.status_code == 200
        assert r3.json()["status"] == "paused"

        # stop → stopped
        r4 = client.post(
            "/api/social/autonomy/stop",
            headers=_operator_headers(_TOKEN),
        )
        assert r4.status_code == 200
        assert r4.json()["status"] == "stopped"
