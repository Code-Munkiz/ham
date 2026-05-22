"""Firestore-backed Telegram inbound transcript store tests.

Covers:
- VAL-M15-M1-TRANSCRIPT-FIRESTORE-ROUNDTRIP-009: append_row then iter_rows
  roundtrip parity — written row equals the row yielded by iter_rows with the
  redacted, allow-listed fields matching the JSONL contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from src.ham.social_telegram_transcript_firestore import (
    FirestoreTelegramTranscriptStore,
    FirestoreTelegramTranscriptStoreError,
)

# ---------------------------------------------------------------------------
# Minimal fake Firestore client (document-level get/set/stream)
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

_TRANSCRIPT_ROW_FIELDS = frozenset(
    {
        "source",
        "role",
        "text",
        "chat_id",
        "author_id",
        "message_id",
        "created_at",
        "chat_type",
        "already_answered",
    }
)

_VALID_ROW: dict[str, Any] = {
    "source": "telegram",
    "role": "user",
    "text": "Hello world",
    "chat_id": 12345,
    "author_id": 67890,
    "message_id": 111,
    "created_at": "2026-05-20T12:00:00Z",
}


def _store_with_fake() -> tuple[FirestoreTelegramTranscriptStore, _FakeFirestoreClient]:
    fake = _FakeFirestoreClient()
    store = FirestoreTelegramTranscriptStore(client=fake)
    return store, fake


# ---------------------------------------------------------------------------
# VAL-M15-M1-TRANSCRIPT-FIRESTORE-ROUNDTRIP-009
# ---------------------------------------------------------------------------


class TestAppendThenIterRoundtrip:
    """VAL-M15-M1-TRANSCRIPT-FIRESTORE-ROUNDTRIP-009

    append_row writes one document under ham_social_telegram_transcripts/{id}
    with the redacted, allow-listed fields matching the JSONL contract;
    iter_rows returns the row(s) with the same schema. Written row equals the
    row yielded by iter_rows.
    """

    def test_append_then_iter_roundtrip(self) -> None:
        """Basic roundtrip: single row written and read back with correct schema."""
        store, _ = _store_with_fake()
        store.append_row(_VALID_ROW.copy())
        rows = list(store.iter_rows())
        assert len(rows) == 1
        row = rows[0]
        assert row["source"] == "telegram"
        assert row["role"] == "user"
        assert row["text"] == "Hello world"
        assert row["chat_id"] == 12345
        assert row["author_id"] == 67890
        assert row["message_id"] == 111
        assert row["created_at"] == "2026-05-20T12:00:00Z"

    def test_only_allowed_fields_in_stored_document(self) -> None:
        """Extra fields are stripped at write time — only allow-listed fields stored."""
        store, fake = _store_with_fake()
        row = {
            **_VALID_ROW,
            "raw_telegram_update": {"evil": "data"},
            "token": "super-secret-token",
        }
        store.append_row(row)
        docs = list(fake.collection("ham_social_telegram_transcripts").stream())
        assert len(docs) == 1
        stored = docs[0].to_dict()
        assert set(stored.keys()) <= _TRANSCRIPT_ROW_FIELDS, (
            f"Extra fields in stored record: {set(stored.keys()) - _TRANSCRIPT_ROW_FIELDS}"
        )
        assert "raw_telegram_update" not in stored
        assert "token" not in stored

    def test_text_redacted_before_storage(self) -> None:
        """Free-form text is passed through the redaction pipeline before storing."""
        store, fake = _store_with_fake()
        # Embed a bearer token in the text
        raw_text = "Bearer supersecretapitoken12345 Hello"
        row = {**_VALID_ROW, "text": raw_text}
        store.append_row(row)

        docs = list(fake.collection("ham_social_telegram_transcripts").stream())
        assert len(docs) == 1
        stored = docs[0].to_dict()
        # The raw token substring must be scrubbed by redact_text
        assert "supersecretapitoken12345" not in stored.get("text", ""), (
            "Bearer token found in stored text — redaction did not run"
        )

    def test_integer_ids_preserved(self) -> None:
        """chat_id, author_id, and message_id are stored as integers."""
        store, fake = _store_with_fake()
        store.append_row(_VALID_ROW.copy())

        docs = list(fake.collection("ham_social_telegram_transcripts").stream())
        stored = docs[0].to_dict()
        assert isinstance(stored.get("chat_id"), int), (
            f"chat_id should be int, got {type(stored.get('chat_id'))}"
        )
        assert isinstance(stored.get("author_id"), int), (
            f"author_id should be int, got {type(stored.get('author_id'))}"
        )
        assert isinstance(stored.get("message_id"), int), (
            f"message_id should be int, got {type(stored.get('message_id'))}"
        )

    def test_iter_rows_empty_when_no_documents(self) -> None:
        """iter_rows on an empty collection yields nothing (no error)."""
        store, _ = _store_with_fake()
        rows = list(store.iter_rows())
        assert rows == []

    def test_multiple_rows_appended_and_iterated(self) -> None:
        """Multiple append_row calls produce multiple iterable rows."""
        store, _ = _store_with_fake()
        row1 = {**_VALID_ROW, "message_id": 100, "text": "First"}
        row2 = {**_VALID_ROW, "message_id": 200, "text": "Second"}
        store.append_row(row1)
        store.append_row(row2)
        rows = list(store.iter_rows())
        assert len(rows) == 2
        message_ids = {r["message_id"] for r in rows}
        assert 100 in message_ids
        assert 200 in message_ids

    def test_optional_fields_included_when_present(self) -> None:
        """Optional fields chat_type and already_answered are stored when provided."""
        store, fake = _store_with_fake()
        row = {
            **_VALID_ROW,
            "chat_type": "group",
            "already_answered": True,
        }
        store.append_row(row)
        docs = list(fake.collection("ham_social_telegram_transcripts").stream())
        stored = docs[0].to_dict()
        assert stored.get("chat_type") == "group"
        assert stored.get("already_answered") is True

    def test_iter_rows_yields_only_allowed_fields(self) -> None:
        """iter_rows defensively strips any extra fields from stored documents."""
        store, fake = _store_with_fake()
        # Manually inject a document with extra fields (simulating legacy data)
        fake.docs["ham_social_telegram_transcripts/legacy-doc"] = {
            **_VALID_ROW,
            "extra_injected_field": "should_be_stripped",
        }
        rows = list(store.iter_rows())
        assert len(rows) == 1
        assert "extra_injected_field" not in rows[0]

    def test_row_schema_matches_jsonl_contract(self) -> None:
        """Stored row schema matches the JSONL contract verbatim."""
        store, _ = _store_with_fake()
        store.append_row(_VALID_ROW.copy())
        rows = list(store.iter_rows())
        assert len(rows) == 1
        row = rows[0]
        # Required fields from the JSONL contract
        assert row.get("source") == "telegram"
        assert row.get("role") == "user"
        assert "text" in row
        assert "chat_id" in row
        assert "author_id" in row
        assert "message_id" in row
        assert "created_at" in row


# ---------------------------------------------------------------------------
# Fail-closed: Firestore SDK errors surface properly
# ---------------------------------------------------------------------------


class TestFailClosed:
    """VAL-M15-M1-STORE-FAILCLOSED-TRANSCRIPT-023 (partial — factory test covers the full assertion)

    append_row / iter_rows surface a typed error rather than falling back to JSONL.
    """

    def test_append_row_raises_on_sdk_error(self) -> None:
        """append_row wraps SDK errors in FirestoreTelegramTranscriptStoreError."""

        class _FailDoc:
            def set(self, data: dict) -> None:
                raise RuntimeError("Simulated SDK write error")

        class _FailCollection:
            def document(self, doc_id: str) -> _FailDoc:
                return _FailDoc()

        class _FailClient:
            def collection(self, name: str) -> _FailCollection:
                return _FailCollection()

        store = FirestoreTelegramTranscriptStore(client=_FailClient())
        with pytest.raises(FirestoreTelegramTranscriptStoreError):
            store.append_row(_VALID_ROW.copy())

    def test_iter_rows_raises_on_sdk_error(self) -> None:
        """iter_rows wraps SDK errors in FirestoreTelegramTranscriptStoreError."""

        class _FailCollection:
            def stream(self):
                raise RuntimeError("Simulated SDK stream error")

        class _FailClient:
            def collection(self, name: str) -> _FailCollection:
                return _FailCollection()

        store = FirestoreTelegramTranscriptStore(client=_FailClient())
        with pytest.raises(FirestoreTelegramTranscriptStoreError):
            list(store.iter_rows())


# ---------------------------------------------------------------------------
# Fail-closed: redaction failures never persist unredacted text
# VAL-M15-M1B-TRANSCRIPT-REDACT-FAIL-CLOSED-001
# ---------------------------------------------------------------------------


class TestRedactFailClosed:
    """VAL-M15-M1B-TRANSCRIPT-REDACT-FAIL-CLOSED-001

    _redact_row_text must distinguish ImportError from runtime failure inside
    redact_text(). Both must fail closed by raising
    FirestoreTelegramTranscriptStoreError; under no circumstances may
    unredacted free-form text be silently persisted to Firestore.
    """

    def test_redact_runtime_error_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Forces redact_text() to raise a generic RuntimeError.

        Asserts:
        - append_row raises FirestoreTelegramTranscriptStoreError
        - The document collection remains empty (zero rows persisted)
        """
        import src.ham.hamgomoon_learning.redaction as redaction_mod

        def _raising_redact(text: str) -> str:
            raise RuntimeError("Simulated redaction runtime failure")

        monkeypatch.setattr(redaction_mod, "redact_text", _raising_redact)

        store, fake = _store_with_fake()
        with pytest.raises(FirestoreTelegramTranscriptStoreError):
            store.append_row(_VALID_ROW.copy())

        # Collection must remain empty — no unredacted text was persisted
        docs = list(fake.collection("ham_social_telegram_transcripts").stream())
        assert len(docs) == 0, (
            "No documents should be persisted when redact_text() raises a RuntimeError"
        )

    def test_redact_import_error_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Forces the redact_text import to raise ImportError.

        Asserts:
        - append_row raises FirestoreTelegramTranscriptStoreError
        - The document collection remains empty (zero rows persisted)
        """
        import importlib
        import sys

        # Remove the redaction module from sys.modules so the inline import
        # inside _redact_row_text will re-execute; then make the import fail.
        original = sys.modules.pop("src.ham.hamgomoon_learning.redaction", None)
        try:
            import builtins

            real_import = builtins.__import__

            def _failing_import(name: str, *args: object, **kwargs: object) -> object:
                if name == "src.ham.hamgomoon_learning.redaction":
                    raise ImportError("Simulated missing redaction module")
                return real_import(name, *args, **kwargs)

            monkeypatch.setattr(builtins, "__import__", _failing_import)

            store, fake = _store_with_fake()
            with pytest.raises(FirestoreTelegramTranscriptStoreError):
                store.append_row(_VALID_ROW.copy())

            # Collection must remain empty — no unredacted text was persisted
            docs = list(fake.collection("ham_social_telegram_transcripts").stream())
            assert len(docs) == 0, (
                "No documents should be persisted when the redaction module is unavailable"
            )
        finally:
            # Restore the original module so subsequent tests are unaffected
            if original is not None:
                sys.modules["src.ham.hamgomoon_learning.redaction"] = original
            else:
                sys.modules.pop("src.ham.hamgomoon_learning.redaction", None)
                # Re-import to restore for other tests
                try:
                    importlib.import_module("src.ham.hamgomoon_learning.redaction")
                except ImportError:
                    pass
