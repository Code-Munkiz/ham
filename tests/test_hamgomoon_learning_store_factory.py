"""Env-switch factory tests for the HAMgomoon learning store.

VAL-M15-M1-STORE-ENVSWITCH-LEARNING-016
VAL-M15-M1-STORE-FAILCLOSED-LEARNING-022
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


class TestFirestoreFailClosedLearning:
    """VAL-M15-M1-STORE-FAILCLOSED-LEARNING-022

    With HAM_HAMGOMOON_LEARNING_BACKEND=firestore and a fake client that
    raises on .add/.stream, append_learning_record surfaces a typed error
    rather than writing to JSONL.
    """

    def test_firestore_failure_does_not_fall_back_to_file(
        self,
        tmp_path,
    ) -> None:
        from src.ham.hamgomoon_learning.firestore_store import (
            FirestoreHamgomoonLearningStore,
            FirestoreHamgomoonLearningStoreError,
        )
        from src.ham.hamgomoon_learning.models import LearningRecord, SocialDraftRecord

        # Create a failing fake client
        class _FailingCollection:
            def stream(self):
                raise RuntimeError("Simulated Firestore SDK error")

            def document(self, doc_id):
                class _FailDoc:
                    def set(self, data):
                        raise RuntimeError("Simulated SDK write error")

                return _FailDoc()

        class _FailingClient:
            def collection(self, name: str) -> _FailingCollection:
                return _FailingCollection()

        store = FirestoreHamgomoonLearningStore(client=_FailingClient())

        draft = SocialDraftRecord(channel="telegram", proposed_action="message", draft_text="Hello")
        record = LearningRecord(channel="telegram", draft=draft)

        # append_learning_record must surface a typed error, not silently write JSONL
        with pytest.raises(FirestoreHamgomoonLearningStoreError):
            store.append_learning_record(record)

        # Verify no file I/O: the JSONL fallback file was never created in tmp_path
        jsonl_path = tmp_path / "hamgomoon_learning.jsonl"
        assert not jsonl_path.exists(), (
            "Firestore failure caused a silent fallback to the file backend"
        )

    def test_list_records_raises_on_sdk_error(self) -> None:
        from src.ham.hamgomoon_learning.firestore_store import (
            FirestoreHamgomoonLearningStore,
            FirestoreHamgomoonLearningStoreError,
        )

        class _FailingCollection:
            def stream(self):
                raise RuntimeError("Simulated stream error")

        class _FailingClient:
            def collection(self, name: str):
                return _FailingCollection()

        store = FirestoreHamgomoonLearningStore(client=_FailingClient())

        with pytest.raises(FirestoreHamgomoonLearningStoreError):
            store.list_recent_learning_records(limit=10)
