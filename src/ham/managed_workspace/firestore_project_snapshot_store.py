"""Firestore persistence for :class:`ProjectSnapshot` rows (optional backend).

Wired through :func:`src.ham.managed_workspace.snapshot_store.get_project_snapshot_store`
only when ``HAM_PROJECT_STORE_BACKEND=firestore``. The default backend remains
the in-process :class:`MemoryProjectSnapshotStore` so unit tests and local dev
keep working unchanged.

Collection layout::

    {collection}/{project_id}___{snapshot_id}

Defaults: collection ``ham_managed_project_snapshots``. The runtime project /
database can be selected via project-store-specific env vars, falling back to
the shared workspace-store env vars when unset:

- ``HAM_PROJECT_FIRESTORE_PROJECT_ID``   -> ``HAM_FIRESTORE_PROJECT_ID``
- ``HAM_PROJECT_FIRESTORE_DATABASE``     -> ``HAM_FIRESTORE_DATABASE``
- ``HAM_PROJECT_SNAPSHOT_FIRESTORE_COLLECTION``
  (default ``ham_managed_project_snapshots``)

Stored shape mirrors :meth:`ProjectSnapshot.model_dump(mode="json")`. No
secrets are persisted; :class:`ProjectSnapshot` is a metadata-only Pydantic
model.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import ValidationError

from src.ham.managed_workspace.models import ProjectSnapshot
from src.ham.managed_workspace.snapshot_store import ProjectSnapshotStore

_LOG = logging.getLogger(__name__)

_PROJECT_FIRESTORE_PROJECT_ENV = "HAM_PROJECT_FIRESTORE_PROJECT_ID"
_PROJECT_FIRESTORE_DATABASE_ENV = "HAM_PROJECT_FIRESTORE_DATABASE"
_PROJECT_SNAPSHOT_FIRESTORE_COLLECTION_ENV = "HAM_PROJECT_SNAPSHOT_FIRESTORE_COLLECTION"

_FALLBACK_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FALLBACK_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"

_DEFAULT_COLLECTION = "ham_managed_project_snapshots"


def _resolve_env(primary: str, fallback: str | None = None) -> str | None:
    val = (os.environ.get(primary) or "").strip()
    if val:
        return val
    if fallback is not None:
        val = (os.environ.get(fallback) or "").strip()
        if val:
            return val
    return None


def _doc_id(project_id: str, snapshot_id: str) -> str:
    return f"{project_id}___{snapshot_id}"


class FirestoreProjectSnapshotStore(ProjectSnapshotStore):
    """Firestore implementation of the :class:`ProjectSnapshotStore` contract.

    The constructor accepts an injected ``client`` for tests; in production the
    real ``google.cloud.firestore.Client`` is constructed lazily on first
    method call so importing this module never contacts Firestore.
    """

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str | None = None,
        collection: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._client: Any | None = client
        self._project = project or _resolve_env(
            _PROJECT_FIRESTORE_PROJECT_ENV,
            _FALLBACK_PROJECT_ENV,
        )
        self._database = database or _resolve_env(
            _PROJECT_FIRESTORE_DATABASE_ENV,
            _FALLBACK_DATABASE_ENV,
        )
        coll = (
            collection
            or _resolve_env(_PROJECT_SNAPSHOT_FIRESTORE_COLLECTION_ENV)
            or _DEFAULT_COLLECTION
        )
        self._coll_name = coll.strip() or _DEFAULT_COLLECTION

    def _db(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.cloud import firestore  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - exercised only without SDK
            raise RuntimeError(
                "google-cloud-firestore is required when HAM_PROJECT_STORE_BACKEND=firestore.",
            ) from exc
        kwargs: dict[str, Any] = {}
        if self._project:
            kwargs["project"] = self._project
        if self._database:
            kwargs["database"] = self._database
        self._client = firestore.Client(**kwargs) if kwargs else firestore.Client()
        return self._client

    def _coll(self) -> Any:
        return self._db().collection(self._coll_name)

    def put_snapshot(self, row: ProjectSnapshot) -> None:
        ref = self._coll().document(_doc_id(row.project_id, row.snapshot_id))
        ref.set(row.model_dump(mode="json"))

    def list_snapshots(self, project_id: str) -> list[ProjectSnapshot]:
        pid = project_id.strip()
        if not pid:
            return []
        rows: list[ProjectSnapshot] = []
        stream = self._coll().stream()
        for snap in stream:
            data = snap.to_dict() or {}
            if str(data.get("project_id") or "") != pid:
                continue
            try:
                rows.append(ProjectSnapshot.model_validate(data))
            except ValidationError as exc:
                _LOG.warning(
                    "ham_managed_snapshots: skip malformed (%s): %s",
                    type(exc).__name__,
                    exc,
                )
                continue
        rows.sort(key=lambda r: r.created_at)
        return rows

    def get_snapshot(self, project_id: str, snapshot_id: str) -> ProjectSnapshot | None:
        ref = self._coll().document(_doc_id(project_id, snapshot_id))
        snap = ref.get()
        if not getattr(snap, "exists", False):
            return None
        data = snap.to_dict() or {}
        if str(data.get("project_id") or "") != project_id.strip():
            return None
        return ProjectSnapshot.model_validate(data)
