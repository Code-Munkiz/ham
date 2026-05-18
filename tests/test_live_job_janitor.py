"""Tests for run_live_job_janitor() — Phase 1 #3 (ADR-0004).

Verifies the live job-level TTL cancel/reap path against a fake store.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.ham.preview_janitor import run_live_job_janitor
from src.persistence.builder_runtime_job_store import (
    BuilderRuntimeJobStore,
    CloudRuntimeJob,
)

_NOW = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
_TS_NOW = "2026-05-18T12:00:00Z"
_TS_OLD = "2026-01-01T00:00:00Z"


@pytest.fixture()
def store(tmp_path: Path) -> BuilderRuntimeJobStore:
    return BuilderRuntimeJobStore(store_path=tmp_path / "jobs.json")


def _make_job(store: BuilderRuntimeJobStore, *, status: str, created_at: str, ttl_seconds: int = 3600) -> CloudRuntimeJob:
    job = CloudRuntimeJob(
        workspace_id="ws_test",
        project_id="proj_test",
        status=status,  # type: ignore[arg-type]
        created_at=created_at,
        ttl_seconds=ttl_seconds,
    )
    return store.upsert_cloud_runtime_job(job)


class TestLiveJobJanitorCancel:
    def test_timed_out_running_job_is_failed(self, store: BuilderRuntimeJobStore):
        job = _make_job(store, status="running", created_at=_TS_OLD)
        run_live_job_janitor(
            store=store,
            all_workspace_ids=["ws_test"],
            all_project_ids=["proj_test"],
            now=_NOW,
        )
        updated = store.get_cloud_runtime_job(
            workspace_id="ws_test", project_id="proj_test", job_id=job.id
        )
        assert updated is not None
        assert updated.status == "failed"
        assert updated.phase == "janitor_timeout"

    def test_cancel_stores_worker_timeout_error(self, store: BuilderRuntimeJobStore):
        job = _make_job(store, status="running", created_at=_TS_OLD)
        run_live_job_janitor(
            store=store,
            all_workspace_ids=["ws_test"],
            all_project_ids=["proj_test"],
            now=_NOW,
        )
        updated = store.get_cloud_runtime_job(
            workspace_id="ws_test", project_id="proj_test", job_id=job.id
        )
        assert updated is not None
        assert updated.last_error is not None
        assert updated.last_error.error_code == "worker.worker_timeout"
        assert updated.last_error.error_details is not None
        assert "timeout_seconds" in updated.last_error.error_details

    def test_healthy_job_is_kept(self, store: BuilderRuntimeJobStore):
        job = _make_job(store, status="running", created_at=_TS_NOW)
        counts = run_live_job_janitor(
            store=store,
            all_workspace_ids=["ws_test"],
            all_project_ids=["proj_test"],
            now=_NOW,
        )
        assert counts["kept"] >= 1
        unchanged = store.get_cloud_runtime_job(
            workspace_id="ws_test", project_id="proj_test", job_id=job.id
        )
        assert unchanged is not None
        assert unchanged.status == "running"

    def test_timed_out_queued_job_is_cancelled(self, store: BuilderRuntimeJobStore):
        job = _make_job(store, status="queued", created_at=_TS_OLD)
        run_live_job_janitor(
            store=store,
            all_workspace_ids=["ws_test"],
            all_project_ids=["proj_test"],
            now=_NOW,
        )
        updated = store.get_cloud_runtime_job(
            workspace_id="ws_test", project_id="proj_test", job_id=job.id
        )
        assert updated is not None
        assert updated.status == "failed"


class TestLiveJobJanitorReap:
    def test_terminal_job_counted_as_reap(self, store: BuilderRuntimeJobStore):
        _make_job(store, status="completed", created_at=_TS_NOW)
        counts = run_live_job_janitor(
            store=store,
            all_workspace_ids=["ws_test"],
            all_project_ids=["proj_test"],
            now=_NOW,
        )
        assert counts["reap_logged"] >= 1

    def test_terminal_job_not_mutated_in_store(self, store: BuilderRuntimeJobStore):
        job = _make_job(store, status="failed", created_at=_TS_NOW)
        run_live_job_janitor(
            store=store,
            all_workspace_ids=["ws_test"],
            all_project_ids=["proj_test"],
            now=_NOW,
        )
        reloaded = store.get_cloud_runtime_job(
            workspace_id="ws_test", project_id="proj_test", job_id=job.id
        )
        assert reloaded is not None
        assert reloaded.status == "failed"


class TestLiveJobJanitorDryRun:
    def test_dry_run_does_not_mutate_store(self, store: BuilderRuntimeJobStore):
        job = _make_job(store, status="running", created_at=_TS_OLD)
        counts = run_live_job_janitor(
            store=store,
            all_workspace_ids=["ws_test"],
            all_project_ids=["proj_test"],
            now=_NOW,
            dry_run=True,
        )
        assert counts["cancelled"] >= 1
        unchanged = store.get_cloud_runtime_job(
            workspace_id="ws_test", project_id="proj_test", job_id=job.id
        )
        assert unchanged is not None
        assert unchanged.status == "running"  # not modified
