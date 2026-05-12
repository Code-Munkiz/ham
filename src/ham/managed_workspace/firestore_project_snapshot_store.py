"""Firestore persistence for :class:`ProjectSnapshot` rows (optional backend)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from src.ham.managed_workspace.models import ProjectSnapshot
from src.ham.managed_workspace.snapshot_store import ProjectSnapshotStore

_LOG = logging.getLogger(__name__)

_COLLECTION = "ham_managed_project_snapshots"


def _doc_id(project_id: str, snapshot_id: str) -> str:
    return f"{project_id}___{snapshot_id}"


class FirestoreProjectSnapshotStore(ProjectSnapshotStore):
    def __init__(self, *, client: Any | None = None, **kwargs: Any) -> None:
        self._client: Any | None = client
        self._kwargs = kwargs

    def _db(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.cloud import firestore  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "google-cloud-firestore is required when HAM_PROJECT_STORE_BACKEND=firestore.",
            ) from exc
        self._client = firestore.Client(**self._kwargs) if self._kwargs else firestore.Client()
        return self._client

    def _coll(self) -> Any:
        return self._db().collection(_COLLECTION)

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
