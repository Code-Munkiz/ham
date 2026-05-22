"""Firestore-backed social scheduler state store tests.

Covers:
- VAL-M15-M1-SCHEDSTATE-FIRESTORE-DEFAULTS-012: Reading from an empty
  ham_social_scheduler_state collection returns a SocialSchedulerState
  with scheduler_enabled=False, last_scheduled_tick_at=None, last_tick_summary=None.
- VAL-M15-M1-SCHEDSTATE-FIRESTORE-UPDATE-013: write_state then read_state
  roundtrip — Pydantic-equal roundtrip.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from src.ham.social_scheduler_state_firestore import (
    FirestoreSocialSchedulerStateStore,
    FirestoreSocialSchedulerStateStoreError,
)
from src.ham.social_scheduler_state_store import SocialSchedulerState

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

_SINGLETON_DOC_PATH = "ham_social_scheduler_state/singleton"


def _store_with_fake() -> tuple[FirestoreSocialSchedulerStateStore, _FakeFirestoreClient]:
    fake = _FakeFirestoreClient()
    store = FirestoreSocialSchedulerStateStore(client=fake)
    return store, fake


# ---------------------------------------------------------------------------
# VAL-M15-M1-SCHEDSTATE-FIRESTORE-DEFAULTS-012
# ---------------------------------------------------------------------------


class TestEmptyCollectionReturnsDefaults:
    """VAL-M15-M1-SCHEDSTATE-FIRESTORE-DEFAULTS-012

    Reading from an empty ham_social_scheduler_state collection returns a
    SocialSchedulerState{scheduler_enabled=False, last_scheduled_tick_at=None,
    last_tick_summary=None}.
    """

    def test_empty_collection_returns_defaults(self) -> None:
        """read_state() with no documents returns safe default state."""
        store, _ = _store_with_fake()
        state = store.read_state()
        assert isinstance(state, SocialSchedulerState)
        assert state.scheduler_enabled is False
        assert state.last_scheduled_tick_at is None
        assert state.last_tick_summary is None

    def test_default_state_scheduler_disabled(self) -> None:
        """Default state: scheduler_enabled is explicitly False (not truthy)."""
        store, _ = _store_with_fake()
        state = store.read_state()
        assert state.scheduler_enabled is False

    def test_default_state_last_tick_at_none(self) -> None:
        """Default state: last_scheduled_tick_at is None."""
        store, _ = _store_with_fake()
        state = store.read_state()
        assert state.last_scheduled_tick_at is None

    def test_default_state_last_tick_summary_none(self) -> None:
        """Default state: last_tick_summary is None."""
        store, _ = _store_with_fake()
        state = store.read_state()
        assert state.last_tick_summary is None


# ---------------------------------------------------------------------------
# VAL-M15-M1-SCHEDSTATE-FIRESTORE-UPDATE-013
# ---------------------------------------------------------------------------


class TestWriteStateThenReadRoundtrip:
    """VAL-M15-M1-SCHEDSTATE-FIRESTORE-UPDATE-013

    A direct write_state(SocialSchedulerState(scheduler_enabled=True,
    last_scheduled_tick_at=<utc>, last_tick_summary={...})) writes to
    ham_social_scheduler_state/{singleton}; read_state() returns an equal record.
    Pass: Pydantic-equal roundtrip.
    """

    def test_write_state_then_read_roundtrip(self) -> None:
        """Roundtrip: write then read returns Pydantic-equal state."""
        store, _ = _store_with_fake()
        now = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
        original = SocialSchedulerState(
            scheduler_enabled=True,
            last_scheduled_tick_at=now,
            last_tick_summary={"actions_taken": [], "blocked_reasons": []},
        )
        store.write_state(original)
        recovered = store.read_state()
        assert recovered == original

    def test_write_state_document_stored_at_singleton_path(self) -> None:
        """State is stored at ham_social_scheduler_state/singleton."""
        store, fake = _store_with_fake()
        now = datetime(2026, 5, 21, 8, 30, tzinfo=UTC)
        state = SocialSchedulerState(
            scheduler_enabled=True,
            last_scheduled_tick_at=now,
            last_tick_summary={"actions_taken": 1},
        )
        store.write_state(state)
        assert _SINGLETON_DOC_PATH in fake.docs, (
            f"Expected document at {_SINGLETON_DOC_PATH!r}, found: {list(fake.docs.keys())}"
        )

    def test_write_then_read_scheduler_enabled_flag(self) -> None:
        """scheduler_enabled=True persists and reads back correctly."""
        store, _ = _store_with_fake()
        state = SocialSchedulerState(scheduler_enabled=True)
        store.write_state(state)
        recovered = store.read_state()
        assert recovered.scheduler_enabled is True

    def test_write_then_read_scheduler_disabled(self) -> None:
        """scheduler_enabled=False persists and reads back correctly."""
        store, _ = _store_with_fake()
        state = SocialSchedulerState(scheduler_enabled=False)
        store.write_state(state)
        recovered = store.read_state()
        assert recovered.scheduler_enabled is False

    def test_write_then_read_last_scheduled_tick_at(self) -> None:
        """last_scheduled_tick_at timestamp round-trips correctly (datetime equality)."""
        store, _ = _store_with_fake()
        now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
        state = SocialSchedulerState(
            scheduler_enabled=True,
            last_scheduled_tick_at=now,
        )
        store.write_state(state)
        recovered = store.read_state()
        assert recovered.last_scheduled_tick_at == now

    def test_write_then_read_last_tick_summary_snapshot(self) -> None:
        """last_tick_summary dict snapshot round-trips correctly."""
        store, _ = _store_with_fake()
        summary = {
            "actions_taken": [{"type": "message", "channel": "telegram"}],
            "blocked_reasons": [],
            "dry_run": True,
        }
        state = SocialSchedulerState(
            scheduler_enabled=True,
            last_tick_summary=summary,
        )
        store.write_state(state)
        recovered = store.read_state()
        assert recovered.last_tick_summary == summary

    def test_overwrite_updates_existing_state(self) -> None:
        """A second write_state replaces the previous state."""
        store, _ = _store_with_fake()
        first = SocialSchedulerState(scheduler_enabled=False)
        store.write_state(first)
        assert store.read_state().scheduler_enabled is False

        now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
        second = SocialSchedulerState(
            scheduler_enabled=True,
            last_scheduled_tick_at=now,
        )
        store.write_state(second)
        recovered = store.read_state()
        assert recovered.scheduler_enabled is True
        assert recovered.last_scheduled_tick_at == now

    def test_singleton_only_one_document_after_multiple_writes(self) -> None:
        """Multiple writes to a singleton store do not accumulate documents."""
        store, fake = _store_with_fake()
        for _ in range(3):
            store.write_state(SocialSchedulerState(scheduler_enabled=True))
        prefix = "ham_social_scheduler_state/"
        doc_paths = [p for p in fake.docs if p.startswith(prefix)]
        assert len(doc_paths) == 1, f"Expected 1 singleton doc, got {len(doc_paths)}: {doc_paths}"


# ---------------------------------------------------------------------------
# Fail-closed: Firestore SDK errors surface properly
# ---------------------------------------------------------------------------


class TestFailClosed:
    """VAL-M15-M1-STORE-FAILCLOSED-SCHEDSTATE-025 (partial — factory test covers the full assertion)

    read_state / write_state surface a typed error rather than falling back to file.
    """

    def test_read_state_raises_on_sdk_error(self) -> None:
        """read_state wraps SDK errors in FirestoreSocialSchedulerStateStoreError."""

        class _FailDoc:
            def get(self) -> None:
                raise RuntimeError("Simulated SDK read error")

        class _FailCollection:
            def document(self, doc_id: str) -> _FailDoc:
                return _FailDoc()

        class _FailClient:
            def collection(self, name: str) -> _FailCollection:
                return _FailCollection()

        store = FirestoreSocialSchedulerStateStore(client=_FailClient())
        with pytest.raises(FirestoreSocialSchedulerStateStoreError):
            store.read_state()

    def test_write_state_raises_on_sdk_error(self) -> None:
        """write_state wraps SDK errors in FirestoreSocialSchedulerStateStoreError."""

        class _FailDoc:
            def set(self, data: dict) -> None:
                raise RuntimeError("Simulated SDK write error")

        class _FailCollection:
            def document(self, doc_id: str) -> _FailDoc:
                return _FailDoc()

        class _FailClient:
            def collection(self, name: str) -> _FailCollection:
                return _FailCollection()

        store = FirestoreSocialSchedulerStateStore(client=_FailClient())
        with pytest.raises(FirestoreSocialSchedulerStateStoreError):
            store.write_state(SocialSchedulerState())
