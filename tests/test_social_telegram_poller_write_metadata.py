"""Tests for TelegramOffsetStoreProtocol.write_poller_metadata and poller script integration.

Covers:
- Protocol method exists on both backends (file + Firestore)
- last_run_at populates after successful poll cycle
- last_error populates on failure path (bounded to 280 chars and redacted)
- Existing offset value preserved across metadata writes (regression)
- Status endpoint surfaces the values written by the poller
- No live Telegram or Firestore calls from any test
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Helpers shared across test classes
# ---------------------------------------------------------------------------

_BOT_DIGEST = "deadbeef01234567"
_SYNTHETIC_TOKEN = "synthetic-bot-token-ABC123"

# Regex mirroring the one in social_telegram_inbound_collector.py and social.py
_NUMERIC_ID_RE = re.compile(r"(?<![A-Za-z])-?\d{6,}(?![A-Za-z])")


class InMemoryOffsetStore:
    """Full-featured in-memory store satisfying TelegramOffsetStoreProtocol (including write_poller_metadata)."""

    def __init__(self, initial_offset: int | None = None) -> None:
        self._offset = initial_offset
        self._last_run_at: str | None = None
        self._last_error: str | None = None

    def read_offset(self, bot_digest: str) -> int | None:
        return self._offset

    def write_offset(self, bot_digest: str, update_offset: int) -> None:
        self._offset = update_offset

    def read_poller_metadata(self, bot_digest: str) -> dict[str, Any]:
        return {"last_run_at": self._last_run_at, "last_error": self._last_error}

    def write_poller_metadata(
        self,
        bot_digest: str,
        *,
        last_run_at: str | None = None,
        last_error: str | None = None,
    ) -> None:
        if last_run_at is not None:
            self._last_run_at = last_run_at
        if last_error is not None:
            self._last_error = last_error


class InMemoryTranscriptStore:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def append_row(self, row: dict[str, Any]) -> None:
        self.rows.append(dict(row))

    def iter_rows(self) -> Iterator[dict[str, Any]]:
        return iter(self.rows)


class RaisingTransport:
    """Transport that always raises — simulates a poll failure."""

    def get_updates(self, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("Simulated transport failure with id 123456789012")


class MockGetUpdatesTransport:
    """Hand-rolled mock transport returning configured updates."""

    def __init__(self, updates: list[dict[str, Any]] | None = None) -> None:
        self._updates = updates or []

    def get_updates(
        self,
        *,
        bot_token: str,
        offset: int,
        limit: int,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        return {"ok": True, "result": list(self._updates)}


def _make_update(
    update_id: int = 1,
    message_id: int = 100,
    chat_id: int = -100100100,
    author_id: int = 99887766,
    text: str = "Hello",
    date: int = 1700000000,
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "from": {"id": author_id, "first_name": "Test"},
            "chat": {"id": chat_id, "type": "supergroup"},
            "date": date,
            "text": text,
        },
    }


# ---------------------------------------------------------------------------
# 1. Protocol method exists on both backends
# ---------------------------------------------------------------------------


class TestWritePollerMetadataProtocolExists:
    """Protocol method write_poller_metadata exists on both backends."""

    def test_protocol_has_write_poller_metadata(self) -> None:
        """TelegramOffsetStoreProtocol declares write_poller_metadata."""
        from src.ham.social_telegram_offset_store import TelegramOffsetStoreProtocol

        assert hasattr(TelegramOffsetStoreProtocol, "write_poller_metadata"), (
            "TelegramOffsetStoreProtocol must declare write_poller_metadata"
        )

    def test_file_backend_conforms_to_protocol_with_write_method(self, tmp_path: Path) -> None:
        """TelegramOffsetFileStore satisfies TelegramOffsetStoreProtocol including write_poller_metadata."""
        from src.ham.social_telegram_offset_store import (
            TelegramOffsetFileStore,
            TelegramOffsetStoreProtocol,
        )

        store = TelegramOffsetFileStore(base_dir=tmp_path)
        assert isinstance(store, TelegramOffsetStoreProtocol)
        assert hasattr(store, "write_poller_metadata")
        assert callable(store.write_poller_metadata)

    def test_firestore_backend_has_write_poller_metadata(self) -> None:
        """FirestoreTelegramOffsetStore has write_poller_metadata method."""
        from src.ham.social_telegram_offset_firestore import FirestoreTelegramOffsetStore
        from src.ham.social_telegram_offset_store import TelegramOffsetStoreProtocol

        store = FirestoreTelegramOffsetStore(client=object())  # client never called
        assert hasattr(store, "write_poller_metadata")
        assert callable(store.write_poller_metadata)
        assert isinstance(store, TelegramOffsetStoreProtocol)


# ---------------------------------------------------------------------------
# 2. File backend: write_poller_metadata sets and preserves fields
# ---------------------------------------------------------------------------


class TestFileBackendWritePollerMetadata:
    """TelegramOffsetFileStore.write_poller_metadata merges without losing the offset."""

    def test_write_last_run_at_sets_field(self, tmp_path: Path) -> None:
        """write_poller_metadata(last_run_at=...) stores the timestamp."""
        from src.ham.social_telegram_offset_store import TelegramOffsetFileStore

        store = TelegramOffsetFileStore(base_dir=tmp_path)
        store.write_poller_metadata(_BOT_DIGEST, last_run_at="2026-05-22T10:00:00+00:00")
        meta = store.read_poller_metadata(_BOT_DIGEST)
        assert meta["last_run_at"] == "2026-05-22T10:00:00+00:00"

    def test_write_last_error_sets_field(self, tmp_path: Path) -> None:
        """write_poller_metadata(last_error=...) stores the error text."""
        from src.ham.social_telegram_offset_store import TelegramOffsetFileStore

        store = TelegramOffsetFileStore(base_dir=tmp_path)
        store.write_poller_metadata(_BOT_DIGEST, last_error="transport error")
        meta = store.read_poller_metadata(_BOT_DIGEST)
        assert meta["last_error"] == "transport error"

    def test_write_metadata_preserves_existing_offset(self, tmp_path: Path) -> None:
        """write_poller_metadata does not clear the stored update_offset."""
        from src.ham.social_telegram_offset_store import TelegramOffsetFileStore

        store = TelegramOffsetFileStore(base_dir=tmp_path)
        store.write_offset(_BOT_DIGEST, 42)
        store.write_poller_metadata(_BOT_DIGEST, last_run_at="2026-05-22T10:00:00+00:00")
        assert store.read_offset(_BOT_DIGEST) == 42, (
            "write_poller_metadata must not clear the stored update_offset"
        )

    def test_write_offset_preserves_existing_metadata(self, tmp_path: Path) -> None:
        """write_offset does not clear existing last_run_at / last_error fields."""
        from src.ham.social_telegram_offset_store import TelegramOffsetFileStore

        store = TelegramOffsetFileStore(base_dir=tmp_path)
        store.write_poller_metadata(_BOT_DIGEST, last_run_at="2026-05-22T10:00:00+00:00")
        store.write_offset(_BOT_DIGEST, 99)
        meta = store.read_poller_metadata(_BOT_DIGEST)
        assert meta["last_run_at"] == "2026-05-22T10:00:00+00:00", (
            "write_offset must not clear existing last_run_at"
        )
        assert store.read_offset(_BOT_DIGEST) == 99

    def test_only_specified_fields_updated(self, tmp_path: Path) -> None:
        """Only specified (non-None) fields are updated; others remain unchanged."""
        from src.ham.social_telegram_offset_store import TelegramOffsetFileStore

        store = TelegramOffsetFileStore(base_dir=tmp_path)
        store.write_poller_metadata(_BOT_DIGEST, last_error="original error")
        store.write_poller_metadata(_BOT_DIGEST, last_run_at="2026-05-22T10:00:00+00:00")
        meta = store.read_poller_metadata(_BOT_DIGEST)
        # last_run_at was updated, last_error was NOT cleared
        assert meta["last_run_at"] == "2026-05-22T10:00:00+00:00"
        assert meta["last_error"] == "original error", (
            "write_poller_metadata must not clear last_error when only last_run_at is provided"
        )

    def test_noop_when_both_args_none(self, tmp_path: Path) -> None:
        """write_poller_metadata() with no non-None args leaves the file unchanged."""
        from src.ham.social_telegram_offset_store import TelegramOffsetFileStore

        store = TelegramOffsetFileStore(base_dir=tmp_path)
        store.write_offset(_BOT_DIGEST, 10)
        store.write_poller_metadata(_BOT_DIGEST)  # no args
        assert store.read_offset(_BOT_DIGEST) == 10
        meta = store.read_poller_metadata(_BOT_DIGEST)
        assert meta["last_run_at"] is None
        assert meta["last_error"] is None


# ---------------------------------------------------------------------------
# 3. Firestore backend: write_poller_metadata sets and preserves fields
# ---------------------------------------------------------------------------


class _FakeFirestoreDoc:
    """In-memory Firestore document fake supporting get/set/update."""

    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] | None = initial

    def get(self) -> _FakeFirestoreSnap:
        return _FakeFirestoreSnap(self._data)

    def set(self, data: dict[str, Any], merge: bool = False) -> None:
        if merge and self._data is not None:
            self._data = {**self._data, **data}
        else:
            self._data = dict(data)


class _FakeFirestoreSnap:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data) if self._data is not None else {}


class _FakeFirestoreCollection:
    def __init__(self) -> None:
        self._docs: dict[str, _FakeFirestoreDoc] = {}

    def document(self, doc_id: str) -> _FakeFirestoreDoc:
        if doc_id not in self._docs:
            self._docs[doc_id] = _FakeFirestoreDoc()
        return self._docs[doc_id]


class _FakeFirestoreClient:
    def __init__(self) -> None:
        self._collections: dict[str, _FakeFirestoreCollection] = {}

    def collection(self, name: str) -> _FakeFirestoreCollection:
        if name not in self._collections:
            self._collections[name] = _FakeFirestoreCollection()
        return self._collections[name]


class TestFirestoreBackendWritePollerMetadata:
    """FirestoreTelegramOffsetStore.write_poller_metadata merges without losing the offset."""

    def _make_store(self) -> tuple[Any, _FakeFirestoreClient]:
        from src.ham.social_telegram_offset_firestore import FirestoreTelegramOffsetStore

        client = _FakeFirestoreClient()
        store = FirestoreTelegramOffsetStore(client=client)
        return store, client

    def test_write_last_run_at_sets_field(self) -> None:
        """write_poller_metadata(last_run_at=...) stores the timestamp in Firestore."""
        store, _ = self._make_store()
        store.write_poller_metadata(_BOT_DIGEST, last_run_at="2026-05-22T10:00:00+00:00")
        meta = store.read_poller_metadata(_BOT_DIGEST)
        assert meta["last_run_at"] == "2026-05-22T10:00:00+00:00"

    def test_write_last_error_sets_field(self) -> None:
        """write_poller_metadata(last_error=...) stores the error in Firestore."""
        store, _ = self._make_store()
        store.write_poller_metadata(_BOT_DIGEST, last_error="transport error")
        meta = store.read_poller_metadata(_BOT_DIGEST)
        assert meta["last_error"] == "transport error"

    def test_write_metadata_preserves_existing_offset(self) -> None:
        """write_poller_metadata does not clear the stored update_offset in Firestore."""
        store, _ = self._make_store()
        store.write_offset(_BOT_DIGEST, 42)
        store.write_poller_metadata(_BOT_DIGEST, last_run_at="2026-05-22T10:00:00+00:00")
        assert store.read_offset(_BOT_DIGEST) == 42, (
            "write_poller_metadata must not clear update_offset in Firestore"
        )

    def test_only_specified_fields_updated(self) -> None:
        """Only specified (non-None) fields are merged into the Firestore document."""
        store, _ = self._make_store()
        store.write_poller_metadata(_BOT_DIGEST, last_error="original error")
        store.write_poller_metadata(_BOT_DIGEST, last_run_at="2026-05-22T10:00:00+00:00")
        meta = store.read_poller_metadata(_BOT_DIGEST)
        assert meta["last_run_at"] == "2026-05-22T10:00:00+00:00"
        assert meta["last_error"] == "original error", (
            "write_poller_metadata must not clear last_error when only last_run_at is provided"
        )

    def test_write_offset_preserves_existing_metadata(self) -> None:
        """write_offset does not clear existing last_run_at / last_error fields in Firestore."""
        store, _ = self._make_store()
        store.write_poller_metadata(_BOT_DIGEST, last_run_at="2026-05-22T10:00:00+00:00")
        store.write_offset(_BOT_DIGEST, 99)
        meta = store.read_poller_metadata(_BOT_DIGEST)
        assert meta["last_run_at"] == "2026-05-22T10:00:00+00:00", (
            "write_offset must not clear existing last_run_at in Firestore"
        )
        assert store.read_offset(_BOT_DIGEST) == 99

    def test_write_poller_metadata_raises_on_sdk_error(self) -> None:
        """write_poller_metadata raises FirestoreTelegramOffsetStoreError on SDK failure."""
        from src.ham.social_telegram_offset_firestore import (
            FirestoreTelegramOffsetStore,
            FirestoreTelegramOffsetStoreError,
        )

        class _FailDoc:
            def get(self) -> None:
                raise RuntimeError("SDK error")

            def set(self, data: Any, merge: bool = False) -> None:
                raise RuntimeError("SDK error")

        class _FailCollection:
            def document(self, doc_id: str) -> _FailDoc:
                return _FailDoc()

        class _FailClient:
            def collection(self, name: str) -> _FailCollection:
                return _FailCollection()

        store = FirestoreTelegramOffsetStore(client=_FailClient())
        with pytest.raises(FirestoreTelegramOffsetStoreError):
            store.write_poller_metadata(_BOT_DIGEST, last_run_at="2026-05-22T10:00:00+00:00")


# ---------------------------------------------------------------------------
# 4. Poller script: last_run_at written after successful poll
# ---------------------------------------------------------------------------


class TestPollerScriptWritesLastRunAt:
    """scripts/social_telegram_inbound_poll.py writes last_run_at after each poll cycle."""

    def test_last_run_at_populated_after_successful_poll_with_updates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """last_run_at is written after a poll cycle that returns updates."""
        from scripts.social_telegram_inbound_poll import main

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _SYNTHETIC_TOKEN)
        offset_store = InMemoryOffsetStore(initial_offset=0)
        transcript_store = InMemoryTranscriptStore()

        with pytest.raises(SystemExit) as excinfo:
            main(
                transport=MockGetUpdatesTransport(updates=[_make_update(update_id=1)]),
                offset_store=offset_store,
                transcript_store=transcript_store,
            )

        assert excinfo.value.code == 0
        assert offset_store._last_run_at is not None, (
            "last_run_at must be set after a successful poll with updates"
        )

    def test_last_run_at_populated_after_poll_with_no_updates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """last_run_at is written even when poll returns 0 updates."""
        from scripts.social_telegram_inbound_poll import main

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _SYNTHETIC_TOKEN)
        offset_store = InMemoryOffsetStore(initial_offset=0)
        transcript_store = InMemoryTranscriptStore()

        with pytest.raises(SystemExit) as excinfo:
            main(
                transport=MockGetUpdatesTransport(updates=[]),
                offset_store=offset_store,
                transcript_store=transcript_store,
            )

        assert excinfo.value.code == 0
        assert offset_store._last_run_at is not None, (
            "last_run_at must be set even when poll returns 0 updates"
        )

    def test_last_run_at_is_iso8601_timestamp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """last_run_at is an ISO-8601 timestamp string."""
        import datetime

        from scripts.social_telegram_inbound_poll import main

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _SYNTHETIC_TOKEN)
        offset_store = InMemoryOffsetStore()
        transcript_store = InMemoryTranscriptStore()

        with pytest.raises(SystemExit):
            main(
                transport=MockGetUpdatesTransport(updates=[]),
                offset_store=offset_store,
                transcript_store=transcript_store,
            )

        ts = offset_store._last_run_at
        assert ts is not None
        # Must be parseable as a datetime
        parsed = datetime.datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None, "last_run_at must be timezone-aware"

    def test_last_run_at_not_written_when_token_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """last_run_at is NOT written when token is absent (no poll happens)."""
        from scripts.social_telegram_inbound_poll import main

        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        offset_store = InMemoryOffsetStore()
        transcript_store = InMemoryTranscriptStore()

        with pytest.raises(SystemExit) as excinfo:
            main(
                transport=RaisingTransport(),  # type: ignore[arg-type]
                offset_store=offset_store,
                transcript_store=transcript_store,
            )

        assert excinfo.value.code != 0
        assert offset_store._last_run_at is None, (
            "last_run_at must NOT be written when token is absent"
        )

    def test_offset_preserved_after_successful_poll(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """write_poller_metadata does not overwrite the stored offset during success path."""
        from scripts.social_telegram_inbound_poll import main

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _SYNTHETIC_TOKEN)
        offset_store = InMemoryOffsetStore(initial_offset=5)
        transcript_store = InMemoryTranscriptStore()

        with pytest.raises(SystemExit) as excinfo:
            main(
                transport=MockGetUpdatesTransport(updates=[_make_update(update_id=10)]),
                offset_store=offset_store,
                transcript_store=transcript_store,
            )

        assert excinfo.value.code == 0
        # Offset must have advanced (10 + 1 = 11)
        assert offset_store._offset == 11, "Offset must be advanced by the poll"
        # And metadata must also be written
        assert offset_store._last_run_at is not None


# ---------------------------------------------------------------------------
# 5. Poller script: last_error written on exception path (bounded + redacted)
# ---------------------------------------------------------------------------


class TestPollerScriptWritesLastError:
    """scripts/social_telegram_inbound_poll.py writes last_error on exception paths."""

    def test_last_error_populated_on_transport_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """last_error is written when the transport raises an exception."""
        from scripts.social_telegram_inbound_poll import main

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _SYNTHETIC_TOKEN)
        offset_store = InMemoryOffsetStore(initial_offset=0)
        transcript_store = InMemoryTranscriptStore()

        with pytest.raises((SystemExit, Exception)):
            main(
                transport=RaisingTransport(),  # type: ignore[arg-type]
                offset_store=offset_store,
                transcript_store=transcript_store,
            )

        assert offset_store._last_error is not None, (
            "last_error must be set when the transport raises"
        )

    def test_last_error_bounded_to_280_chars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """last_error stored in the offset store is bounded to ≤ 280 characters."""

        class LongErrorTransport:
            def get_updates(self, **kwargs: Any) -> dict[str, Any]:
                raise RuntimeError("x" * 5000)

        from scripts.social_telegram_inbound_poll import main

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _SYNTHETIC_TOKEN)
        offset_store = InMemoryOffsetStore()
        transcript_store = InMemoryTranscriptStore()

        with pytest.raises((SystemExit, Exception)):
            main(
                transport=LongErrorTransport(),  # type: ignore[arg-type]
                offset_store=offset_store,
                transcript_store=transcript_store,
            )

        error = offset_store._last_error
        assert error is not None
        assert len(error) <= 280, f"last_error must be ≤ 280 chars, got {len(error)}"

    def test_last_error_numeric_ids_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """6+-digit numeric sequences in last_error are stripped (redacted)."""
        from scripts.social_telegram_inbound_poll import main

        # RaisingTransport raises RuntimeError with "123456789012" in the message
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _SYNTHETIC_TOKEN)
        offset_store = InMemoryOffsetStore()
        transcript_store = InMemoryTranscriptStore()

        with pytest.raises((SystemExit, Exception)):
            main(
                transport=RaisingTransport(),  # type: ignore[arg-type]
                offset_store=offset_store,
                transcript_store=transcript_store,
            )

        error = offset_store._last_error
        assert error is not None
        # The RaisingTransport raises with "id 123456789012" — 12 digits, must be stripped
        assert "123456789012" not in error, (
            "6+-digit numeric sequences must be stripped from last_error"
        )

    def test_last_run_at_not_written_on_exception_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """last_run_at is NOT written when the poll cycle raises an exception."""
        from scripts.social_telegram_inbound_poll import main

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _SYNTHETIC_TOKEN)
        offset_store = InMemoryOffsetStore()
        transcript_store = InMemoryTranscriptStore()

        with pytest.raises((SystemExit, Exception)):
            main(
                transport=RaisingTransport(),  # type: ignore[arg-type]
                offset_store=offset_store,
                transcript_store=transcript_store,
            )

        assert offset_store._last_run_at is None, (
            "last_run_at must NOT be written when the transport raises"
        )

    def test_exception_propagates_after_last_error_write(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The original exception is re-raised (not swallowed) after writing last_error.

        Cloud Run Job --max-retries=0 guarantee: non-zero exit is preserved.
        """
        from scripts.social_telegram_inbound_poll import main

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _SYNTHETIC_TOKEN)
        offset_store = InMemoryOffsetStore()
        transcript_store = InMemoryTranscriptStore()

        # The process must exit non-zero (via re-raise or sys.exit(1))
        with pytest.raises((SystemExit, RuntimeError)) as excinfo:
            main(
                transport=RaisingTransport(),  # type: ignore[arg-type]
                offset_store=offset_store,
                transcript_store=transcript_store,
            )

        # Must be non-zero exit or unhandled RuntimeError — never sys.exit(0)
        exc = excinfo.value
        if isinstance(exc, SystemExit):
            assert exc.code != 0, "Must exit non-zero when transport raises"
        # RuntimeError propagating is also acceptable — confirms non-zero exit to Cloud Run


