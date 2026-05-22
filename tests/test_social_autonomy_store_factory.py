"""Env-switch factory tests for the AutonomyProfile store.

VAL-M15-M1-STORE-ENVSWITCH-AUTONOMY-014
"""

from __future__ import annotations

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
