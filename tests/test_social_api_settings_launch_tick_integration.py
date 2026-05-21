"""Integration tests for the draft → PATCH /settings → POST /launch → GET → POST /tick flow.

Uses FastAPI TestClient against an in-memory (tmp_path) profile store to verify
end-to-end: after PATCH /settings configures channels and daily_caps, POST /launch
transitions the profile to running, and a subsequent dry-run tick does NOT emit
autonomy_channel_unavailable or autonomy_channel_disabled for the enabled channel.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.clerk_auth import HamActor
from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import apply_social_autonomy_profile

client = TestClient(app)

_TOKEN = "integration-write-token"  # noqa: S105


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clerk_actor() -> HamActor:
    return HamActor(
        user_id="user_integration_test",
        org_id="org_integration_test",
        session_id="session_integration_test",
        email="operator@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Isolate the test to tmp_path; enable Clerk + write-token."""
    target = tmp_path / "profile.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(target))
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)
    return target


def _auth_headers() -> dict[str, str]:
    """Headers for a Clerk-authenticated request (no write-token in Authorization)."""
    return {"Authorization": "Bearer fake.clerk.jwt"}


def _write_headers() -> dict[str, str]:
    """Headers carrying both Clerk JWT and write-token via operator header."""
    return {
        "Authorization": "Bearer fake.clerk.jwt",
        "X-Ham-Operator-Authorization": f"Bearer {_TOKEN}",
    }


def _draft_profile_payload(**overrides: Any) -> dict[str, Any]:
    """Minimal canary-style draft profile with ONLY telegram in channels."""
    stamp = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    payload: dict[str, Any] = {
        "profile_id": "canary-integration-profile",
        "status": "draft",
        "goal": "Grow awareness for HAM safely.",
        "persona_id": "ham-canonical",
        # Only telegram — avoids discord/x channel blockers in tick assertions.
        "channels": {
            "telegram": {"enabled": False, "available": True},
        },
        "actions_allowed_per_channel": {
            "telegram": ["message"],
        },
        "daily_caps": {"telegram": 0},
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
        "created_at": stamp.isoformat().replace("+00:00", "Z"),
        "updated_at": stamp.isoformat().replace("+00:00", "Z"),
    }
    payload.update(overrides)
    return payload


def _draft_profile(**overrides: Any) -> GoHamSocialProfile:
    return GoHamSocialProfile.model_validate(_draft_profile_payload(**overrides))


def _persist_profile(tmp_path: Path, profile: GoHamSocialProfile) -> None:
    apply_social_autonomy_profile(tmp_path, profile, token=_TOKEN, actor="pytest")


def _post_tick(body: dict[str, Any]) -> Any:
    """POST /api/social/autonomy/tick with a mocked Clerk session."""
    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=_clerk_actor()):
        return client.post(
            "/api/social/autonomy/tick",
            headers=_auth_headers(),
            json=body,
        )


def _patch_settings(body: dict[str, Any]) -> Any:
    """PATCH /api/social/autonomy/settings with both Clerk JWT and write-token."""
    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=_clerk_actor()):
        return client.patch(
            "/api/social/autonomy/settings",
            headers=_write_headers(),
            json=body,
        )


def _post_launch() -> Any:
    """POST /api/social/autonomy/launch with both Clerk JWT and write-token."""
    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=_clerk_actor()):
        return client.post(
            "/api/social/autonomy/launch",
            headers=_write_headers(),
        )


