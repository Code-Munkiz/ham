"""Tick runner store-backend regression tests (Mission 17).

Ensures ``run_social_autonomy_tick`` reads/writes through the configured
``get_social_autonomy_store()`` backend instead of the legacy file-only gate.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.clerk_auth import HamActor
from src.ham.social_autonomy.firestore_store import (
    FirestoreSocialAutonomyStore,
    FirestoreSocialAutonomyStoreError,
)
from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import (
    apply_social_autonomy_profile,
    set_social_autonomy_store_for_tests,
    social_autonomy_path,
)
from src.ham.social_autonomy.tick import (
    AUTONOMY_PROFILE_MISSING,
    run_social_autonomy_tick,
)
from tests.test_firestore_social_autonomy_store import _store_with_fake

_TOKEN = "autonomy-write-token"  # noqa: S105
_NOW = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_social_autonomy_store_singleton() -> Any:
    set_social_autonomy_store_for_tests(None)
    yield
    set_social_autonomy_store_for_tests(None)


def _actor() -> HamActor:
    return HamActor(
        user_id="user_tick_store_backend",
        org_id="org_tick_store_backend",
        session_id="session_tick_store_backend",
        email="operator@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _zero_usage(channel: str, action: str, now: datetime) -> int:
    assert channel
    assert action
    assert now == _NOW
    return 0


def _allowing_content_guard(*_args: Any, **_kwargs: Any) -> list[str]:
    return []


def _configure_file_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target = tmp_path / "profile.json"
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(target))
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_STORE_BACKEND", raising=False)
    set_social_autonomy_store_for_tests(None)
    return target


def _configure_firestore_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[FirestoreSocialAutonomyStore, Path]:
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_STORE_BACKEND", "firestore")
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    monkeypatch.chdir(tmp_path)
    store, _fake = _store_with_fake()
    set_social_autonomy_store_for_tests(store)
    return store, social_autonomy_path(tmp_path)


def _running_telegram_profile(**overrides: Any) -> GoHamSocialProfile:
    created_at = _NOW - timedelta(days=1)
    payload: dict[str, Any] = {
        "profile_id": "goham-social-default",
        "status": "running",
        "goal": "Mission 17 Firestore tick store regression.",
        "persona_id": "ham-canonical",
        "channels": {
            "telegram": {"enabled": True, "available": True},
            "x": {"enabled": False, "available": True},
            "discord": {"enabled": False, "available": False},
        },
        "actions_allowed_per_channel": {
            "telegram": ["message", "activity"],
            "x": [],
            "discord": [],
        },
        "daily_caps": {"telegram": 1, "x": 0, "discord": 0},
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
        "learning_enabled": True,
        "emergency_stop": False,
        "created_at": created_at,
        "updated_at": created_at,
    }
    payload.update(overrides)
    return GoHamSocialProfile.model_validate(payload)


def test_file_backend_missing_profile_still_returns_autonomy_profile_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = _configure_file_store(monkeypatch, tmp_path)

    result = run_social_autonomy_tick(store_path=tmp_path, now=_NOW)

    assert result.ran is False
    assert result.blocked_reasons == [AUTONOMY_PROFILE_MISSING]
    assert not target.exists()


def test_file_backend_existing_profile_still_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_file_store(monkeypatch, tmp_path)
    apply_social_autonomy_profile(
        tmp_path,
        _running_telegram_profile(
            channels={"x": {"enabled": True, "available": True}},
            actions_allowed_per_channel={"x": ["reply", "broadcast"], "telegram": ["message"]},
            daily_caps={"x": 3, "telegram": 1, "discord": 0},
        ),
        token=_TOKEN,
        actor="pytest-seed",
    )

    result = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_NOW,
        dry_run=True,
        run_once=True,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
    )

    assert AUTONOMY_PROFILE_MISSING not in result.blocked_reasons
    assert result.profile_status == "running"


def test_firestore_backend_missing_document_returns_autonomy_profile_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_firestore_store(monkeypatch, tmp_path)

    result = run_social_autonomy_tick(store_path=tmp_path, now=_NOW)

    assert result.ran is False
    assert result.blocked_reasons == [AUTONOMY_PROFILE_MISSING]
    assert result.profile_status == "stopped"


def test_firestore_backend_running_profile_is_read_by_tick(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store, file_path = _configure_firestore_store(monkeypatch, tmp_path)
    store.apply(None, _running_telegram_profile(), token=_TOKEN, actor="pytest-seed")
    assert not file_path.exists()

    result = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_NOW,
        dry_run=True,
        run_once=True,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
    )

    assert AUTONOMY_PROFILE_MISSING not in result.blocked_reasons
    assert result.profile_status == "running"


def test_firestore_backend_dry_run_reaches_telegram_dispatch_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.api.social as social_mod

    monkeypatch.setattr(
        social_mod,
        "_telegram_status_response",
        lambda: SimpleNamespace(
            overall_readiness="ready",
            hermes_gateway=SimpleNamespace(provider_runtime_state="connected"),
            telegram_self_probe_state="ok",
        ),
    )
    monkeypatch.delenv("HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH", raising=False)

    store, file_path = _configure_firestore_store(monkeypatch, tmp_path)
    store.apply(None, _running_telegram_profile(), token=_TOKEN, actor="pytest-seed")
    assert not file_path.exists()

    result = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_NOW,
        dry_run=True,
        run_once=True,
        usage_counter=_zero_usage,
        content_guard=_allowing_content_guard,
    )

    assert AUTONOMY_PROFILE_MISSING not in result.blocked_reasons
    assert result.profile_status == "running"
    assert result.actions_considered
    assert any(item.startswith("telegram:") for item in result.actions_considered)


def test_firestore_read_failure_does_not_fall_back_to_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_file_store(monkeypatch, tmp_path)
    apply_social_autonomy_profile(
        tmp_path,
        _running_telegram_profile(),
        token=_TOKEN,
        actor="pytest-seed",
    )
    assert social_autonomy_path(tmp_path).is_file()

    class _ErrorStore(FirestoreSocialAutonomyStore):
        def profile_document_exists(self, root: Path | None = None) -> bool:
            del root
            return True

        def read(self, root: Path | None = None) -> GoHamSocialProfile:
            del root
            raise FirestoreSocialAutonomyStoreError("simulated Firestore outage")

        def save(
            self,
            root: Path | None,
            profile: GoHamSocialProfile,
            *,
            actor: str = "system",
        ) -> Any:
            del root, profile, actor
            raise FirestoreSocialAutonomyStoreError("simulated Firestore outage")

    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_STORE_BACKEND", "firestore")
    set_social_autonomy_store_for_tests(_ErrorStore(client=object()))

    with pytest.raises(FirestoreSocialAutonomyStoreError, match="simulated Firestore outage"):
        run_social_autonomy_tick(
            store_path=tmp_path,
            now=_NOW,
            dry_run=True,
            run_once=True,
            usage_counter=_zero_usage,
            content_guard=_allowing_content_guard,
        )


def test_tick_route_uses_firestore_profile_when_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    store, file_path = _configure_firestore_store(monkeypatch, tmp_path)
    store.apply(None, _running_telegram_profile(status="paused"), token=_TOKEN, actor="pytest-seed")
    assert not file_path.exists()

    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=_actor()):
        response = client.post(
            "/api/social/autonomy/tick",
            headers={"Authorization": "Bearer fake.clerk.jwt"},
            json={"dry_run": True, "run_once": True},
        )

    assert response.status_code == 200
    body = response.json()
    assert AUTONOMY_PROFILE_MISSING not in body["blocked_reasons"]
    assert body["profile_status"] == "paused"


def test_scheduled_tick_delegate_reads_firestore_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_DRY_RUN", "true")
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_TOKEN", "scheduler-token")  # noqa: S106
    store, file_path = _configure_firestore_store(monkeypatch, tmp_path)
    store.apply(None, _running_telegram_profile(), token=_TOKEN, actor="pytest-seed")
    assert not file_path.exists()

    with patch(
        "src.api.social_scheduler._validate_auth",
        return_value=None,
    ):
        response = client.post(
            "/api/social/autonomy/scheduled-tick",
            headers={"Authorization": "Bearer scheduler-token"},
            json={"dry_run": True},
        )

    assert response.status_code == 200
    body = response.json()
    assert AUTONOMY_PROFILE_MISSING not in body["blocked_reasons"]
    assert body["profile_status"] == "running"
