"""Migration tests for CloudRuntimeJob v1.0.0 → v1.1.0.

Ensures old records (no last_error, free-string status) load successfully,
and new records with last_error populate deprecated string fields on write.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ham.builder_plan import ErrorEnvelope
from src.persistence.builder_runtime_job_store import (
    BuilderRuntimeJobStore,
    CloudRuntimeJob,
)

_TS = "2026-05-18T12:00:00Z"


@pytest.fixture()
def store(tmp_path: Path) -> BuilderRuntimeJobStore:
    return BuilderRuntimeJobStore(store_path=tmp_path / "jobs.json")


# ── Old → new migration ──────────────────────────────────────────


class TestOldRecordMigration:
    def test_old_record_without_new_fields_loads(self, store: BuilderRuntimeJobStore):
        """v1.0.0 records (no last_error, cancel_*) load with defaults."""
        old_record = {
            "id": "crjb_old",
            "version": "1.0.0",
            "workspace_id": "ws_1",
            "project_id": "proj_1",
            "status": "completed",
            "phase": "received",
            "provider": "disabled",
            "created_at": _TS,
            "updated_at": _TS,
            "metadata": {},
        }
        raw = {"cloud_runtime_jobs": [old_record]}
        store._path.parent.mkdir(parents=True, exist_ok=True)
        store._path.write_text(json.dumps(raw), encoding="utf-8")

        jobs = store.list_cloud_runtime_jobs(workspace_id="ws_1", project_id="proj_1")
        assert len(jobs) == 1
        job = jobs[0]
        assert job.id == "crjb_old"
        assert job.last_error is None
        assert job.cancel_requested_at is None
        assert job.cancel_reason is None

    def test_old_record_with_unknown_status_gets_normalized(self, store: BuilderRuntimeJobStore):
        """Legacy records with non-Literal status values are normalized."""
        old_record = {
            "id": "crjb_legacy",
            "version": "1.0.0",
            "workspace_id": "ws_1",
            "project_id": "proj_1",
            "status": "some_old_status",
            "phase": "received",
            "provider": "disabled",
            "created_at": _TS,
            "updated_at": _TS,
            "metadata": {},
        }
        raw = {"cloud_runtime_jobs": [old_record]}
        store._path.parent.mkdir(parents=True, exist_ok=True)
        store._path.write_text(json.dumps(raw), encoding="utf-8")

        jobs = store.list_cloud_runtime_jobs(workspace_id="ws_1", project_id="proj_1")
        assert len(jobs) == 1
        assert jobs[0].status == "failed"

    def test_v1_succeeded_status_loads_as_completed_and_serializes_as_succeeded(
        self, store: BuilderRuntimeJobStore
    ):
        """v1.x jobs use succeeded; Phase 0 Literal uses completed internally."""
        old_record = {
            "id": "crjb_ok",
            "version": "1.0.0",
            "workspace_id": "ws_1",
            "project_id": "proj_1",
            "status": "succeeded",
            "phase": "completed",
            "provider": "gcp_gke_sandbox",
            "created_at": _TS,
            "updated_at": _TS,
            "metadata": {},
        }
        raw = {"cloud_runtime_jobs": [old_record]}
        store._path.parent.mkdir(parents=True, exist_ok=True)
        store._path.write_text(json.dumps(raw), encoding="utf-8")

        jobs = store.list_cloud_runtime_jobs(workspace_id="ws_1", project_id="proj_1")
        assert len(jobs) == 1
        assert jobs[0].status == "completed"
        assert jobs[0].model_dump(mode="json")["status"] == "succeeded"


# ── New → old backward-compat ─────────────────────────────────────


class TestBackwardCompatWrite:
    def test_last_error_populates_deprecated_fields(self, store: BuilderRuntimeJobStore):
        """When last_error is set, deprecated error_code/error_message are written."""
        err = ErrorEnvelope(
            error_code="step.step_failed",
            error_message="Something broke",
            fatal=True,
            occurred_at=_TS,
        )
        job = CloudRuntimeJob(
            workspace_id="ws_1",
            project_id="proj_1",
            status="failed",
            last_error=err,
        )
        result = store.upsert_cloud_runtime_job(job)
        assert result.error_code == "step.step_failed"
        assert result.error_message == "Something broke"

    def test_no_last_error_leaves_deprecated_fields_none(self, store: BuilderRuntimeJobStore):
        """Without last_error, deprecated fields stay None."""
        job = CloudRuntimeJob(
            workspace_id="ws_1",
            project_id="proj_1",
        )
        result = store.upsert_cloud_runtime_job(job)
        assert result.error_code is None
        assert result.error_message is None
        assert result.last_error is None

    def test_written_json_has_deprecated_fields(self, store: BuilderRuntimeJobStore):
        """Raw JSON file contains both last_error and deprecated string fields."""
        err = ErrorEnvelope(
            error_code="gate.plan_stale",
            error_message="drift",
            fatal=True,
            occurred_at=_TS,
        )
        job = CloudRuntimeJob(
            workspace_id="ws_1",
            project_id="proj_1",
            status="failed",
            last_error=err,
        )
        store.upsert_cloud_runtime_job(job)

        raw = json.loads(store._path.read_text(encoding="utf-8"))
        written = raw["cloud_runtime_jobs"][0]
        assert written["error_code"] == "gate.plan_stale"
        assert written["error_message"] == "drift"
        assert written["last_error"]["error_code"] == "gate.plan_stale"


# ── TTL field migration (Phase 1 #3) ────────────────────────────


class TestTtlFieldMigration:
    def test_old_record_without_ttl_fields_loads_with_defaults(self, store: BuilderRuntimeJobStore):
        """Records created before Phase 1 #3 have no ttl_seconds/ttl_deadline."""
        old_record = {
            "id": "crjb_old_ttl",
            "version": "1.0.0",
            "workspace_id": "ws_ttl",
            "project_id": "proj_ttl",
            "status": "running",
            "phase": "received",
            "provider": "disabled",
            "created_at": _TS,
            "updated_at": _TS,
            "metadata": {},
        }
        raw = {"cloud_runtime_jobs": [old_record]}
        store._path.parent.mkdir(parents=True, exist_ok=True)
        store._path.write_text(json.dumps(raw), encoding="utf-8")

        jobs = store.list_cloud_runtime_jobs(workspace_id="ws_ttl", project_id="proj_ttl")
        assert len(jobs) == 1
        job = jobs[0]
        assert job.ttl_seconds == 3600
        assert job.ttl_deadline is None

    def test_new_record_with_ttl_fields_round_trips(self, store: BuilderRuntimeJobStore):
        job = CloudRuntimeJob(
            workspace_id="ws_ttl",
            project_id="proj_ttl",
            ttl_seconds=1800,
            ttl_deadline="2026-05-18T13:00:00Z",
        )
        store.upsert_cloud_runtime_job(job)
        loaded = store.get_cloud_runtime_job(
            workspace_id="ws_ttl", project_id="proj_ttl", job_id=job.id
        )
        assert loaded is not None
        assert loaded.ttl_seconds == 1800
        assert loaded.ttl_deadline == "2026-05-18T13:00:00Z"

    def test_default_ttl_seconds_is_3600(self):
        job = CloudRuntimeJob(workspace_id="ws", project_id="proj")
        assert job.ttl_seconds == 3600

    def test_default_ttl_deadline_is_none(self):
        job = CloudRuntimeJob(workspace_id="ws", project_id="proj")
        assert job.ttl_deadline is None
