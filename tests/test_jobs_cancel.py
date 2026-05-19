"""Tests for POST /api/jobs/<job_id>/cancel (Phase 2 Contract 6)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.jobs import router as jobs_router
from src.ham.clerk_auth import HamActor
from src.persistence.builder_runtime_job_store import (
    BuilderRuntimeJobStore,
    CloudRuntimeJob,
    set_builder_runtime_job_store_for_tests,
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _make_actor() -> HamActor:
    return HamActor(
        user_id="user_test",
        org_id=None,
        session_id="sess_test",
        email="user_test@example.com",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _make_job(*, job_id: str = "crjb_cancel", status: str = "running") -> CloudRuntimeJob:
    return CloudRuntimeJob(
        id=job_id,
        workspace_id="ws_test",
        project_id="proj_test",
        status=status,  # type: ignore[arg-type]
        metadata={"plan_id": "pln_test"},
    )


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(jobs_router)

    async def _override_actor() -> HamActor | None:
        return _make_actor()

    app.dependency_overrides[get_ham_clerk_actor] = _override_actor
    return app


class TestJobsCancel:
    def test_cancel_running_job_returns_202(self, tmp_path):
        job_store = BuilderRuntimeJobStore(store_path=tmp_path / "jobs.json")
        job_store.upsert_cloud_runtime_job(_make_job())
        set_builder_runtime_job_store_for_tests(job_store)
        try:
            client = TestClient(_build_app())
            res = client.post(
                "/api/jobs/crjb_cancel/cancel",
                json={},
                params={"workspace_id": "ws_test", "project_id": "proj_test"},
            )
            assert res.status_code == 202
            body = res.json()
            assert body["job_id"] == "crjb_cancel"
            assert body["status"] == "cancelling"
            assert body["cancel_requested_at"]
            stored = job_store.get_cloud_runtime_job(
                workspace_id="ws_test",
                project_id="proj_test",
                job_id="crjb_cancel",
            )
            assert stored is not None
            assert stored.status == "cancelling"
            assert stored.cancel_requested_at == body["cancel_requested_at"]
        finally:
            set_builder_runtime_job_store_for_tests(None)

    def test_cancel_terminal_job_returns_409(self, tmp_path):
        job_store = BuilderRuntimeJobStore(store_path=tmp_path / "jobs.json")
        job_store.upsert_cloud_runtime_job(_make_job(status="completed"))
        set_builder_runtime_job_store_for_tests(job_store)
        try:
            client = TestClient(_build_app())
            res = client.post(
                "/api/jobs/crjb_cancel/cancel",
                json={},
                params={"workspace_id": "ws_test", "project_id": "proj_test"},
            )
            assert res.status_code == 409
            assert res.json()["detail"]["error"]["code"] == "job_already_terminal"
        finally:
            set_builder_runtime_job_store_for_tests(None)

    def test_cancel_missing_job_returns_404(self, tmp_path):
        job_store = BuilderRuntimeJobStore(store_path=tmp_path / "jobs.json")
        set_builder_runtime_job_store_for_tests(job_store)
        try:
            client = TestClient(_build_app())
            res = client.post(
                "/api/jobs/crjb_missing/cancel",
                json={},
                params={"workspace_id": "ws_test", "project_id": "proj_test"},
            )
            assert res.status_code == 404
            assert res.json()["detail"]["error"]["code"] == "JOB_NOT_FOUND"
        finally:
            set_builder_runtime_job_store_for_tests(None)
