"""Firestore-backed BuilderRuntimeStore.

Mirrors the file-backed :class:`BuilderRuntimeStore` Protocol so ham-api and
ham-native-builder-worker share runtime sessions and preview endpoints across
Cloud Run instances. Selected when ``HAM_BUILDER_RUNTIME_STORE_BACKEND=firestore``
(default remains file-backed for local/dev/tests).

Layout (one document per record id)::

    {sessions_collection}/{runtime_session_id}
    {preview_endpoints_collection}/{preview_endpoint_id}

Env vars (per-store first, shared HAM_FIRESTORE_* fallback):

- ``HAM_BUILDER_RUNTIME_FIRESTORE_PROJECT_ID``  -> ``HAM_FIRESTORE_PROJECT_ID``
- ``HAM_BUILDER_RUNTIME_FIRESTORE_DATABASE``    -> ``HAM_FIRESTORE_DATABASE``
- ``HAM_BUILDER_RUNTIME_FIRESTORE_SESSIONS_COLLECTION`` (default ``builder_runtime_sessions``)
- ``HAM_BUILDER_RUNTIME_FIRESTORE_PREVIEW_ENDPOINTS_COLLECTION`` (default ``builder_preview_endpoints``)

User-facing APIs surface only safe preview URLs — never raw pod IPs or internal upstreams.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from src.persistence.builder_runtime_store import (
    PreviewEndpoint,
    RuntimeSession,
    _utc_now_iso,
)

_LOG = logging.getLogger(__name__)

_BR_FS_PROJECT_ENV = "HAM_BUILDER_RUNTIME_FIRESTORE_PROJECT_ID"
_BR_FS_DATABASE_ENV = "HAM_BUILDER_RUNTIME_FIRESTORE_DATABASE"
_BR_FS_SESSIONS_ENV = "HAM_BUILDER_RUNTIME_FIRESTORE_SESSIONS_COLLECTION"
_BR_FS_ENDPOINTS_ENV = "HAM_BUILDER_RUNTIME_FIRESTORE_PREVIEW_ENDPOINTS_COLLECTION"

_FALLBACK_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FALLBACK_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"

_DEFAULT_SESSIONS_COLLECTION = "builder_runtime_sessions"
_DEFAULT_ENDPOINTS_COLLECTION = "builder_preview_endpoints"


class FirestoreBuilderRuntimeStoreError(RuntimeError):
    """Wrapper for unexpected errors from the Firestore SDK."""


def _resolve_env(primary: str, fallback: str | None = None) -> str | None:
    val = (os.environ.get(primary) or "").strip()
    if val:
        return val
    if fallback is not None:
        val = (os.environ.get(fallback) or "").strip()
        if val:
            return val
    return None


class FirestoreBuilderRuntimeStore:
    """Firestore implementation of :class:`BuilderRuntimeStoreProtocol`."""

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str | None = None,
        sessions_collection: str | None = None,
        preview_endpoints_collection: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._project = project or _resolve_env(_BR_FS_PROJECT_ENV, _FALLBACK_PROJECT_ENV)
        self._database = database or _resolve_env(_BR_FS_DATABASE_ENV, _FALLBACK_DATABASE_ENV)
        self._sessions_coll = (
            sessions_collection
            or _resolve_env(_BR_FS_SESSIONS_ENV)
            or _DEFAULT_SESSIONS_COLLECTION
        ).strip() or _DEFAULT_SESSIONS_COLLECTION
        self._endpoints_coll = (
            preview_endpoints_collection
            or _resolve_env(_BR_FS_ENDPOINTS_ENV)
            or _DEFAULT_ENDPOINTS_COLLECTION
        ).strip() or _DEFAULT_ENDPOINTS_COLLECTION
        self._client = client

    def _db(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.cloud import firestore  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            msg = (
                "google-cloud-firestore is required when "
                "HAM_BUILDER_RUNTIME_STORE_BACKEND=firestore."
            )
            raise FirestoreBuilderRuntimeStoreError(msg) from exc
        kwargs: dict[str, Any] = {}
        if self._project:
            kwargs["project"] = self._project
        if self._database:
            kwargs["database"] = self._database
        self._client = firestore.Client(**kwargs) if kwargs else firestore.Client()
        return self._client

    def _sessions(self) -> Any:
        return self._db().collection(self._sessions_coll)

    def _endpoints(self) -> Any:
        return self._db().collection(self._endpoints_coll)

    @staticmethod
    def _wrap(op: str, exc: Exception) -> FirestoreBuilderRuntimeStoreError:
        return FirestoreBuilderRuntimeStoreError(
            f"firestore builder runtime store: {op} failed: {exc}",
        )

    @staticmethod
    def _hydrate_datetimes(raw: dict[str, Any]) -> dict[str, Any]:
        out = dict(raw)
        for k, v in list(out.items()):
            if isinstance(v, datetime) and v.tzinfo is None:
                out[k] = v.replace(tzinfo=UTC)
        return out

    @classmethod
    def _validate_session(cls, snap: Any) -> RuntimeSession | None:
        data = snap.to_dict() or {}
        try:
            return RuntimeSession.model_validate(cls._hydrate_datetimes(data))
        except ValidationError as exc:
            doc_id = getattr(snap, "id", "<unknown>")
            _LOG.warning(
                "skipping malformed runtime session %s (%s): %s",
                doc_id,
                type(exc).__name__,
                exc,
            )
            return None

    @classmethod
    def _validate_endpoint(cls, snap: Any) -> PreviewEndpoint | None:
        data = snap.to_dict() or {}
        try:
            return PreviewEndpoint.model_validate(cls._hydrate_datetimes(data))
        except ValidationError as exc:
            doc_id = getattr(snap, "id", "<unknown>")
            _LOG.warning(
                "skipping malformed preview endpoint %s (%s): %s",
                doc_id,
                type(exc).__name__,
                exc,
            )
            return None

    def list_runtime_sessions(self, *, workspace_id: str, project_id: str) -> list[RuntimeSession]:
        ws = (workspace_id or "").strip()
        proj = (project_id or "").strip()
        if not ws or not proj:
            return []
        try:
            stream = self._sessions().stream()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("list_runtime_sessions", exc) from exc
        out: list[RuntimeSession] = []
        for snap in stream:
            data = (snap.to_dict() or {}) if hasattr(snap, "to_dict") else {}
            if str(data.get("workspace_id") or "") != ws:
                continue
            if str(data.get("project_id") or "") != proj:
                continue
            row = self._validate_session(snap)
            if row is not None:
                out.append(row)
        return sorted(out, key=lambda r: (r.updated_at, r.id), reverse=True)

    def list_preview_endpoints(self, *, workspace_id: str, project_id: str) -> list[PreviewEndpoint]:
        ws = (workspace_id or "").strip()
        proj = (project_id or "").strip()
        if not ws or not proj:
            return []
        try:
            stream = self._endpoints().stream()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("list_preview_endpoints", exc) from exc
        out: list[PreviewEndpoint] = []
        for snap in stream:
            data = (snap.to_dict() or {}) if hasattr(snap, "to_dict") else {}
            if str(data.get("workspace_id") or "") != ws:
                continue
            if str(data.get("project_id") or "") != proj:
                continue
            row = self._validate_endpoint(snap)
            if row is not None:
                out.append(row)
        return sorted(out, key=lambda r: (r.last_checked_at or "", r.id), reverse=True)

    def upsert_runtime_session(self, record: RuntimeSession) -> RuntimeSession:
        payload = record.model_dump(mode="json")
        try:
            self._sessions().document(record.id).set(payload)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("upsert_runtime_session", exc) from exc
        return record

    def upsert_preview_endpoint(self, record: PreviewEndpoint) -> PreviewEndpoint:
        payload = record.model_dump(mode="json")
        try:
            self._endpoints().document(record.id).set(payload)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("upsert_preview_endpoint", exc) from exc
        return record

    def upsert_local_runtime_session(
        self,
        *,
        workspace_id: str,
        project_id: str,
        source_snapshot_id: str | None,
        message: str | None = None,
    ) -> RuntimeSession:
        existing = self.get_active_runtime_session(workspace_id=workspace_id, project_id=project_id)
        if existing is None:
            existing = RuntimeSession(
                workspace_id=workspace_id,
                project_id=project_id,
            )
        existing.mode = "local"
        existing.status = "running"
        existing.health = "healthy"
        existing.snapshot_id = source_snapshot_id
        existing.message = message
        if not existing.started_at:
            existing.started_at = _utc_now_iso()
        existing.expires_at = None
        existing.updated_at = _utc_now_iso()
        return self.upsert_runtime_session(existing)

    def get_active_runtime_session(
        self,
        *,
        workspace_id: str,
        project_id: str,
    ) -> RuntimeSession | None:
        candidates: list[RuntimeSession] = []
        for row in self.list_runtime_sessions(workspace_id=workspace_id, project_id=project_id):
            if row.status in {"stopped", "expired"}:
                continue
            candidates.append(row)
        if not candidates:
            return None
        for row in candidates:
            if row.mode == "cloud":
                return row
        return candidates[0]

    def get_latest_runtime_session(
        self,
        *,
        workspace_id: str,
        project_id: str,
        mode: str | None = None,
    ) -> RuntimeSession | None:
        for row in self.list_runtime_sessions(workspace_id=workspace_id, project_id=project_id):
            if mode is not None and row.mode != mode:
                continue
            return row
        return None

    def get_active_preview_endpoint(
        self,
        *,
        workspace_id: str,
        project_id: str,
        runtime_session_id: str,
    ) -> PreviewEndpoint | None:
        for row in self.list_preview_endpoints(workspace_id=workspace_id, project_id=project_id):
            if row.runtime_session_id != runtime_session_id:
                continue
            if row.status in {"revoked", "unavailable"}:
                continue
            return row
        return None

    def clear_local_preview(
        self,
        *,
        workspace_id: str,
        project_id: str,
    ) -> tuple[RuntimeSession | None, PreviewEndpoint | None]:
        runtime = self.get_active_runtime_session(workspace_id=workspace_id, project_id=project_id)
        endpoint: PreviewEndpoint | None = None
        if runtime is not None:
            endpoint = self.get_active_preview_endpoint(
                workspace_id=workspace_id,
                project_id=project_id,
                runtime_session_id=runtime.id,
            )
            runtime.status = "stopped"
            runtime.health = "unknown"
            runtime.updated_at = _utc_now_iso()
            runtime.preview_endpoint_id = None
            self.upsert_runtime_session(runtime)
        if endpoint is not None:
            endpoint.status = "revoked"
            endpoint.last_checked_at = _utc_now_iso()
            self.upsert_preview_endpoint(endpoint)
        return runtime, endpoint

    def request_cloud_runtime_session(
        self,
        *,
        workspace_id: str,
        project_id: str,
        source_snapshot_id: str | None,
        requested_by: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeSession:
        existing = self.get_latest_runtime_session(
            workspace_id=workspace_id,
            project_id=project_id,
            mode="cloud",
        )
        if existing is None:
            existing = RuntimeSession(
                workspace_id=workspace_id,
                project_id=project_id,
                mode="cloud",
            )
        existing.mode = "cloud"
        existing.status = "queued"
        existing.health = "unknown"
        existing.snapshot_id = source_snapshot_id
        existing.message = "Cloud runtime request recorded. Preparing live preview runtime."
        if not existing.started_at:
            existing.started_at = _utc_now_iso()
        existing.updated_at = _utc_now_iso()
        existing.metadata = {
            "requested_at": existing.updated_at,
            **(existing.metadata or {}),
            **(metadata or {}),
        }
        if requested_by:
            existing.metadata["requested_by"] = requested_by
        return self.upsert_runtime_session(existing)

    def clear_cloud_runtime(self, *, workspace_id: str, project_id: str) -> RuntimeSession | None:
        runtime = self.get_latest_runtime_session(
            workspace_id=workspace_id,
            project_id=project_id,
            mode="cloud",
        )
        if runtime is None:
            return None
        runtime.status = "expired"
        runtime.health = "unknown"
        runtime.message = "Cloud runtime request cleared."
        runtime.updated_at = _utc_now_iso()
        runtime.preview_endpoint_id = None
        runtime.metadata = {**(runtime.metadata or {}), "cleared_at": runtime.updated_at}
        return self.upsert_runtime_session(runtime)