# ---------------------------------------------------------------------------
# 6. Status endpoint surfaces values written by the poller
# ---------------------------------------------------------------------------


class _FakeOffsetStoreWithWrite:
    """In-memory fake that supports read/write + write_poller_metadata for endpoint tests."""

    def __init__(
        self,
        update_offset: int | None = None,
        last_run_at: str | None = None,
        last_error: str | None = None,
    ) -> None:
        self._update_offset = update_offset
        self._last_run_at = last_run_at
        self._last_error = last_error

    def read_offset(self, bot_digest: str) -> int | None:
        return self._update_offset

    def write_offset(self, bot_digest: str, update_offset: int) -> None:
        self._update_offset = update_offset

    def read_poller_metadata(self, bot_digest: str) -> dict[str, Any]:
        return {"last_run_at": self._last_run_at, "last_error": self._last_error}

    def write_poller_metadata(
        self,
        bot_digest: str,
        *,
        last_run_at: str | None = None,
        last_error: str | None = None,
    ) -> None:
        if last_run_at is not None:
            self._last_run_at = last_run_at
        if last_error is not None:
            self._last_error = last_error


class _FakeTranscriptStore:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows: list[dict[str, Any]] = rows or []

    def append_row(self, row: dict[str, Any]) -> None:
        self._rows.append(row)

    def iter_rows(self) -> Iterator[dict[str, Any]]:
        return iter(self._rows)


