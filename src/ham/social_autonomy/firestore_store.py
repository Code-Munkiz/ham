"""Firestore-backed social autonomy profile store (M1 F2 implementation).

Implements the ``FirestoreSocialAutonomyStore`` backend for the
``SocialAutonomyStoreProtocol``. Selected by the factory in
:mod:`src.ham.social_autonomy.store` when
``HAM_SOCIAL_AUTONOMY_STORE_BACKEND=firestore``.

Collection layout::

    ham_social_autonomy_profiles/{profile_id}
    ham_social_autonomy_profiles/{profile_id}/_audit/{audit_id}
    ham_social_autonomy_profiles/{profile_id}/_backups/{backup_id}

The singleton profile is stored at ``{collection}/goham-social-default``
(``_SINGLETON_DOC_ID``), matching the default profile's ``profile_id`` field.

Transactional read-modify-write:
    The main document is written inside a Firestore transaction so that
    concurrent ``apply()`` calls serialize without losing fields.  Audit and
    backup subcollection documents are written after the transaction commits
    (append-only; they do not need atomic consistency with the main write).

Fail-closed:
    Any exception from the Firestore SDK (``_db().collection(...)...``) is
    wrapped in :class:`FirestoreSocialAutonomyStoreError` and re-raised.  The
    store **never** silently falls back to the file backend.

Legacy documents:
    Documents stored before M2 schema additions (missing optional fields,
    free-form ``cadence`` values) are loaded via ``GoHamSocialProfile.model_validate``
    which fills in Pydantic defaults for absent optional fields.  Invalid
    schemas surface as ``FirestoreSocialAutonomyStoreError``.

Per-store env-var overrides (all fall back to shared workspace vars)::

    HAM_SOCIAL_AUTONOMY_FIRESTORE_PROJECT_ID  -> HAM_FIRESTORE_PROJECT_ID
    HAM_SOCIAL_AUTONOMY_FIRESTORE_DATABASE    -> HAM_FIRESTORE_DATABASE
    HAM_SOCIAL_AUTONOMY_FIRESTORE_COLLECTION  (default ham_social_autonomy_profiles)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.ham.social_autonomy.schema import GoHamSocialProfile, profile_to_safe_dict
from src.ham.social_autonomy.store import (
    _BACKUP_ID_RE,
    ApplyResult,
    RollbackResult,
    _canonical_profile_bytes,
    _coerce_profile,
    _default_profile,
    _iso_timestamp,
    _new_id,
    _require_write_token,
    _snapshot_from_bytes,
    revision_for_bytes,
    social_autonomy_path,
    social_autonomy_writes_enabled,
)

_LOG = logging.getLogger(__name__)

_FS_PROJECT_ENV = "HAM_SOCIAL_AUTONOMY_FIRESTORE_PROJECT_ID"
_FS_DATABASE_ENV = "HAM_SOCIAL_AUTONOMY_FIRESTORE_DATABASE"
_FS_COLLECTION_ENV = "HAM_SOCIAL_AUTONOMY_FIRESTORE_COLLECTION"
_FALLBACK_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FALLBACK_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"
_DEFAULT_COLLECTION = "ham_social_autonomy_profiles"

# Singleton document ID — matches the default profile's profile_id field so
# read() and apply() are consistent without an explicit profile-id parameter.
_SINGLETON_DOC_ID = "goham-social-default"


def _resolve_env(primary: str, fallback: str | None = None) -> str | None:
    val = (os.environ.get(primary) or "").strip()
    if val:
        return val
    if fallback is not None:
        val = (os.environ.get(fallback) or "").strip()
        if val:
            return val
    return None


class FirestoreSocialAutonomyStoreError(RuntimeError):
    """Wrapper for unexpected errors from the Firestore SDK.

    Raised by every method of :class:`FirestoreSocialAutonomyStore` when the
    Firestore client raises, ensuring callers never silently swallow SDK errors
    and the API layer can convert them to structured ``503 firestore_unavailable``
    responses.
    """


class FirestoreSocialAutonomyStore:
    """Firestore-backed social autonomy profile store.

    Satisfies :class:`SocialAutonomyStoreProtocol`.

    The constructor accepts an injected ``client`` for tests; in production
    the real ``google.cloud.firestore.Client`` is constructed lazily on first
    method call so importing this module never contacts Firestore at import time.
    """

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str | None = None,
        collection: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._project = project or _resolve_env(_FS_PROJECT_ENV, _FALLBACK_PROJECT_ENV)
        self._database = database or _resolve_env(_FS_DATABASE_ENV, _FALLBACK_DATABASE_ENV)
        coll = collection or _resolve_env(_FS_COLLECTION_ENV) or _DEFAULT_COLLECTION
        self._coll_name = coll.strip() or _DEFAULT_COLLECTION
        self._client = client

    # ------------------------------------------------------------------
    # Lazy client + transaction helpers
    # ------------------------------------------------------------------

    def _db(self) -> Any:
        """Return the Firestore client, constructing it lazily when not injected."""
        if self._client is not None:
            return self._client
        try:
            from google.cloud import firestore  # noqa: PLC0415
        except ImportError as exc:
            msg = (
                "google-cloud-firestore is required when "
                "HAM_SOCIAL_AUTONOMY_STORE_BACKEND=firestore."
            )
            raise FirestoreSocialAutonomyStoreError(msg) from exc
        kwargs: dict[str, Any] = {}
        if self._project:
            kwargs["project"] = self._project
        if self._database:
            kwargs["database"] = self._database
        self._client = firestore.Client(**kwargs) if kwargs else firestore.Client()
        return self._client

    @staticmethod
    def _ensure_transaction_begun(transaction: Any) -> None:
        """Call ``_begin()`` on the transaction if not already in progress.

        ``Client.transaction()`` returns a transaction object that is **not**
        in progress until ``_begin`` is called; reads with ``transaction=...``
        require an active transaction id.  The ``@transactional`` helper does
        this implicitly; explicit use must call ``_begin`` first.  Mirrors the
        pattern in :class:`FirestoreWorkspaceStore`.
        """
        begin = getattr(transaction, "_begin", None)
        if not callable(begin):
            return
        if getattr(transaction, "in_progress", True):
            return
        begin()

    @staticmethod
    def _commit_transaction(transaction: Any) -> None:
        """Commit the transaction, preferring ``_commit`` over ``commit``."""
        commit = getattr(transaction, "_commit", None)
        if callable(commit):
            commit()
            return
        legacy = getattr(transaction, "commit", None)
        if callable(legacy):
            legacy()

    @staticmethod
    def _rollback_transaction(transaction: Any) -> None:
        """Roll back the transaction if possible."""
        rollback = getattr(transaction, "_rollback", None)
        if callable(rollback):
            rollback()
            return
        legacy = getattr(transaction, "rollback", None)
        if callable(legacy):
            legacy()

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def profile_document_exists(self, root: Path | None = None) -> bool:
        """Return whether the singleton autonomy profile document exists in Firestore.

        Args:
            root: Ignored for the Firestore backend (kept for Protocol compat).
        """
        del root
        db = self._db()
        try:
            snap = db.collection(self._coll_name).document(_SINGLETON_DOC_ID).get()
        except Exception as exc:  # noqa: BLE001
            raise FirestoreSocialAutonomyStoreError(
                f"Firestore profile existence check failed: {exc}"
            ) from exc
        return bool(getattr(snap, "exists", False))

    def read(self, root: Path | None = None) -> GoHamSocialProfile:
        """Read the persisted profile from Firestore, or return a default draft.

        Args:
            root: Ignored for the Firestore backend (kept for Protocol compat).

        Returns:
            The stored :class:`GoHamSocialProfile`, or a fresh default draft
            when no document exists.

        Raises:
            FirestoreSocialAutonomyStoreError: On any Firestore SDK error or if
                the stored document fails schema validation.
        """
        db = self._db()
        try:
            snap = db.collection(self._coll_name).document(_SINGLETON_DOC_ID).get()
        except Exception as exc:  # noqa: BLE001
            raise FirestoreSocialAutonomyStoreError(
                f"Firestore read failed: {exc}"
            ) from exc

        if not getattr(snap, "exists", False):
            return _default_profile()

        data = snap.to_dict() or {}
        try:
            return GoHamSocialProfile.model_validate(data)
        except ValidationError as exc:
            raise FirestoreSocialAutonomyStoreError(
                f"Stored profile is invalid: {exc}"
            ) from exc

    def preview(
        self,
        root: Path | None,
        candidate: GoHamSocialProfile | dict[str, Any],
    ) -> dict[str, Any]:
        """Return a normalized candidate profile dict without persisting.

        Mirrors :func:`~src.ham.social_autonomy.store.preview_social_autonomy_profile`.
        """
        profile = _coerce_profile(candidate)
        return profile_to_safe_dict(profile)

    def apply(
        self,
        root: Path | None,
        candidate: GoHamSocialProfile | dict[str, Any],
        *,
        token: str | None,
        actor: str = "system",
    ) -> ApplyResult:
        """Persist a profile atomically with an audit envelope and backup.

        Verifies ``HAM_SOCIAL_AUTONOMY_WRITE_TOKEN`` before writing. Uses a
        Firestore transaction to atomically read the current document and write
        the new one.  The backup and audit subcollection documents are written
        after the transaction commits (append-only).

        Raises:
            SocialAutonomyWriteAuthError: When the token does not match.
            FirestoreSocialAutonomyStoreError: On any Firestore SDK error.
        """
        _require_write_token(token)
        profile = _coerce_profile(candidate)
        return self._apply_profile(profile, actor=actor)

    def save(
        self,
        root: Path | None,
        profile: GoHamSocialProfile,
        *,
        actor: str = "system",
    ) -> ApplyResult:
        """Persist an internally-trusted profile mutation with audit.

        Unlike :meth:`apply`, does NOT check ``HAM_SOCIAL_AUTONOMY_WRITE_TOKEN``
        so the autonomous tick can persist state without requiring an operator
        token.  Mirrors :func:`~src.ham.social_autonomy.store.save_profile`.

        Raises:
            FirestoreSocialAutonomyStoreError: On any Firestore SDK error.
        """
        return self._apply_profile(profile, actor=actor)

    def rollback(
        self,
        root: Path | None,
        backup_id: str,
        *,
        token: str | None,
        actor: str = "system",
    ) -> RollbackResult:
        """Restore a previously captured backup byte-for-byte with audit.

        Raises:
            ValueError: When ``backup_id`` has an invalid shape.
            FileNotFoundError: When the backup document does not exist.
            SocialAutonomyWriteAuthError: When the token does not match.
            FirestoreSocialAutonomyStoreError: On any Firestore SDK error.
        """
        _require_write_token(token)
        if not _BACKUP_ID_RE.match(backup_id):
            raise ValueError("backup_id has invalid shape")

        db = self._db()
        doc_ref = db.collection(self._coll_name).document(_SINGLETON_DOC_ID)
        backup_ref = doc_ref.collection("_backups").document(backup_id)

        try:
            backup_snap = backup_ref.get()
        except Exception as exc:  # noqa: BLE001
            raise FirestoreSocialAutonomyStoreError(
                f"Firestore rollback read failed: {exc}"
            ) from exc

        if not getattr(backup_snap, "exists", False):
            raise FileNotFoundError(f"backup {backup_id!r} not found")

        backup_payload = backup_snap.to_dict() or {}
        try:
            backup_profile = GoHamSocialProfile.model_validate(backup_payload)
        except ValidationError as exc:
            raise FirestoreSocialAutonomyStoreError(
                f"Backup {backup_id!r} contains invalid profile: {exc}"
            ) from exc

        backup_raw = _canonical_profile_bytes(backup_profile)

        # Transactional read-modify-write to restore the backup
        transaction = db.transaction()
        before_raw: bytes | None = None
        try:
            self._ensure_transaction_begun(transaction)
            snapshot = doc_ref.get(transaction=transaction)
            if getattr(snapshot, "exists", False):
                before_data = snapshot.to_dict() or {}
                try:
                    before_profile = GoHamSocialProfile.model_validate(before_data)
                    before_raw = _canonical_profile_bytes(before_profile)
                except ValidationError:
                    before_raw = None
            transaction.set(doc_ref, backup_payload)
            self._commit_transaction(transaction)
        except FirestoreSocialAutonomyStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._rollback_transaction(transaction)
            raise FirestoreSocialAutonomyStoreError(
                f"rollback transaction failed: {exc}"
            ) from exc

        audit_id = _write_firestore_audit(
            doc_ref.collection("_audit"),
            op="rollback",
            actor=actor,
            before_raw=before_raw,
            after_raw=backup_raw,
            restored_from_backup_id=backup_id,
        )

        return RollbackResult(
            backup_id=backup_id,
            audit_id=audit_id,
            effective_after=profile_to_safe_dict(backup_profile),
            new_revision=revision_for_bytes(backup_raw),
        )

    def writes_enabled(self) -> bool:
        """Return whether the autonomy write token env var is configured.

        Mirrors the file backend: both backends require ``HAM_SOCIAL_AUTONOMY_WRITE_TOKEN``
        to be set for operator-facing mutations.
        """
        return social_autonomy_writes_enabled()

    def path(self, root: Path | None = None) -> Path:
        """Return the file path that the file backend would use.

        For the Firestore backend the profile is NOT stored at this path, but
        the Protocol requires returning a :class:`~pathlib.Path`.  Callers
        that check ``path().exists()`` as a "profile is configured" sentinel
        may need updating to use ``read()`` instead when the Firestore backend
        is active.
        """
        return social_autonomy_path(root)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_profile(
        self,
        profile: GoHamSocialProfile,
        *,
        actor: str,
    ) -> ApplyResult:
        """Core apply logic shared by :meth:`apply` and :meth:`save`.

        Always writes to ``_SINGLETON_DOC_ID`` regardless of
        ``profile.profile_id``, so that a subsequent :meth:`read` (which
        always reads from ``_SINGLETON_DOC_ID``) is guaranteed to return the
        applied profile even when the caller supplies a profile whose
        ``profile_id`` differs from the singleton key.
        """
        doc_id = _SINGLETON_DOC_ID  # always write to the singleton path
        db = self._db()

        doc_ref = db.collection(self._coll_name).document(doc_id)
        after_payload = profile.model_dump(mode="json")
        after_raw = _canonical_profile_bytes(profile)

        # --- Transactional read-modify-write (main document only) -------
        transaction = db.transaction()
        before_raw: bytes | None = None
        before_payload: dict[str, Any] | None = None
        try:
            self._ensure_transaction_begun(transaction)
            snapshot = doc_ref.get(transaction=transaction)
            if getattr(snapshot, "exists", False):
                before_payload = snapshot.to_dict() or {}
                try:
                    before_profile = GoHamSocialProfile.model_validate(before_payload)
                    before_raw = _canonical_profile_bytes(before_profile)
                except ValidationError:
                    # Legacy doc that doesn't fully validate — still preserve
                    # the raw stored bytes for backup/audit purposes.
                    before_raw = (
                        json.dumps(
                            before_payload, indent=2, ensure_ascii=True, sort_keys=True
                        ).encode()
                        + b"\n"
                    )
            transaction.set(doc_ref, after_payload)
            self._commit_transaction(transaction)
        except FirestoreSocialAutonomyStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._rollback_transaction(transaction)
            raise FirestoreSocialAutonomyStoreError(
                f"apply transaction failed: {exc}"
            ) from exc

        # --- Post-transaction: backup (best-effort, append-only) --------
        backup_id: str | None = None
        if before_payload is not None:
            backup_id = _new_id()
            try:
                doc_ref.collection("_backups").document(backup_id).set(before_payload)
            except Exception as exc:  # noqa: BLE001
                _LOG.warning(
                    "Failed to write backup %s for profile %s: %s",
                    backup_id,
                    doc_id,
                    exc,
                )
                backup_id = None

        # --- Post-transaction: audit (best-effort, append-only) ---------
        audit_id = _write_firestore_audit(
            doc_ref.collection("_audit"),
            op="apply",
            actor=actor,
            before_raw=before_raw,
            after_raw=after_raw,
            backup_id=backup_id,
        )

        return ApplyResult(
            backup_id=backup_id,
            audit_id=audit_id,
            effective_after=profile_to_safe_dict(profile),
            new_revision=revision_for_bytes(after_raw),
        )


# ---------------------------------------------------------------------------
# Module-level audit writer
# ---------------------------------------------------------------------------


def _write_firestore_audit(
    audit_coll: Any,
    *,
    op: str,
    actor: str,
    before_raw: bytes | None,
    after_raw: bytes | None,
    backup_id: str | None = None,
    restored_from_backup_id: str | None = None,
) -> str:
    """Write an audit envelope document to ``audit_coll`` and return the audit_id.

    Mirrors the shape of :func:`~src.ham.social_autonomy.store._write_audit_envelope`
    so that file-backend and Firestore-backend audit documents are structurally
    identical.  Write errors are logged and swallowed (audit is best-effort).
    """
    audit_id = _new_id()
    payload = {
        "audit_id": audit_id,
        "op": op,
        "timestamp": _iso_timestamp(),
        "actor": actor,
        "backup_id": backup_id,
        "restored_from_backup_id": restored_from_backup_id,
        "before_digest": revision_for_bytes(before_raw),
        "after_digest": revision_for_bytes(after_raw),
        "before": _snapshot_from_bytes(before_raw),
        "after": _snapshot_from_bytes(after_raw),
        "result": "ok",
    }
    try:
        audit_coll.document(audit_id).set(payload)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("Failed to write audit %s: %s", audit_id, exc)
    return audit_id


__all__ = [
    "FirestoreSocialAutonomyStore",
    "FirestoreSocialAutonomyStoreError",
]
