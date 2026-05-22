"""Env-switch factory tests for the AutonomyProfile store.

Covers:
- VAL-M15-M1-STORE-ENVSWITCH-AUTONOMY-014: env switch selects correct backend
- VAL-M15-M1-STORE-FAILCLOSED-AUTONOMY-020: Firestore failure does not fall back to file
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.ham.social_autonomy.store import (
    SocialAutonomyFileStore,
    build_social_autonomy_store,
    set_social_autonomy_store_for_tests,
)


class TestEnvSwitchSelectsBackend:
    """VAL-M15-M1-STORE-ENVSWITCH-AUTONOMY-014"""

    def test_env_switch_selects_backend(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Unset / =file → file backend; =firestore → Firestore backend."""
        # Reset singleton between each sub-check
        set_social_autonomy_store_for_tests(None)

        # Unset → file backend
        monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_STORE_BACKEND", raising=False)
        store_unset = build_social_autonomy_store()
        assert isinstance(store_unset, SocialAutonomyFileStore)

        # =file → file backend
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_STORE_BACKEND", "file")
        store_file = build_social_autonomy_store()
        assert isinstance(store_file, SocialAutonomyFileStore)

        # =firestore → Firestore backend (lazy import)
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_STORE_BACKEND", "firestore")
        store_fs = build_social_autonomy_store()
        from src.ham.social_autonomy.firestore_store import FirestoreSocialAutonomyStore

        assert isinstance(store_fs, FirestoreSocialAutonomyStore)

    def test_unknown_backend_falls_back_to_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_STORE_BACKEND", "unknown_backend")
        store = build_social_autonomy_store()
        assert isinstance(store, SocialAutonomyFileStore)

    def test_set_for_tests_then_reset(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_STORE_BACKEND", raising=False)
        from src.ham.social_autonomy.store import get_social_autonomy_store

        # Inject custom store
        custom = SocialAutonomyFileStore()
        set_social_autonomy_store_for_tests(custom)
        assert get_social_autonomy_store() is custom

        # Reset → a fresh store is built on next access
        set_social_autonomy_store_for_tests(None)
        fresh = get_social_autonomy_store()
        assert fresh is not custom
        set_social_autonomy_store_for_tests(None)  # clean up


class TestFirestoreFailClosed:
    """VAL-M15-M1-STORE-FAILCLOSED-AUTONOMY-020"""

    def test_firestore_failure_does_not_silently_fall_back_to_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """With firestore backend + failing client, read() raises; no file I/O."""
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_STORE_BACKEND", "firestore")
        # Point the file path to a temp directory so we can verify it's not written
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(tmp_path / "profile.json"))

        from src.ham.social_autonomy.firestore_store import (
            FirestoreSocialAutonomyStore,
            FirestoreSocialAutonomyStoreError,
        )

        # Failing fake client — every SDK call raises
        class _ErrorDocRef:
            @property
            def path(self) -> str:
                return "ham_social_autonomy_profiles/goham-social-default"

            def get(self, transaction: Any = None) -> None:
                raise RuntimeError("Simulated Firestore SDK unavailable")

            def collection(self, name: str) -> Any:
                return _ErrorDocRef()

            def document(self, doc_id: str) -> _ErrorDocRef:
                return _ErrorDocRef()

            def set(self, data: Any) -> None:
                raise RuntimeError("Simulated Firestore SDK unavailable")

        class _ErrorCollection:
            def document(self, doc_id: str) -> _ErrorDocRef:
                return _ErrorDocRef()

        class _ErrorClient:
            def collection(self, name: str) -> _ErrorCollection:
                return _ErrorCollection()

            def transaction(self) -> Any:
                raise RuntimeError("Simulated Firestore SDK unavailable")

        store = FirestoreSocialAutonomyStore(client=_ErrorClient())
        set_social_autonomy_store_for_tests(store)

        try:
            # Factory returns the Firestore backend, not the file backend
            assert isinstance(store, FirestoreSocialAutonomyStore)

            # read() raises FirestoreSocialAutonomyStoreError — does NOT return
            # a file-backed default or write to the local JSON file
            with pytest.raises(FirestoreSocialAutonomyStoreError):
                store.read(None)

            # The local file was NOT created (no silent fallback to file backend)
            file_path = tmp_path / "profile.json"
            assert not file_path.exists(), (
                "File backend file should NOT exist when Firestore backend is active"
            )
        finally:
            set_social_autonomy_store_for_tests(None)

    def test_firestore_apply_failure_does_not_fall_back_to_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """With firestore backend + failing client, apply() raises; no file I/O."""
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_STORE_BACKEND", "firestore")
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(tmp_path / "profile.json"))
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", "test-token")  # noqa: S106

        from datetime import UTC, datetime

        from src.ham.social_autonomy.firestore_store import (
            FirestoreSocialAutonomyStore,
            FirestoreSocialAutonomyStoreError,
        )
        from src.ham.social_autonomy.schema import GoHamSocialProfile

        # Transaction fails on set()
        class _FailTxTransaction:
            @property
            def in_progress(self) -> bool:
                return True

            def _begin(self, retry_id: Any = None) -> None:
                pass

            def set(self, ref: Any, data: Any) -> None:
                raise RuntimeError("Simulated Firestore transaction failure")

            def _commit(self) -> list:
                return []

            def _rollback(self) -> None:
                pass

        class _FailDocRef:
            @property
            def path(self) -> str:
                return "ham_social_autonomy_profiles/goham-social-default"

            def get(self, transaction: Any = None) -> Any:
                class _EmptySnap:
                    exists = False

                    def to_dict(self) -> dict:
                        return {}

                return _EmptySnap()

            def collection(self, name: str) -> Any:
                return _FailDocRef()

            def document(self, doc_id: str) -> _FailDocRef:
                return _FailDocRef()

            def set(self, data: Any) -> None:
                raise RuntimeError("Simulated Firestore error")

        class _FailCollection:
            def document(self, doc_id: str) -> _FailDocRef:
                return _FailDocRef()

        class _FailClient:
            def collection(self, name: str) -> _FailCollection:
                return _FailCollection()

            def transaction(self) -> _FailTxTransaction:
                return _FailTxTransaction()

        created_at = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
        profile = GoHamSocialProfile.model_validate(
            {
                "profile_id": "goham-social-default",
                "status": "draft",
                "goal": "Test",
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
                "daily_caps": {"x": 0, "telegram": 0, "discord": 0},
                "cadence": "manual",
                "forbidden_topics": [],
                "safety_rules": [],
                "learning_enabled": True,
                "emergency_stop": False,
                "created_at": created_at,
                "updated_at": created_at,
            }
        )

        store = FirestoreSocialAutonomyStore(client=_FailClient())

        with pytest.raises(FirestoreSocialAutonomyStoreError):
            store.apply(None, profile, token="test-token", actor="test")

        # File backend should NOT have been written
        file_path = tmp_path / "profile.json"
        assert not file_path.exists(), (
            "File backend file should NOT be written when Firestore backend fails"
        )
