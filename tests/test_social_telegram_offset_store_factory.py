"""Env-switch factory tests for the Telegram offset store.

VAL-M15-M1-STORE-ENVSWITCH-OFFSET-018
VAL-M15-M1-STORE-FAILCLOSED-OFFSET-024
"""

from __future__ import annotations

import pytest

from src.ham.social_telegram_offset_store import (
    TelegramOffsetFileStore,
    build_telegram_offset_store,
    set_telegram_offset_store_for_tests,
)

_BOT_DIGEST = "deadbeef01234567"


class TestEnvSwitchSelectsBackend:
    """VAL-M15-M1-STORE-ENVSWITCH-OFFSET-018"""

    def test_env_switch_selects_backend(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_telegram_offset_store_for_tests(None)

        monkeypatch.delenv("HAM_TELEGRAM_OFFSET_BACKEND", raising=False)
        assert isinstance(build_telegram_offset_store(), TelegramOffsetFileStore)

        monkeypatch.setenv("HAM_TELEGRAM_OFFSET_BACKEND", "file")
        assert isinstance(build_telegram_offset_store(), TelegramOffsetFileStore)

        monkeypatch.setenv("HAM_TELEGRAM_OFFSET_BACKEND", "firestore")
        store_fs = build_telegram_offset_store()
        from src.ham.social_telegram_offset_firestore import FirestoreTelegramOffsetStore

        assert isinstance(store_fs, FirestoreTelegramOffsetStore)

    def test_unknown_backend_falls_back_to_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("HAM_TELEGRAM_OFFSET_BACKEND", "oops")
        assert isinstance(build_telegram_offset_store(), TelegramOffsetFileStore)


class TestFirestoreFailClosedOffset:
    """VAL-M15-M1-STORE-FAILCLOSED-OFFSET-024

    With HAM_TELEGRAM_OFFSET_BACKEND=firestore and a fake client that raises,
    read_offset / write_offset surface a typed error rather than falling back
    to file. Offset file path on disk remains untouched.
    """

    def test_firestore_failure_does_not_fall_back_to_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        from src.ham.social_telegram_offset_firestore import (
            FirestoreTelegramOffsetStore,
            FirestoreTelegramOffsetStoreError,
        )

        monkeypatch.setenv("HAM_TELEGRAM_OFFSET_BACKEND", "firestore")
        set_telegram_offset_store_for_tests(None)

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

        store = FirestoreTelegramOffsetStore(client=_FailClient())

        # read_offset must raise, not return None silently
        with pytest.raises(FirestoreTelegramOffsetStoreError):
            store.read_offset(_BOT_DIGEST)

        # Verify no offset file was created (no silent fallback)
        offset_file = tmp_path / f"{_BOT_DIGEST[:16]}.json"
        assert not offset_file.exists(), (
            "Firestore failure caused a silent fallback to the file backend"
        )

    def test_write_offset_raises_on_sdk_error_fail_closed(self) -> None:
        from src.ham.social_telegram_offset_firestore import (
            FirestoreTelegramOffsetStore,
            FirestoreTelegramOffsetStoreError,
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

        store = FirestoreTelegramOffsetStore(client=_FailClient())
        with pytest.raises(FirestoreTelegramOffsetStoreError):
            store.write_offset(_BOT_DIGEST, 42)
