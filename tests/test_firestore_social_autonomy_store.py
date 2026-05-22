"""Firestore-backed social autonomy profile store tests.

Covers:
- VAL-M15-M1-PROFILE-FIRESTORE-ROUNDTRIP-001: apply then read round-trip
- VAL-M15-M1-PROFILE-FIRESTORE-TRANSACTION-002: transactional read-modify-write
- VAL-M15-M1-PROFILE-FIRESTORE-AUDIT-003: audit subcollection written on apply
- VAL-M15-M1-PROFILE-FIRESTORE-BACKUP-004: backup subcollection on overwrite
- VAL-M15-M1-PROFILE-FIRESTORE-LEGACY-LOAD-029: legacy profile docs deserialize cleanly
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from src.ham.social_autonomy.firestore_store import (
    FirestoreSocialAutonomyStore,
    FirestoreSocialAutonomyStoreError,
)
from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import (
    revision_for_profile,
)

# ---------------------------------------------------------------------------
# Minimal fake Firestore client with transaction recorder
# ---------------------------------------------------------------------------


@dataclass
class _TxRecord:
    """Records operations within a single transaction for assertion."""

    gets: list[str] = field(default_factory=list)
    sets: list[str] = field(default_factory=list)
    begun: bool = False
    committed: bool = False


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
class _FakeTransaction:
    root: _FakeFirestoreClient
    record: _TxRecord
    _begun: bool = False

    @property
    def in_progress(self) -> bool:
        return self._begun

    def _begin(self, retry_id: Any = None) -> None:  # noqa: ARG002
        self._begun = True
        self.record.begun = True

    def set(self, doc_ref: _FakeDocRef, data: dict[str, Any]) -> None:
        if not self._begun:
            msg = "Transaction not begun; cannot set."
            raise ValueError(msg)
        self.record.sets.append(doc_ref.path)
        doc_ref.root.docs[doc_ref.path] = dict(data)

    def _commit(self) -> list:
        self._begun = False
        self.record.committed = True
        return []

    def _rollback(self) -> None:
        self._begun = False


@dataclass
class _FakeDocRef:
    root: _FakeFirestoreClient
    path: str  # e.g. "ham_social_autonomy_profiles/goham-social-default"

    @property
    def id(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    def get(self, transaction: _FakeTransaction | None = None) -> _FakeDocSnap:
        if transaction is not None:
            transaction.record.gets.append(self.path)
        data = self.root.docs.get(self.path)
        return _FakeDocSnap(id=self.id, _data=dict(data) if data is not None else None)

    def set(self, data: dict[str, Any]) -> None:
        # Out-of-band write (not within a transaction)
        self.root.out_of_band_writes.append(self.path)
        self.root.docs[self.path] = dict(data)

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self.root, f"{self.path}/{name}")


@dataclass
class _FakeCollection:
    root: _FakeFirestoreClient
    prefix: str  # e.g. "ham_social_autonomy_profiles"

    def document(self, doc_id: str) -> _FakeDocRef:
        return _FakeDocRef(self.root, f"{self.prefix}/{doc_id}")

    def stream(self) -> list[_FakeDocSnap]:
        sep = self.prefix + "/"
        for path, data in list(self.root.docs.items()):
            if not path.startswith(sep):
                continue
            rest = path[len(sep):]
            if "/" not in rest:
                yield _FakeDocSnap(id=rest, _data=dict(data))


class _FakeFirestoreClient:
    """In-memory Firestore client that records transactions for assertions."""

    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}
        self.transaction_count: int = 0
        self.tx_records: list[_TxRecord] = []
        self.out_of_band_writes: list[str] = []

    def transaction(self) -> _FakeTransaction:
        self.transaction_count += 1
        record = _TxRecord()
        self.tx_records.append(record)
        return _FakeTransaction(self, record)

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self, name)


# ---------------------------------------------------------------------------
# Helper: build a minimal valid profile payload
# ---------------------------------------------------------------------------

_DEFAULT_PROFILE_ID = "goham-social-default"


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    created_at = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    payload: dict[str, Any] = {
        "profile_id": _DEFAULT_PROFILE_ID,
        "status": "draft",
        "goal": "Test Firestore store.",
        "persona_id": "ham-canonical",
        "channels": {
            "x": {"enabled": False, "available": True},
            "telegram": {"enabled": False, "available": True},
            "discord": {"enabled": False, "available": False},
        },
        "actions_allowed_per_channel": {
            "x": ["reply"],
            "telegram": ["message"],
            "discord": [],
        },
        "daily_caps": {"x": 1, "telegram": 1, "discord": 0},
        "cadence": "manual",
        "quiet_hours": None,
        "forbidden_topics": [],
        "safety_rules": ["credential_request"],
        "learning_enabled": True,
        "emergency_stop": False,
        "created_at": created_at,
        "updated_at": created_at,
    }
    payload.update(overrides)
    return payload


def _profile(**overrides: Any) -> GoHamSocialProfile:
    return GoHamSocialProfile.model_validate(_profile_payload(**overrides))


def _store_with_fake() -> tuple[FirestoreSocialAutonomyStore, _FakeFirestoreClient]:
    fake = _FakeFirestoreClient()
    store = FirestoreSocialAutonomyStore(client=fake)
    return store, fake


# ---------------------------------------------------------------------------
# VAL-M15-M1-PROFILE-FIRESTORE-ROUNDTRIP-001
# ---------------------------------------------------------------------------


class TestApplyThenReadRoundtrip:
    """VAL-M15-M1-PROFILE-FIRESTORE-ROUNDTRIP-001"""

    def test_apply_then_read_roundtrip(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """apply(...) writes to Firestore; read(...) returns the same profile."""
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", "test-write-token")  # noqa: S106

        store, fake = _store_with_fake()
        profile = _profile(goal="Round-trip test")

        result = store.apply(None, profile, token="test-write-token", actor="test")
        assert result.effective_after["goal"] == "Round-trip test"
        assert result.new_revision == revision_for_profile(profile)

        # Verify the document was written at the expected collection path
        doc_path = f"ham_social_autonomy_profiles/{_DEFAULT_PROFILE_ID}"
        assert doc_path in fake.docs, f"Document not found at {doc_path}"

        stored = fake.docs[doc_path]
        assert stored == profile.model_dump(mode="json"), (
            "Stored payload does not equal profile.model_dump(mode='json')"
        )

        # read() returns the same profile
        recovered = store.read(None)
        assert isinstance(recovered, GoHamSocialProfile)
        assert recovered.profile_id == _DEFAULT_PROFILE_ID
        assert revision_for_profile(recovered) == revision_for_profile(profile), (
            "read() did not return the same profile revision as was applied"
        )

    def test_read_returns_default_when_collection_empty(self) -> None:
        """read() returns a default draft when no document exists."""
        store, _ = _store_with_fake()
        profile = store.read(None)
        assert isinstance(profile, GoHamSocialProfile)
        assert profile.status == "draft"


# ---------------------------------------------------------------------------
# VAL-M15-M1-PROFILE-FIRESTORE-TRANSACTION-002
# ---------------------------------------------------------------------------


class TestTransactionalReadModifyWrite:
    """VAL-M15-M1-PROFILE-FIRESTORE-TRANSACTION-002"""

    def test_apply_uses_transactional_read_modify_write(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """apply() uses db.transaction(): recorder shows {transactions:1, gets>=1, sets:1, no out-of-band writes on main doc}."""
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", "test-write-token")  # noqa: S106

        store, fake = _store_with_fake()
        profile = _profile()

        store.apply(None, profile, token="test-write-token", actor="test")

        # Exactly one transaction was initiated
        assert fake.transaction_count == 1, (
            f"Expected 1 transaction; got {fake.transaction_count}"
        )

        tx = fake.tx_records[0]
        # At least one get within the transaction (the main document read)
        main_doc_path = f"ham_social_autonomy_profiles/{_DEFAULT_PROFILE_ID}"
        assert any(main_doc_path in g for g in tx.gets), (
            f"Expected a get of {main_doc_path!r} in transaction; got {tx.gets}"
        )
        # Exactly one set within the transaction (the main document write)
        assert main_doc_path in tx.sets, (
            f"Expected main doc set within transaction; got {tx.sets}"
        )
        assert tx.sets.count(main_doc_path) == 1, (
            f"Expected exactly 1 set of main doc in transaction; got {tx.sets}"
        )
        # No out-of-band writes to the MAIN document (outside the transaction)
        assert main_doc_path not in fake.out_of_band_writes, (
            f"Main document was written outside the transaction: {fake.out_of_band_writes}"
        )

    def test_concurrent_applies_serialize_via_transaction(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Each apply() call uses exactly one transaction; second call reads updated state."""
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", "test-write-token")  # noqa: S106

        store, fake = _store_with_fake()
        p1 = _profile(goal="First apply")
        p2 = _profile(
            goal="Second apply",
            updated_at=datetime(2026, 5, 21, 12, 0, tzinfo=UTC),
        )

        store.apply(None, p1, token="test-write-token", actor="actor1")
        store.apply(None, p2, token="test-write-token", actor="actor2")

        assert fake.transaction_count == 2, (
            f"Expected 2 transactions (one per apply); got {fake.transaction_count}"
        )
        # After both applies, the last state is p2
        recovered = store.read(None)
        assert recovered.goal == "Second apply"


