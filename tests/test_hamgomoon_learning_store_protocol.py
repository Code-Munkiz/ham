"""Protocol conformance tests for the HAMgomoon learning file backend.

VAL-M15-M1-STORE-PROTOCOL-LEARNING-FILE-003
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ham.hamgomoon_learning.models import LearningRecord, SocialDraftRecord
from src.ham.hamgomoon_learning.store import (
    HamgomoonLearningFileStore,
    HamgomoonLearningStoreProtocol,
    set_hamgomoon_learning_store_for_tests,
)


def _make_record(channel: str = "telegram") -> LearningRecord:
    draft = SocialDraftRecord(
        channel=channel,
        proposed_action="message",
        draft_text="Hello world",
        prompt="Test prompt",
    )
    return LearningRecord(channel=channel, draft=draft)


class TestFileBackendConformsToProtocol:
    """VAL-M15-M1-STORE-PROTOCOL-LEARNING-FILE-003"""

    def test_file_backend_conforms_to_protocol(self) -> None:
        store = HamgomoonLearningFileStore()
        assert isinstance(store, HamgomoonLearningStoreProtocol)

    def test_append_and_list_roundtrip(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        log_path = tmp_path / "learning.jsonl"
        store = HamgomoonLearningFileStore()
        record = _make_record("telegram")
        returned = store.append_learning_record(record, path=log_path)
        assert returned.record_id == record.record_id
        records = store.list_recent_learning_records(path=log_path)
        assert len(records) == 1
        assert records[0].record_id == record.record_id

    def test_list_empty_when_no_file(self, tmp_path: Path) -> None:
        log_path = tmp_path / "missing.jsonl"
        store = HamgomoonLearningFileStore()
        records = store.list_recent_learning_records(path=log_path)
        assert records == []

    def test_summarize_returns_dict(
        self,
        tmp_path: Path,
    ) -> None:
        log_path = tmp_path / "learning.jsonl"
        store = HamgomoonLearningFileStore()
        result = store.summarize_learning_hints(path=log_path)
        assert isinstance(result, dict)
        assert "recent_lessons" in result

    def test_set_hamgomoon_learning_store_for_tests(self) -> None:
        custom = HamgomoonLearningFileStore()
        set_hamgomoon_learning_store_for_tests(custom)
        try:
            from src.ham.hamgomoon_learning.store import get_hamgomoon_learning_store

            assert get_hamgomoon_learning_store() is custom
        finally:
            set_hamgomoon_learning_store_for_tests(None)
