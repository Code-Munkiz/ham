"""Persistence for Plan and PlanApprovalRecord — Contract 1 + 2.

File-backed for dev (under ~/.ham/); Protocol-typed; swappable via
set_builder_plan_store_for_tests(). Matches BuilderRuntimeJobStore
pattern exactly.

Spec: docs/PHASE_0_CONTRACTS.md § Contract 1, § Contract 2
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import ValidationError

from src.ham.builder_plan import Plan, PlanApprovalRecord

_DEFAULT_STORE_PATH = Path.home() / ".ham" / "builder_plans.json"


@runtime_checkable
class BuilderPlanStoreProtocol(Protocol):
    def list_plans(self, *, workspace_id: str, project_id: str) -> list[Plan]: ...

    def get_plan(self, *, plan_id: str) -> Plan | None: ...

    def upsert_plan(self, plan: Plan) -> Plan: ...

    def get_approval_record(self, *, plan_id: str) -> PlanApprovalRecord | None: ...

    def upsert_approval_record(self, record: PlanApprovalRecord) -> PlanApprovalRecord: ...


class BuilderPlanStore:
    def __init__(self, store_path: Path | None = None) -> None:
        self._path = Path(store_path) if store_path is not None else _DEFAULT_STORE_PATH

    def list_plans(self, *, workspace_id: str, project_id: str) -> list[Plan]:
        out: list[Plan] = []
        for item in self._load_raw().get("plans", []):
            try:
                rec = Plan.model_validate(item)
            except ValidationError as exc:
                print(
                    f"Warning: skipping malformed plan ({type(exc).__name__}: {exc})",
                    file=sys.stderr,
                )
                continue
            if rec.workspace_id != workspace_id or rec.project_id != project_id:
                continue
            out.append(rec)
        return sorted(out, key=lambda r: r.created_at, reverse=True)

    def get_plan(self, *, plan_id: str) -> Plan | None:
        for item in self._load_raw().get("plans", []):
            try:
                rec = Plan.model_validate(item)
            except ValidationError:
                continue
            if rec.plan_id == plan_id:
                return rec
        return None

    def upsert_plan(self, plan: Plan) -> Plan:
        raw = self._load_raw()
        rows = [r for r in raw.get("plans", []) if str(r.get("plan_id") or "") != plan.plan_id]
        rows.append(plan.model_dump(mode="json"))
        raw["plans"] = rows
        self._save_raw(raw)
        return plan

    def get_approval_record(self, *, plan_id: str) -> PlanApprovalRecord | None:
        for item in self._load_raw().get("approval_records", []):
            try:
                rec = PlanApprovalRecord.model_validate(item)
            except ValidationError:
                continue
            if rec.plan_id == plan_id:
                return rec
        return None

    def upsert_approval_record(self, record: PlanApprovalRecord) -> PlanApprovalRecord:
        raw = self._load_raw()
        rows = [r for r in raw.get("approval_records", []) if str(r.get("plan_id") or "") != record.plan_id]
        rows.append(record.model_dump(mode="json"))
        raw["approval_records"] = rows
        self._save_raw(raw)
        return record

    def _load_raw(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {"plans": [], "approval_records": []}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"plans": [], "approval_records": []}
        if not isinstance(data, dict):
            return {"plans": [], "approval_records": []}
        data.setdefault("plans", [])
        data.setdefault("approval_records", [])
        return data

    def _save_raw(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self._path)


_STORE_SINGLETON: list[BuilderPlanStoreProtocol | None] = [None]

_BACKEND_ENV = "HAM_BUILDER_PLAN_STORE_BACKEND"


def build_builder_plan_store() -> BuilderPlanStoreProtocol:
    """Pick the plan store backend based on env.

    Defaults to the file-backed implementation. ``HAM_BUILDER_PLAN_STORE_BACKEND
    =firestore`` selects :class:`FirestoreBuilderPlanStore` (lazy import).
    """
    backend = (os.environ.get(_BACKEND_ENV) or "").strip().lower()
    if backend == "firestore":
        from src.persistence.firestore_builder_plan_store import (  # noqa: PLC0415
            FirestoreBuilderPlanStore,
        )

        return FirestoreBuilderPlanStore()
    return BuilderPlanStore()


def get_builder_plan_store() -> BuilderPlanStoreProtocol:
    if _STORE_SINGLETON[0] is None:
        _STORE_SINGLETON[0] = build_builder_plan_store()
    return _STORE_SINGLETON[0]


def set_builder_plan_store_for_tests(store: BuilderPlanStoreProtocol | None) -> None:
    _STORE_SINGLETON[0] = store
