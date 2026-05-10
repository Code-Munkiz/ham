"""
Firestore-backed :class:`ProjectStore` (durable hosted persistence).

Wired through :func:`src.persistence.project_store.build_project_store` only
when ``HAM_PROJECT_STORE_BACKEND=firestore``. The default backend remains
:class:`src.persistence.project_store.ProjectStore` (file-backed under
``~/.ham/projects.json``) so local dev keeps working unchanged.

Collection layout::

    {collection}/{project_id}

Defaults: collection ``ham_projects``. The runtime project / database can be
selected via :class:`ProjectStore`-specific env vars, falling back to the
shared workspace-store env vars when unset (one Cloud Run revision should
generally hit a single Firestore database):

- ``HAM_PROJECT_FIRESTORE_PROJECT_ID``  -> ``HAM_FIRESTORE_PROJECT_ID``
- ``HAM_PROJECT_FIRESTORE_DATABASE``    -> ``HAM_FIRESTORE_DATABASE``
- ``HAM_PROJECT_FIRESTORE_COLLECTION``  (default ``ham_projects``)

Stored shape mirrors :meth:`ProjectRecord.model_dump`. No secrets are ever
written to any document touched by this store; ``ProjectRecord`` is an
allowlist of metadata fields (``id``, ``version``, ``name``, ``root``,
``description``, ``metadata``, ``build_lane_enabled``, ``github_repo``).
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from src.registry.projects import ProjectRecord

_LOG = logging.getLogger(__name__)

_PROJECT_FIRESTORE_PROJECT_ENV = "HAM_PROJECT_FIRESTORE_PROJECT_ID"
_PROJECT_FIRESTORE_DATABASE_ENV = "HAM_PROJECT_FIRESTORE_DATABASE"
_PROJECT_FIRESTORE_COLLECTION_ENV = "HAM_PROJECT_FIRESTORE_COLLECTION"

_FALLBACK_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FALLBACK_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"

_DEFAULT_COLLECTION = "ham_projects"


class FirestoreProjectStoreError(RuntimeError):
    """Wrapper for unexpected errors from the Firestore SDK."""


class _FallbackFieldFilter:
    """Duck-typed FieldFilter shim for tests when google-cloud-firestore is absent."""

    def __init__(self, field_path: str, op_string: str, value: Any) -> None:
        self.field_path = field_path
        self.op_string = op_string
        self.value = value


def _resolve_env(primary: str, fallback: str | None = None) -> str | None:
    val = (os.environ.get(primary) or "").strip()
    if val:
        return val
    if fallback is not None:
        val = (os.environ.get(fallback) or "").strip()
        if val:
            return val
    return None


class FirestoreProjectStore:
    """Real Firestore implementation of the project store contract.

    Method shape mirrors :class:`src.persistence.project_store.ProjectStore`
    exactly (``list_projects`` / ``get_project`` / ``register`` / ``remove`` /
    ``make_record`` / ``ensure_default_cursor_metadata``) so callers using the
    :func:`get_project_store` singleton do not need to know which backend is
    active.

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
            or _resolve_env(_PROJECT_FIRESTORE_COLLECTION_ENV)
            or _DEFAULT_COLLECTION
        )
        self._coll_name = coll.strip() or _DEFAULT_COLLECTION
        self._client = client

    # ------------------------------------------------------------------
    # Lazy client + helpers
    # ------------------------------------------------------------------

    def _db(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.cloud import firestore  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - exercised only without SDK
            msg = (
                "google-cloud-firestore is required when "
                "HAM_PROJECT_STORE_BACKEND=firestore."
            )
            raise FirestoreProjectStoreError(msg) from exc
        kwargs: dict[str, Any] = {}
        if self._project:
            kwargs["project"] = self._project
        if self._database:
            kwargs["database"] = self._database
        self._client = firestore.Client(**kwargs) if kwargs else firestore.Client()
        return self._client

    def _coll(self) -> Any:
        return self._db().collection(self._coll_name)

    @staticmethod
    def _wrap(op: str, exc: Exception) -> FirestoreProjectStoreError:
        return FirestoreProjectStoreError(f"firestore project store: {op} failed: {exc}")

    @staticmethod
    def _hydrate(raw: dict[str, Any]) -> dict[str, Any]:
        """Coerce naive datetimes to UTC; ProjectRecord has none today but stay safe."""
        out = dict(raw)
        for k, v in list(out.items()):
            if isinstance(v, datetime) and v.tzinfo is None:
                out[k] = v.replace(tzinfo=UTC)
        return out

    # ------------------------------------------------------------------
    # Public API (mirrors file-backed ProjectStore)
    # ------------------------------------------------------------------

    def list_projects(self) -> list[ProjectRecord]:
        try:
            stream = self._coll().stream()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("list_projects", exc) from exc
        out: list[ProjectRecord] = []
        for snap in stream:
            data = (snap.to_dict() or {}) if hasattr(snap, "to_dict") else {}
            try:
                out.append(ProjectRecord.model_validate(self._hydrate(data)))
            except ValidationError as exc:
                _LOG.warning(
                    "skipping malformed project document (%s): %s",
                    type(exc).__name__,
                    exc,
                )
                continue
        return out

    def get_project(self, project_id: str) -> ProjectRecord | None:
        if not project_id:
            return None
        try:
            snap = self._coll().document(project_id).get()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("get_project", exc) from exc
        if not getattr(snap, "exists", False):
            return None
        data = snap.to_dict() or {}
        try:
            return ProjectRecord.model_validate(self._hydrate(data))
        except ValidationError as exc:
            _LOG.warning(
                "skipping malformed project document %s (%s): %s",
                project_id,
                type(exc).__name__,
                exc,
            )
            return None

    def register(self, record: ProjectRecord) -> ProjectRecord:
        record = self._apply_default_cursor_metadata(record)
        payload = record.model_dump(mode="python")
        try:
            self._coll().document(record.id).set(payload)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("register", exc) from exc
        return record

    def remove(self, project_id: str) -> bool:
        if not project_id:
            return False
        doc_ref = self._coll().document(project_id)
        try:
            snap = doc_ref.get()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("remove", exc) from exc
        if not getattr(snap, "exists", False):
            return False
        try:
            doc_ref.delete()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("remove", exc) from exc
        return True

    def make_record(
        self,
        name: str,
        root: str,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ProjectRecord:
        # Reuse the same id derivation as the file-backed store so a
        # local-dev project record can move into Firestore unchanged.
        from pathlib import Path  # noqa: PLC0415

        from src.persistence.project_store import _project_id  # noqa: PLC0415

        return ProjectRecord(
            id=_project_id(name, root),
            name=name,
            root=str(Path(root).resolve()),
            description=description,
            metadata=metadata or {},
        )

    # ------------------------------------------------------------------
    # Default cursor metadata seeder (parity with file-backed store)
    # ------------------------------------------------------------------

    def ensure_default_cursor_metadata(self) -> bool:
        from src.persistence.project_store import (  # noqa: PLC0415
            _default_cursor_metadata_from_env,
        )

        defaults = _default_cursor_metadata_from_env()
        project_id = defaults.get("project_id")
        if not project_id:
            return False
        project = self.get_project(project_id)
        if project is None:
            project = self._create_default_project_record(defaults)
            if project is None:
                return False
            self.register(project)
            return True
        updated = self._apply_default_cursor_metadata(project)
        if updated == project:
            return False
        self.register(updated)
        return True

    def _apply_default_cursor_metadata(self, record: ProjectRecord) -> ProjectRecord:
        from src.persistence.project_store import (  # noqa: PLC0415
            _default_cursor_metadata_from_env,
        )

        defaults = _default_cursor_metadata_from_env()
        project_id = defaults.get("project_id")
        if not project_id or record.id != project_id:
            return record
        merged = dict(record.metadata or {})
        changed = False
        repo = defaults.get("cursor_cloud_repository")
        if repo and not str(merged.get("cursor_cloud_repository") or "").strip():
            merged["cursor_cloud_repository"] = repo
            changed = True
        ref = defaults.get("cursor_cloud_ref")
        if ref and not str(merged.get("cursor_cloud_ref") or "").strip():
            merged["cursor_cloud_ref"] = ref
            changed = True
        if not changed:
            return record
        return record.model_copy(update={"metadata": merged})

    def _create_default_project_record(
        self, defaults: dict[str, str]
    ) -> ProjectRecord | None:
        from src.persistence.project_store import (  # noqa: PLC0415
            _DEFAULT_PROJECT_ROOT_ENV,
            _project_name_from_id,
        )

        project_id = str(defaults.get("project_id") or "").strip()
        repo = str(defaults.get("cursor_cloud_repository") or "").strip()
        if not project_id or not repo:
            return None
        root = (os.environ.get(_DEFAULT_PROJECT_ROOT_ENV) or "/app").strip() or "/app"
        name = _project_name_from_id(project_id)
        metadata: dict[str, str] = {"cursor_cloud_repository": repo}
        ref = str(defaults.get("cursor_cloud_ref") or "").strip()
        if ref:
            metadata["cursor_cloud_ref"] = ref
        return ProjectRecord(
            id=project_id[:180],
            name=name,
            root=root[:1000],
            description="Default project seeded from environment.",
            metadata=metadata,
        )


__all__ = [
    "FirestoreProjectStore",
    "FirestoreProjectStoreError",
]
