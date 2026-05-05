"""
Workspace persistence Protocol + concrete backends (Phase 1a — skeleton).

Three impls:

- :class:`InMemoryWorkspaceStore`     — for tests; thread-safe.
- :class:`FileWorkspaceStore`         — local-dev fallback, JSON file under
  ``HAM_WORKSPACE_STORE_PATH`` (default ``~/.ham/workspaces.json``).
- :class:`FirestoreWorkspaceStore`    — hosted prod (lazy import — see
  ``src/persistence/firestore_workspace_store.py``).

Phase 1a does **not** wire :func:`build_workspace_store` into any router or
existing endpoint; it is consumed only by the tests in ``tests/`` and (in
Phase 1b) by ``src/api/me.py`` / ``src/api/workspaces.py``.

**Tenant isolation**: every method takes ``workspace_id`` (or returns
filtered records keyed by it). The store never returns rows from another
``workspace_id`` and never mutates rows outside the requested workspace.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, Protocol, runtime_checkable

from src.ham.workspace_models import (
    WORKSPACE_ID_PREFIX,
    MembershipRecord,
    OrgRecord,
    UserRecord,
    WorkspaceMember,
    WorkspaceRecord,
    WorkspaceStatus,
    is_valid_slug,
)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class WorkspaceStoreError(Exception):
    """Base error for workspace store violations."""


class WorkspaceSlugConflict(WorkspaceStoreError):  # noqa: N818  # HTTP-409-shaped name (Phase 1b maps to 409)
    """Raised when ``(org_id|owner, slug)`` already exists for ``status=active``."""


class WorkspaceNotFoundError(WorkspaceStoreError):
    """Raised on get/update of a missing workspace."""


# ---------------------------------------------------------------------------
# ID + time helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(UTC)


def new_workspace_id() -> str:
    """Issue a fresh workspace_id (``ws_`` + 16 lowercase base32 chars)."""
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    suffix = "".join(secrets.choice(alphabet) for _ in range(16))
    return f"{WORKSPACE_ID_PREFIX}{suffix}"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class WorkspaceStore(Protocol):
    """Tenant-scoped persistence for users / orgs / workspaces / members.

    All methods are synchronous — Phase 2 may add async variants when chat
    streaming demands it; the Protocol stays narrow for Phase 1a.
    """

    # --- users ----------------------------------------------------------------
    def upsert_user(self, record: UserRecord) -> UserRecord: ...
    def get_user(self, user_id: str) -> UserRecord | None: ...

    # --- orgs -----------------------------------------------------------------
    def upsert_org(self, record: OrgRecord) -> OrgRecord: ...
    def get_org(self, org_id: str) -> OrgRecord | None: ...

    # --- memberships (org-level mirror) --------------------------------------
    def upsert_membership(self, record: MembershipRecord) -> MembershipRecord: ...
    def list_memberships_for_user(self, user_id: str) -> list[MembershipRecord]: ...

    # --- workspaces -----------------------------------------------------------
    def create_workspace(self, record: WorkspaceRecord) -> WorkspaceRecord: ...
    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None: ...
    def update_workspace(
        self,
        workspace_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: WorkspaceStatus | None = None,
        updated_at: datetime | None = None,
    ) -> WorkspaceRecord: ...
    def list_workspaces_for_user(
        self,
        user_id: str,
        *,
        org_id: str | None = None,
        include_archived: bool = False,
    ) -> list[WorkspaceRecord]: ...

    # --- workspace members ---------------------------------------------------
    def upsert_member(self, record: WorkspaceMember) -> WorkspaceMember: ...
    def get_member(self, workspace_id: str, user_id: str) -> WorkspaceMember | None: ...
    def list_members(self, workspace_id: str) -> list[WorkspaceMember]: ...
    def remove_member(self, workspace_id: str, user_id: str) -> bool: ...


# ---------------------------------------------------------------------------
# In-memory backend
# ---------------------------------------------------------------------------


class InMemoryWorkspaceStore:
    """Thread-safe in-memory implementation. Used by tests."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._users: dict[str, UserRecord] = {}
        self._orgs: dict[str, OrgRecord] = {}
        self._memberships: dict[tuple[str, str], MembershipRecord] = {}
        self._workspaces: dict[str, WorkspaceRecord] = {}
        # nested by (workspace_id, user_id)
        self._members: dict[tuple[str, str], WorkspaceMember] = {}

    # users -------------------------------------------------------------------

    def upsert_user(self, record: UserRecord) -> UserRecord:
        with self._lock:
            self._users[record.user_id] = record
            return record

    def get_user(self, user_id: str) -> UserRecord | None:
        with self._lock:
            return self._users.get(user_id)

    # orgs --------------------------------------------------------------------

    def upsert_org(self, record: OrgRecord) -> OrgRecord:
        with self._lock:
            self._orgs[record.org_id] = record
            return record

    def get_org(self, org_id: str) -> OrgRecord | None:
        with self._lock:
            return self._orgs.get(org_id)

    # memberships -------------------------------------------------------------

    def upsert_membership(self, record: MembershipRecord) -> MembershipRecord:
        with self._lock:
            self._memberships[(record.user_id, record.org_id)] = record
            return record

    def list_memberships_for_user(self, user_id: str) -> list[MembershipRecord]:
        with self._lock:
            return [m for (uid, _), m in self._memberships.items() if uid == user_id]

    # workspaces --------------------------------------------------------------

    def create_workspace(self, record: WorkspaceRecord) -> WorkspaceRecord:
        with self._lock:
            if record.workspace_id in self._workspaces:
                raise WorkspaceStoreError(
                    f"workspace_id collision: {record.workspace_id}",
                )
            self._enforce_slug_unique(record)
            self._workspaces[record.workspace_id] = record
            return record

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        with self._lock:
            return self._workspaces.get(workspace_id)

    def update_workspace(
        self,
        workspace_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: WorkspaceStatus | None = None,
        updated_at: datetime | None = None,
    ) -> WorkspaceRecord:
        with self._lock:
            existing = self._workspaces.get(workspace_id)
            if existing is None:
                raise WorkspaceNotFoundError(workspace_id)
            payload: dict[str, Any] = {}
            if name is not None:
                payload["name"] = name
            if description is not None:
                payload["description"] = description
            if status is not None:
                payload["status"] = status
            payload["updated_at"] = updated_at or _utc_now()
            updated = existing.model_copy(update=payload)
            self._workspaces[workspace_id] = updated
            return updated

    def list_workspaces_for_user(
        self,
        user_id: str,
        *,
        org_id: str | None = None,
        include_archived: bool = False,
    ) -> list[WorkspaceRecord]:
        with self._lock:
            owned_or_member: set[str] = {
                w.workspace_id for w in self._workspaces.values() if w.owner_user_id == user_id
            }
            owned_or_member.update(wid for (wid, uid) in self._members.keys() if uid == user_id)
            # Org-level fallback (member-row absent but actor in same org)
            user_org_ids: set[str] = {
                m.org_id for m in self._memberships.values() if m.user_id == user_id
            }
            for w in self._workspaces.values():
                if w.org_id and w.org_id in user_org_ids:
                    owned_or_member.add(w.workspace_id)
            results: list[WorkspaceRecord] = []
            for wid in owned_or_member:
                w = self._workspaces.get(wid)
                if w is None:
                    continue
                if org_id is not None and w.org_id != org_id:
                    continue
                if not include_archived and w.status == "archived":
                    continue
                results.append(w)
            results.sort(key=lambda w: w.updated_at, reverse=True)
            return results

    # workspace members -------------------------------------------------------

    def upsert_member(self, record: WorkspaceMember) -> WorkspaceMember:
        with self._lock:
            if record.workspace_id not in self._workspaces:
                raise WorkspaceNotFoundError(record.workspace_id)
            self._members[(record.workspace_id, record.user_id)] = record
            return record

    def get_member(self, workspace_id: str, user_id: str) -> WorkspaceMember | None:
        with self._lock:
            return self._members.get((workspace_id, user_id))

    def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        with self._lock:
            return [m for (wid, _), m in self._members.items() if wid == workspace_id]

    def remove_member(self, workspace_id: str, user_id: str) -> bool:
        with self._lock:
            return self._members.pop((workspace_id, user_id), None) is not None

    # internals ---------------------------------------------------------------

    def _enforce_slug_unique(self, record: WorkspaceRecord) -> None:
        scope_key = record.org_id or f"_personal:{record.owner_user_id}"
        for existing in self._workspaces.values():
            if existing.status != "active":
                continue
            existing_scope = existing.org_id or f"_personal:{existing.owner_user_id}"
            if existing_scope == scope_key and existing.slug == record.slug:
                msg = f"slug {record.slug!r} already exists in scope {scope_key!r}"
                raise WorkspaceSlugConflict(msg)