@pytest.fixture()
def _api_client() -> Iterator[Any]:
    from fastapi.testclient import TestClient

    from src.api.server import app

    with TestClient(app) as client:
        yield client


class TestStatusEndpointSurfacesPollerValues:
    """GET /api/social/providers/telegram/poller/status surfaces values written by the poller."""

    def test_status_endpoint_surfaces_last_run_at_written_by_poller(self, _api_client: Any) -> None:
        """Status endpoint returns last_run_at set via write_poller_metadata."""
        import datetime

        from src.ham.social_telegram_offset_store import set_telegram_offset_store_for_tests
        from src.ham.social_telegram_transcript_store import (
            set_telegram_transcript_store_for_tests,
        )

        ts = datetime.datetime.now(datetime.UTC).isoformat()
        fake_offset = _FakeOffsetStoreWithWrite(last_run_at=ts)
        fake_transcript = _FakeTranscriptStore()

        set_telegram_offset_store_for_tests(fake_offset)  # type: ignore[arg-type]
        set_telegram_transcript_store_for_tests(fake_transcript)  # type: ignore[arg-type]
        try:
            resp = _api_client.get("/api/social/providers/telegram/poller/status")
            assert resp.status_code == 200
            body = resp.json()
            assert body["last_run_at"] == ts
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)

    def test_status_endpoint_surfaces_last_error_written_by_poller(self, _api_client: Any) -> None:
        """Status endpoint returns last_error_code (bounded+redacted) from write_poller_metadata."""
        from src.ham.social_telegram_offset_store import set_telegram_offset_store_for_tests
        from src.ham.social_telegram_transcript_store import (
            set_telegram_transcript_store_for_tests,
        )

        # Simulate poller writing a bounded+redacted error
        stored_error = "transport error occurred"
        fake_offset = _FakeOffsetStoreWithWrite(last_error=stored_error)
        fake_transcript = _FakeTranscriptStore()

        set_telegram_offset_store_for_tests(fake_offset)  # type: ignore[arg-type]
        set_telegram_transcript_store_for_tests(fake_transcript)  # type: ignore[arg-type]
        try:
            resp = _api_client.get("/api/social/providers/telegram/poller/status")
            assert resp.status_code == 200
            body = resp.json()
            assert body["last_error_code"] == stored_error
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)

    def test_status_endpoint_last_run_at_null_when_not_written(self, _api_client: Any) -> None:
        """Status endpoint returns null last_run_at when poller has not written metadata."""
        from src.ham.social_telegram_offset_store import set_telegram_offset_store_for_tests
        from src.ham.social_telegram_transcript_store import (
            set_telegram_transcript_store_for_tests,
        )

        fake_offset = _FakeOffsetStoreWithWrite()
        fake_transcript = _FakeTranscriptStore()

        set_telegram_offset_store_for_tests(fake_offset)  # type: ignore[arg-type]
        set_telegram_transcript_store_for_tests(fake_transcript)  # type: ignore[arg-type]
        try:
            resp = _api_client.get("/api/social/providers/telegram/poller/status")
            assert resp.status_code == 200
            body = resp.json()
            assert body["last_run_at"] is None
            assert body["last_error_code"] is None
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)

    def test_status_endpoint_offset_preserved_after_metadata_write(self, _api_client: Any) -> None:
        """Offset is preserved after write_poller_metadata (not wiped); status endpoint reflects it."""
        from src.ham.social_telegram_offset_store import set_telegram_offset_store_for_tests
        from src.ham.social_telegram_transcript_store import (
            set_telegram_transcript_store_for_tests,
        )

        # Simulate: write_offset(42) then write_poller_metadata(last_run_at=...)
        fake_offset = _FakeOffsetStoreWithWrite(
            update_offset=42, last_run_at="2026-05-22T10:00:00+00:00"
        )
        fake_transcript = _FakeTranscriptStore()

        set_telegram_offset_store_for_tests(fake_offset)  # type: ignore[arg-type]
        set_telegram_transcript_store_for_tests(fake_transcript)  # type: ignore[arg-type]
        try:
            resp = _api_client.get("/api/social/providers/telegram/poller/status")
            assert resp.status_code == 200
            body = resp.json()
            assert body["last_offset"] == 42, "Offset must not be lost after metadata write"
            assert body["last_run_at"] == "2026-05-22T10:00:00+00:00"
        finally:
            set_telegram_offset_store_for_tests(None)
            set_telegram_transcript_store_for_tests(None)
