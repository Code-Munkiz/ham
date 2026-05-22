"""Protocol conformance tests for the Telegram offset file-backend skeleton.

VAL-M15-M1-STORE-PROTOCOL-OFFSET-FILE-005
"""

from __future__ import annotations

from pathlib import Path

from src.ham.social_telegram_offset_store import (
    TelegramOffsetFileStore,
    TelegramOffsetStoreProtocol,
    set_telegram_offset_store_for_tests,
)

_BOT_DIGEST = "deadbeef01234567"


class TestFileBackendConformsToProtocol:
    """VAL-M15-M1-STORE-PROTOCOL-OFFSET-FILE-005"""

    def test_file_backend_conforms_to_protocol(self) -> None:
        store = TelegramOffsetFileStore()
        assert isinstance(store, TelegramOffsetStoreProtocol)

    def test_write_then_read_roundtrip(self, tmp_path: Path) -> None:
        store = TelegramOffsetFileStore(base_dir=tmp_path)
        assert store.read_offset(_BOT_DIGEST) is None
        store.write_offset(_BOT_DIGEST, 42)
        assert store.read_offset(_BOT_DIGEST) == 42

    def test_write_overwrite(self, tmp_path: Path) -> None:
        store = TelegramOffsetFileStore(base_dir=tmp_path)
        store.write_offset(_BOT_DIGEST, 10)
        store.write_offset(_BOT_DIGEST, 20)
        assert store.read_offset(_BOT_DIGEST) == 20

    def test_read_returns_none_when_no_file(self, tmp_path: Path) -> None:
        store = TelegramOffsetFileStore(base_dir=tmp_path / "nonexistent")
        assert store.read_offset(_BOT_DIGEST) is None

    def test_write_idempotent_on_same_value(self, tmp_path: Path) -> None:
        """Writing the same offset twice results in exactly one stored value."""
        store = TelegramOffsetFileStore(base_dir=tmp_path)
        store.write_offset(_BOT_DIGEST, 42)
        store.write_offset(_BOT_DIGEST, 42)
        assert store.read_offset(_BOT_DIGEST) == 42
        # Only one file on disk
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1

    def test_different_digests_independent(self, tmp_path: Path) -> None:
        store = TelegramOffsetFileStore(base_dir=tmp_path)
        store.write_offset("aaaa0000aaaa0000", 10)
        store.write_offset("bbbb1111bbbb1111", 20)
        assert store.read_offset("aaaa0000aaaa0000") == 10
        assert store.read_offset("bbbb1111bbbb1111") == 20

    def test_set_offset_store_for_tests(self) -> None:
        custom = TelegramOffsetFileStore()
        set_telegram_offset_store_for_tests(custom)
        try:
            from src.ham.social_telegram_offset_store import get_telegram_offset_store

            assert get_telegram_offset_store() is custom
        finally:
            set_telegram_offset_store_for_tests(None)
