"""Integration tests for POST /api/plans/<plan_id>/approve — Phase 2 PR 4."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.plans import router as plans_router
from src.ham.builder_plan import Plan, PlanApprovalRecord, Step
from src.ham.builder_plan_approval_service import set_worker_enqueue_for_tests
from src.persistence.builder_plan_store import BuilderPlanStore, set_builder_plan_store_for_tests
from src.persistence.builder_runtime_job_store import (
    BuilderRuntimeJobStore,
    CloudRuntimeJob,
    set_builder_runtime_job_store_for_tests,
)
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    ProjectSource,
    set_builder_source_store_for_tests,
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _make_plan(
    *,
    plan_id: str = "pln_test",
    snapshot_id: str | None = "ssnp_a",
) -> Plan:
    return Plan(
        plan_id=plan_id,
        workspace_id="ws_test",
        project_id="proj_test",
        user_message="add login",
        source_snapshot_id=snapshot_id,
        steps=[Step(title="Step 1", description="Do thing")],
        planner_confidence="high",
    )


class _CaptureEnqueue:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def enqueue(self, envelope, *, job: CloudRuntimeJob) -> None:
        self.calls.append((envelope.plan_id, envelope.job_id))


@pytest.fixture()
def plans_client(tmp_path: Path) -> TestClient:
    plan_store = BuilderPlanStore(store_path=tmp_path / "plans.json")
    job_store = BuilderRuntimeJobStore(store_path=tmp_path / "jobs.json")
    source_store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_plan_store_for_tests(plan_store)
    set_builder_runtime_job_store_for_tests(job_store)
    set_builder_source_store_for_tests(source_store)
    capture = _CaptureEnqueue()
    set_worker_enqueue_for_tests(capture)

    app = FastAPI()
    app.include_router(plans_router)
    client = TestClient(app)
    client._capture_enqueue = capture  # type: ignore[attr-defined]
    client._plan_store = plan_store  # type: ignore[attr-defined]
    client._job_store = job_store  # type: ignore[attr-defined]
    client._source_store = source_store  # type: ignore[attr-defined]

    yield client

    set_builder_plan_store_for_tests(None)
    set_builder_runtime_job_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_worker_enqueue_for_tests(None)


class TestApprovePlan:
    def test_approve_returns_202_and_creates_job(self, plans_client: TestClient) -> None:
        plan = _make_plan()
        plans_client._plan_store.upsert_plan(plan)  # type: ignore[attr-defined]
        plans_client._plan_store.upsert_approval_record(  # type: ignore[attr-defined]
            PlanApprovalRecord(plan_id=plan.plan_id, state="proposed", proposed_at=_utc_now_iso())
        )
        plans_client._source_store.upsert_project_source(  # type: ignore[attr-defined]
            ProjectSource(
                project_id=plan.project_id,
                workspace_id=plan.workspace_id,
                status="ready",
                active_snapshot_id="ssnp_a",
            )
        )

        res = plans_client.post(f"/api/plans/{plan.plan_id}/approve")
        assert res.status_code == 202, res.text
        body = res.json()
        assert body["plan_id"] == plan.plan_id
        assert body["job_id"].startswith("crjb_")
        assert body["approval_state"] == "approved"

        record = plans_client._plan_store.get_approval_record(plan_id=plan.plan_id)  # type: ignore[attr-defined]
        assert record is not None
        assert record.state == "approved"

        jobs = plans_client._job_store.list_cloud_runtime_jobs(  # type: ignore[attr-defined]
            workspace_id=plan.workspace_id,
            project_id=plan.project_id,
        )
        assert len(jobs) == 1
        assert jobs[0].metadata.get("plan_id") == plan.plan_id

    def test_approve_plan_stale_returns_409(self, plans_client: TestClient) -> None:
        plan = _make_plan(snapshot_id="ssnp_old")
        plans_client._plan_store.upsert_plan(plan)  # type: ignore[attr-defined]
        plans_client._plan_store.upsert_approval_record(  # type: ignore[attr-defined]
            PlanApprovalRecord(plan_id=plan.plan_id, state="proposed", proposed_at=_utc_now_iso())
        )
        plans_client._source_store.upsert_project_source(  # type: ignore[attr-defined]
            ProjectSource(
                project_id=plan.project_id,
                workspace_id=plan.workspace_id,
                status="ready",
                active_snapshot_id="ssnp_new",
            )
        )

        res = plans_client.post(f"/api/plans/{plan.plan_id}/approve")
        assert res.status_code == 409
        assert res.json()["detail"]["error"]["code"] == "plan_stale"

    def test_approve_project_busy_returns_409(self, plans_client: TestClient) -> None:
        plan = _make_plan()
        plans_client._plan_store.upsert_plan(plan)  # type: ignore[attr-defined]
        plans_client._plan_store.upsert_approval_record(  # type: ignore[attr-defined]
            PlanApprovalRecord(plan_id=plan.plan_id, state="proposed", proposed_at=_utc_now_iso())
        )
        plans_client._source_store.upsert_project_source(  # type: ignore[attr-defined]
            ProjectSource(
                project_id=plan.project_id,
                workspace_id=plan.workspace_id,
                status="ready",
                active_snapshot_id="ssnp_a",
            )
        )
        plans_client._job_store.upsert_cloud_runtime_job(  # type: ignore[attr-defined]
            CloudRuntimeJob(
                id="crjb_busy",
                workspace_id=plan.workspace_id,
                project_id=plan.project_id,
                status="running",
            )
        )

        res = plans_client.post(f"/api/plans/{plan.plan_id}/approve")
        assert res.status_code == 409
        assert res.json()["detail"]["error"]["code"] == "project_busy"
