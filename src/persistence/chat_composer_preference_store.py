"""Persistence for per-user, per-workspace chat composer model preference (HAM catalog model_id only)."""

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
    h = hashlib.sha256(scope_key.encode("utf-8")).hexdigest()
    return f"c_{h}"


@runtime_checkable
class ChatComposerPreferenceStore(Protocol):
    def get_raw(self, scope_key: str) -> dict[str, Any] | None: ...
    def put_raw(self, scope_key: str, data: dict[str, Any]) -> None: ...


class LocalJsonChatComposerPreferenceStore:
    """One JSON file per (user, workspace) scope under a directory."""

    def __init__(self, base: Path) -> None:
        self._base = base
        self._lock = threading.Lock()
        self._base.mkdir(parents=True, exist_ok=True)

    def _path_for(self, scope_key: str) -> Path:
        return self._base / f"{_scope_doc_id(scope_key)}.json"

    def get_raw(self, scope_key: str) -> dict[str, Any] | None:
        p = self._path_for(scope_key)
        if not p.is_file():
            return None
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else None
        except (OSError, json.JSONDecodeError):
            logger.warning("chat composer preference local read failed: %s", p)
            return None

    def put_raw(self, scope_key: str, data: dict[str, Any]) -> None:
        p = self._path_for(scope_key)
        tmp = p.with_suffix(".tmp")
        blob = json.dumps(data, indent=2, sort_keys=True)
        with self._lock:
            tmp.write_text(blob, encoding="utf-8")
            tmp.replace(p)


class FirestoreChatComposerPreferenceStore:
    """Document with ``preference`` map + ``scope_key`` (debug only)."""

    def __init__(
        self,
        collection: str,
        *,
        project: str | None = None,
        database: str | None = None,
        client: firestore.Client | None = None,
    ) -> None:
        self._coll_name = (collection or "ham_chat_composer_preferences").strip() or (
            "ham_chat_composer_preferences"
        )
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
        inner = data.get("preference")
        return inner if isinstance(inner, dict) else None

    def put_raw(self, scope_key: str, data: dict[str, Any]) -> None:
        doc_id = _scope_doc_id(scope_key)
        with self._lock:
            self._coll().document(doc_id).set(
                {"scope_key": scope_key, "preference": data},
                merge=True,
            )


def _workspace_root_default() -> Path:
    raw = (os.environ.get("HAM_WORKSPACE_ROOT") or "").strip() or (
        os.environ.get("HAM_WORKSPACE_FILES_ROOT") or ""
    ).strip()
    if raw:
        p = Path(raw).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    repo = Path(__file__).resolve().parent.parent.parent
    d = repo / ".ham_workspace_sandbox"
    d.mkdir(parents=True, exist_ok=True)
    return d.resolve()


def _local_base_path() -> Path:
    raw = (os.environ.get("HAM_CHAT_COMPOSER_PREFS_LOCAL_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    root = _workspace_root_default()
    return (root / ".ham" / "workspace_state" / "chat_composer_preferences").resolve()


def build_chat_composer_preference_store() -> ChatComposerPreferenceStore:
    mode = (os.environ.get("HAM_CHAT_COMPOSER_PREFS_STORE") or "local").strip().lower()
    if mode == "firestore":
        coll = (
            os.environ.get("HAM_CHAT_COMPOSER_PREFS_FIRESTORE_COLLECTION") or "ham_chat_composer_preferences"
        ).strip()
        proj = (os.environ.get("HAM_CHAT_COMPOSER_PREFS_FIRESTORE_PROJECT") or "").strip() or None
        database = (os.environ.get("HAM_CHAT_COMPOSER_PREFS_FIRESTORE_DATABASE") or "").strip() or None
        return FirestoreChatComposerPreferenceStore(coll, project=proj, database=database)
    return LocalJsonChatComposerPreferenceStore(_local_base_path())


def preference_scope_key(*, user_id: str, workspace_id: str) -> str:
    return f"user:{user_id.strip()}:workspace:{workspace_id.strip()}"
