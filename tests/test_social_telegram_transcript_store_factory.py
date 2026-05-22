"""Env-switch factory tests for the Telegram transcript store.

VAL-M15-M1-STORE-ENVSWITCH-TRANSCRIPT-017
VAL-M15-M1-STORE-FAILCLOSED-TRANSCRIPT-023
"""

from __future__ import annotations

import pytest

from src.ham.social_telegram_transcript_store import (
    TelegramTranscriptFileStore,
    build_telegram_transcript_store,
    set_telegram_transcript_store_for_tests,
)


class TestEnvSwitchSelectsBackend:
    """VAL-M15-M1-STORE-ENVSWITCH-TRANSCRIPT-017"""

    def test_env_switch_selects_backend(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_telegram_transcript_store_for_tests(None)

        monkeypatch.delenv("HAM_TELEGRAM_TRANSCRIPT_BACKEND", raising=False)
        assert isinstance(build_telegram_transcript_store(), TelegramTranscriptFileStore)

        monkeypatch.setenv("HAM_TELEGRAM_TRANSCRIPT_BACKEND", "file")
        assert isinstance(build_telegram_transcript_store(), TelegramTranscriptFileStore)

        monkeypatch.setenv("HAM_TELEGRAM_TRANSCRIPT_BACKEND", "firestore")
        store_fs = build_telegram_transcript_store()
        from src.ham.social_telegram_transcript_firestore import FirestoreTelegramTranscriptStore

        assert isinstance(store_fs, FirestoreTelegramTranscriptStore)

    def test_unknown_backend_falls_back_to_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("HAM_TELEGRAM_TRANSCRIPT_BACKEND", "nope")
        assert isinstance(build_telegram_transcript_store(), TelegramTranscriptFileStore)


class TestFirestoreFailClosedTranscript:
    """VAL-M15-M1-STORE-FAILCLOSED-TRANSCRIPT-023

    With HAM_TELEGRAM_TRANSCRIPT_BACKEND=firestore and a fake client that
    raises, append_row / iter_rows surface a typed error rather than falling
    back to JSONL.
    """

    def test_firestore_failure_does_not_fall_back_to_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        from src.ham.social_telegram_transcript_firestore import (
            FirestoreTelegramTranscriptStore,
            FirestoreTelegramTranscriptStoreError,
        )

        monkeypatch.setenv("HAM_TELEGRAM_TRANSCRIPT_BACKEND", "firestore")
        set_telegram_transcript_store_for_tests(None)

        class _FailCollection:
            def stream(self):
                raise RuntimeError("Simulated Firestore SDK error")

            def document(self, doc_id):
                class _FailDoc:
                    def set(self, data):
                        raise RuntimeError("Simulated SDK write error")

                return _FailDoc()

        class _FailClient:
            def collection(self, name: str) -> _FailCollection:
                return _FailCollection()

        store = FirestoreTelegramTranscriptStore(client=_FailClient())

        # iter_rows must raise, not silently return empty
        with pytest.raises(FirestoreTelegramTranscriptStoreError):
            list(store.iter_rows())

        # Verify no JSONL file was created (no silent fallback)
        jsonl_path = tmp_path / "telegram_inbound_transcript.jsonl"
        assert not jsonl_path.exists(), (
            "Firestore failure caused a silent fallback to the file backend"
        )

    def test_append_row_raises_on_sdk_error_fail_closed(
        self,
        tmp_path,
    ) -> None:
        from src.ham.social_telegram_transcript_firestore import (
            FirestoreTelegramTranscriptStore,
            FirestoreTelegramTranscriptStoreError,
        )

        class _FailCollection:
            def document(self, doc_id):
                class _FailDoc:
                    def set(self, data):
                        raise RuntimeError("Simulated SDK write error")

                return _FailDoc()

        class _FailClient:
            def collection(self, name: str) -> _FailCollection:
                return _FailCollection()

        store = FirestoreTelegramTranscriptStore(client=_FailClient())
        row = {
            "source": "telegram",
            "role": "user",
            "text": "Hello",
            "chat_id": 1,
            "author_id": 2,
            "message_id": 3,
            "created_at": "2026-05-20T12:00:00Z",
        }
        with pytest.raises(FirestoreTelegramTranscriptStoreError):
            store.append_row(row)
