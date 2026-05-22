"""Firestore-backed Telegram getUpdates offset store tests.

Covers:
- VAL-M15-M1-OFFSET-FIRESTORE-ATOMIC-010: write_offset then read_offset atomic
  round-trip — monotonic sequence write(42)→read=42→write(43)→read=43.
- VAL-M15-M1-OFFSET-FIRESTORE-IDEMPOTENT-011: writing the same offset twice
  yields exactly one post-state; collection size remains 1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from src.ham.social_telegram_offset_firestore import (
    FirestoreTelegramOffsetStore,
    FirestoreTelegramOffsetStoreError,
)

# ---------------------------------------------------------------------------
# Minimal fake Firestore client (document-level get/set)
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


@dataclass
class _FakeFirestoreClient:
    """In-memory Firestore client for tests."""

    docs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self, name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BOT_DIGEST = "deadbeef01234567"


def _store_with_fake() -> tuple[FirestoreTelegramOffsetStore, _FakeFirestoreClient]:
    fake = _FakeFirestoreClient()
    store = FirestoreTelegramOffsetStore(client=fake)
    return store, fake


def _count_docs(fake: _FakeFirestoreClient, collection: str) -> int:
    prefix = collection + "/"
    return sum(
        1 for path in fake.docs if path.startswith(prefix) and "/" not in path[len(prefix) :]
    )


# ---------------------------------------------------------------------------
# VAL-M15-M1-OFFSET-FIRESTORE-ATOMIC-010
# ---------------------------------------------------------------------------


class TestWriteThenReadAtomic:
    """VAL-M15-M1-OFFSET-FIRESTORE-ATOMIC-010

    write_offset(bot_digest, 42) writes a single document at
    ham_social_telegram_poller_state/{bot_digest} with field update_offset=42;
    read_offset(bot_digest) returns 42. Monotonic sequence
    write(42)→read=42→write(43)→read=43.
    """

    def test_write_then_read_atomic(self) -> None:
        """write(42) → read() == 42."""
        store, _ = _store_with_fake()
        store.write_offset(_BOT_DIGEST, 42)
        result = store.read_offset(_BOT_DIGEST)
        assert result == 42

    def test_monotonic_sequence(self) -> None:
        """write(42)→read=42→write(43)→read=43."""
        store, _ = _store_with_fake()
        store.write_offset(_BOT_DIGEST, 42)
        assert store.read_offset(_BOT_DIGEST) == 42
        store.write_offset(_BOT_DIGEST, 43)
        assert store.read_offset(_BOT_DIGEST) == 43

    def test_document_stored_at_bot_digest_path(self) -> None:
        """Document is stored at ham_social_telegram_poller_state/{bot_digest}."""
        store, fake = _store_with_fake()
        store.write_offset(_BOT_DIGEST, 99)
        expected_path = f"ham_social_telegram_poller_state/{_BOT_DIGEST}"
        assert expected_path in fake.docs, (
            f"Expected document at path {expected_path!r}, found paths: {list(fake.docs.keys())}"
        )
        stored = fake.docs[expected_path]
        assert stored.get("update_offset") == 99

    def test_read_returns_none_when_absent(self) -> None:
        """read_offset returns None when no document exists for that digest."""
        store, _ = _store_with_fake()
        assert store.read_offset("nonexistent_digest") is None

    def test_different_digests_are_independent(self) -> None:
        """Different bot digests store and read independently."""
        store, _ = _store_with_fake()
        store.write_offset("digest_aaa", 10)
        store.write_offset("digest_bbb", 20)
        assert store.read_offset("digest_aaa") == 10
        assert store.read_offset("digest_bbb") == 20


# ---------------------------------------------------------------------------
# VAL-M15-M1-OFFSET-FIRESTORE-IDEMPOTENT-011
# ---------------------------------------------------------------------------


class TestWriteOffsetIdempotentOnSameValue:
    """VAL-M15-M1-OFFSET-FIRESTORE-IDEMPOTENT-011

    Calling write_offset(bot_digest, 42) twice in succession yields exactly one
    post-state with update_offset=42; the second call must not raise and must
    not produce duplicate documents. Collection size remains 1 after duplicate writes.
    """

    def test_write_offset_idempotent_on_same_value(self) -> None:
        """Duplicate write(42) → collection size remains 1 and value is 42."""
        store, fake = _store_with_fake()
        store.write_offset(_BOT_DIGEST, 42)
        store.write_offset(_BOT_DIGEST, 42)

        # Collection should have exactly one document
        count = _count_docs(fake, "ham_social_telegram_poller_state")
        assert count == 1, f"Expected 1 document after duplicate writes, got {count}"

        # Value is still 42
        assert store.read_offset(_BOT_DIGEST) == 42

    def test_second_write_does_not_raise(self) -> None:
        """The second write of the same offset does not raise."""
        store, _ = _store_with_fake()
        store.write_offset(_BOT_DIGEST, 42)
        # Must not raise
        store.write_offset(_BOT_DIGEST, 42)

    def test_overwrite_with_different_value_updates_correctly(self) -> None:
        """Writing a different offset overwrites and updates the value."""
        store, fake = _store_with_fake()
        store.write_offset(_BOT_DIGEST, 42)
        store.write_offset(_BOT_DIGEST, 100)

        # Still exactly one document
        count = _count_docs(fake, "ham_social_telegram_poller_state")
        assert count == 1

        # Value is now 100
        assert store.read_offset(_BOT_DIGEST) == 100


# ---------------------------------------------------------------------------
# Fail-closed: Firestore SDK errors surface properly
# ---------------------------------------------------------------------------


class TestFailClosed:
    """VAL-M15-M1-STORE-FAILCLOSED-OFFSET-024 (partial — factory test covers the full assertion)

    read_offset / write_offset surface a typed error rather than falling back to file.
    """

    def test_write_offset_raises_on_sdk_error(self) -> None:
        """write_offset wraps SDK errors in FirestoreTelegramOffsetStoreError."""

        class _FailDoc:
            def set(self, data: dict) -> None:
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

    def test_read_offset_raises_on_sdk_error(self) -> None:
        """read_offset wraps SDK errors in FirestoreTelegramOffsetStoreError."""

        class _FailDoc:
            def get(self) -> None:
                raise RuntimeError("Simulated SDK read error")

        class _FailCollection:
            def document(self, doc_id: str) -> _FailDoc:
                return _FailDoc()

        class _FailClient:
            def collection(self, name: str) -> _FailCollection:
                return _FailCollection()

        store = FirestoreTelegramOffsetStore(client=_FailClient())
        with pytest.raises(FirestoreTelegramOffsetStoreError):
            store.read_offset(_BOT_DIGEST)
