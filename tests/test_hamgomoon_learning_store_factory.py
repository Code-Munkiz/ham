"""Env-switch factory tests for the HAMgomoon learning store.

VAL-M15-M1-STORE-ENVSWITCH-LEARNING-016
"""

from __future__ import annotations

import pytest

from src.ham.hamgomoon_learning.store import (
    HamgomoonLearningFileStore,
    build_hamgomoon_learning_store,
    set_hamgomoon_learning_store_for_tests,
)


class TestEnvSwitchSelectsBackend:
    """VAL-M15-M1-STORE-ENVSWITCH-LEARNING-016"""

    def test_env_switch_selects_backend(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_hamgomoon_learning_store_for_tests(None)

        monkeypatch.delenv("HAM_HAMGOMOON_LEARNING_BACKEND", raising=False)
        assert isinstance(build_hamgomoon_learning_store(), HamgomoonLearningFileStore)

        monkeypatch.setenv("HAM_HAMGOMOON_LEARNING_BACKEND", "file")
        assert isinstance(build_hamgomoon_learning_store(), HamgomoonLearningFileStore)

        monkeypatch.setenv("HAM_HAMGOMOON_LEARNING_BACKEND", "firestore")
        store_fs = build_hamgomoon_learning_store()
        from src.ham.hamgomoon_learning.firestore_store import FirestoreHamgomoonLearningStore

        assert isinstance(store_fs, FirestoreHamgomoonLearningStore)

    def test_unknown_backend_falls_back_to_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("HAM_HAMGOMOON_LEARNING_BACKEND", "whatever")
        assert isinstance(build_hamgomoon_learning_store(), HamgomoonLearningFileStore)
