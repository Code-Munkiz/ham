"""Firestore-backed BuilderPlanStore — Phase 2.5.

Mirrors the file-backed :class:`BuilderPlanStore` Protocol exactly so callers
do not need to know which backend is active. Selected when
``HAM_BUILDER_PLAN_STORE_BACKEND=firestore`` (default remains file-backed).

Layout::

    {collection}/{plan_id}

The PlanApprovalRecord lives **nested** in the same document under the
``approval`` field. The file backend stores plans and approvals in two
parallel arrays in one JSON file; the Firestore variant denormalises into
the plan document because they are 1:1 and always read together. The
:class:`BuilderPlanStoreProtocol` API is unchanged.

Env vars (per-store first, shared HAM_FIRESTORE_* fallback):

- ``HAM_BUILDER_PLAN_FIRESTORE_PROJECT_ID``  -> ``HAM_FIRESTORE_PROJECT_ID``
- ``HAM_BUILDER_PLAN_FIRESTORE_DATABASE``    -> ``HAM_FIRESTORE_DATABASE``
- ``HAM_BUILDER_PLAN_FIRESTORE_COLLECTION``  (default ``builder_plans``)

See ADR-0014 / docs/PHASE_2_5_DESIGN.md.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from src.ham.builder_plan import Plan, PlanApprovalRecord

_LOG = logging.getLogger(__name__)

_BP_FS_PROJECT_ENV = "HAM_BUILDER_PLAN_FIRESTORE_PROJECT_ID"
_BP_FS_DATABASE_ENV = "HAM_BUILDER_PLAN_FIRESTORE_DATABASE"
_BP_FS_COLLECTION_ENV = "HAM_BUILDER_PLAN_FIRESTORE_COLLECTION"

_FALLBACK_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FALLBACK_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"

_DEFAULT_COLLECTION = "builder_plans"

_APPROVAL_FIELD = "approval"


class FirestoreBuilderPlanStoreError(RuntimeError):
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


class FirestoreBuilderPlanStore:
    """Firestore implementation of :class:`BuilderPlanStoreProtocol`.

    Plan and PlanApprovalRecord are co-located in one document per plan.
    The document ID is the ``plan_id``; the approval record lives under the
    ``approval`` field as a nested map.
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
            _BP_FS_PROJECT_ENV, _FALLBACK_PROJECT_ENV,
        )
        self._database = database or _resolve_env(
            _BP_FS_DATABASE_ENV, _FALLBACK_DATABASE_ENV,
        )
        coll = (
            collection
            or _resolve_env(_BP_FS_COLLECTION_ENV)
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
                "HAM_BUILDER_PLAN_STORE_BACKEND=firestore."
            )
            raise FirestoreBuilderPlanStoreError(msg) from exc
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
    def _wrap(op: str, exc: Exception) -> FirestoreBuilderPlanStoreError:
        return FirestoreBuilderPlanStoreError(
            f"firestore builder plan store: {op} failed: {exc}",
        )

    @staticmethod
    def _hydrate_datetimes(raw: dict[str, Any]) -> dict[str, Any]:
        """Normalise naive datetimes to tz-aware UTC."""
        out = dict(raw)
        for k, v in list(out.items()):
            if isinstance(v, datetime) and v.tzinfo is None:
                out[k] = v.replace(tzinfo=UTC)
        return out

    @classmethod
    def _validate_plan(cls, snap: Any) -> Plan | None:
        data = snap.to_dict() or {}
        # Strip the nested approval field before validating the Plan
        plan_data = {k: v for k, v in data.items() if k != _APPROVAL_FIELD}
        try:
            return Plan.model_validate(cls._hydrate_datetimes(plan_data))
        except ValidationError as exc:
            doc_id = getattr(snap, "id", "<unknown>")
            _LOG.warning(
                "skipping malformed plan %s (%s): %s",
                doc_id,
                type(exc).__name__,
                exc,
            )
            return None

    @classmethod
    def _validate_approval(cls, snap: Any) -> PlanApprovalRecord | None:
        data = snap.to_dict() or {}
        approval_raw = data.get(_APPROVAL_FIELD)
        if not isinstance(approval_raw, dict):
            return None
        # Inject the plan_id from the document ID since we strip it on write.
        hydrated = cls._hydrate_datetimes(approval_raw)
        hydrated["plan_id"] = getattr(snap, "id", hydrated.get("plan_id", ""))
        try:
            return PlanApprovalRecord.model_validate(hydrated)
        except ValidationError as exc:
            doc_id = getattr(snap, "id", "<unknown>")
            _LOG.warning(
                "skipping malformed approval for plan %s (%s): %s",
                doc_id,
                type(exc).__name__,
                exc,
            )
            return None

    @staticmethod
    def _approval_payload(record: PlanApprovalRecord) -> dict[str, Any]:
        # Drop plan_id from the nested map since the document already
        # identifies the plan; keep the stored shape minimal.
        payload = record.model_dump(mode="json", exclude={"plan_id"})
        return payload

    # ------------------------------------------------------------------
    # Public API (mirrors file-backed BuilderPlanStore)
    # ------------------------------------------------------------------

    def list_plans(self, *, workspace_id: str, project_id: str) -> list[Plan]:
        ws = (workspace_id or "").strip()
        proj = (project_id or "").strip()
        if not ws or not proj:
            return []
        try:
            stream = self._coll().stream()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("list_plans", exc) from exc
        out: list[Plan] = []
        for snap in stream:
            data = (snap.to_dict() or {}) if hasattr(snap, "to_dict") else {}
            if str(data.get("workspace_id") or "") != ws:
                continue
            if str(data.get("project_id") or "") != proj:
                continue
            plan = self._validate_plan(snap)
            if plan is not None:
                out.append(plan)
        return sorted(out, key=lambda r: r.created_at, reverse=True)

    def get_plan(self, *, plan_id: str) -> Plan | None:
        pid = (plan_id or "").strip()
        if not pid:
            return None
        try:
            snap = self._coll().document(pid).get()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("get_plan", exc) from exc
        if not getattr(snap, "exists", False):
            return None
        return self._validate_plan(snap)

    def upsert_plan(self, plan: Plan) -> Plan:
        # Merge-write so we don't clobber an existing nested approval map.
        # Explicitly exclude the approval field from the plan payload — the
        # approval lifecycle is managed via upsert_approval_record only.
        payload = plan.model_dump(mode="json")
        payload.pop(_APPROVAL_FIELD, None)
        try:
            self._coll().document(plan.plan_id).set(payload, merge=True)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("upsert_plan", exc) from exc
        return plan

    def get_approval_record(self, *, plan_id: str) -> PlanApprovalRecord | None:
        pid = (plan_id or "").strip()
        if not pid:
            return None
        try:
            snap = self._coll().document(pid).get()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("get_approval_record", exc) from exc
        if not getattr(snap, "exists", False):
            return None
        return self._validate_approval(snap)

    def upsert_approval_record(self, record: PlanApprovalRecord) -> PlanApprovalRecord:
        payload = self._approval_payload(record)
        try:
            # Merge-write so the rest of the plan document is preserved.
            self._coll().document(record.plan_id).set(
                {_APPROVAL_FIELD: payload},
                merge=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("upsert_approval_record", exc) from exc
        return record
