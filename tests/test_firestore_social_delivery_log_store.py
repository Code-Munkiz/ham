"""Firestore-backed social delivery log store tests.

Covers:
- VAL-M15-M1-DELIVERY-FIRESTORE-ROUNDTRIP-005: append then read preserves
  the redacted, allow-listed field shape.
- VAL-M15-M1-DELIVERY-FIRESTORE-MISSING-ZERO-006: missing source (empty
  collection) returns zero records, preserving the M14 M1c semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from src.ham.social_delivery_log import build_delivery_record
from src.ham.social_delivery_log_firestore import FirestoreSocialDeliveryLogStore

# ---------------------------------------------------------------------------
# Minimal fake Firestore client (no transactions needed for delivery log)
# ---------------------------------------------------------------------------


@dataclass
class _FakeDocSnap:
    id: str
    _data: dict[str, Any] | None

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data) if self._data is not None else {}


@dataclass
class _FakeDocRef:
    root: _FakeFirestoreClient
    path: str

    def set(self, data: dict[str, Any]) -> None:
        self.root.docs[self.path] = dict(data)

    def get(self) -> _FakeDocSnap:
        data = self.root.docs.get(self.path)
        return _FakeDocSnap(
            id=self.path.rsplit("/", 1)[-1],
            _data=dict(data) if data is not None else None,
        )


@dataclass
class _FakeCollection:
    root: _FakeFirestoreClient
    prefix: str

    def document(self, doc_id: str) -> _FakeDocRef:
        return _FakeDocRef(self.root, f"{self.prefix}/{doc_id}")

    def stream(self):
        sep = self.prefix + "/"
        for path, data in list(self.root.docs.items()):
            if not path.startswith(sep):
                continue
            rest = path[len(sep) :]
            if "/" not in rest:
                yield _FakeDocSnap(id=rest, _data=dict(data))


class _FakeFirestoreClient:
    """In-memory Firestore client for tests."""

    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self, name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALLOWED_FIELDS = {
    "provider_id",
    "execution_kind",
    "action_type",
    "target_kind",
    "target_ref",
    "proposal_digest",
    "persona_digest",
    "idempotency_key",
    "provider_message_id",
    "status",
    "executed_at",
    "execution_allowed",
    "mutation_attempted",
}

_NOW = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)


def _store_with_fake() -> tuple[FirestoreSocialDeliveryLogStore, _FakeFirestoreClient]:
    fake = _FakeFirestoreClient()
    store = FirestoreSocialDeliveryLogStore(client=fake)
    return store, fake


def _sample_record(
    idempotency_key: str = "key-001",
    status: str = "sent",
    executed_at: datetime | None = None,
) -> dict[str, Any]:
    ts = (executed_at or _NOW).isoformat().replace("+00:00", "Z")
    return {
        "provider_id": "telegram",
        "execution_kind": "social_telegram_message",
        "action_type": "message",
        "target_kind": "group",
        "target_ref": "some_ref",
        "proposal_digest": "abc123",
        "persona_digest": "def456",
        "idempotency_key": idempotency_key,
        "provider_message_id": "msg-001",
        "status": status,
        "executed_at": ts,
        "execution_allowed": True,
        "mutation_attempted": True,
    }


# ---------------------------------------------------------------------------
# VAL-M15-M1-DELIVERY-FIRESTORE-ROUNDTRIP-005
# ---------------------------------------------------------------------------


class TestAppendThenReadPreservesRedactedShape:
    """VAL-M15-M1-DELIVERY-FIRESTORE-ROUNDTRIP-005

    append_record writes one document under ham_social_delivery_log/{id}
    whose stored fields are exactly the file backend's allow-listed set;
    strings are redacted via redact(). Roundtrip equals file-backend roundtrip
    on the same input.
    """

    def test_append_then_read_preserves_redacted_shape(self) -> None:
        store, fake = _store_with_fake()
        record = _sample_record()
        store.append_record(record)

        # Exactly one document written to the collection
        docs = list(fake.collection("ham_social_delivery_log").stream())
        assert len(docs) == 1

        stored = docs[0].to_dict()

        # All stored fields are in the allow-list
        assert set(stored.keys()) <= _ALLOWED_FIELDS, (
            f"Extra fields in stored record: {set(stored.keys()) - _ALLOWED_FIELDS}"
        )

        # Round-trip parity with the file backend's build_delivery_record
        file_record = build_delivery_record(**record)
        for key in file_record:
            assert stored.get(key) == file_record[key], (
                f"Field {key!r} mismatch: stored={stored.get(key)!r} file={file_record[key]!r}"
            )

    def test_iter_records_in_window_returns_appended_record(self) -> None:
        store, _ = _store_with_fake()
        record = _sample_record()
        store.append_record(record)

        results = list(
            store.iter_records_in_window(
                start=_NOW - timedelta(seconds=1),
                end=_NOW + timedelta(seconds=1),
            )
        )
        assert len(results) == 1
        assert results[0]["idempotency_key"] == "key-001"

    def test_successful_delivery_exists_after_append(self) -> None:
        store, _ = _store_with_fake()
        record = _sample_record(idempotency_key="key-002", status="sent")
        assert not store.successful_delivery_exists(
            idempotency_key="key-002", provider_id="telegram"
        )
        store.append_record(record)
        assert store.successful_delivery_exists(idempotency_key="key-002", provider_id="telegram")

    def test_only_allowed_fields_stored_extra_fields_dropped(self) -> None:
        """Extra fields in the input are dropped by build_delivery_record."""
        store, fake = _store_with_fake()
        record = dict(_sample_record(), extra_secret_field="sensitive_value")
        store.append_record(record)

        docs = list(fake.collection("ham_social_delivery_log").stream())
        stored = docs[0].to_dict()
        assert "extra_secret_field" not in stored

    def test_strings_redacted_via_redact(self) -> None:
        """Strings in allowed fields are passed through _safe/redact()."""
        from src.ham.ham_x.redaction import redact

        store, fake = _store_with_fake()
        # Embed a bearer token in the target_ref (a string field)
        raw_token = "Bearer supersecrettoken12345"
        record = _sample_record()
        record["target_ref"] = raw_token
        store.append_record(record)

        docs = list(fake.collection("ham_social_delivery_log").stream())
        stored = docs[0].to_dict()
        # The stored value should be the redacted version
        assert stored.get("target_ref") == str(redact(raw_token))[:1000]
        assert "supersecrettoken12345" not in stored.get("target_ref", "")


# ---------------------------------------------------------------------------
# VAL-M15-M1-DELIVERY-FIRESTORE-MISSING-ZERO-006
# ---------------------------------------------------------------------------


class TestMissingSourceReturnsZeroRecords:
    """VAL-M15-M1-DELIVERY-FIRESTORE-MISSING-ZERO-006

    With an empty collection, iter_records_in_window returns zero records rather
    than raising UsageSourceUnavailable. Preserves the M14 M1c semantics that a
    missing source = zero records for the cap path.
    """

    def test_missing_source_returns_zero_records(self) -> None:
        store, _ = _store_with_fake()  # empty fake client
        now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
        records = list(store.iter_records_in_window(start=now, end=now))
        assert records == [], "Expected empty list for empty collection, got non-empty"

    def test_missing_source_does_not_raise(self) -> None:
        store, _ = _store_with_fake()
        now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
        # Must not raise UsageSourceUnavailable or any other exception
        try:
            list(store.iter_records_in_window(start=now, end=now))
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"iter_records_in_window raised on empty collection: {exc!r}")

    def test_empty_collection_successful_delivery_returns_false(self) -> None:
        store, _ = _store_with_fake()
        result = store.successful_delivery_exists(
            idempotency_key="nonexistent", provider_id="telegram"
        )
        assert result is False

    def test_records_outside_window_not_returned(self) -> None:
        store, _ = _store_with_fake()
        # Append a record at _NOW
        store.append_record(_sample_record(executed_at=_NOW))
        # Query a window completely before the record
        before = _NOW - timedelta(hours=2)
        results = list(
            store.iter_records_in_window(
                start=before - timedelta(seconds=1),
                end=before,
            )
        )
        assert results == []
