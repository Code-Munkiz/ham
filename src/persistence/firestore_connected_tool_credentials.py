"""Firestore-backed Connected Tools credentials — encrypted at rest (operator key)."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_LOG = logging.getLogger(__name__)

_FIRESTORE_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FIRESTORE_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"
_COLLECTION = "connected_tool_credentials"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sanitize_doc_token(s: str, *, max_len: int = 480) -> str:
    t = (s or "").strip().replace("/", "_").replace(" ", "_")
    t = re.sub(r"[^a-zA-Z0-9._:-]+", "_", t)
    return t[:max_len]


def document_id_for(owner_type: str, owner_id: str, tool_id: str) -> str:
    ot = _sanitize_doc_token(owner_type, max_len=48)
    oid = _sanitize_doc_token(owner_id, max_len=400)
    tid = _sanitize_doc_token(tool_id, max_len=64)
    return f"{ot}__{oid}__{tid}"


class FirestoreCredentialStoreError(RuntimeError):
    """Non-specific failure surfaced to callers (never includes secrets)."""

    pass


@dataclass
class StoredConnectedToolCredential:
    owner_type: str
    owner_id: str
    tool_id: str
    masked_preview: str
    ciphertext: str
    encryption_version: str
    status: str


class FirestoreConnectedToolCredentialStore:
    """Firestore document store keyed by deterministic doc IDs."""

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._project = (project or os.environ.get(_FIRESTORE_PROJECT_ENV) or "").strip() or None
        self._database = (database or os.environ.get(_FIRESTORE_DATABASE_ENV) or "").strip() or None
        self._client = client

    def _db(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.cloud import firestore  # noqa: PLC0415
        except ImportError as exc:
            raise FirestoreCredentialStoreError(
                "google-cloud-firestore is required for Firestore Connected Tools credentials."
            ) from exc

        kwargs: dict[str, Any] = {}
        if self._project:
            kwargs["project"] = self._project
        if self._database:
            kwargs["database"] = self._database

        client = firestore.Client(**kwargs) if kwargs else firestore.Client()
        self._client = client
        return client

    def _collection(self) -> Any:
        db = self._db()
        return db.collection(_COLLECTION)

    def get_record(
        self,
        *,
        owner_type: str,
        owner_id: str,
        tool_id: str,
    ) -> StoredConnectedToolCredential | None:
        doc_id = document_id_for(owner_type, owner_id, tool_id)
        snap = self._collection().document(doc_id).get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        if not isinstance(data, dict):
            return None

        ciphertext = data.get("ciphertext")
        if not isinstance(ciphertext, str) or not ciphertext.strip():
            raise FirestoreCredentialStoreError("credential document missing ciphertext.")

        masked = data.get("masked_preview")
        if not isinstance(masked, str):
            masked = ""

        encryption_version = data.get("encryption_version")
        if not isinstance(encryption_version, str) or not encryption_version.strip():
            raise FirestoreCredentialStoreError("credential document missing encryption_version.")

        status_raw = data.get("status") or "on"
        status = status_raw if isinstance(status_raw, str) else str(status_raw)

        return StoredConnectedToolCredential(
            owner_type=str(data.get("owner_type") or owner_type),
            owner_id=str(data.get("owner_id") or owner_id),
            tool_id=str(data.get("tool_id") or tool_id),
            masked_preview=masked,
            ciphertext=ciphertext.strip(),
            encryption_version=encryption_version.strip(),
            status=status,
        )

    def upsert_record(
        self,
        *,
        owner_type: str,
        owner_id: str,
        tool_id: str,
        ciphertext: str,
        encryption_version: str,
        masked_preview: str,
        status: str,
        acting_user_id: str,
        now_iso: str | None = None,
    ) -> None:
        ts = now_iso or _utc_now_iso()
        doc_id = document_id_for(owner_type, owner_id, tool_id)
        ref = self._collection().document(doc_id)
        snap = ref.get()
        prior = snap.to_dict() if snap.exists else None
        created_at = ts
        if isinstance(prior, dict) and isinstance(prior.get("created_at"), str):
            created_at = prior["created_at"]

        payload = {
            "owner_type": owner_type,
            "owner_id": owner_id,
            "tool_id": tool_id,
            "ciphertext": ciphertext,
            "encryption_version": encryption_version,
            "masked_preview": masked_preview,
            "status": status,
            "created_at": created_at,
            "updated_at": ts,
            "created_by": acting_user_id,
            "updated_by": acting_user_id,
        }
        try:
            ref.set(payload, merge=False)
        except Exception as exc:
            _LOG.warning("Firestore credential upsert failed: %s", type(exc).__name__)
            raise FirestoreCredentialStoreError("Could not save Connected Tools credential.") from exc

    def delete_record(
        self,
        *,
        owner_type: str,
        owner_id: str,
        tool_id: str,
    ) -> bool:
        doc_id = document_id_for(owner_type, owner_id, tool_id)
        ref = self._collection().document(doc_id)
        try:
            snap = ref.get()
            if not snap.exists:
                return False
            ref.delete()
            return True
        except Exception as exc:
            _LOG.warning("Firestore credential delete failed: %s", type(exc).__name__)
            raise FirestoreCredentialStoreError(
                "Could not remove Connected Tools credential."
            ) from exc
