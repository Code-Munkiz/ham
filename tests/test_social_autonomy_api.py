"""HTTP contract tests for the GoHAM Social autonomy routes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.social_autonomy.schema import GoHamSocialProfile, profile_to_safe_dict
from src.ham.social_autonomy.store import apply_social_autonomy_profile

client = TestClient(app)

_TOKEN = "autonomy-write-token"  # noqa: S105


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


def _operator_headers(token: str = _TOKEN) -> dict[str, str]:
    return {
        "Authorization": "Bearer clerk-session-jwt",
        "X-Ham-Operator-Authorization": f"Bearer {token}",
    }


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    created_at = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    payload: dict[str, Any] = {
        "profile_id": "profile-1",
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
            "telegram": ["message", "activity"],
            "discord": [],
        },
        "daily_caps": {"x": 3, "telegram": 2, "discord": 0},
        "cadence": "daily",
        "quiet_hours": None,
        "forbidden_topics": ["politics"],
        "safety_rules": ["no spam", "no financial promises"],
        "learning_enabled": True,
        "emergency_stop": False,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": created_at.isoformat().replace("+00:00", "Z"),
    }
    payload.update(overrides)
    return payload


def _profile(**overrides: Any) -> GoHamSocialProfile:
    return GoHamSocialProfile.model_validate(_profile_payload(**overrides))


def _persist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    profile: GoHamSocialProfile,
) -> dict[str, Any]:
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    result = apply_social_autonomy_profile(tmp_path, profile, token=_TOKEN, actor="pytest")
    return result.effective_after


def _audit_files(tmp_path: Path) -> list[Path]:
    audit_dir = tmp_path / "_audit" / "social_autonomy"
    return sorted(audit_dir.glob("*.json")) if audit_dir.exists() else []


def _backup_files(tmp_path: Path) -> list[Path]:
    backup_dir = tmp_path / "_backups" / "social_autonomy"
    return sorted(backup_dir.glob("*.json")) if backup_dir.exists() else []


def test_get_default_draft_returns_200_without_creating_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _isolate(monkeypatch, tmp_path)

    response = client.get("/api/social/autonomy")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft"
    assert body["profile_id"]
    assert GoHamSocialProfile.model_validate(body).status == "draft"
    assert not target.exists()


def test_manual_get_autonomy_via_testclient_returns_200(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)

    assert client.get("/api/social/autonomy").status_code == 200


def test_write_status_disabled_when_env_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)

    response = client.get("/api/social/autonomy/write-status")

    assert response.status_code == 200
    assert response.json() == {
        "kind": "ham_social_autonomy_write_status",
        "writes_enabled": False,
    }


def test_write_status_enabled_when_env_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)

    response = client.get("/api/social/autonomy/write-status")

    assert response.status_code == 200
    assert response.json() == {
        "kind": "ham_social_autonomy_write_status",
        "writes_enabled": True,
    }


def test_get_returns_persisted_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    persisted = _persist(monkeypatch, tmp_path, _profile(status="paused"))

    response = client.get("/api/social/autonomy")

    assert response.status_code == 200
    assert response.json() == persisted


def test_preview_no_persist_returns_normalized_profile_without_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile(profile_id="seed"))
    before_bytes = target.read_bytes()
    before_mtime = target.stat().st_mtime_ns
    audit_before = list(_audit_files(tmp_path))
    backups_before = list(_backup_files(tmp_path))
    candidate = _profile(profile_id="candidate", goal="  Grow HAM awareness safely.  ")

    response = client.post("/api/social/autonomy/preview", json=candidate.model_dump(mode="json"))

    assert response.status_code == 200
    body = response.json()
    assert body == profile_to_safe_dict(candidate)
    assert body["goal"] == "Grow HAM awareness safely."
    assert target.read_bytes() == before_bytes
    assert target.stat().st_mtime_ns == before_mtime
    assert _audit_files(tmp_path) == audit_before
    assert _backup_files(tmp_path) == backups_before


def test_preview_validation_error_does_not_mutate_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile(profile_id="seed"))
    before_bytes = target.read_bytes()
    invalid = _profile_payload(status="armed")

    response = client.post("/api/social/autonomy/preview", json=invalid)

    assert response.status_code == 422
    assert target.read_bytes() == before_bytes


def test_launch_transitions_to_running_and_writes_audit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile(status="draft"))
    audit_before = len(_audit_files(tmp_path))

    response = client.post("/api/social/autonomy/launch", headers=_headers())

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert client.get("/api/social/autonomy").json()["status"] == "running"
    assert len(_audit_files(tmp_path)) == audit_before + 1


def test_launch_transitions_paused_to_running(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile(status="paused"))

    response = client.post("/api/social/autonomy/launch", headers=_headers())

    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_launch_write_token_required(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)

    missing_env = client.post("/api/social/autonomy/launch", headers=_headers())
    assert missing_env.status_code == 403
    assert missing_env.json()["detail"]["error"]["code"] == "AUTONOMY_WRITE_DISABLED"

    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    missing_header = client.post("/api/social/autonomy/launch")
    assert missing_header.status_code == 401
    assert missing_header.json()["detail"]["error"]["code"] == "AUTONOMY_AUTH_REQUIRED"

    wrong_header = client.post("/api/social/autonomy/launch", headers=_headers("wrong-token"))
    assert wrong_header.status_code == 403
    assert wrong_header.json()["detail"]["error"]["code"] == "AUTONOMY_AUTH_INVALID"


def test_pause_transitions_to_paused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile(status="running"))

    response = client.post("/api/social/autonomy/pause", headers=_headers())

    assert response.status_code == 200
    assert response.json()["status"] == "paused"
    assert client.get("/api/social/autonomy").json()["status"] == "paused"


def test_pause_idempotent_on_paused_without_audit_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)
    paused = _persist(monkeypatch, tmp_path, _profile(status="paused"))
    audit_before = len(_audit_files(tmp_path))

    response = client.post("/api/social/autonomy/pause", headers=_headers())

    assert response.status_code == 200
    assert response.json() == paused
    assert len(_audit_files(tmp_path)) == audit_before


def test_stop_transitions_to_stopped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile(status="running"))

    response = client.post("/api/social/autonomy/stop", headers=_headers())

    assert response.status_code == 200
    assert response.json()["status"] == "stopped"
    assert response.json()["emergency_stop"] is False
    assert client.get("/api/social/autonomy").json()["status"] == "stopped"


def test_stop_sets_emergency_stop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile(status="paused"))

    response = client.post(
        "/api/social/autonomy/stop",
        json={"emergency_stop": True},
        headers=_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "stopped"
    assert body["emergency_stop"] is True
    assert client.get("/api/social/autonomy").json()["emergency_stop"] is True


def test_settings_patch_preserves_status_and_updates_limits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile(status="running", quiet_hours=None))

    response = client.patch(
        "/api/social/autonomy/settings",
        json={
            "daily_caps": {"x": 5, "telegram": 4, "discord": 0},
            "quiet_hours": {"start_hour": 22, "end_hour": 6, "timezone": "UTC"},
        },
        headers=_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["daily_caps"] == {"x": 5, "telegram": 4, "discord": 0}
    assert body["quiet_hours"] == {"start_hour": 22, "end_hour": 6, "timezone": "UTC"}
    assert client.get("/api/social/autonomy").json()["status"] == "running"


def test_settings_patch_rejects_status_change_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile(status="running"))
    before = json.loads(target.read_text(encoding="utf-8"))

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"status": "paused", "daily_caps": {"x": 1, "telegram": 1, "discord": 0}},
        headers=_headers(),
    )

    assert response.status_code == 422
    after = json.loads(target.read_text(encoding="utf-8"))
    assert after["status"] == "running"
    assert after == before


@pytest.mark.parametrize(
    ("method", "path", "seed_status", "body", "expected_status"),
    [
        ("post", "/api/social/autonomy/launch", "draft", None, "running"),
        ("post", "/api/social/autonomy/pause", "running", None, "paused"),
        ("post", "/api/social/autonomy/stop", "running", {}, "stopped"),
        (
            "patch",
            "/api/social/autonomy/settings",
            "running",
            {"daily_caps": {"x": 1, "telegram": 1, "discord": 0}},
            "running",
        ),
    ],
)
def test_mutating_routes_accept_operator_header_with_clerk_authorization_present(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    method: str,
    path: str,
    seed_status: str,
    body: dict[str, Any] | None,
    expected_status: str,
) -> None:
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile(status=seed_status))
    request = getattr(client, method)

    if body is None:
        response = request(path, headers=_operator_headers())
    else:
        response = request(path, json=body, headers=_operator_headers())

    assert response.status_code == 200
    assert response.json()["status"] == expected_status


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/social/autonomy/launch", None),
        ("post", "/api/social/autonomy/pause", None),
        ("post", "/api/social/autonomy/stop", {}),
        (
            "patch",
            "/api/social/autonomy/settings",
            {"daily_caps": {"x": 1, "telegram": 1, "discord": 0}},
        ),
    ],
)
def test_write_token_matrix_for_mutating_routes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    _isolate(monkeypatch, tmp_path)
    request = getattr(client, method)

    missing_env = request(path, json=body, headers=_headers())
    assert missing_env.status_code == 403

    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    missing_bearer = request(path, json=body)
    assert missing_bearer.status_code == 401

    wrong_bearer = request(path, json=body, headers=_headers("wrong-token"))
    assert wrong_bearer.status_code == 403

    assert client.get("/api/social/autonomy").status_code == 200
    preview = client.post("/api/social/autonomy/preview", json=_profile().model_dump(mode="json"))
    assert preview.status_code == 200


def test_no_live_transport(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    calls = {
        "telegram_send": 0,
        "reactive_live": 0,
        "reactive_batch": 0,
        "live_controller": 0,
    }

    def _forbidden(name: str) -> Any:
        def _inner(*args: Any, **kwargs: Any) -> Any:
            calls[name] += 1
            raise RuntimeError(f"{name} forbidden during autonomy route")

        return _inner

    monkeypatch.setattr(
        "src.api.social.send_confirmed_telegram_message", _forbidden("telegram_send")
    )
    monkeypatch.setattr("src.api.social.run_reactive_live_once", _forbidden("reactive_live"))
    monkeypatch.setattr("src.api.social.run_reactive_batch_once", _forbidden("reactive_batch"))
    monkeypatch.setattr("src.api.social.run_live_controller_once", _forbidden("live_controller"))
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)

    assert client.get("/api/social/autonomy").status_code == 200
    assert (
        client.post(
            "/api/social/autonomy/preview", json=_profile().model_dump(mode="json")
        ).status_code
        == 200
    )
    assert client.post("/api/social/autonomy/launch", headers=_headers()).status_code == 200
    assert client.post("/api/social/autonomy/pause", headers=_headers()).status_code == 200
    assert client.post("/api/social/autonomy/stop", headers=_headers()).status_code == 200
    assert (
        client.patch(
            "/api/social/autonomy/settings",
            json={"daily_caps": {"x": 1, "telegram": 1, "discord": 0}},
            headers=_headers(),
        ).status_code
        == 200
    )

    assert calls == {
        "telegram_send": 0,
        "reactive_live": 0,
        "reactive_batch": 0,
        "live_controller": 0,
    }


def test_no_env_file_reads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    calls = {"load_dotenv": 0}

    import dotenv

    def _load_dotenv_forbidden(*args: Any, **kwargs: Any) -> bool:
        calls["load_dotenv"] += 1
        raise RuntimeError("load_dotenv forbidden during autonomy route")

    monkeypatch.setattr(dotenv, "load_dotenv", _load_dotenv_forbidden)

    assert client.get("/api/social/autonomy").status_code == 200
    assert (
        client.post(
            "/api/social/autonomy/preview", json=_profile().model_dump(mode="json")
        ).status_code
        == 200
    )
    assert client.post("/api/social/autonomy/launch", headers=_headers()).status_code == 200
    assert (
        client.patch(
            "/api/social/autonomy/settings",
            json={"daily_caps": {"x": 2, "telegram": 1, "discord": 0}},
            headers=_headers(),
        ).status_code
        == 200
    )

    assert calls == {"load_dotenv": 0}