# ---------------------------------------------------------------------------
# VAL-M15-M1-PROFILE-FIRESTORE-AUDIT-003
# ---------------------------------------------------------------------------


class TestApplyWritesAuditSubdoc:
    """VAL-M15-M1-PROFILE-FIRESTORE-AUDIT-003"""

    def test_apply_writes_audit_subdoc(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """After apply(), exactly one document is written to the _audit subcollection."""
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", "test-write-token")  # noqa: S106

        store, fake = _store_with_fake()
        profile = _profile()

        result = store.apply(None, profile, token="test-write-token", actor="test-actor")

        audit_id = result.audit_id
        audit_path = f"ham_social_autonomy_profiles/{_DEFAULT_PROFILE_ID}/_audit/{audit_id}"
        assert audit_path in fake.docs, (
            f"Audit document not found at {audit_path!r}"
        )

        audit_doc = fake.docs[audit_path]
        # Verify required fields
        assert audit_doc["audit_id"] == audit_id
        assert audit_doc["op"] == "apply"
        assert "timestamp" in audit_doc
        assert audit_doc["actor"] == "test-actor"
        assert "before_digest" in audit_doc
        assert "after_digest" in audit_doc
        assert "before" in audit_doc
        assert "after" in audit_doc

    def test_audit_after_digest_matches_applied_profile(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Audit after_digest matches the applied profile's canonical bytes digest."""
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", "test-write-token")  # noqa: S106

        store, fake = _store_with_fake()
        profile = _profile()
        expected_revision = revision_for_profile(profile)

        result = store.apply(None, profile, token="test-write-token", actor="test")
        audit_path = (
            f"ham_social_autonomy_profiles/{_DEFAULT_PROFILE_ID}/_audit/{result.audit_id}"
        )
        audit_doc = fake.docs[audit_path]
        assert audit_doc["after_digest"] == expected_revision


# ---------------------------------------------------------------------------
# VAL-M15-M1-PROFILE-FIRESTORE-BACKUP-004
# ---------------------------------------------------------------------------


class TestApplyWritesBackupOnOverwrite:
    """VAL-M15-M1-PROFILE-FIRESTORE-BACKUP-004"""

    def test_first_apply_no_backup(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """First apply (no prior document) creates no backup."""
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", "test-write-token")  # noqa: S106

        store, fake = _store_with_fake()
        profile = _profile()

        result = store.apply(None, profile, token="test-write-token", actor="test")
        assert result.backup_id is None, "First apply should not create a backup"

        backup_prefix = f"ham_social_autonomy_profiles/{_DEFAULT_PROFILE_ID}/_backups/"
        backup_docs = [p for p in fake.docs if p.startswith(backup_prefix)]
        assert len(backup_docs) == 0, f"Unexpected backup docs: {backup_docs}"

    def test_apply_writes_backup_on_overwrite(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Second apply writes the prior document to the _backups subcollection."""
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", "test-write-token")  # noqa: S106

        store, fake = _store_with_fake()

        # First apply: initial profile
        p1 = _profile(goal="Initial profile")
        initial_revision = revision_for_profile(p1)
        store.apply(None, p1, token="test-write-token", actor="test")

        # Second apply: updated profile
        p2 = _profile(
            goal="Updated profile",
            updated_at=datetime(2026, 5, 21, 12, 0, tzinfo=UTC),
        )
        result2 = store.apply(None, p2, token="test-write-token", actor="test")

        # Backup should be created
        assert result2.backup_id is not None, (
            "Second apply on existing document should create a backup"
        )

        # Backup document should exist
        backup_path = (
            f"ham_social_autonomy_profiles/{_DEFAULT_PROFILE_ID}"
            f"/_backups/{result2.backup_id}"
        )
        assert backup_path in fake.docs, (
            f"Backup document not found at {backup_path!r}"
        )

        # Backup content should equal the pre-apply canonical bytes
        backup_data = fake.docs[backup_path]
        backup_profile = GoHamSocialProfile.model_validate(backup_data)
        backup_revision = revision_for_profile(backup_profile)
        assert backup_revision == initial_revision, (
            f"Backup revision {backup_revision!r} does not match "
            f"initial revision {initial_revision!r}"
        )

    def test_audit_references_backup_id(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Audit envelope's backup_id references the backup document."""
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", "test-write-token")  # noqa: S106

        store, fake = _store_with_fake()
        p1 = _profile(goal="First")
        store.apply(None, p1, token="test-write-token", actor="test")

        p2 = _profile(
            goal="Second",
            updated_at=datetime(2026, 5, 21, 12, 0, tzinfo=UTC),
        )
        result2 = store.apply(None, p2, token="test-write-token", actor="test")

        audit_path = (
            f"ham_social_autonomy_profiles/{_DEFAULT_PROFILE_ID}"
            f"/_audit/{result2.audit_id}"
        )
        audit_doc = fake.docs[audit_path]
        assert audit_doc["backup_id"] == result2.backup_id


# ---------------------------------------------------------------------------
# VAL-M15-M1-PROFILE-FIRESTORE-LEGACY-LOAD-029
# ---------------------------------------------------------------------------


class TestLegacyPayloadLoadsWithDefaults:
    """VAL-M15-M1-PROFILE-FIRESTORE-LEGACY-LOAD-029"""

    def test_legacy_payload_loads_with_defaults(self) -> None:
        """A stored doc without new M2 fields loads cleanly via model_validate."""
        store, fake = _store_with_fake()

        # Pre-seed with a legacy-style payload (missing optional fields, old cadence value)
        created_at = "2026-01-01T00:00:00+00:00"
        legacy_payload: dict[str, Any] = {
            "profile_id": _DEFAULT_PROFILE_ID,
            "status": "draft",
            "goal": "Legacy profile",
            "persona_id": "ham-canonical",
            "channels": {
                "x": {"enabled": False, "available": True},
                "telegram": {"enabled": False, "available": True},
                "discord": {"enabled": False, "available": False},
            },
            "actions_allowed_per_channel": {
                "x": ["reply"],
                "telegram": ["message"],
                "discord": [],
            },
            "daily_caps": {"x": 0, "telegram": 0, "discord": 0},
            # Free-form cadence value predating the M2 enum
            "cadence": "daily_frequency_legacy_v1",
            "forbidden_topics": [],
            "safety_rules": ["credential_request"],
            "learning_enabled": True,
            "emergency_stop": False,
            "created_at": created_at,
            "updated_at": created_at,
            # Missing optional fields: quiet_hours, last_run_at, next_run_at, last_tick_summary
            # These should use Pydantic defaults (None)
        }

        # Pre-seed the fake Firestore client
        doc_path = f"ham_social_autonomy_profiles/{_DEFAULT_PROFILE_ID}"
        fake.docs[doc_path] = legacy_payload

        # Should not raise ValidationError
        profile = store.read(None)
        assert isinstance(profile, GoHamSocialProfile)
        assert profile.profile_id == _DEFAULT_PROFILE_ID
        # Optional fields default to None
        assert profile.quiet_hours is None
        assert profile.last_run_at is None
        assert profile.last_tick_summary is None
        # Legacy cadence value is preserved as-is (M2's validator normalizes to "manual")
        assert profile.cadence == "daily_frequency_legacy_v1"

    def test_legacy_payload_missing_optional_fields(self) -> None:
        """Profile stored without workspace_id/project_id loads with None defaults."""
        store, fake = _store_with_fake()

        created_at = "2026-01-01T00:00:00+00:00"
        legacy_payload: dict[str, Any] = {
            "profile_id": _DEFAULT_PROFILE_ID,
            "status": "draft",
            "goal": "Minimal legacy profile",
            "persona_id": "ham-canonical",
            "channels": {
                "x": {"enabled": False, "available": True},
                "telegram": {"enabled": False, "available": True},
                "discord": {"enabled": False, "available": False},
            },
            "actions_allowed_per_channel": {
                "x": ["reply"],
                "telegram": ["message"],
                "discord": [],
            },
            "daily_caps": {"x": 0, "telegram": 0, "discord": 0},
            "cadence": "manual",
            "forbidden_topics": [],
            "safety_rules": [],
            "learning_enabled": False,
            "emergency_stop": False,
            "created_at": created_at,
            "updated_at": created_at,
            # workspace_id and project_id are absent — should default to None
        }

        doc_path = f"ham_social_autonomy_profiles/{_DEFAULT_PROFILE_ID}"
        fake.docs[doc_path] = legacy_payload

        profile = store.read(None)
        assert profile.workspace_id is None
        assert profile.project_id is None


# ---------------------------------------------------------------------------
# VAL-M15-M1B-PROFILE-SINGLETON-PATH-001
# ---------------------------------------------------------------------------


class TestSingletonPathInvariant:
    """VAL-M15-M1B-PROFILE-SINGLETON-PATH-001

    Verifies that _apply_profile always writes to _SINGLETON_DOC_ID,
    regardless of profile.profile_id.  After applying a profile with an
    alternate profile_id, read() must return the same applied profile bytes
    — not a default draft.
    """

    def test_singleton_path_with_alt_profile_id(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """apply() with alt profile_id writes to _SINGLETON_DOC_ID; read() returns the same profile."""
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", "test-write-token")  # noqa: S106

        store, fake = _store_with_fake()

        # Use a profile_id that differs from the singleton doc id
        alt_id = "alt-id"
        profile = _profile(profile_id=alt_id, goal="Alt-id profile")

        result = store.apply(None, profile, token="test-write-token", actor="test")

        # The document must be written at the singleton path, not the alt-id path
        singleton_path = "ham_social_autonomy_profiles/goham-social-default"
        alt_path = f"ham_social_autonomy_profiles/{alt_id}"

        assert singleton_path in fake.docs, (
            f"Profile was NOT written to singleton path {singleton_path!r}; "
            f"docs present: {list(fake.docs.keys())}"
        )
        assert alt_path not in fake.docs, (
            f"Profile was incorrectly written to alt path {alt_path!r} — "
            "write must always target _SINGLETON_DOC_ID"
        )

        # read() must return the applied profile bytes (not a default draft)
        recovered = store.read(None)
        assert isinstance(recovered, GoHamSocialProfile)
        assert recovered.goal == "Alt-id profile", (
            f"read() returned goal={recovered.goal!r}; "
            "expected the applied profile, not the default draft"
        )
        assert recovered.status != "draft" or profile.status == "draft", (
            "read() returned a default draft instead of the applied profile"
        )

        # Revision must match what was applied
        assert result.new_revision == revision_for_profile(profile), (
            "apply() result revision does not match the applied profile"
        )

    def test_apply_doc_path_is_always_singleton_for_any_profile_id(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The Firestore document path written by apply() is _SINGLETON_DOC_ID regardless of profile.profile_id."""
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", "test-write-token")  # noqa: S106

        store, fake = _store_with_fake()
        profile = _profile(profile_id="some-other-id", goal="Path invariant test")

        store.apply(None, profile, token="test-write-token", actor="test")

        # Collect all top-level document paths (not subcollections) in the profile collection
        top_level_docs = [
            path
            for path in fake.docs
            if path.startswith("ham_social_autonomy_profiles/")
            and path.count("/") == 1  # top-level docs only
        ]
        assert top_level_docs == ["ham_social_autonomy_profiles/goham-social-default"], (
            f"Expected only the singleton doc to be written; got: {top_level_docs}"
        )


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestFirestoreErrorHandling:
    """Error paths and exception propagation."""

    def test_read_propagates_firestore_error(self) -> None:
        """read() raises FirestoreSocialAutonomyStoreError on Firestore SDK failures."""

        class _ErrorDocRef:
            @property
            def path(self) -> str:
                return "ham_social_autonomy_profiles/goham-social-default"

            def get(self, transaction: Any = None) -> None:
                raise RuntimeError("Simulated Firestore SDK error")

            def collection(self, name: str) -> Any:
                return _ErrorDocRef()

            def document(self, doc_id: str) -> _ErrorDocRef:
                return _ErrorDocRef()

            def set(self, data: Any) -> None:
                raise RuntimeError("Simulated Firestore SDK error")

        class _ErrorCollection:
            def document(self, doc_id: str) -> _ErrorDocRef:
                return _ErrorDocRef()

        class _ErrorClient:
            def collection(self, name: str) -> _ErrorCollection:
                return _ErrorCollection()

            def transaction(self) -> Any:
                raise RuntimeError("Simulated Firestore SDK error")

        store = FirestoreSocialAutonomyStore(client=_ErrorClient())

        with pytest.raises(FirestoreSocialAutonomyStoreError):
            store.read(None)

    def test_apply_propagates_firestore_transaction_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """apply() raises FirestoreSocialAutonomyStoreError when transaction fails."""
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", "test-write-token")  # noqa: S106

        class _FailTxDocRef:
            @property
            def path(self) -> str:
                return "ham_social_autonomy_profiles/goham-social-default"

            def get(self, transaction: Any = None) -> None:
                raise RuntimeError("Simulated transaction error")

            def collection(self, name: str) -> Any:
                return _FailTxDocRef()

            def document(self, doc_id: str) -> _FailTxDocRef:
                return _FailTxDocRef()

            def set(self, data: Any) -> None:
                raise RuntimeError("Simulated error")

        class _FailTxTransaction:
            @property
            def in_progress(self) -> bool:
                return True

            def _begin(self, retry_id: Any = None) -> None:
                pass

            def set(self, ref: Any, data: Any) -> None:
                raise RuntimeError("Simulated transaction error")

            def _commit(self) -> list:
                return []

            def _rollback(self) -> None:
                pass

        class _FailTxCollection:
            def document(self, doc_id: str) -> _FailTxDocRef:
                return _FailTxDocRef()

        class _FailTxClient:
            def collection(self, name: str) -> _FailTxCollection:
                return _FailTxCollection()

            def transaction(self) -> _FailTxTransaction:
                return _FailTxTransaction()

        store = FirestoreSocialAutonomyStore(client=_FailTxClient())

        with pytest.raises(FirestoreSocialAutonomyStoreError):
            store.apply(None, _profile(), token="test-write-token", actor="test")
