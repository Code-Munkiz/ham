"""
Firestore-backed :class:`WorkspaceStore` (Phase 1a — skeleton).

**Skeleton only**: methods raise :class:`WorkspaceStoreError` if invoked. The
class is wired through :func:`workspace_store.build_workspace_store` *only*
when ``HAM_WORKSPACE_STORE_BACKEND=firestore`` is set on the API host. It is
not enabled by default; local-dev uses the file backend.

This file exists to:

1. Lock in the Firestore collection layout (see docstring below).
2. Keep ``google-cloud-firestore`` an optional import (never required for
   local dev or unit tests).
3. Give Phase 1b/2 a single place to fill in the real Admin-SDK calls.

Collection layout::

    users/{user_id}
    orgs/{org_id}
    memberships/{user_id}__{org_id}
    workspaces/{workspace_id}
      members/{user_id}                (subcollection)

All write paths must be tenant-scoped: workspace-bearing reads/writes hit
``workspaces/{workspace_id}/...`` exclusively. The Admin SDK runs as the
Cloud Run service account; Firestore security rules deny direct browser
writes (``firestore.rules`` lands in PR 1d).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from src.ham.workspace_models import (
    MembershipRecord,
    OrgRecord,
    UserRecord,
    WorkspaceMember,
    WorkspaceRecord,
    WorkspaceStatus,
)
from src.persistence.workspace_store import WorkspaceStoreError

_FIRESTORE_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FIRESTORE_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"
_USERS_COLL = "users"
_ORGS_COLL = "orgs"
_MEMBERSHIPS_COLL = "memberships"
_WORKSPACES_COLL = "workspaces"
_WORKSPACE_MEMBERS_SUBCOLL = "members"


def _membership_doc_id(user_id: str, org_id: str) -> str:
    return f"{user_id}__{org_id}"


class FirestoreWorkspaceStore:
    """Skeleton Firestore implementation. Real methods land in Phase 1b/2.

    The constructor accepts an injected ``client`` for tests; Phase 1a tests
    do not exercise this class directly (they use
    :class:`InMemoryWorkspaceStore`).
    """

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._project = (project or os.environ.get(_FIRESTORE_PROJECT_ENV) or "").strip() or None
        self._database = (database or os.environ.get(_FIRESTORE_DATABASE_ENV) or "").strip() or None
        self._client = client  # filled lazily in :meth:`_db`

    # ----- internal ---------------------------------------------------------

    def _db(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.cloud import firestore  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            msg = "google-cloud-firestore is required when HAM_WORKSPACE_STORE_BACKEND=firestore."
            raise WorkspaceStoreError(msg) from exc
        kwargs: dict[str, Any] = {}
        if self._project:
            kwargs["project"] = self._project
        if self._database:
            kwargs["database"] = self._database
        self._client = firestore.Client(**kwargs) if kwargs else firestore.Client()
        return self._client

    @staticmethod
    def _not_implemented(method: str) -> WorkspaceStoreError:
        return WorkspaceStoreError(
            f"FirestoreWorkspaceStore.{method} is a skeleton in Phase 1a; "
            "set HAM_WORKSPACE_STORE_BACKEND=memory or use FileWorkspaceStore.",
        )

    # ----- protocol ---------------------------------------------------------

    def upsert_user(self, record: UserRecord) -> UserRecord:
        raise self._not_implemented("upsert_user")

    def get_user(self, user_id: str) -> UserRecord | None:
        raise self._not_implemented("get_user")

    def upsert_org(self, record: OrgRecord) -> OrgRecord:
        raise self._not_implemented("upsert_org")

    def get_org(self, org_id: str) -> OrgRecord | None:
        raise self._not_implemented("get_org")

    def upsert_membership(self, record: MembershipRecord) -> MembershipRecord:
        raise self._not_implemented("upsert_membership")

    def list_memberships_for_user(self, user_id: str) -> list[MembershipRecord]:
        raise self._not_implemented("list_memberships_for_user")

    def create_workspace(self, record: WorkspaceRecord) -> WorkspaceRecord:
        raise self._not_implemented("create_workspace")

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        raise self._not_implemented("get_workspace")

    def update_workspace(
        self,
        workspace_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: WorkspaceStatus | None = None,
        updated_at: datetime | None = None,
    ) -> WorkspaceRecord:
        raise self._not_implemented("update_workspace")

    def list_workspaces_for_user(
        self,
        user_id: str,
        *,
        org_id: str | None = None,
        include_archived: bool = False,
    ) -> list[WorkspaceRecord]:
        raise self._not_implemented("list_workspaces_for_user")

    def upsert_member(self, record: WorkspaceMember) -> WorkspaceMember:
        raise self._not_implemented("upsert_member")

    def get_member(self, workspace_id: str, user_id: str) -> WorkspaceMember | None:
        raise self._not_implemented("get_member")

    def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        raise self._not_implemented("list_members")

    def remove_member(self, workspace_id: str, user_id: str) -> bool:
        raise self._not_implemented("remove_member")


__all__ = [
    "FirestoreWorkspaceStore",
]
