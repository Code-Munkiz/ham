"""Protocol conformance tests for the Telegram transcript file-backend skeleton.

VAL-M15-M1-STORE-PROTOCOL-TRANSCRIPT-FILE-004
"""

from __future__ import annotations

from pathlib import Path

from src.ham.social_telegram_transcript_store import (
    TelegramTranscriptFileStore,
    TelegramTranscriptStoreProtocol,
    set_telegram_transcript_store_for_tests,
)

_VALID_ROW = {
    "source": "telegram",
    "role": "user",
    "text": "Hello",
    "chat_id": 12345,
    "author_id": 67890,
    "message_id": 111,
    "created_at": "2026-05-20T12:00:00Z",
}


class TestFileBackendConformsToProtocol:
    """VAL-M15-M1-STORE-PROTOCOL-TRANSCRIPT-FILE-004"""

    def test_file_backend_conforms_to_protocol(self) -> None:
        store = TelegramTranscriptFileStore()
        assert isinstance(store, TelegramTranscriptStoreProtocol)

    def test_append_and_iter_roundtrip(self, tmp_path: Path) -> None:
        store = TelegramTranscriptFileStore(path=tmp_path / "transcript.jsonl")
        store.append_row(_VALID_ROW.copy())
        rows = list(store.iter_rows())
        assert len(rows) == 1
        row = rows[0]
        assert row["source"] == "telegram"
        assert row["role"] == "user"
        assert row["message_id"] == 111

    def test_iter_empty_when_no_file(self, tmp_path: Path) -> None:
        store = TelegramTranscriptFileStore(path=tmp_path / "missing.jsonl")
        rows = list(store.iter_rows())
        assert rows == []

    def test_append_filters_to_allowed_fields(self, tmp_path: Path) -> None:
        """Only allow-listed fields are persisted — extra fields are stripped."""
        store = TelegramTranscriptFileStore(path=tmp_path / "transcript.jsonl")
        row = {**_VALID_ROW, "raw_telegram_update": {"evil": "data"}}
        store.append_row(row)
        rows = list(store.iter_rows())
        assert len(rows) == 1
        assert "raw_telegram_update" not in rows[0]

    def test_set_transcript_store_for_tests(self) -> None:
        custom = TelegramTranscriptFileStore()
        set_telegram_transcript_store_for_tests(custom)
        try:
            from src.ham.social_telegram_transcript_store import get_telegram_transcript_store

            assert get_telegram_transcript_store() is custom
        finally:
            set_telegram_transcript_store_for_tests(None)

    def test_roundtrip_parity_with_jsonl_contract(self, tmp_path: Path) -> None:
        """Row fields match the JSONL contract used by social_telegram_inbound.py."""
        store = TelegramTranscriptFileStore(path=tmp_path / "transcript.jsonl")
        store.append_row(_VALID_ROW.copy())
        rows = list(store.iter_rows())
        assert len(rows) == 1
        row = rows[0]
        # These fields are required by the existing contract
        assert row.get("source") == "telegram"
        assert row.get("role") == "user"
        assert "text" in row
        assert "chat_id" in row
        assert "author_id" in row
        assert "message_id" in row
        assert "created_at" in row
