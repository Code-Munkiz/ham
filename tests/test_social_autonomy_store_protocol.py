"""Protocol conformance tests for the AutonomyProfile file backend.

VAL-M15-M1-STORE-PROTOCOL-AUTONOMY-FILE-001
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import (
    SocialAutonomyFileStore,
    SocialAutonomyStoreProtocol,
    set_social_autonomy_store_for_tests,
)
from src.ham.social_autonomy.store_protocol import (
    SocialAutonomyStoreProtocol as ProtocolFromAggregator,
)


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    created_at = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    payload: dict[str, Any] = {
        "profile_id": "profile-proto-test",
        "status": "draft",
        "goal": "Test protocol conformance.",
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
        "created_at": created_at,
        "updated_at": created_at,
    }
    payload.update(overrides)
    return payload


def _profile(**overrides: Any) -> GoHamSocialProfile:
    return GoHamSocialProfile.model_validate(_profile_payload(**overrides))


class TestFileBackendConformsToProtocol:
    """VAL-M15-M1-STORE-PROTOCOL-AUTONOMY-FILE-001"""

    def test_file_backend_conforms_to_protocol(self) -> None:
        store = SocialAutonomyFileStore()
        assert isinstance(store, SocialAutonomyStoreProtocol)

    def test_protocol_from_aggregator_same_class(self) -> None:
        """store_protocol.py re-exports the same Protocol class."""
        assert SocialAutonomyStoreProtocol is ProtocolFromAggregator

    def test_file_backend_read_returns_default_when_no_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(tmp_path / "profile.json"))
        store = SocialAutonomyFileStore()
        profile = store.read(None)
        assert isinstance(profile, GoHamSocialProfile)
        assert profile.status == "draft"

    def test_file_backend_roundtrip(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(tmp_path / "profile.json"))
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", "test-token")  # noqa: S106
        store = SocialAutonomyFileStore()
        p = _profile()
        result = store.apply(None, p, token="test-token", actor="test")
        assert result.effective_after["profile_id"] == "profile-proto-test"
        recovered = store.read(None)
        assert recovered.profile_id == "profile-proto-test"

    def test_file_backend_path_method(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = tmp_path / "profile.json"
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(target))
        store = SocialAutonomyFileStore()
        assert store.path(None) == target

    def test_file_backend_writes_enabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", raising=False)
        store = SocialAutonomyFileStore()
        assert store.writes_enabled() is False
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", "tok")  # noqa: S106
        assert store.writes_enabled() is True

    def test_set_social_autonomy_store_for_tests(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """set_social_autonomy_store_for_tests injects a custom store; None restores default."""
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(tmp_path / "profile.json"))
        custom = SocialAutonomyFileStore()
        set_social_autonomy_store_for_tests(custom)
        try:
            from src.ham.social_autonomy.store import get_social_autonomy_store

            assert get_social_autonomy_store() is custom
        finally:
            set_social_autonomy_store_for_tests(None)
        # After reset, a fresh build is used
        from src.ham.social_autonomy.store import get_social_autonomy_store as _g

        fresh = _g()
        assert fresh is not custom