def _get_autonomy() -> Any:
    """GET /api/social/autonomy with a mocked Clerk session."""
    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=_clerk_actor()):
        return client.get(
            "/api/social/autonomy",
            headers=_auth_headers(),
        )


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def test_draft_patch_launch_shows_running_with_configured_envelope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Draft profile → PATCH /settings (channels+caps) → POST /launch → GET /autonomy.

    Confirms that after PATCH the channels and daily_caps persist, launch transitions
    status to running, and the profile envelope is intact (emergency_stop=False).
    """
    _isolate(monkeypatch, tmp_path)
    _persist_profile(tmp_path, _draft_profile())

    # Step 1: PATCH /settings — enable telegram, set cap=1.
    patch_response = _patch_settings(
        {
            "channels": {"telegram": {"enabled": True}},
            "daily_caps": {"telegram": 1},
        }
    )
    assert patch_response.status_code == 200, patch_response.text
    patched = patch_response.json()
    assert patched["channels"]["telegram"]["enabled"] is True
    assert patched["channels"]["telegram"]["available"] is True
    assert patched["daily_caps"]["telegram"] == 1
    assert patched["status"] == "draft"

    # Step 2: POST /launch — transition to running.
    launch_response = _post_launch()
    assert launch_response.status_code == 200, launch_response.text
    launched = launch_response.json()
    assert launched["status"] == "running"
    assert launched["emergency_stop"] is False

    # Step 3: GET /api/social/autonomy — verify persisted envelope.
    get_response = _get_autonomy()
    assert get_response.status_code == 200, get_response.text
    profile_data = get_response.json()
    assert profile_data["status"] == "running"
    assert profile_data["emergency_stop"] is False
    assert profile_data["channels"]["telegram"]["enabled"] is True
    assert profile_data["daily_caps"]["telegram"] == 1


def test_tick_after_channel_enable_does_not_report_channel_blockers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """After enabling telegram via PATCH and launching, a dry-run tick MUST NOT emit
    autonomy_channel_unavailable or autonomy_channel_disabled for telegram.

    The profile has only the telegram channel, so the only possible channel-level
    blockers are from telegram itself. After the PATCH sets enabled=True, those
    blockers should not appear. Other blockers (e.g. cap_tracking_unavailable) may
    appear and are explicitly allowed here.
    """
    _isolate(monkeypatch, tmp_path)
    _persist_profile(tmp_path, _draft_profile())

    # Configure: enable telegram.
    patch_resp = _patch_settings(
        {
            "channels": {"telegram": {"enabled": True}},
            "daily_caps": {"telegram": 1},
        }
    )
    assert patch_resp.status_code == 200, patch_resp.text

    # Launch → running.
    launch_resp = _post_launch()
    assert launch_resp.status_code == 200, launch_resp.text
    assert launch_resp.json()["status"] == "running"

    # Dry-run tick.
    tick_response = _post_tick({"dry_run": True, "run_once": True})
    assert tick_response.status_code == 200, tick_response.text
    body = tick_response.json()

    blocked: list[str] = body.get("blocked_reasons", [])
    assert "autonomy_channel_unavailable" not in blocked, (
        f"autonomy_channel_unavailable should not appear after enabling telegram; "
        f"full blocked_reasons: {blocked}"
    )
    assert "autonomy_channel_disabled" not in blocked, (
        f"autonomy_channel_disabled should not appear after enabling telegram; "
        f"full blocked_reasons: {blocked}"
    )


def test_launch_idempotency_leaves_envelope_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A second POST /launch on an already-running profile returns 200 and the
    profile envelope is byte-for-byte unchanged (status, channels, daily_caps, etc.).
    """
    _isolate(monkeypatch, tmp_path)
    _persist_profile(tmp_path, _draft_profile())

    # PATCH + first launch.
    _patch_settings(
        {
            "channels": {"telegram": {"enabled": True}},
            "daily_caps": {"telegram": 1},
        }
    )
    first_launch = _post_launch()
    assert first_launch.status_code == 200, first_launch.text
    first_body = first_launch.json()

    # Second launch on an already-running profile must be idempotent.
    second_launch = _post_launch()
    assert second_launch.status_code == 200, second_launch.text
    second_body = second_launch.json()

    # The envelope must be identical (status, channels, daily_caps, emergency_stop).
    assert second_body["status"] == first_body["status"]
    assert second_body["channels"] == first_body["channels"]
    assert second_body["daily_caps"] == first_body["daily_caps"]
    assert second_body["emergency_stop"] == first_body["emergency_stop"]
    assert second_body["profile_id"] == first_body["profile_id"]
