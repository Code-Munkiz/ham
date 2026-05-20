"""Cross-area integration tests for Social autonomy API round-trips.

These tests exercise the FastAPI route surface against the file-backed
``HAM_SOCIAL_AUTONOMY_PATH`` store so the frontend integration suite has a
paired backend contract covering real on-disk persistence.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import apply_social_autonomy_profile

client = TestClient(app)

_TOKEN = "integration-autonomy-token"  # noqa: S105


def _headers(token: str = _TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target = tmp_path / "profile.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(target))
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)
    monkeypatch.delenv("HAMGOMOON_AUTOPILOT_ENABLED", raising=False)
    monkeypatch.delenv("HAMGOMOON_AUTOPILOT_DRY_RUN", raising=False)
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
    return target


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    created_at = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    payload: dict[str, Any] = {
        "profile_id": "integration-profile",
        "status": "draft",
        "goal": "Grow awareness for HAM safely.",
        "persona_id": "ham-canonical",
        "channels": {
            "x": {"enabled": True, "available": True},
            "telegram": {"enabled": True, "available": True},
            "discord": {"enabled": False, "available": False},
        },
        "actions_allowed_per_channel": {
            "x": ["reply", "broadcast"],
            "telegram": ["message", "activity", "reply"],
            "discord": [],
        },
        "daily_caps": {"x": 3, "telegram": 5, "discord": 0},
        "cadence": "daily",
        "quiet_hours": None,
        "forbidden_topics": [],
        "safety_rules": [
            "no spam",
            "no mass tagging",
            "no financial promises",
            "no credential requests",
            "emergency stop available",
        ],
        "learning_enabled": True,
        "emergency_stop": False,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": created_at.isoformat().replace("+00:00", "Z"),
    }
    payload.update(overrides)
    return payload


def _profile(**overrides: Any) -> GoHamSocialProfile:
    return GoHamSocialProfile.model_validate(_profile_payload(**overrides))


def _persist(tmp_path: Path, profile: GoHamSocialProfile) -> None:
    apply_social_autonomy_profile(tmp_path, profile, token=_TOKEN, actor="pytest")


def _read_disk(target: Path) -> dict[str, Any]:
    return json.loads(target.read_text(encoding="utf-8"))


def test_launch_pause_resume_and_stop_round_trip_to_disk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _isolate(monkeypatch, tmp_path)
    _persist(tmp_path, _profile(status="draft"))

    launch = client.post("/api/social/autonomy/launch", headers=_headers())
    assert launch.status_code == 200
    assert launch.json()["status"] == "running"
    assert _read_disk(target)["status"] == "running"
    assert client.get("/api/social/autonomy").json()["status"] == "running"

    pause = client.post("/api/social/autonomy/pause", headers=_headers())
    assert pause.status_code == 200
    assert pause.json()["status"] == "paused"
    assert _read_disk(target)["status"] == "paused"
    assert client.get("/api/social/autonomy").json()["status"] == "paused"

    resume = client.post("/api/social/autonomy/launch", headers=_headers())
    assert resume.status_code == 200
    assert resume.json()["status"] == "running"
    assert _read_disk(target)["status"] == "running"

    stop = client.post("/api/social/autonomy/stop", headers=_headers())
    assert stop.status_code == 200
    assert stop.json()["status"] == "stopped"
    assert stop.json()["emergency_stop"] is False
    assert _read_disk(target)["status"] == "stopped"
    assert client.get("/api/social/autonomy").json()["status"] == "stopped"


def test_stop_from_paused_and_emergency_stop_persist_to_disk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _isolate(monkeypatch, tmp_path)
    _persist(tmp_path, _profile(status="paused"))

    paused_stop = client.post("/api/social/autonomy/stop", headers=_headers())
    assert paused_stop.status_code == 200
    assert paused_stop.json()["status"] == "stopped"
    assert _read_disk(target)["status"] == "stopped"

    _persist(tmp_path, _profile(status="running"))
    emergency = client.post(
        "/api/social/autonomy/stop",
        json={"emergency_stop": True},
        headers=_headers(),
    )
    assert emergency.status_code == 200
    body = emergency.json()
    assert body["status"] == "stopped"
    assert body["emergency_stop"] is True
    on_disk = _read_disk(target)
    assert on_disk["status"] == "stopped"
    assert on_disk["emergency_stop"] is True
    assert client.get("/api/social/autonomy").json()["emergency_stop"] is True


def test_settings_patch_updates_caps_byte_equal_and_preserves_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _isolate(monkeypatch, tmp_path)
    _persist(tmp_path, _profile(status="running", daily_caps={"x": 3, "telegram": 5, "discord": 0}))

    new_caps = {"x": 8, "telegram": 6, "discord": 0}
    response = client.patch(
        "/api/social/autonomy/settings",
        json={"daily_caps": new_caps},
        headers=_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["daily_caps"] == new_caps
    on_disk = _read_disk(target)
    assert on_disk["status"] == "running"
    assert on_disk["daily_caps"] == new_caps
    assert client.get("/api/social/autonomy").json()["daily_caps"] == new_caps


def test_default_launch_creates_profile_without_live_apply_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _isolate(monkeypatch, tmp_path)
    assert not target.exists()

    response = client.post("/api/social/autonomy/launch", headers=_headers())

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert target.exists()
    assert _read_disk(target)["status"] == "running"
    live_apply_token_name = "_".join(["HAM", "SOCIAL", "LIVE", "APPLY", "TOKEN"])
    assert live_apply_token_name not in target.read_text(encoding="utf-8")
