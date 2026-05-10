"""
Firestore-backed :class:`ControlPlaneRunStore` (durable hosted persistence).

Wired through :func:`src.persistence.control_plane_run.build_control_plane_run_store`
only when ``HAM_CONTROL_PLANE_RUN_STORE_BACKEND=firestore``. The default
backend remains the file-backed :class:`ControlPlaneRunStore` (one JSON per
``ham_run_id`` under ``HAM_CONTROL_PLANE_RUNS_DIR``), so local dev keeps
working unchanged.

Collection layout::

    {collection}/{ham_run_id}

Defaults: collection ``ham_control_plane_runs``. The runtime project /
database can be selected via control-plane-specific env vars, falling back
to the shared workspace-store env vars when unset:

- ``HAM_CONTROL_PLANE_RUN_FIRESTORE_PROJECT_ID``  -> ``HAM_FIRESTORE_PROJECT_ID``
- ``HAM_CONTROL_PLANE_RUN_FIRESTORE_DATABASE``    -> ``HAM_FIRESTORE_DATABASE``
- ``HAM_CONTROL_PLANE_RUN_FIRESTORE_COLLECTION``  (default
  ``ham_control_plane_runs``)

Stored shape mirrors :meth:`ControlPlaneRun.model_dump(mode="json", exclude_none=True)`
so legacy documents that predate the Build Lane PR fields
(``pr_url`` / ``pr_branch`` / ``pr_commit_sha`` / ``build_outcome``) load with
the model's ``None`` defaults. No secrets are persisted; ``ControlPlaneRun``
is a metadata-only Pydantic model with ``extra="forbid"``.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.persistence.control_plane_run import (
    ControlPlaneRun,
    _json_ready,
    cap_error_summary,
    cap_status_reason,
    cap_summary,
)

_LOG = logging.getLogger(__name__)

_CP_FS_PROJECT_ENV = "HAM_CONTROL_PLANE_RUN_FIRESTORE_PROJECT_ID"
_CP_FS_DATABASE_ENV = "HAM_CONTROL_PLANE_RUN_FIRESTORE_DATABASE"
_CP_FS_COLLECTION_ENV = "HAM_CONTROL_PLANE_RUN_FIRESTORE_COLLECTION"

_FALLBACK_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FALLBACK_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"

_DEFAULT_COLLECTION = "ham_control_plane_runs"


class FirestoreControlPlaneRunStoreError(RuntimeError):
    """Wrapper for unexpected errors from the Firestore SDK."""


class _FallbackFieldFilter:
    """Duck-typed FieldFilter shim used when google-cloud-firestore is absent."""

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


class FirestoreControlPlaneRunStore:
    """Real Firestore implementation of the control-plane run store contract.

    Method shape mirrors :class:`ControlPlaneRunStore` exactly (``get`` /
    ``find_by_project_and_external`` / ``find_by_provider_and_external`` /
    ``list_for_project`` / ``save``) so callers using either store do not need
    to know which backend is active. ``save`` still honors the
    ``project_root_for_mirror`` filesystem mirror so project-local audit
    tracking continues to work even when the canonical store is hosted.

    The constructor accepts an injected ``client`` for tests; in production
    the real ``google.cloud.firestore.Client`` is constructed lazily on first
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
            _CP_FS_PROJECT_ENV, _FALLBACK_PROJECT_ENV,
        )
        self._database = database or _resolve_env(
            _CP_FS_DATABASE_ENV, _FALLBACK_DATABASE_ENV,
        )
        coll = (
            collection
            or _resolve_env(_CP_FS_COLLECTION_ENV)
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
                "HAM_CONTROL_PLANE_RUN_STORE_BACKEND=firestore."
            )
            raise FirestoreControlPlaneRunStoreError(msg) from exc
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
    def _wrap(op: str, exc: Exception) -> FirestoreControlPlaneRunStoreError:
        return FirestoreControlPlaneRunStoreError(
            f"firestore control-plane run store: {op} failed: {exc}",
        )

    @staticmethod
    def _hydrate(raw: dict[str, Any]) -> dict[str, Any]:
        """Coerce naive datetimes to UTC.

        ``ControlPlaneRun`` carries timestamps as ISO-8601 strings today, but
        any future or operator-injected ``datetime`` value is normalized to
        tz-aware UTC for consistency with the workspace store.
        """
        out = dict(raw)
        for k, v in list(out.items()):
            if isinstance(v, datetime) and v.tzinfo is None:
                out[k] = v.replace(tzinfo=UTC)
        return out

    @classmethod
    def _validate(cls, snap: Any, *, op: str) -> ControlPlaneRun | None:
        data = snap.to_dict() or {}
        try:
            return ControlPlaneRun.model_validate(cls._hydrate(data))
        except ValidationError as exc:
            doc_id = getattr(snap, "id", "<unknown>")
            _LOG.warning(
                "%s: skipping malformed control-plane run %s (%s): %s",
                op,
                doc_id,
                type(exc).__name__,
                exc,
            )
            return None

    # ------------------------------------------------------------------
    # Public API (mirrors file-backed ControlPlaneRunStore)
    # ------------------------------------------------------------------

    def get(self, ham_run_id: str) -> ControlPlaneRun | None:
        rid = (ham_run_id or "").strip()
        if not rid:
            return None
        try:
            snap = self._coll().document(rid).get()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("get", exc) from exc
        if not getattr(snap, "exists", False):
            return None
        return self._validate(snap, op="get")

    def find_by_project_and_external(
        self,
        *,
        project_id: str,
        provider: str,
        external_id: str,
    ) -> ControlPlaneRun | None:
        eid = (external_id or "").strip()
        pid = (project_id or "").strip()
        prov = (provider or "").strip()
        if not eid or not pid or not prov:
            return None
        try:
            stream = self._coll().stream()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("find_by_project_and_external", exc) from exc
        for snap in stream:
            data = (snap.to_dict() or {}) if hasattr(snap, "to_dict") else {}
            if str(data.get("project_id") or "") != pid:
                continue
            if str(data.get("provider") or "") != prov:
                continue
            if str(data.get("external_id") or "") != eid:
                continue
            run = self._validate(snap, op="find_by_project_and_external")
            if run is not None:
                return run
        return None

    def find_by_provider_and_external(
        self,
        *,
        provider: str,
        external_id: str,
    ) -> ControlPlaneRun | None:
        eid = (external_id or "").strip()
        prov = (provider or "").strip()
        if not eid or not prov:
            return None
        try:
            stream = self._coll().stream()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("find_by_provider_and_external", exc) from exc
        for snap in stream:
            data = (snap.to_dict() or {}) if hasattr(snap, "to_dict") else {}
            if str(data.get("provider") or "") != prov:
                continue
            if str(data.get("external_id") or "") != eid:
                continue
            run = self._validate(snap, op="find_by_provider_and_external")
            if run is not None:
                return run
        return None

    def list_for_project(
        self,
        project_id: str,
        *,
        provider: str | None = None,
        limit: int = 100,
    ) -> list[ControlPlaneRun]:
        pid = (project_id or "").strip()
        if not pid:
            return []
        cap = max(1, min(int(limit), 500))
        prov = provider.strip() if (provider and str(provider).strip()) else None
        try:
            stream = self._coll().stream()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("list_for_project", exc) from exc

        # Match the file-backed store: collect → filter → sort by
        # ``ham_run_id`` descending → cap. This preserves the "filename
        # reverse-sort" semantics callers rely on without requiring a
        # composite Firestore index.
        rows: list[ControlPlaneRun] = []
        for snap in stream:
            data = (snap.to_dict() or {}) if hasattr(snap, "to_dict") else {}
            if str(data.get("project_id") or "") != pid:
                continue
            if prov and str(data.get("provider") or "") != prov:
                continue
            run = self._validate(snap, op="list_for_project")
            if run is None:
                continue
            rows.append(run)
        rows.sort(key=lambda r: r.ham_run_id, reverse=True)
        return rows[:cap]

    def save(
        self,
        run: ControlPlaneRun,
        *,
        project_root_for_mirror: str | None = None,
    ) -> None:
        # Apply the same caps the file-backed store applies before persisting,
        # so the on-disk and Firestore document shapes stay byte-identical.
        run = run.model_copy(
            update={
                "summary": cap_summary(run.summary),
                "error_summary": cap_error_summary(run.error_summary),
                "status_reason": cap_status_reason(run.status_reason),
            },
        )
        # ``_json_ready`` returns ``model_dump(mode="json", exclude_none=True)``
        # so legacy load semantics survive: writes drop ``None`` keys; reads
        # default missing keys via the Pydantic model.
        payload = _json_ready(run)
        if not isinstance(payload, dict):
            raise self._wrap(
                "save", TypeError(f"unexpected payload type: {type(payload).__name__}"),
            )
        try:
            self._coll().document(run.ham_run_id).set(payload)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("save", exc) from exc

        if project_root_for_mirror and str(project_root_for_mirror).strip():
            self._write_mirror(run, payload, project_root_for_mirror)

    @staticmethod
    def _write_mirror(
        run: ControlPlaneRun,
        payload: dict[str, Any],
        project_root_for_mirror: str,
    ) -> None:
        # Best-effort filesystem mirror so project-local audit tracking still
        # works when the canonical store is hosted. Mirrors are advisory only;
        # any error is swallowed (parity with the file-backed implementation).
        import json  # noqa: PLC0415

        try:
            pr = Path(project_root_for_mirror).expanduser().resolve()
            if not pr.is_dir():
                return
            mp = pr / ".ham" / "control_plane" / "runs" / f"{run.ham_run_id}.json"
            mp.parent.mkdir(parents=True, exist_ok=True)
            mtmp = mp.with_suffix(".json.tmp")
            mtmp.write_text(
                json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(mtmp, mp)
        except OSError:
            return


__all__ = [
    "FirestoreControlPlaneRunStore",
    "FirestoreControlPlaneRunStoreError",
]
