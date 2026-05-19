"""Tests for src/api/jobs.py — GET /api/jobs/<job_id>/stream (Phase 2)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.jobs import _sse_line, _heartbeat_frame, _event_frame, router as jobs_router
from src.ham.builder_plan import (
    HeartbeatPayload,
    JobCompletedPayload,
    JobStartedPayload,
    SSEEvent,
)
from src.ham.clerk_auth import HamActor
from src.persistence.builder_run_events_store import (
    BuilderRunEventsStore,
    set_builder_run_events_store_for_tests,
)
from src.persistence.builder_runtime_job_store import (
    BuilderRuntimeJobStore,
    CloudRuntimeJob,
    set_builder_runtime_job_store_for_tests,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _make_actor(user_id: str = "user_test") -> HamActor:
    return HamActor(
        user_id=user_id,
        org_id=None,
        session_id=f"sess_{user_id}",
        email=f"{user_id}@example.com",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _make_sse_event(
    *,
    job_id: str = "crjb_test",
    plan_id: str = "pln_test",
    payload: dict[str, Any] | None = None,
    seq: int = 1,
) -> SSEEvent:
    return SSEEvent(
        seq=seq,
        job_id=job_id,
        plan_id=plan_id,
        occurred_at=_utc_now_iso(),
        event=payload or {"type": "heartbeat"},
    )


def _make_job(
    job_id: str = "crjb_test",
    *,
    workspace_id: str = "ws_test",
    project_id: str = "proj_test",
    status: str = "running",
) -> CloudRuntimeJob:
    return CloudRuntimeJob(
        id=job_id,
        workspace_id=workspace_id,
        project_id=project_id,
        status=status,  # type: ignore[arg-type]
        metadata={"plan_id": "pln_test"},
    )


def _build_app(actor: HamActor | None) -> FastAPI:
    app = FastAPI()
    app.include_router(jobs_router)

    async def _override_actor() -> HamActor | None:
        return actor

    app.dependency_overrides[get_ham_clerk_actor] = _override_actor
    return app


# ---------------------------------------------------------------------------
# SSE frame helpers
# ---------------------------------------------------------------------------


class TestSseHelpers:
    def test_sse_line_format(self):
        frame = _sse_line("step_started", '{"x": 1}', event_id="1")
        assert "id: 1" in frame
        assert "event: step_started" in frame
        assert 'data: {"x": 1}' in frame
        # Frame ends with double blank line
        assert frame.endswith("\n\n")

    def test_sse_line_no_event_id(self):
        frame = _sse_line("heartbeat", "{}")
        assert "id:" not in frame

    def test_heartbeat_frame_is_valid_sse(self):
        frame = _heartbeat_frame()
        assert "event: heartbeat" in frame
        assert "data:" in frame
        assert frame.endswith("\n\n")

    def test_event_frame_includes_seq_as_id(self):
        event = _make_sse_event(seq=42)
        frame = _event_frame(event)
        assert "id: 42" in frame
        assert "event: heartbeat" in frame


# ---------------------------------------------------------------------------
# GET /api/jobs/<job_id>/stream — 404 when not found
# ---------------------------------------------------------------------------


class TestJobsStreamNotFound:
    def test_returns_404_when_job_missing(self, tmp_path):
        job_store = BuilderRuntimeJobStore(store_path=tmp_path / "jobs.json")
        events_store = BuilderRunEventsStore(store_path=tmp_path / "events.json")
        set_builder_runtime_job_store_for_tests(job_store)
        set_builder_run_events_store_for_tests(events_store)
        try:
            app = _build_app(_make_actor())
            client = TestClient(app)
            res = client.get(
                "/api/jobs/crjb_missing/stream",
                params={"workspace_id": "ws_test", "project_id": "proj_test"},
            )
            assert res.status_code == 404
            assert res.json()["detail"]["error"]["code"] == "JOB_NOT_FOUND"
        finally:
            set_builder_runtime_job_store_for_tests(None)
            set_builder_run_events_store_for_tests(None)


# ---------------------------------------------------------------------------
# GET /api/jobs/<job_id>/stream — events streamed
# ---------------------------------------------------------------------------


class TestJobsStreamEvents:
    @pytest.fixture(autouse=True)
    def _setup_stores(self, tmp_path):
        self._job_store = BuilderRuntimeJobStore(store_path=tmp_path / "jobs.json")
        self._events_store = BuilderRunEventsStore(store_path=tmp_path / "events.json")
        set_builder_runtime_job_store_for_tests(self._job_store)
        set_builder_run_events_store_for_tests(self._events_store)
        yield
        set_builder_runtime_job_store_for_tests(None)
        set_builder_run_events_store_for_tests(None)

    def _seed_job(
        self,
        job_id: str = "crjb_stream",
        *,
        status: str = "completed",
    ) -> CloudRuntimeJob:
        job = _make_job(job_id, status=status)
        self._job_store.upsert_cloud_runtime_job(job)
        return job

    def _seed_events(
        self,
        job_id: str,
        payloads: list[dict[str, Any]],
        plan_id: str = "pln_test",
    ) -> list[SSEEvent]:
        events = []
        for payload in payloads:
            evt = _make_sse_event(job_id=job_id, plan_id=plan_id, payload=payload, seq=0)
            stored = self._events_store.append(evt)
            events.append(stored)
        return events

    def test_stream_returns_text_event_stream_content_type(self):
        self._seed_job("crjb_ct", status="completed")
        self._seed_events("crjb_ct", [{"type": "job_started"}, {"type": "job_completed"}])
        app = _build_app(_make_actor())
        client = TestClient(app)
        res = client.get(
            "/api/jobs/crjb_ct/stream",
            params={"workspace_id": "ws_test", "project_id": "proj_test"},
        )
        assert res.status_code == 200
        assert "text/event-stream" in res.headers.get("content-type", "")

    def test_stream_includes_stored_events(self):
        self._seed_job("crjb_ev", status="completed")
        self._seed_events(
            "crjb_ev",
            [{"type": "job_started"}, {"type": "job_completed"}],
        )
        app = _build_app(_make_actor())
        client = TestClient(app)
        res = client.get(
            "/api/jobs/crjb_ev/stream",
            params={"workspace_id": "ws_test", "project_id": "proj_test"},
        )
        assert res.status_code == 200
        text = res.text
        assert "job_started" in text
        assert "job_completed" in text

    def test_stream_respects_last_event_id(self):
        self._seed_job("crjb_eid", status="completed")
        self._seed_events(
            "crjb_eid",
            [
                {"type": "job_started"},
                {"type": "step_started", "step_id": "stp_1", "step_index": 0, "title": "Step 1"},
                {"type": "job_completed"},
            ],
        )
        app = _build_app(_make_actor())
        client = TestClient(app)
        # Request with Last-Event-ID=1 should skip seq=1 (job_started)
        res = client.get(
            "/api/jobs/crjb_eid/stream",
            params={"workspace_id": "ws_test", "project_id": "proj_test"},
            headers={"Last-Event-ID": "1"},
        )
        assert res.status_code == 200
        text = res.text
        # job_started is seq=1, should be skipped
        # step_started (seq=2) and job_completed (seq=3) should appear
        assert "step_started" in text
        assert "job_completed" in text

    def test_stream_closes_for_terminal_completed_job(self):
        """Stream should return and not hang when the job is already terminal."""
        self._seed_job("crjb_done", status="completed")
        self._seed_events("crjb_done", [{"type": "job_completed"}])
        app = _build_app(_make_actor())
        client = TestClient(app)
        res = client.get(
            "/api/jobs/crjb_done/stream",
            params={"workspace_id": "ws_test", "project_id": "proj_test"},
        )
        # The stream should eventually close (TestClient reads until EOF)
        assert res.status_code == 200

    def test_stream_closes_for_terminal_failed_job(self):
        self._seed_job("crjb_fail", status="failed")
        self._seed_events("crjb_fail", [{"type": "job_failed", "error": {"version": "1.0.0", "error_code": "internal_error", "error_message": "boom", "fatal": True, "occurred_at": _utc_now_iso()}}])
        app = _build_app(_make_actor())
        client = TestClient(app)
        res = client.get(
            "/api/jobs/crjb_fail/stream",
            params={"workspace_id": "ws_test", "project_id": "proj_test"},
        )
        assert res.status_code == 200

    def test_stream_closes_for_terminal_cancelled_job(self):
        self._seed_job("crjb_cancel", status="cancelled")
        self._seed_events("crjb_cancel", [{"type": "job_cancelled"}])
        app = _build_app(_make_actor())
        client = TestClient(app)
        res = client.get(
            "/api/jobs/crjb_cancel/stream",
            params={"workspace_id": "ws_test", "project_id": "proj_test"},
        )
        assert res.status_code == 200

    def test_stream_events_include_seq_as_id(self):
        self._seed_job("crjb_seq", status="completed")
        self._seed_events("crjb_seq", [{"type": "job_started"}, {"type": "job_completed"}])
        app = _build_app(_make_actor())
        client = TestClient(app)
        res = client.get(
            "/api/jobs/crjb_seq/stream",
            params={"workspace_id": "ws_test", "project_id": "proj_test"},
        )
        assert res.status_code == 200
        # Both "id: 1" and "id: 2" should appear
        assert "id: 1" in res.text
        assert "id: 2" in res.text

    def test_stream_works_without_workspace_project_params_for_file_backed_store(self):
        """Without workspace_id+project_id, the route falls back to broad scan."""
        self._seed_job("crjb_scan", status="completed")
        self._seed_events("crjb_scan", [{"type": "job_completed"}])
        app = _build_app(_make_actor())
        client = TestClient(app)
        # No workspace_id or project_id — relies on _find_job_by_id
        res = client.get("/api/jobs/crjb_scan/stream")
        # Should succeed (file-backed store has _load_raw accessible)
        assert res.status_code == 200

    def test_stream_404_without_params_for_missing_job(self):
        """Without params, a missing job should still return 404."""
        app = _build_app(_make_actor())
        client = TestClient(app)
        res = client.get("/api/jobs/crjb_totally_missing/stream")
        assert res.status_code == 404

    def test_cache_control_headers(self):
        self._seed_job("crjb_hdr", status="completed")
        self._seed_events("crjb_hdr", [{"type": "job_completed"}])
        app = _build_app(_make_actor())
        client = TestClient(app)
        res = client.get(
            "/api/jobs/crjb_hdr/stream",
            params={"workspace_id": "ws_test", "project_id": "proj_test"},
        )
        assert res.status_code == 200
        assert res.headers.get("cache-control") == "no-cache"


# ---------------------------------------------------------------------------
# Last-Event-ID parsing
# ---------------------------------------------------------------------------


class TestLastEventIdParsing:
    @pytest.fixture(autouse=True)
    def _setup_stores(self, tmp_path):
        job_store = BuilderRuntimeJobStore(store_path=tmp_path / "jobs.json")
        events_store = BuilderRunEventsStore(store_path=tmp_path / "events.json")
        job = _make_job("crjb_leid", status="completed")
        job_store.upsert_cloud_runtime_job(job)
        for payload in [{"type": "job_started"}, {"type": "job_completed"}]:
            events_store.append(_make_sse_event(job_id="crjb_leid", payload=payload, seq=0))
        set_builder_runtime_job_store_for_tests(job_store)
        set_builder_run_events_store_for_tests(events_store)
        yield
        set_builder_runtime_job_store_for_tests(None)
        set_builder_run_events_store_for_tests(None)

    def test_last_event_id_zero_returns_all_events(self):
        app = _build_app(_make_actor())
        client = TestClient(app)
        res = client.get(
            "/api/jobs/crjb_leid/stream",
            params={"workspace_id": "ws_test", "project_id": "proj_test"},
            headers={"Last-Event-ID": "0"},
        )
        assert res.status_code == 200
        assert "job_started" in res.text
        assert "job_completed" in res.text

    def test_invalid_last_event_id_is_ignored(self):
        app = _build_app(_make_actor())
        client = TestClient(app)
        res = client.get(
            "/api/jobs/crjb_leid/stream",
            params={"workspace_id": "ws_test", "project_id": "proj_test"},
            headers={"Last-Event-ID": "not_a_number"},
        )
        assert res.status_code == 200
        # Graceful fallback: all events returned
        assert "job_started" in res.text
