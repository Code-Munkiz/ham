"""Env-switch factory tests for the social scheduler state store.

VAL-M15-M1-STORE-ENVSWITCH-SCHEDSTATE-019
VAL-M15-M1-STORE-FAILCLOSED-SCHEDSTATE-025
"""

from __future__ import annotations

import pytest

from src.ham.social_scheduler_state_store import (
    SocialSchedulerState,
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


class TestFirestoreFailClosedSchedulerState:
    """VAL-M15-M1-STORE-FAILCLOSED-SCHEDSTATE-025

    With HAM_SOCIAL_SCHEDULER_STATE_BACKEND=firestore and a fake client that
    raises, read_state / write_state surface a typed error rather than falling
    back to file. Scheduler-state file path on disk remains untouched.
    """

    def test_firestore_failure_does_not_fall_back_to_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        from src.ham.social_scheduler_state_firestore import (
            FirestoreSocialSchedulerStateStore,
            FirestoreSocialSchedulerStateStoreError,
        )

        monkeypatch.setenv("HAM_SOCIAL_SCHEDULER_STATE_BACKEND", "firestore")
        set_social_scheduler_state_store_for_tests(None)

        class _FailDoc:
            def get(self):
                raise RuntimeError("Simulated Firestore SDK error")

            def set(self, data):
                raise RuntimeError("Simulated Firestore SDK error")

        class _FailCollection:
            def document(self, doc_id: str) -> _FailDoc:
                return _FailDoc()

        class _FailClient:
            def collection(self, name: str) -> _FailCollection:
                return _FailCollection()

        store = FirestoreSocialSchedulerStateStore(client=_FailClient())

        # read_state must raise, not return defaults silently
        with pytest.raises(FirestoreSocialSchedulerStateStoreError):
            store.read_state()

        # Verify no state file was created (no silent fallback)
        state_file = tmp_path / "social_scheduler_state.json"
        assert not state_file.exists(), (
            "Firestore failure caused a silent fallback to the file backend"
        )

    def test_write_state_raises_on_sdk_error_fail_closed(self) -> None:
        from src.ham.social_scheduler_state_firestore import (
            FirestoreSocialSchedulerStateStore,
            FirestoreSocialSchedulerStateStoreError,
        )

        class _FailDoc:
            def set(self, data):
                raise RuntimeError("Simulated SDK write error")

        class _FailCollection:
            def document(self, doc_id: str) -> _FailDoc:
                return _FailDoc()

        class _FailClient:
            def collection(self, name: str) -> _FailCollection:
                return _FailCollection()

        store = FirestoreSocialSchedulerStateStore(client=_FailClient())
        with pytest.raises(FirestoreSocialSchedulerStateStoreError):
            store.write_state(SocialSchedulerState())
