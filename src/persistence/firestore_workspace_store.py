"""
Firestore-backed :class:`WorkspaceStore` (PR-1d-A).

Wired through :func:`workspace_store.build_workspace_store` only when
``HAM_WORKSPACE_STORE_BACKEND=firestore``. The default backend remains
``FileWorkspaceStore`` for local-dev safety; this module is dormant unless
explicitly selected.

Collection layout::

    users/{user_id}
    orgs/{org_id}
    memberships/{user_id}__{org_id}
    workspaces/{workspace_id}
      members/{user_id}                (subcollection)

Tenant isolation: every workspace-bearing read/write hits
``workspaces/{workspace_id}/...`` exclusively. The Admin SDK runs as the
Cloud Run service account; Firestore security rules deny direct browser
writes (``firestore.rules`` lands in PR-1d-B).

No secret material is ever written to any document touched by this store —
the records validated here (``UserRecord`` / ``OrgRecord`` / ``MembershipRecord``
/ ``WorkspaceRecord`` / ``WorkspaceMember``) define a metadata-only schema.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from src.ham.workspace_models import (
    MembershipRecord,
    OrgRecord,
    UserRecord,
    WorkspaceMember,
    WorkspaceRecord,
    WorkspaceStatus,
)
from src.persistence.workspace_store import (
    WorkspaceNotFoundError,
    WorkspaceSlugConflict,
    WorkspaceStoreError,
)

_FIRESTORE_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FIRESTORE_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"
_USERS_COLL = "users"
_ORGS_COLL = "orgs"
_MEMBERSHIPS_COLL = "memberships"
_WORKSPACES_COLL = "workspaces"
_WORKSPACE_MEMBERS_SUBCOLL = "members"

# Firestore caps ``in`` queries at 30 values; chunk smaller for safety/cost.
_IN_QUERY_CHUNK = 10


class _FallbackFieldFilter:
    """Duck-typed fallback when google-cloud-firestore is unavailable.

    The fake client in tests only needs ``field_path`` / ``op_string`` /
    ``value`` attributes. Production continues to use real ``FieldFilter``
    objects whenever the firestore SDK is installed.
    """

    def __init__(self, field_path: str, op_string: str, value: Any) -> None:
        self.field_path = field_path
        self.op_string = op_string
        self.value = value


def _membership_doc_id(user_id: str, org_id: str) -> str:
    return f"{user_id}__{org_id}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class FirestoreWorkspaceStore:
    """Real Firestore implementation of :class:`WorkspaceStore`.

    Constructor accepts an injected ``client`` for tests (a fake that mimics
    enough of the ``google.cloud.firestore`` surface — see
    ``tests/test_firestore_workspace_store.py``). In production the client is
    constructed lazily on first method call so importing this module never
    contacts Firestore.
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

    # ------------------------------------------------------------------
    # Lazy client + error helpers
    # ------------------------------------------------------------------

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
    def _wrap(op: str, exc: Exception) -> WorkspaceStoreError:
        return WorkspaceStoreError(f"firestore: {op} failed: {exc}")

    @staticmethod
    def _field_filter(field: str, op: str, value: Any) -> Any:
        """Return a ``FieldFilter`` for modern firestore SDKs.

        Imported lazily so this module stays importable when the firestore
        package is absent (file-backed local dev).
        """
        try:
            from google.cloud.firestore_v1.base_query import FieldFilter  # noqa: PLC0415
        except ImportError:
            return _FallbackFieldFilter(field, op, value)

        return FieldFilter(field, op, value)

    @staticmethod
    def _commit_transaction(transaction: Any) -> None:
        commit = getattr(transaction, "commit", None)
        if callable(commit):
            commit()

    @staticmethod
    def _rollback_transaction(transaction: Any) -> None:
        rollback = getattr(transaction, "rollback", None)
        if callable(rollback):
            rollback()

    # ------------------------------------------------------------------
    # Datetime hydration
    # ------------------------------------------------------------------

    @staticmethod
    def _hydrate(raw: dict[str, Any]) -> dict[str, Any]:
        """Coerce Firestore-returned datetimes to tz-aware UTC.

        ``DatetimeWithNanoseconds`` is a ``datetime`` subclass and Firestore
        always returns UTC; this guard handles fakes / legacy strings without
        changing already-aware datetimes.
        """
        out = dict(raw)
        for k, v in list(out.items()):
            if isinstance(v, datetime) and v.tzinfo is None:
                out[k] = v.replace(tzinfo=UTC)
        return out

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def upsert_user(self, record: UserRecord) -> UserRecord:
        db = self._db()
        try:
            db.collection(_USERS_COLL).document(record.user_id).set(
                record.model_dump(mode="python"),
            )
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, WorkspaceStoreError):
                raise
            raise self._wrap("upsert_user", exc) from exc
        return record

    def get_user(self, user_id: str) -> UserRecord | None:
        db = self._db()
        try:
            snap = db.collection(_USERS_COLL).document(user_id).get()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("get_user", exc) from exc
        if not getattr(snap, "exists", False):
            return None
        data = snap.to_dict() or {}
        try:
            return UserRecord.model_validate(self._hydrate(data))
        except (ValueError, TypeError) as exc:
            raise self._wrap("get_user", exc) from exc

    # ------------------------------------------------------------------
    # Orgs
    # ------------------------------------------------------------------

    def upsert_org(self, record: OrgRecord) -> OrgRecord:
        db = self._db()
        try:
            db.collection(_ORGS_COLL).document(record.org_id).set(
                record.model_dump(mode="python"),
            )
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("upsert_org", exc) from exc
        return record

    def get_org(self, org_id: str) -> OrgRecord | None:
        db = self._db()
        try:
            snap = db.collection(_ORGS_COLL).document(org_id).get()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("get_org", exc) from exc
        if not getattr(snap, "exists", False):
            return None
        data = snap.to_dict() or {}
        try:
            return OrgRecord.model_validate(self._hydrate(data))
        except (ValueError, TypeError) as exc:
            raise self._wrap("get_org", exc) from exc

    # ------------------------------------------------------------------
    # Memberships
    # ------------------------------------------------------------------

    def upsert_membership(self, record: MembershipRecord) -> MembershipRecord:
        db = self._db()
        doc_id = _membership_doc_id(record.user_id, record.org_id)
        try:
            db.collection(_MEMBERSHIPS_COLL).document(doc_id).set(
                record.model_dump(mode="python"),
            )
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("upsert_membership", exc) from exc
        return record

    def list_memberships_for_user(self, user_id: str) -> list[MembershipRecord]:
        db = self._db()
        try:
            q = db.collection(_MEMBERSHIPS_COLL).where(
                filter=self._field_filter("user_id", "==", user_id),
            )
            rows = list(q.stream())
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("list_memberships_for_user", exc) from exc
        out: list[MembershipRecord] = []
        for snap in rows:
            data = snap.to_dict() or {}
            try:
                out.append(MembershipRecord.model_validate(self._hydrate(data)))
            except (ValueError, TypeError):
                # Skip corrupt rows; never crash list operations.
                continue
        return out

    # ------------------------------------------------------------------
    # Workspaces
    # ------------------------------------------------------------------

    def create_workspace(self, record: WorkspaceRecord) -> WorkspaceRecord:
        db = self._db()
        coll = db.collection(_WORKSPACES_COLL)
        new_doc = coll.document(record.workspace_id)

        transaction = db.transaction()
        try:
            # Slug-uniqueness scan within the active scope. Reads precede the
            # write so Firestore transactions can detect conflicting commits.
            if record.org_id is not None:
                slug_q = (
                    coll.where(filter=self._field_filter("org_id", "==", record.org_id))
                    .where(filter=self._field_filter("slug", "==", record.slug))
                    .where(filter=self._field_filter("status", "==", "active"))
                )
            else:
                slug_q = (
                    coll.where(filter=self._field_filter("org_id", "==", None))
                    .where(
                        filter=self._field_filter(
                            "owner_user_id",
                            "==",
                            record.owner_user_id,
                        ),
                    )
                    .where(filter=self._field_filter("slug", "==", record.slug))
                    .where(filter=self._field_filter("status", "==", "active"))
                )
            for _ in slug_q.stream(transaction=transaction):
                msg = (
                    f"slug {record.slug!r} already exists in scope "
                    f"{record.org_id or ('_personal:' + record.owner_user_id)!r}"
                )
                raise WorkspaceSlugConflict(msg)
            existing_snap = new_doc.get(transaction=transaction)
            if getattr(existing_snap, "exists", False):
                raise WorkspaceStoreError(
                    f"workspace_id collision: {record.workspace_id}",
                )
            transaction.set(new_doc, record.model_dump(mode="python"))
            self._commit_transaction(transaction)
            return record
        except (WorkspaceSlugConflict, WorkspaceStoreError):
            self._rollback_transaction(transaction)
            raise
        except Exception as exc:  # noqa: BLE001
            self._rollback_transaction(transaction)
            raise self._wrap("create_workspace", exc) from exc

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        db = self._db()
        try:
            snap = db.collection(_WORKSPACES_COLL).document(workspace_id).get()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("get_workspace", exc) from exc
        if not getattr(snap, "exists", False):
            return None
        data = snap.to_dict() or {}
        try:
            return WorkspaceRecord.model_validate(self._hydrate(data))
        except (ValueError, TypeError) as exc:
            raise self._wrap("get_workspace", exc) from exc

    def update_workspace(
        self,
        workspace_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: WorkspaceStatus | None = None,
        updated_at: datetime | None = None,
    ) -> WorkspaceRecord:
        db = self._db()
        doc_ref = db.collection(_WORKSPACES_COLL).document(workspace_id)

        transaction = db.transaction()
        try:
            snap = doc_ref.get(transaction=transaction)
            if not getattr(snap, "exists", False):
                raise WorkspaceNotFoundError(workspace_id)
            data = snap.to_dict() or {}
            existing = WorkspaceRecord.model_validate(self._hydrate(data))
            payload: dict[str, Any] = {}
            if name is not None:
                payload["name"] = name
            if description is not None:
                payload["description"] = description
            if status is not None:
                payload["status"] = status
            payload["updated_at"] = updated_at or _utc_now()
            updated = existing.model_copy(update=payload)
            transaction.set(doc_ref, updated.model_dump(mode="python"))
            self._commit_transaction(transaction)
            return updated
        except WorkspaceNotFoundError:
            self._rollback_transaction(transaction)
            raise
        except Exception as exc:  # noqa: BLE001
            self._rollback_transaction(transaction)
            raise self._wrap("update_workspace", exc) from exc

    def _absorb_workspace(
        self,
        snap: Any,
        sink: dict[str, WorkspaceRecord],
    ) -> None:
        data = snap.to_dict() or {}
        try:
            rec = WorkspaceRecord.model_validate(self._hydrate(data))
        except (ValueError, TypeError):
            return
        sink.setdefault(rec.workspace_id, rec)

    def _accumulate_owned(
        self,
        coll: Any,
        user_id: str,
        sink: dict[str, WorkspaceRecord],
    ) -> None:
        owned_q = coll.where(
            filter=self._field_filter("owner_user_id", "==", user_id),
        )
        for snap in owned_q.stream():
            self._absorb_workspace(snap, sink)

    def _accumulate_member_rows(
        self,
        db: Any,
        coll: Any,
        user_id: str,
        sink: dict[str, WorkspaceRecord],
    ) -> None:
        member_q = db.collection_group(_WORKSPACE_MEMBERS_SUBCOLL).where(
            filter=self._field_filter("user_id", "==", user_id),
        )
        member_workspace_ids: set[str] = set()
        for snap in member_q.stream():
            data = snap.to_dict() or {}
            wid = str(data.get("workspace_id") or "")
            if wid:
                member_workspace_ids.add(wid)
        for wid in member_workspace_ids - set(sink.keys()):
            ws_snap = coll.document(wid).get()
            if getattr(ws_snap, "exists", False):
                self._absorb_workspace(ws_snap, sink)

    def _accumulate_org_fallback(
        self,
        db: Any,
        coll: Any,
        user_id: str,
        sink: dict[str, WorkspaceRecord],
    ) -> None:
        mem_q = db.collection(_MEMBERSHIPS_COLL).where(
            filter=self._field_filter("user_id", "==", user_id),
        )
        user_org_ids: list[str] = []
        for snap in mem_q.stream():
            data = snap.to_dict() or {}
            oid = str(data.get("org_id") or "")
            if oid:
                user_org_ids.append(oid)
        for i in range(0, len(user_org_ids), _IN_QUERY_CHUNK):
            chunk = user_org_ids[i : i + _IN_QUERY_CHUNK]
            if not chunk:
                continue
            org_q = coll.where(filter=self._field_filter("org_id", "in", chunk))
            for snap in org_q.stream():
                self._absorb_workspace(snap, sink)

    def list_workspaces_for_user(
        self,
        user_id: str,
        *,
        org_id: str | None = None,
        include_archived: bool = False,
    ) -> list[WorkspaceRecord]:
        db = self._db()
        coll = db.collection(_WORKSPACES_COLL)
        records: dict[str, WorkspaceRecord] = {}

        try:
            self._accumulate_owned(coll, user_id, records)
            self._accumulate_member_rows(db, coll, user_id, records)
            self._accumulate_org_fallback(db, coll, user_id, records)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("list_workspaces_for_user", exc) from exc

        results: list[WorkspaceRecord] = []
        for rec in records.values():
            if org_id is not None and rec.org_id != org_id:
                continue
            if not include_archived and rec.status == "archived":
                continue
            results.append(rec)
        results.sort(key=lambda w: w.updated_at, reverse=True)
        return results

    # ------------------------------------------------------------------
    # Workspace members (subcollection)
    # ------------------------------------------------------------------

    def upsert_member(self, record: WorkspaceMember) -> WorkspaceMember:
        db = self._db()
        ws_ref = db.collection(_WORKSPACES_COLL).document(record.workspace_id)
        try:
            ws_snap = ws_ref.get()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("upsert_member", exc) from exc
        if not getattr(ws_snap, "exists", False):
            raise WorkspaceNotFoundError(record.workspace_id)
        try:
            ws_ref.collection(_WORKSPACE_MEMBERS_SUBCOLL).document(record.user_id).set(
                record.model_dump(mode="python"),
            )
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("upsert_member", exc) from exc
        return record

    def get_member(self, workspace_id: str, user_id: str) -> WorkspaceMember | None:
        db = self._db()
        try:
            snap = (
                db.collection(_WORKSPACES_COLL)
                .document(workspace_id)
                .collection(_WORKSPACE_MEMBERS_SUBCOLL)
                .document(user_id)
                .get()
            )
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("get_member", exc) from exc
        if not getattr(snap, "exists", False):
            return None
        data = snap.to_dict() or {}
        try:
            return WorkspaceMember.model_validate(self._hydrate(data))
        except (ValueError, TypeError) as exc:
            raise self._wrap("get_member", exc) from exc

    def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        db = self._db()
        try:
            stream = (
                db.collection(_WORKSPACES_COLL)
                .document(workspace_id)
                .collection(_WORKSPACE_MEMBERS_SUBCOLL)
                .stream()
            )
            rows = list(stream)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("list_members", exc) from exc
        out: list[WorkspaceMember] = []
        for snap in rows:
            data = snap.to_dict() or {}
            try:
                out.append(WorkspaceMember.model_validate(self._hydrate(data)))
            except (ValueError, TypeError):
                continue
        return out

    def remove_member(self, workspace_id: str, user_id: str) -> bool:
        db = self._db()
        member_ref = (
            db.collection(_WORKSPACES_COLL)
            .document(workspace_id)
            .collection(_WORKSPACE_MEMBERS_SUBCOLL)
            .document(user_id)
        )
        try:
            snap = member_ref.get()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("remove_member", exc) from exc
        if not getattr(snap, "exists", False):
            return False
        try:
            member_ref.delete()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("remove_member", exc) from exc
        return True


__all__ = [
    "FirestoreWorkspaceStore",
]
