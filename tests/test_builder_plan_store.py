"""Tests for src/persistence/builder_plan_store.py — Plan + approval CRUD."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.ham.builder_plan import Plan, PlanApprovalRecord, Step
from src.persistence.builder_plan_store import BuilderPlanStore

_TS = "2026-05-18T12:00:00Z"


@pytest.fixture()
def store(tmp_path: Path) -> BuilderPlanStore:
    return BuilderPlanStore(store_path=tmp_path / "plans.json")


def _make_plan(*, workspace_id: str = "ws_1", project_id: str = "proj_1", **kw) -> Plan:
    defaults = {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "user_message": "build something",
        "steps": [Step(title="s1", description="d1")],
        "planner_confidence": "high",
        "created_at": _TS,
    }
    defaults.update(kw)
    return Plan(**defaults)


# ── Plan CRUD ──────────────────────────────────────────────────────


class TestPlanCRUD:
    def test_upsert_and_get(self, store: BuilderPlanStore):
        plan = _make_plan()
        store.upsert_plan(plan)
        got = store.get_plan(plan_id=plan.plan_id)
        assert got is not None
        assert got.plan_id == plan.plan_id

    def test_get_nonexistent(self, store: BuilderPlanStore):
        assert store.get_plan(plan_id="pln_nope") is None

    def test_list_filters_by_workspace_and_project(self, store: BuilderPlanStore):
        p1 = _make_plan(workspace_id="ws_a", project_id="proj_a")
        p2 = _make_plan(workspace_id="ws_a", project_id="proj_b")
        p3 = _make_plan(workspace_id="ws_b", project_id="proj_a")
        for p in [p1, p2, p3]:
            store.upsert_plan(p)
        result = store.list_plans(workspace_id="ws_a", project_id="proj_a")
        assert len(result) == 1
        assert result[0].plan_id == p1.plan_id

    def test_upsert_replaces(self, store: BuilderPlanStore):
        plan = _make_plan(plan_id="pln_fixed")
        store.upsert_plan(plan)
        updated = plan.model_copy(update={"user_message": "new message"})
        store.upsert_plan(updated)
        got = store.get_plan(plan_id="pln_fixed")
        assert got is not None
        assert got.user_message == "new message"


# ── Approval record CRUD ──────────────────────────────────────────


class TestApprovalRecordCRUD:
    def test_upsert_and_get(self, store: BuilderPlanStore):
        rec = PlanApprovalRecord(plan_id="pln_1", proposed_at=_TS)
        store.upsert_approval_record(rec)
        got = store.get_approval_record(plan_id="pln_1")
        assert got is not None
        assert got.state == "proposed"

    def test_get_nonexistent(self, store: BuilderPlanStore):
        assert store.get_approval_record(plan_id="pln_nope") is None

    def test_upsert_replaces(self, store: BuilderPlanStore):
        rec = PlanApprovalRecord(plan_id="pln_1", proposed_at=_TS)
        store.upsert_approval_record(rec)
        updated = rec.model_copy(update={"state": "approved", "approved_at": _TS})
        store.upsert_approval_record(updated)
        got = store.get_approval_record(plan_id="pln_1")
        assert got is not None
        assert got.state == "approved"
