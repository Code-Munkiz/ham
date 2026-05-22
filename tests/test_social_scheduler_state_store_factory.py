"""Env-switch factory tests for the social scheduler state store.

VAL-M15-M1-STORE-ENVSWITCH-SCHEDSTATE-019
"""

from __future__ import annotations

import pytest

from src.ham.social_scheduler_state_store import (
    SocialSchedulerStateFileStore,
    build_social_scheduler_state_store,
    set_social_scheduler_state_store_for_tests,
)


class TestEnvSwitchSelectsBackend:
    """VAL-M15-M1-STORE-ENVSWITCH-SCHEDSTATE-019"""

    def test_env_switch_selects_backend(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_social_scheduler_state_store_for_tests(None)

        monkeypatch.delenv("HAM_SOCIAL_SCHEDULER_STATE_BACKEND", raising=False)
        assert isinstance(build_social_scheduler_state_store(), SocialSchedulerStateFileStore)

        monkeypatch.setenv("HAM_SOCIAL_SCHEDULER_STATE_BACKEND", "file")
        assert isinstance(build_social_scheduler_state_store(), SocialSchedulerStateFileStore)

        monkeypatch.setenv("HAM_SOCIAL_SCHEDULER_STATE_BACKEND", "firestore")
        store_fs = build_social_scheduler_state_store()
        from src.ham.social_scheduler_state_firestore import FirestoreSocialSchedulerStateStore

        assert isinstance(store_fs, FirestoreSocialSchedulerStateStore)

    def test_unknown_backend_falls_back_to_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("HAM_SOCIAL_SCHEDULER_STATE_BACKEND", "bad_value")
        assert isinstance(build_social_scheduler_state_store(), SocialSchedulerStateFileStore)
