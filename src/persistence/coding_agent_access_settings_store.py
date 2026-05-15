"""Persistence for workspace-scoped coding-agent access settings.

Follows the same dual-backend (LocalJson + Firestore) pattern as
:mod:`src.persistence.chat_composer_preference_store`.

Scope: ``workspace:{workspace_id}`` — one settings document per workspace,
not per-user. Workspace members can read; updates require the caller to
have workspace write access (enforced in the API layer).

Never stores or returns secret values, env variable names, runner URLs,
or provider internals. The stored blob contains only booleans and
enumerated mode strings.
"""

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

_SCHEMA_VERSION = 1


def _scope_doc_id(scope_key: str) -> str:
    h = hashlib.sha256(scope_key.encode("utf-8")).hexdigest()
    return f"cas_{h}"


@runtime_checkable
class CodingAgentAccessSettingsStore(Protocol):
    def get_raw(self, scope_key: str) -> dict[str, Any] | None: ...
    def put_raw(self, scope_key: str, data: dict[str, Any]) -> None: ...


class LocalJsonCodingAgentAccessSettingsStore:
    """One JSON file per workspace scope under a directory."""

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
            logger.warning("coding agent access settings local read failed: %s", p)
            return None

    def put_raw(self, scope_key: str, data: dict[str, Any]) -> None:
        p = self._path_for(scope_key)
        tmp = p.with_suffix(".tmp")
        blob = json.dumps(data, indent=2, sort_keys=True)
        with self._lock:
            tmp.write_text(blob, encoding="utf-8")
            tmp.replace(p)


class FirestoreCodingAgentAccessSettingsStore:
    """Document with ``settings`` map + ``scope_key`` (debug only)."""

    def __init__(
        self,
        collection: str,
        *,
        project: str | None = None,
        database: str | None = None,
        client: firestore.Client | None = None,
    ) -> None:
        self._coll_name = (collection or "ham_coding_agent_access_settings").strip() or (
            "ham_coding_agent_access_settings"
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
    raw = (os.environ.get("HAM_CODING_AGENT_SETTINGS_LOCAL_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    root = _workspace_root_default()
    return (root / ".ham" / "workspace_state" / "coding_agent_access_settings").resolve()


def build_coding_agent_access_settings_store() -> CodingAgentAccessSettingsStore:
    """Return the configured store backend.

    Backend is selected by ``HAM_CODING_AGENT_SETTINGS_STORE=firestore|local``.
    Falls back to ``HAM_WORKSPACE_STORE_BACKEND`` for consistency with other
    Firestore-backed stores. Defaults to ``local``.
    """
    mode = (
        (os.environ.get("HAM_CODING_AGENT_SETTINGS_STORE") or "").strip().lower()
        or (os.environ.get("HAM_WORKSPACE_STORE_BACKEND") or "").strip().lower()
        or "local"
    )
    if mode == "firestore":
        coll = (
            os.environ.get("HAM_CODING_AGENT_SETTINGS_FIRESTORE_COLLECTION")
            or "ham_coding_agent_access_settings"
        ).strip()
        proj = (os.environ.get("HAM_CODING_AGENT_SETTINGS_FIRESTORE_PROJECT") or "").strip() or None
        database = (
            os.environ.get("HAM_CODING_AGENT_SETTINGS_FIRESTORE_DATABASE") or ""
        ).strip() or None
        return FirestoreCodingAgentAccessSettingsStore(coll, project=proj, database=database)
    return LocalJsonCodingAgentAccessSettingsStore(_local_base_path())


def workspace_settings_scope_key(workspace_id: str) -> str:
    """Stable scope key for a workspace's coding-agent settings."""
    return f"workspace:{workspace_id.strip()}"
