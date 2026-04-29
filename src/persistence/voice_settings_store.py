"""Persistence for HAM voice settings (local JSON or Firestore), scoped per tenant key."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from google.cloud import firestore

logger = logging.getLogger(__name__)


def _scope_doc_id(scope_key: str) -> str:
    """Stable Firestore-safe document id (avoid raw ':' in ids for readability issues)."""
    h = hashlib.sha256(scope_key.encode("utf-8")).hexdigest()
    return f"v_{h}"


@runtime_checkable
class VoiceSettingsStore(Protocol):
    def get_raw(self, scope_key: str) -> dict[str, Any] | None: ...
    def put_raw(self, scope_key: str, data: dict[str, Any]) -> None: ...


class LocalJsonVoiceSettingsStore:
    """
    One JSON file per scope under a directory (default: workspace ``.ham/workspace_state/voice_settings``).
    Env: ``HAM_VOICE_SETTINGS_LOCAL_PATH`` — if set to a **directory**, files are ``{scope_hash}.json``;
    if set to a **.json file**, only ``scope_key=default`` uses that file (single-tenant dev).
    """

    def __init__(self, base: Path) -> None:
        self._base = base
        self._single_file: Path | None = None
        if base.suffix.lower() == ".json":
            self._single_file = base
            self._base.parent.mkdir(parents=True, exist_ok=True)
        else:
            self._base.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path_for(self, scope_key: str) -> Path:
        if self._single_file is not None:
            return self._single_file
        return self._base / f"{_scope_doc_id(scope_key)}.json"

    def get_raw(self, scope_key: str) -> dict[str, Any] | None:
        p = self._path_for(scope_key)
        if not p.is_file():
            return None
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else None
        except (OSError, json.JSONDecodeError):
            logger.warning("voice settings local read failed: %s", p)
            return None

    def put_raw(self, scope_key: str, data: dict[str, Any]) -> None:
        p = self._path_for(scope_key)
        tmp = p.with_suffix(".tmp")
        blob = json.dumps(data, indent=2, sort_keys=True)
        with self._lock:
            tmp.write_text(blob, encoding="utf-8")
            tmp.replace(p)


class FirestoreVoiceSettingsStore:
    """Document ``{collection}/{doc_id}`` with fields ``settings`` (map), ``scope_key`` (debug)."""

    def __init__(
        self,
        collection: str,
        *,
        project: str | None = None,
        database: str | None = None,
        client: firestore.Client | None = None,
    ) -> None:
        self._coll_name = (collection or "ham_voice_settings").strip() or "ham_voice_settings"
        self._lock = threading.Lock()
        if client is not None:
            self._db = client
        else:
            kwargs: dict[str, Any] = {}
            if project:
                kwargs["project"] = project
            if database:
                kwargs["database"] = database
            self._db = firestore.Client(**kwargs) if kwargs else firestore.Client()

    def _coll(self) -> firestore.CollectionReference:
        return self._db.collection(self._coll_name)

    def get_raw(self, scope_key: str) -> dict[str, Any] | None:
        doc_id = _scope_doc_id(scope_key)
        snap = self._coll().document(doc_id).get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        inner = data.get("settings")
        return inner if isinstance(inner, dict) else None

    def put_raw(self, scope_key: str, data: dict[str, Any]) -> None:
        doc_id = _scope_doc_id(scope_key)
        with self._lock:
            self._coll().document(doc_id).set(
                {"scope_key": scope_key, "settings": data},
                merge=True,
            )


def _workspace_root_default() -> Path:
    raw = (os.environ.get("HAM_WORKSPACE_ROOT") or "").strip() or (os.environ.get("HAM_WORKSPACE_FILES_ROOT") or "").strip()
    if raw:
        p = Path(raw).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    repo = Path(__file__).resolve().parent.parent.parent
    d = repo / ".ham_workspace_sandbox"
    d.mkdir(parents=True, exist_ok=True)
    return d.resolve()


def _local_base_path() -> Path:
    raw = (os.environ.get("HAM_VOICE_SETTINGS_LOCAL_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    root = _workspace_root_default()
    return (root / ".ham" / "workspace_state" / "voice_settings").resolve()


def build_voice_settings_store() -> VoiceSettingsStore:
    mode = (os.environ.get("HAM_VOICE_SETTINGS_STORE") or "local").strip().lower()
    if mode == "firestore":
        coll = (os.environ.get("HAM_VOICE_SETTINGS_FIRESTORE_COLLECTION") or "ham_voice_settings").strip()
        proj = (os.environ.get("HAM_VOICE_SETTINGS_FIRESTORE_PROJECT") or "").strip() or None
        database = (os.environ.get("HAM_VOICE_SETTINGS_FIRESTORE_DATABASE") or "").strip() or None
        return FirestoreVoiceSettingsStore(coll, project=proj, database=database)
    return LocalJsonVoiceSettingsStore(_local_base_path())
