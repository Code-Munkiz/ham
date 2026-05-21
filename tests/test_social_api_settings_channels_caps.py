"""Unit tests for PATCH /api/social/autonomy/settings — channels and daily_caps extension.

Covers:
- channels-only update persists
- daily_caps-only update persists
- combined channels + daily_caps + quiet_hours update
- 401 CLERK_SESSION_REQUIRED when Clerk enforcement is on and no Clerk JWT supplied
- AUTONOMY_WRITE_DISABLED when HAM_SOCIAL_AUTONOMY_WRITE_TOKEN is absent
- 422 for unknown top-level key in request body
- 422 for unknown nested key inside channels (e.g. writable ``available`` field)
- quiet_hours-only update back-compat (byte-for-byte with existing behaviour)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import apply_social_autonomy_profile

client = TestClient(app)

_TOKEN = "settings-write-token"  # noqa: S105


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _disable_clerk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target = tmp_path / "profile.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(target))
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)
    _disable_clerk(monkeypatch)
    return target


def _headers(token: str = _TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    created_at = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    payload: dict[str, Any] = {
        "profile_id": "settings-test-profile",
        "status": "draft",
        "goal": "Grow awareness for HAM safely.",
        "persona_id": "ham-canonical",
        "channels": {
            "x": {"enabled": False, "available": True},
            "telegram": {"enabled": False, "available": True},
            "discord": {"enabled": False, "available": False},
        },
        "actions_allowed_per_channel": {
            "x": ["reply", "broadcast"],
            "telegram": ["message"],
            "discord": [],
        },
        "daily_caps": {"x": 0, "telegram": 0, "discord": 0},
        "cadence": "manual",
        "quiet_hours": None,
        "forbidden_topics": [],
        "safety_rules": [
            "credential_request",
            "price_guarantee",
            "mass_tagging",
            "repeated_payload",
            "no_external_links",
            "payload_min_length",
        ],
        "learning_enabled": False,
        "emergency_stop": False,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": created_at.isoformat().replace("+00:00", "Z"),
    }
    payload.update(overrides)
    return payload


def _profile(**overrides: Any) -> GoHamSocialProfile:
    return GoHamSocialProfile.model_validate(_profile_payload(**overrides))


def _persist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, profile: GoHamSocialProfile) -> None:
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    apply_social_autonomy_profile(tmp_path, profile, token=_TOKEN, actor="pytest")


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


def test_patch_settings_channels_only_persists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """PATCH with channels-only body updates enabled flags; available is preserved."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"channels": {"telegram": {"enabled": True}, "x": {"enabled": False}}},
        headers=_headers(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    # telegram.enabled toggled to True
    assert body["channels"]["telegram"]["enabled"] is True
    # available should be preserved (server-managed, not overwritten)
    assert body["channels"]["telegram"]["available"] is True
    # x.enabled stays False
    assert body["channels"]["x"]["enabled"] is False
    # Status unchanged
    assert body["status"] == "draft"
    # daily_caps unchanged
    assert body["daily_caps"]["telegram"] == 0


def test_patch_settings_daily_caps_only_persists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """PATCH with daily_caps-only body updates cap values; channels unchanged."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"daily_caps": {"telegram": 5, "x": 2, "discord": 0}},
        headers=_headers(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["daily_caps"] == {"telegram": 5, "x": 2, "discord": 0}
    # channels unchanged
    assert body["channels"]["telegram"]["enabled"] is False
    assert body["status"] == "draft"


def test_patch_settings_combined_channels_daily_caps_quiet_hours(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """PATCH with all three keys together; all persist correctly."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={
            "channels": {
                "telegram": {"enabled": True},
                "x": {"enabled": False},
                "discord": {"enabled": False},
            },
            "daily_caps": {"telegram": 1, "x": 0, "discord": 0},
            "quiet_hours": {"start_hour": 23, "end_hour": 7, "timezone": "UTC"},
        },
        headers=_headers(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["channels"]["telegram"]["enabled"] is True
    assert body["channels"]["telegram"]["available"] is True
    assert body["daily_caps"] == {"telegram": 1, "x": 0, "discord": 0}
    assert body["quiet_hours"] == {"start_hour": 23, "end_hour": 7, "timezone": "UTC"}
    assert body["status"] == "draft"
    assert body["emergency_stop"] is False


def test_patch_settings_quiet_hours_only_backcompat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Quiet-hours-only PATCH still works byte-for-byte — back-compat guard."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"quiet_hours": {"start_hour": 22, "end_hour": 6, "timezone": "Europe/Berlin"}},
        headers=_headers(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["quiet_hours"] == {
        "start_hour": 22,
        "end_hour": 6,
        "timezone": "Europe/Berlin",
    }
    # channels and daily_caps unchanged
    assert body["channels"]["telegram"]["enabled"] is False
    assert body["daily_caps"]["telegram"] == 0


# ---------------------------------------------------------------------------
# Auth-gate tests
# ---------------------------------------------------------------------------


def test_patch_settings_without_clerk_session_returns_401(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When Clerk enforcement is on, PATCH /settings without a Clerk JWT → 401."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())
    # Enable Clerk enforcement — the dependency raises 401 for missing Clerk JWT.
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "1")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")

    # No Authorization header at all → no Clerk JWT → 401
    response = client.patch(
        "/api/social/autonomy/settings",
        json={"channels": {"telegram": {"enabled": True}}},
    )

    assert response.status_code == 401, response.text
    detail = response.json().get("detail", {})
    assert detail.get("error", {}).get("code") == "CLERK_SESSION_REQUIRED"


def test_patch_settings_without_write_token_returns_write_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """PATCH /settings without HAM_SOCIAL_AUTONOMY_WRITE_TOKEN → write-disabled error."""
    _isolate(monkeypatch, tmp_path)
    # Deliberately do NOT set HAM_SOCIAL_AUTONOMY_WRITE_TOKEN so the env is absent.
    # _isolate already deletes it; persist without the write-token env to set up the file.
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    apply_social_autonomy_profile(tmp_path, _profile(), token=_TOKEN, actor="pytest")
    # Now remove the write token to simulate a disabled-write environment.
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", raising=False)

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"daily_caps": {"telegram": 3, "x": 0, "discord": 0}},
        headers=_headers(),
    )

    assert response.status_code == 403, response.text
    detail = response.json().get("detail", {})
    assert detail.get("error", {}).get("code") == "AUTONOMY_WRITE_DISABLED"


# ---------------------------------------------------------------------------
# Schema-rejection tests (unknown keys)
# ---------------------------------------------------------------------------


def test_patch_settings_unknown_top_level_key_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Unknown top-level key in PATCH body → 422 Unprocessable Entity."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"channels": {"telegram": {"enabled": True}}, "evil_key": "oops"},
        headers=_headers(),
    )

    assert response.status_code == 422, response.text


def test_patch_settings_unknown_nested_channels_key_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Sending ``available`` inside channels (a read-only field) → 422."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"channels": {"telegram": {"enabled": True, "available": False}}},
        headers=_headers(),
    )

    assert response.status_code == 422, response.text
