"""Env-switch factory tests for the Telegram transcript store.

VAL-M15-M1-STORE-ENVSWITCH-TRANSCRIPT-017
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