# ---------------------------------------------------------------------------
# File-backed (local dev) backend
# ---------------------------------------------------------------------------


_DEFAULT_FILE_STORE_PATH = Path.home() / ".ham" / "workspaces.json"
_FILE_STORE_PATH_ENV = "HAM_WORKSPACE_STORE_PATH"


def default_file_store_path() -> Path:
    raw = (os.environ.get(_FILE_STORE_PATH_ENV) or "").strip()
    if raw:
        return Path(raw).expanduser()
    return _DEFAULT_FILE_STORE_PATH


class FileWorkspaceStore:
    """JSON-file backed store for local-dev mode.

    Wraps :class:`InMemoryWorkspaceStore` for in-process behaviour and persists
    on every mutation. The file is created lazily; a missing file is treated as
    "no rows yet". Concurrent multi-process use is **not** supported (single
    developer machine assumed); cloud mode uses Firestore.

    The store is dormant: it is constructed but holds no rows until callers
    upsert. This means existing local ``.ham/`` files (``social_policy.json``,
    ``settings.json``, ``projects.json``) are untouched.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path is not None else default_file_store_path()
        self._inner = InMemoryWorkspaceStore()
        self._lock = RLock()
        self._loaded = False

    # --- IO -----------------------------------------------------------------

    def _load_if_needed(self) -> None:
        with self._lock:
            if self._loaded:
                return
            self._loaded = True
            if not self._path.is_file():
                return
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return
            for u in raw.get("users", []):
                try:
                    self._inner.upsert_user(UserRecord.model_validate(u))
                except (ValueError, TypeError):
                    continue
            for o in raw.get("orgs", []):
                try:
                    self._inner.upsert_org(OrgRecord.model_validate(o))
                except (ValueError, TypeError):
                    continue
            for m in raw.get("memberships", []):
                try:
                    self._inner.upsert_membership(MembershipRecord.model_validate(m))
                except (ValueError, TypeError):
                    continue
            for w in raw.get("workspaces", []):
                try:
                    self._inner.create_workspace(WorkspaceRecord.model_validate(w))
                except (WorkspaceStoreError, ValueError, TypeError):
                    continue
            for wm in raw.get("workspace_members", []):
                try:
                    self._inner.upsert_member(WorkspaceMember.model_validate(wm))
                except (WorkspaceStoreError, ValueError, TypeError):
                    continue

    def _persist(self) -> None:
        with self._lock:
            payload = {
                "users": [u.model_dump(mode="json") for u in self._inner._users.values()],
                "orgs": [o.model_dump(mode="json") for o in self._inner._orgs.values()],
                "memberships": [
                    m.model_dump(mode="json") for m in self._inner._memberships.values()
                ],
                "workspaces": [w.model_dump(mode="json") for w in self._inner._workspaces.values()],
                "workspace_members": [
                    wm.model_dump(mode="json") for wm in self._inner._members.values()
                ],
            }
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
            tmp.replace(self._path)

    # --- protocol pass-through ---------------------------------------------

    def upsert_user(self, record: UserRecord) -> UserRecord:
        self._load_if_needed()
        out = self._inner.upsert_user(record)
        self._persist()
        return out

    def get_user(self, user_id: str) -> UserRecord | None:
        self._load_if_needed()
        return self._inner.get_user(user_id)

    def upsert_org(self, record: OrgRecord) -> OrgRecord:
        self._load_if_needed()
        out = self._inner.upsert_org(record)
        self._persist()
        return out

    def get_org(self, org_id: str) -> OrgRecord | None:
        self._load_if_needed()
        return self._inner.get_org(org_id)

    def upsert_membership(self, record: MembershipRecord) -> MembershipRecord:
        self._load_if_needed()
        out = self._inner.upsert_membership(record)
        self._persist()
        return out

    def list_memberships_for_user(self, user_id: str) -> list[MembershipRecord]:
        self._load_if_needed()
        return self._inner.list_memberships_for_user(user_id)

    def create_workspace(self, record: WorkspaceRecord) -> WorkspaceRecord:
        self._load_if_needed()
        out = self._inner.create_workspace(record)
        self._persist()
        return out

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        self._load_if_needed()
        return self._inner.get_workspace(workspace_id)

    def update_workspace(
        self,
        workspace_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: WorkspaceStatus | None = None,
        updated_at: datetime | None = None,
    ) -> WorkspaceRecord:
        self._load_if_needed()
        out = self._inner.update_workspace(
            workspace_id,
            name=name,
            description=description,
            status=status,
            updated_at=updated_at,
        )
        self._persist()
        return out

    def list_workspaces_for_user(
        self,
        user_id: str,
        *,
        org_id: str | None = None,
        include_archived: bool = False,
    ) -> list[WorkspaceRecord]:
        self._load_if_needed()
        return self._inner.list_workspaces_for_user(
            user_id,
            org_id=org_id,
            include_archived=include_archived,
        )

    def upsert_member(self, record: WorkspaceMember) -> WorkspaceMember:
        self._load_if_needed()
        out = self._inner.upsert_member(record)
        self._persist()
        return out

    def get_member(self, workspace_id: str, user_id: str) -> WorkspaceMember | None:
        self._load_if_needed()
        return self._inner.get_member(workspace_id, user_id)

    def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        self._load_if_needed()
        return self._inner.list_members(workspace_id)

    def remove_member(self, workspace_id: str, user_id: str) -> bool:
        self._load_if_needed()
        out = self._inner.remove_member(workspace_id, user_id)
        if out:
            self._persist()
        return out


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


_WORKSPACE_STORE_BACKEND_ENV = "HAM_WORKSPACE_STORE_BACKEND"  # memory|file|firestore


def build_workspace_store() -> WorkspaceStore:
    """Pick a backend based on env. Defaults to file (local-dev safe).

    Phase 1a only: this is **not** called by any router yet.
    """
    backend = (os.environ.get(_WORKSPACE_STORE_BACKEND_ENV) or "").strip().lower()
    if backend == "memory":
        return InMemoryWorkspaceStore()
    if backend == "firestore":
        # Lazy import: avoids requiring google-cloud-firestore for local dev.
        from src.persistence.firestore_workspace_store import (  # noqa: PLC0415
            FirestoreWorkspaceStore,
        )

        return FirestoreWorkspaceStore()
    return FileWorkspaceStore()


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------


def normalize_slug_input(raw: str) -> str | None:
    """Return ``raw.strip().lower()`` if it parses as a slug; ``None`` otherwise."""
    if not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    return s if is_valid_slug(s) else None


__all__ = [
    "FileWorkspaceStore",
    "InMemoryWorkspaceStore",
    "WorkspaceNotFoundError",
    "WorkspaceSlugConflict",
    "WorkspaceStore",
    "WorkspaceStoreError",
    "build_workspace_store",
    "default_file_store_path",
    "new_workspace_id",
    "normalize_slug_input",
]
