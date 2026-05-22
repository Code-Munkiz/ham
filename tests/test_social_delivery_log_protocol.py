"""Protocol conformance tests for the delivery-log file backend.

VAL-M15-M1-STORE-PROTOCOL-DELIVERY-FILE-002
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from src.ham.social_delivery_log import (
    SocialDeliveryLogFileStore,
    SocialDeliveryLogStoreProtocol,
    set_social_delivery_log_store_for_tests,
)


class TestFileBackendConformsToProtocol:
    """VAL-M15-M1-STORE-PROTOCOL-DELIVERY-FILE-002"""

    def test_file_backend_conforms_to_protocol(self) -> None:
        store = SocialDeliveryLogFileStore()
        assert isinstance(store, SocialDeliveryLogStoreProtocol)

    def test_append_and_iter_roundtrip(self, tmp_path: Path) -> None:
        log_path = tmp_path / "delivery_log.jsonl"
        store = SocialDeliveryLogFileStore()
        now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
        record = {
            "provider_id": "telegram",
            "execution_kind": "telegram_message",
            "action_type": "message",
            "target_kind": "group",
            "target_ref": "some_ref",
            "proposal_digest": "abc123",
            "persona_digest": "def456",
            "idempotency_key": "key-001",
            "provider_message_id": "msg-001",
            "status": "sent",
            "executed_at": now.isoformat().replace("+00:00", "Z"),
            "execution_allowed": True,
            "mutation_attempted": True,
        }
        store.append_record(record, log_path)
        records = list(store.iter_records_in_window(start=now, end=now, path=log_path))
        assert len(records) == 1
        assert records[0]["idempotency_key"] == "key-001"

    def test_successful_delivery_exists(self, tmp_path: Path) -> None:
        log_path = tmp_path / "delivery_log.jsonl"
        store = SocialDeliveryLogFileStore()
        now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
        record = {
            "provider_id": "telegram",
            "idempotency_key": "key-002",
            "status": "sent",
            "executed_at": now.isoformat().replace("+00:00", "Z"),
        }
        assert not store.successful_delivery_exists(
            idempotency_key="key-002", provider_id="telegram", path=log_path
        )
        store.append_record(record, log_path)
        assert store.successful_delivery_exists(
            idempotency_key="key-002", provider_id="telegram", path=log_path
        )

    def test_iter_records_in_window_empty_when_no_file(self, tmp_path: Path) -> None:
        log_path = tmp_path / "missing.jsonl"
        store = SocialDeliveryLogFileStore()
        now = datetime(2026, 5, 20, tzinfo=UTC)
        records = list(store.iter_records_in_window(start=now, end=now, path=log_path))
        assert records == []

    def test_set_delivery_log_store_for_tests(self) -> None:
        custom = SocialDeliveryLogFileStore()
        set_social_delivery_log_store_for_tests(custom)
        try:
            from src.ham.social_delivery_log import get_social_delivery_log_store

            assert get_social_delivery_log_store() is custom
        finally:
            set_social_delivery_log_store_for_tests(None)
