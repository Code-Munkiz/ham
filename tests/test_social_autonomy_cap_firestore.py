"""Cap-counter backend-parity tests — VAL-M15-M1B-CAP-FIRESTORE-COUNT-001.

Verifies that ``count_actions_in_window`` derives its Telegram cap count from
``get_social_delivery_log_store().iter_records_in_window(...)`` rather than
reading the JSONL file path directly.

Under ``HAM_SOCIAL_DELIVERY_LOG_BACKEND=firestore`` (or any non-file store
injected via ``set_social_delivery_log_store_for_tests``), records written via
the store are counted correctly — the cap counter no longer silently returns 0.

File-backend behaviour is preserved byte-equal (missing source ⇒ 0, not an
exception; existing M14 M1c regression tests remain green).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from collections.abc import Iterator

import pytest

from src.ham.social_autonomy.usage import count_actions_in_window
from src.ham.social_delivery_log import (
    SocialDeliveryLogFileStore,
    set_social_delivery_log_store_for_tests,
)
from src.ham.social_delivery_log_firestore import FirestoreSocialDeliveryLogStore
from src.ham.social_telegram_send import TELEGRAM_EXECUTION_KIND

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
_WINDOW_SECONDS = 86_400  # 24 h


# ---------------------------------------------------------------------------
# Minimal fake Firestore client (mirrors test_firestore_social_delivery_log_store.py)
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

    def stream(self) -> Iterator[_FakeDocSnap]:
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


def _telegram_delivery_record(
    executed_at: datetime | None = None,
    execution_kind: str = TELEGRAM_EXECUTION_KIND,
    status: str = "sent",
    provider_id: str = "telegram",
) -> dict[str, Any]:
    ts = (executed_at or _NOW).isoformat().replace("+00:00", "Z")
    return {
        "provider_id": provider_id,
        "execution_kind": execution_kind,
        "action_type": "message",
        "idempotency_key": f"key-{ts}",
        "status": status,
        "executed_at": ts,
        "execution_allowed": True,
        "mutation_attempted": True,
    }


def _append_jsonl(path: Path, *rows: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# VAL-M15-M1B-CAP-FIRESTORE-COUNT-001 — Firestore backend: counter returns N
# ---------------------------------------------------------------------------


class TestCapCounterFirestoreBackend:
    """VAL-M15-M1B-CAP-FIRESTORE-COUNT-001

    Under HAM_SOCIAL_DELIVERY_LOG_BACKEND=firestore (or when a fake Firestore
    store is injected), the cap counter reads from the store and returns the
    correct count — not 0.
    """

    def test_cap_counter_firestore_backend_counts_3_records(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Write 3 records via a fake Firestore store; cap counter returns 3."""
        monkeypatch.setenv("HAM_SOCIAL_DELIVERY_LOG_BACKEND", "firestore")
        fake_client = _FakeFirestoreClient()
        store = FirestoreSocialDeliveryLogStore(client=fake_client)

        # Write 3 sent Telegram delivery records within the 24-h window.
        for i in range(3):
            executed_at = _NOW - timedelta(hours=i + 1)
            store.append_record(_telegram_delivery_record(executed_at=executed_at))

        set_social_delivery_log_store_for_tests(store)
        try:
            count = count_actions_in_window("telegram", "message", _NOW)
        finally:
            set_social_delivery_log_store_for_tests(None)

        assert count == 3, (
            f"Expected cap counter to return 3 for 3 Firestore records, got {count}. "
            "This indicates count_actions_in_window is bypassing the store and reading "
            "the JSONL file directly (which has no records)."
        )

    def test_cap_counter_firestore_backend_missing_source_returns_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Empty Firestore collection (missing source) returns 0 — M14 M1c parity."""
        monkeypatch.setenv("HAM_SOCIAL_DELIVERY_LOG_BACKEND", "firestore")
        fake_client = _FakeFirestoreClient()  # empty
        store = FirestoreSocialDeliveryLogStore(client=fake_client)

        set_social_delivery_log_store_for_tests(store)
        try:
            count = count_actions_in_window("telegram", "message", _NOW)
        finally:
            set_social_delivery_log_store_for_tests(None)

        assert count == 0, f"Empty Firestore collection should return 0, got {count}."

    def test_cap_counter_firestore_backend_filters_outside_window(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Records outside the window are not counted."""
        monkeypatch.setenv("HAM_SOCIAL_DELIVERY_LOG_BACKEND", "firestore")
        fake_client = _FakeFirestoreClient()
        store = FirestoreSocialDeliveryLogStore(client=fake_client)

        # Inside window: 1 record
        store.append_record(_telegram_delivery_record(executed_at=_NOW - timedelta(hours=1)))
        # Outside window (>24h ago): 2 records
        store.append_record(_telegram_delivery_record(executed_at=_NOW - timedelta(hours=25)))
        store.append_record(_telegram_delivery_record(executed_at=_NOW - timedelta(hours=48)))

        set_social_delivery_log_store_for_tests(store)
        try:
            count = count_actions_in_window(
                "telegram", "message", _NOW, window_seconds=_WINDOW_SECONDS
            )
        finally:
            set_social_delivery_log_store_for_tests(None)

        assert count == 1, f"Expected 1 record in window, got {count}."

    def test_cap_counter_firestore_only_counts_sent_status(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Only records with status='sent' are counted (same as file backend)."""
        monkeypatch.setenv("HAM_SOCIAL_DELIVERY_LOG_BACKEND", "firestore")
        fake_client = _FakeFirestoreClient()
        store = FirestoreSocialDeliveryLogStore(client=fake_client)

        store.append_record(
            _telegram_delivery_record(executed_at=_NOW - timedelta(hours=1), status="sent")
        )
        store.append_record(
            _telegram_delivery_record(executed_at=_NOW - timedelta(hours=2), status="blocked")
        )
        store.append_record(
            _telegram_delivery_record(executed_at=_NOW - timedelta(hours=3), status="dry_run")
        )

        set_social_delivery_log_store_for_tests(store)
        try:
            count = count_actions_in_window("telegram", "message", _NOW)
        finally:
            set_social_delivery_log_store_for_tests(None)

        assert count == 1, f"Expected only 1 'sent' record counted, got {count}."


# ---------------------------------------------------------------------------
# File backend parity — must stay byte-equal with existing M14/M1c behaviour
# ---------------------------------------------------------------------------


class TestCapCounterFileBackendParity:
    """Parity tests confirming the file backend is byte-equal after the fix.

    These cover the expected-behavior item: 'file: write 3 JSONL rows →
    counter=3'.  The file backend path (explicit delivery_log_path) is
    unchanged; the no-explicit-path path now calls the store, which for
    the file backend calls the same underlying function.
    """

    def test_cap_counter_file_backend_counts_3_records(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Write 3 JSONL rows via file store; cap counter without explicit path returns 3."""
        import src.ham.social_delivery_log as sdl_mod

        delivery_log = tmp_path / "delivery_log.jsonl"
        for i in range(3):
            executed_at = _NOW - timedelta(hours=i + 1)
            _append_jsonl(delivery_log, _telegram_delivery_record(executed_at=executed_at))

        # Patch default path so the file store reads our temp file.
        monkeypatch.setattr(sdl_mod, "default_delivery_log_path", lambda: delivery_log)

        # Inject a fresh file store to avoid any residual singleton state.
        set_social_delivery_log_store_for_tests(SocialDeliveryLogFileStore())
        try:
            count = count_actions_in_window("telegram", "message", _NOW)
        finally:
            set_social_delivery_log_store_for_tests(None)

        assert count == 3, f"Expected file backend to count 3 records, got {count}."

    def test_cap_counter_file_backend_missing_source_returns_zero(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Missing JSONL file returns 0 — preserves M14 M1c missing-source-zero semantics."""
        import src.ham.social_delivery_log as sdl_mod

        missing_log = tmp_path / "nonexistent.jsonl"
        assert not missing_log.exists()

        monkeypatch.setattr(sdl_mod, "default_delivery_log_path", lambda: missing_log)

        set_social_delivery_log_store_for_tests(SocialDeliveryLogFileStore())
        try:
            count = count_actions_in_window("telegram", "message", _NOW)
        finally:
            set_social_delivery_log_store_for_tests(None)

        assert count == 0, f"Missing delivery log should return 0 (not raise), got {count}."

    def test_cap_counter_explicit_path_still_reads_jsonl_directly(
        self,
        tmp_path: Path,
    ) -> None:
        """Explicit delivery_log_path bypasses the store (backward compat)."""
        delivery_log = tmp_path / "delivery_log.jsonl"
        for i in range(3):
            executed_at = _NOW - timedelta(hours=i + 1)
            _append_jsonl(delivery_log, _telegram_delivery_record(executed_at=executed_at))

        # Even with a Firestore store injected, explicit path reads JSONL.
        fake_client = _FakeFirestoreClient()  # empty Firestore
        store = FirestoreSocialDeliveryLogStore(client=fake_client)
        set_social_delivery_log_store_for_tests(store)
        try:
            count = count_actions_in_window(
                "telegram", "message", _NOW, delivery_log_path=delivery_log
            )
        finally:
            set_social_delivery_log_store_for_tests(None)

        assert count == 3, f"Explicit path should read 3 JSONL records directly, got {count}."

    def test_cap_counter_explicit_missing_path_returns_zero(
        self,
        tmp_path: Path,
    ) -> None:
        """Explicit missing path returns 0 — M14 M1c regression guard (unchanged)."""
        missing_log = tmp_path / "missing.jsonl"
        assert not missing_log.exists()

        count = count_actions_in_window(
            "telegram",
            "message",
            _NOW,
            delivery_log_path=missing_log,
        )
        assert count == 0
