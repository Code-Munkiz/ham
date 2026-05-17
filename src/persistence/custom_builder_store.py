"""Persistence for workspace-scoped Custom Builder profiles.

Mirrors :mod:`src.persistence.coding_agent_access_settings_store`: a thin
``CustomBuilderStore`` protocol with a LocalJson backend (one file per
scope key) and a Firestore backend (one document per scope key) selected
by environment variables.

Scope key shape: ``workspace:{workspace_id}:builder:{builder_id}`` — the
``:builder:`` segment leaves room to add a ``user:{uid}:builder:{bid}``
namespace later without migrations.

Soft-delete only: callers do not remove rows; :func:`soft_delete_profile`
sets ``enabled=False`` so audit history and any in-flight runs keep
working. Hard deletion is intentionally not exposed here.

Never logs or persists raw secrets. ``model_ref`` is constrained by the
:class:`CustomBuilderProfile` validator (rejects ``^[A-Za-z0-9]{32,}$``
shaped values).
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

from src.ham.custom_builder.profile import CustomBuilderProfile

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1
_DEFAULT_FIRESTORE_COLLECTION = "ham_custom_builders"


def _scope_doc_id(scope_key: str) -> str:
    h = hashlib.sha256(scope_key.encode("utf-8")).hexdigest()
    return f"cb_{h}"


def workspace_builder_scope_key(workspace_id: str, builder_id: str) -> str:
    """Stable scope key: ``workspace:{ws}:builder:{bid}``."""
    return f"workspace:{workspace_id.strip()}:builder:{builder_id.strip()}"


@runtime_checkable
class CustomBuilderStore(Protocol):
    def get_raw(self, scope_key: str) -> dict[str, Any] | None: ...
    def put_raw(self, scope_key: str, data: dict[str, Any]) -> None: ...
    def list_workspace_raw(self, workspace_id: str) -> list[dict[str, Any]]: ...


class LocalJsonCustomBuilderStore:
    """One JSON file per scope key under ``base``."""

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
        except (OSError, json.JSONDecodeError):
            logger.warning("custom builder local read failed: %s", p)
            return None
        if not isinstance(raw, dict):
            return None
        inner = raw.get("profile")
        return inner if isinstance(inner, dict) else None

    def put_raw(self, scope_key: str, data: dict[str, Any]) -> None:
        p = self._path_for(scope_key)
        tmp = p.with_suffix(".tmp")
        workspace_id = str(data.get("workspace_id") or "").strip()
        body = {
            "scope_key": scope_key,
            "workspace_id": workspace_id,
            "profile": data,
        }
        blob = json.dumps(body, indent=2, sort_keys=True)
        with self._lock:
            tmp.write_text(blob, encoding="utf-8")
            tmp.replace(p)

    def list_workspace_raw(self, workspace_id: str) -> list[dict[str, Any]]:
        target = workspace_id.strip()
        out: list[dict[str, Any]] = []
        if not self._base.is_dir():
            return out
        for entry in sorted(self._base.glob("cb_*.json")):
            try:
                raw = json.loads(entry.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                logger.warning("custom builder local list skip: %s", entry)
                continue
            if not isinstance(raw, dict):
                continue
            ws = str(raw.get("workspace_id") or "").strip()
            inner = raw.get("profile")
            if ws == target and isinstance(inner, dict):
                out.append(inner)
        return out


class FirestoreCustomBuilderStore:
    """Document body: ``{scope_key, workspace_id, profile}``."""

    def __init__(
        self,
        collection: str,
        *,
        project: str | None = None,
        database: str | None = None,
        client: firestore.Client | None = None,
    ) -> None:
        self._coll_name = (collection or _DEFAULT_FIRESTORE_COLLECTION).strip() or (
            _DEFAULT_FIRESTORE_COLLECTION
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
        inner = data.get("profile")
        return inner if isinstance(inner, dict) else None

    def put_raw(self, scope_key: str, data: dict[str, Any]) -> None:
        doc_id = _scope_doc_id(scope_key)
        workspace_id = str(data.get("workspace_id") or "").strip()
        with self._lock:
            self._coll().document(doc_id).set(
                {
                    "scope_key": scope_key,
                    "workspace_id": workspace_id,
                    "profile": data,
                },
                merge=True,
            )

    def list_workspace_raw(self, workspace_id: str) -> list[dict[str, Any]]:
        target = workspace_id.strip()
        snaps = self._coll().where("workspace_id", "==", target).stream()
        out: list[dict[str, Any]] = []
        for snap in snaps:
            data = snap.to_dict() or {}
            inner = data.get("profile")
            if isinstance(inner, dict):
                out.append(inner)
        return out


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
    raw = (os.environ.get("HAM_CUSTOM_BUILDER_LOCAL_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    root = _workspace_root_default()
    return (root / ".ham" / "workspace_state" / "custom_builders").resolve()


def build_custom_builder_store() -> CustomBuilderStore:
    """Return the configured store backend.

    Backend is selected by ``HAM_CUSTOM_BUILDER_STORE=firestore|local``,
    falling back to ``HAM_WORKSPACE_STORE_BACKEND`` for parity with other
    Firestore-backed stores. Defaults to ``local``.
    """
    mode = (
        (os.environ.get("HAM_CUSTOM_BUILDER_STORE") or "").strip().lower()
        or (os.environ.get("HAM_WORKSPACE_STORE_BACKEND") or "").strip().lower()
        or "local"
    )
    if mode == "firestore":
        coll = (
            os.environ.get("HAM_CUSTOM_BUILDER_FIRESTORE_COLLECTION")
            or _DEFAULT_FIRESTORE_COLLECTION
        ).strip()
        proj = (os.environ.get("HAM_CUSTOM_BUILDER_FIRESTORE_PROJECT") or "").strip() or None
        database = (os.environ.get("HAM_CUSTOM_BUILDER_FIRESTORE_DATABASE") or "").strip() or None
        return FirestoreCustomBuilderStore(coll, project=proj, database=database)
    return LocalJsonCustomBuilderStore(_local_base_path())


def put_profile(store: CustomBuilderStore, profile: CustomBuilderProfile) -> None:
    """Persist ``profile`` under its workspace + builder scope key."""
    key = workspace_builder_scope_key(profile.workspace_id, profile.builder_id)
    store.put_raw(key, profile.model_dump())


def get_profile(
    store: CustomBuilderStore,
    workspace_id: str,
    builder_id: str,
) -> CustomBuilderProfile | None:
    """Return the profile for ``(workspace_id, builder_id)`` or ``None``."""
    key = workspace_builder_scope_key(workspace_id, builder_id)
    raw = store.get_raw(key)
    if raw is None:
        return None
    return CustomBuilderProfile.model_validate(raw)


def list_profiles_for_workspace(
    store: CustomBuilderStore,
    workspace_id: str,
) -> list[CustomBuilderProfile]:
    """Return all profiles for ``workspace_id``, newest ``updated_at`` first."""
    rows = store.list_workspace_raw(workspace_id)
    profiles: list[CustomBuilderProfile] = []
    for raw in rows:
        try:
            profiles.append(CustomBuilderProfile.model_validate(raw))
        except Exception:
            logger.warning("custom builder list skip: invalid stored profile")
            continue
    profiles.sort(key=lambda p: (p.updated_at, p.builder_id), reverse=True)
    return profiles


def soft_delete_profile(
    store: CustomBuilderStore,
    workspace_id: str,
    builder_id: str,
    *,
    updated_by: str,
    updated_at: str,
) -> CustomBuilderProfile | None:
    """Disable the profile (``enabled=False``) while retaining the stored row."""
    existing = get_profile(store, workspace_id, builder_id)
    if existing is None:
        return None
    updated = existing.model_copy(
        update={
            "enabled": False,
            "updated_by": updated_by,
            "updated_at": updated_at,
        }
    )
    put_profile(store, updated)
    return updated


__all__ = [
    "CustomBuilderStore",
    "FirestoreCustomBuilderStore",
    "LocalJsonCustomBuilderStore",
    "build_custom_builder_store",
    "get_profile",
    "list_profiles_for_workspace",
    "put_profile",
    "soft_delete_profile",
    "workspace_builder_scope_key",
]
