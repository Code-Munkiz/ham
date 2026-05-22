"""Env-switch factory tests for the Telegram offset store.

VAL-M15-M1-STORE-ENVSWITCH-OFFSET-018
"""

from __future__ import annotations

import pytest

from src.ham.social_telegram_offset_store import (
    TelegramOffsetFileStore,
    build_telegram_offset_store,
    set_telegram_offset_store_for_tests,
)


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
