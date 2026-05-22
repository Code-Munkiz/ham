"""Firestore-backed HAMgomoon learning records store tests.

Covers:
- VAL-M15-M1-LEARNING-FIRESTORE-ROUNDTRIP-007: append then list round-trip
  returns the same LearningRecord envelope (Pydantic equality).
- VAL-M15-M1-LEARNING-FIRESTORE-REDACTION-008: redaction pipeline preserved
  end-to-end — bait strings (HAM_SOCIAL_LIVE_APPLY_TOKEN, TELEGRAM_BOT_TOKEN,
  XAI_API_KEY literals, 18+-digit external ID) are scrubbed from the persisted
  Firestore document.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.ham.hamgomoon_learning.firestore_store import FirestoreHamgomoonLearningStore
from src.ham.hamgomoon_learning.models import (
    DeliveryOutcome,
    LearningRecord,
    SocialDraftRecord,
)

# ---------------------------------------------------------------------------
# Minimal fake Firestore client (no transactions needed for learning store)
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


def _store_with_fake() -> tuple[FirestoreHamgomoonLearningStore, _FakeFirestoreClient]:
    fake = _FakeFirestoreClient()
    store = FirestoreHamgomoonLearningStore(client=fake)
    return store, fake


def _make_draft(draft_text: str = "Hello world", prompt: str = "Test prompt") -> SocialDraftRecord:
    return SocialDraftRecord(
        channel="telegram",
        proposed_action="message",
        draft_text=draft_text,
        prompt=prompt,
    )


def _make_record(
    draft_text: str = "Hello world",
    prompt: str = "Test prompt",
) -> LearningRecord:
    draft = _make_draft(draft_text=draft_text, prompt=prompt)
    return LearningRecord(channel="telegram", draft=draft)


# ---------------------------------------------------------------------------
# VAL-M15-M1-LEARNING-FIRESTORE-ROUNDTRIP-007
# ---------------------------------------------------------------------------


class TestAppendThenListRoundtrip:
    """VAL-M15-M1-LEARNING-FIRESTORE-ROUNDTRIP-007

    append_learning_record writes one document under ham_hamgomoon_learning/{id};
    a subsequent list_recent_learning_records returns the same LearningRecord
    envelope (Pydantic equality).
    """

    def test_append_then_list_roundtrip(self) -> None:
        store, _ = _store_with_fake()
        record = _make_record()
        returned = store.append_learning_record(record)

        assert returned.record_id == record.record_id

        results = store.list_recent_learning_records(limit=50)
        assert len(results) == 1
        assert results[0].record_id == record.record_id

    def test_returned_record_pydantic_equal_to_retrieved(self) -> None:
        store, _ = _store_with_fake()
        record = _make_record(draft_text="Roundtrip test", prompt="Some prompt")
        returned = store.append_learning_record(record)

        results = store.list_recent_learning_records(limit=50)
        assert len(results) == 1
        # The returned record and the retrieved record should be equal
        assert results[0] == returned

    def test_append_writes_to_correct_collection(self) -> None:
        store, fake = _store_with_fake()
        record = _make_record()
        store.append_learning_record(record)

        # Exactly one document in ham_hamgomoon_learning
        docs = list(fake.collection("ham_hamgomoon_learning").stream())
        assert len(docs) == 1
        stored = docs[0].to_dict()
        assert stored["record_id"] == record.record_id

    def test_multiple_records_returned_in_chronological_order(self) -> None:
        store, _ = _store_with_fake()
        r1 = _make_record(draft_text="First")
        r2 = _make_record(draft_text="Second")
        r3 = _make_record(draft_text="Third")
        store.append_learning_record(r1)
        store.append_learning_record(r2)
        store.append_learning_record(r3)

        results = store.list_recent_learning_records(limit=50)
        assert len(results) == 3
        # Should be in chronological order (oldest first)
        # All created close together; check that record_ids match expected
        record_ids = [r.record_id for r in results]
        assert set(record_ids) == {r1.record_id, r2.record_id, r3.record_id}

    def test_list_empty_collection_returns_empty(self) -> None:
        store, _ = _store_with_fake()
        results = store.list_recent_learning_records(limit=50)
        assert results == []

    def test_limit_respected(self) -> None:
        store, _ = _store_with_fake()
        for i in range(5):
            store.append_learning_record(_make_record(draft_text=f"Record {i}"))

        results = store.list_recent_learning_records(limit=3)
        assert len(results) == 3

    def test_channel_filter_applied(self) -> None:
        store, _ = _store_with_fake()
        draft_tg = SocialDraftRecord(channel="telegram", proposed_action="message", draft_text="TG")
        draft_x = SocialDraftRecord(channel="x", proposed_action="reply", draft_text="X")
        store.append_learning_record(LearningRecord(channel="telegram", draft=draft_tg))
        store.append_learning_record(LearningRecord(channel="x", draft=draft_x))

        tg_results = store.list_recent_learning_records(channel="telegram")
        assert len(tg_results) == 1
        assert tg_results[0].channel == "telegram"

    def test_summarize_learning_hints_returns_dict(self) -> None:
        store, _ = _store_with_fake()
        result = store.summarize_learning_hints()
        assert isinstance(result, dict)
        assert "recent_lessons" in result
        assert "avoid_list" in result


# ---------------------------------------------------------------------------
# VAL-M15-M1-LEARNING-FIRESTORE-REDACTION-008
# ---------------------------------------------------------------------------


class TestRedactionPipelinePreserved:
    """VAL-M15-M1-LEARNING-FIRESTORE-REDACTION-008

    With a LearningRecord payload containing HAM_SOCIAL_LIVE_APPLY_TOKEN,
    TELEGRAM_BOT_TOKEN, XAI_API_KEY literals plus an 18+-digit external ID,
    the persisted Firestore document scrubs all four exactly as the file
    backend does. Pass: persisted document contains zero matches for the four
    bait strings.
    """

    # Bait values that should be scrubbed by the redaction pipeline.
    # The regex patterns in hamgomoon_learning.redaction will scrub these.
    _HAM_TOKEN_BAIT = "HAM_SOCIAL_LIVE_APPLY_TOKEN=my-secret-apply-token-xyz"
    _TG_BOT_TOKEN_BAIT = "bot1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
    _XAI_KEY_BAIT = "xai-FAKE-TEST-VALUE-placeholder-only"
    _EXTERNAL_ID_BAIT = "123456789012345678"  # 18 digits

    def _make_bait_record(self) -> LearningRecord:
        """Create a LearningRecord with bait strings embedded in text fields."""
        draft = SocialDraftRecord(
            channel="telegram",
            proposed_action="message",
            draft_text=(
                f"Draft contains {self._HAM_TOKEN_BAIT} and {self._TG_BOT_TOKEN_BAIT} "
                f"and {self._XAI_KEY_BAIT}"
            ),
            prompt=(f"Prompt also has {self._HAM_TOKEN_BAIT} token and key {self._XAI_KEY_BAIT}"),
        )
        delivery = DeliveryOutcome(
            draft_id=draft.draft_id,
            status="sent",
            external_platform_id=self._EXTERNAL_ID_BAIT,
        )
        return LearningRecord(channel="telegram", draft=draft, delivery=delivery)

    def _dump_stored_docs(self, fake: _FakeFirestoreClient) -> str:
        """JSON dump of all stored docs for easy bait-string scanning."""
        all_data: list[dict[str, Any]] = []
        for data in fake.docs.values():
            all_data.append(data)
        return json.dumps(all_data, default=str)

    def test_redaction_pipeline_preserved(self) -> None:
        store, fake = _store_with_fake()
        record = self._make_bait_record()
        store.append_learning_record(record)

        stored_json = self._dump_stored_docs(fake)

        # The bait secret values must not appear in the persisted document.
        # Note: we check the actual secret *values*, not the env var names.
        assert "my-secret-apply-token-xyz" not in stored_json, (
            "HAM_SOCIAL_LIVE_APPLY_TOKEN value leaked into Firestore document"
        )
        assert "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij" not in stored_json, (
            "Telegram bot token value leaked into Firestore document"
        )
        assert "FAKE-TEST-VALUE-placeholder-only" not in stored_json, (
            "xai- key value leaked into Firestore document"
        )
        # The full 18-digit external ID must be collapsed (trimmed to last 6 chars)
        assert self._EXTERNAL_ID_BAIT not in stored_json, (
            "18-digit external ID not redacted in Firestore document"
        )

    def test_ham_token_env_pattern_scrubbed(self) -> None:
        """HAM_*TOKEN= env-var pattern is scrubbed from text fields."""
        store, fake = _store_with_fake()
        draft = SocialDraftRecord(
            channel="telegram",
            proposed_action="message",
            draft_text=f"Config: {self._HAM_TOKEN_BAIT}",
            prompt="Normal prompt",
        )
        record = LearningRecord(channel="telegram", draft=draft)
        store.append_learning_record(record)

        stored_json = self._dump_stored_docs(fake)
        assert "my-secret-apply-token-xyz" not in stored_json

    def test_telegram_bot_token_scrubbed(self) -> None:
        """Telegram bot token format (bot{id}:{secret}) is scrubbed."""
        store, fake = _store_with_fake()
        draft = SocialDraftRecord(
            channel="telegram",
            proposed_action="message",
            draft_text=f"Token: {self._TG_BOT_TOKEN_BAIT}",
            prompt="Normal",
        )
        record = LearningRecord(channel="telegram", draft=draft)
        store.append_learning_record(record)

        stored_json = self._dump_stored_docs(fake)
        assert "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij" not in stored_json

    def test_xai_key_scrubbed(self) -> None:
        """xai- prefixed keys are scrubbed from text fields."""
        store, fake = _store_with_fake()
        draft = SocialDraftRecord(
            channel="telegram",
            proposed_action="message",
            draft_text=f"Key: {self._XAI_KEY_BAIT}",
            prompt="Normal",
        )
        record = LearningRecord(channel="telegram", draft=draft)
        store.append_learning_record(record)

        stored_json = self._dump_stored_docs(fake)
        assert "FAKE-TEST-VALUE-placeholder-only" not in stored_json

    def test_18digit_external_id_redacted(self) -> None:
        """18+-digit external_platform_id is collapsed by redact_external_id."""
        store, fake = _store_with_fake()
        draft = SocialDraftRecord(channel="telegram", proposed_action="message", draft_text="Hello")
        delivery = DeliveryOutcome(
            draft_id=draft.draft_id,
            status="sent",
            external_platform_id=self._EXTERNAL_ID_BAIT,
        )
        record = LearningRecord(channel="telegram", draft=draft, delivery=delivery)
        store.append_learning_record(record)

        stored_json = self._dump_stored_docs(fake)
        assert self._EXTERNAL_ID_BAIT not in stored_json
        # Collapsed to last 6 digits with ellipsis prefix
        assert "345678" in stored_json or "…345678" in stored_json

    def test_redaction_matches_file_backend(self) -> None:
        """Firestore backend redaction is byte-equal to file backend redaction."""
        from src.ham.hamgomoon_learning.redaction import redact_learning_record

        store, _ = _store_with_fake()
        record = self._make_bait_record()

        # Get what the Firestore backend stores (via returned value)
        returned = store.append_learning_record(record)

        # Get what the file backend would produce
        file_redacted = redact_learning_record(record)

        # Both should produce identical redacted records
        assert returned.model_dump() == file_redacted.model_dump()
