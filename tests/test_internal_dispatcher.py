"""Tests for src/api/internal_dispatcher.py — Phase 2 Subsystem 2."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.internal_dispatcher import (
    WorkerPodSchedulerProtocol,
    _decode_jwt_payload,
    router as dispatcher_router,
    set_worker_pod_scheduler_for_tests,
)
from src.ham.builder_plan import WorkerEnvelope
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


def _make_jwt_token(payload: dict[str, Any]) -> str:
    """Create a minimal (unsigned) JWT for testing."""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(b"fake_signature").rstrip(b"=").decode()
    return f"{header}.{body}.{sig}"


_VALID_SA = "cloud-tasks@my-project.iam.gserviceaccount.com"
_VALID_AUD = "https://ham-api.example.com/api/internal/dispatch-worker"


def _valid_token() -> str:
    return _make_jwt_token(
        {
            "iss": "https://accounts.google.com",
            "aud": _VALID_AUD,
            "email": _VALID_SA,
            "exp": 9999999999,
        }
    )


def _make_envelope(
    *,
    job_id: str = "crjb_test001",
    plan_id: str = "pln_test001",
) -> dict[str, Any]:
    return {
        "version": "1.0.0",
        "envelope_id": f"env_{job_id}",
        "plan_id": plan_id,
        "job_id": job_id,
        "workspace_id": "ws_test",
        "project_id": "proj_test",
        "requested_by": "user@test.com",
        "enqueued_at": _utc_now_iso(),
        "correlation_id": job_id,
    }


class _OkScheduler(WorkerPodSchedulerProtocol):
    """Scheduler that records calls and succeeds."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def schedule_worker_pod(
        self, *, job_id: str, plan_id: str, workspace_id: str, project_id: str
    ) -> str:
        self.calls.append(
            {
                "job_id": job_id,
                "plan_id": plan_id,
                "workspace_id": workspace_id,
                "project_id": project_id,
            }
        )
        return f"ham-worker-{job_id[:8]}"


class _FailingScheduler(WorkerPodSchedulerProtocol):
    """Scheduler that always raises."""

    def schedule_worker_pod(
        self, *, job_id: str, plan_id: str, workspace_id: str, project_id: str
    ) -> str:
        raise RuntimeError("GKE cluster unreachable")


def _build_app(tmp_path) -> FastAPI:
    app = FastAPI()
    app.include_router(dispatcher_router)
    return app


# ---------------------------------------------------------------------------
# _decode_jwt_payload
# ---------------------------------------------------------------------------


class TestDecodeJwtPayload:
    def test_decodes_valid_jwt(self):
        payload = {"iss": "https://accounts.google.com", "email": "svc@project.iam.gserviceaccount.com"}
        token = _make_jwt_token(payload)
        decoded = _decode_jwt_payload(token)
        assert decoded["iss"] == "https://accounts.google.com"
        assert decoded["email"] == "svc@project.iam.gserviceaccount.com"

    def test_raises_on_not_three_parts(self):
        with pytest.raises(ValueError, match="3 dot-separated"):
            _decode_jwt_payload("only.twoparts")

    def test_raises_on_malformed_base64(self):
        with pytest.raises(ValueError):
            _decode_jwt_payload("header.NOT_BASE64_$$$.signature")


# ---------------------------------------------------------------------------
# Dispatcher endpoint — configuration guard
# ---------------------------------------------------------------------------


class TestDispatcherConfigurationGuard:
    def test_returns_503_when_not_configured(self, tmp_path, monkeypatch):
        monkeypatch.delenv("HAM_CLOUD_TASKS_SERVICE_ACCOUNT", raising=False)
        monkeypatch.delenv("HAM_DISPATCHER_AUDIENCE", raising=False)
        app = _build_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        res = client.post(
            "/api/internal/dispatch-worker",
            json=_make_envelope(),
            headers={"Authorization": f"Bearer {_valid_token()}"},
        )
        assert res.status_code == 503
        assert res.json()["detail"]["error"]["code"] == "DISPATCHER_NOT_CONFIGURED"


# ---------------------------------------------------------------------------
# Dispatcher endpoint — authentication
# ---------------------------------------------------------------------------


class TestDispatcherAuth:
    @pytest.fixture(autouse=True)
    def _configure_env(self, monkeypatch):
        monkeypatch.setenv("HAM_CLOUD_TASKS_SERVICE_ACCOUNT", _VALID_SA)
        monkeypatch.setenv("HAM_DISPATCHER_AUDIENCE", _VALID_AUD)

    def test_401_when_no_auth_header(self, tmp_path):
        app = _build_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        res = client.post("/api/internal/dispatch-worker", json=_make_envelope())
        assert res.status_code == 401
        assert res.json()["detail"]["error"]["code"] == "DISPATCHER_TOKEN_MISSING"

    def test_401_when_wrong_audience(self, tmp_path):
        bad_token = _make_jwt_token(
            {"aud": "https://wrong-audience.example.com", "email": _VALID_SA}
        )
        app = _build_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        res = client.post(
            "/api/internal/dispatch-worker",
            json=_make_envelope(),
            headers={"Authorization": f"Bearer {bad_token}"},
        )
        assert res.status_code == 401
        assert res.json()["detail"]["error"]["code"] == "DISPATCHER_TOKEN_INVALID"

    def test_401_when_wrong_service_account(self, tmp_path):
        bad_token = _make_jwt_token(
            {"aud": _VALID_AUD, "email": "wrong@project.iam.gserviceaccount.com"}
        )
        app = _build_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        res = client.post(
            "/api/internal/dispatch-worker",
            json=_make_envelope(),
            headers={"Authorization": f"Bearer {bad_token}"},
        )
        assert res.status_code == 401

    def test_401_on_malformed_jwt(self, tmp_path):
        app = _build_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        res = client.post(
            "/api/internal/dispatch-worker",
            json=_make_envelope(),
            headers={"Authorization": "Bearer not.a.jwt.at.all.extra"},
        )
        assert res.status_code in (400, 401)


# ---------------------------------------------------------------------------
# Dispatcher endpoint — body validation
# ---------------------------------------------------------------------------


class TestDispatcherBodyValidation:
    @pytest.fixture(autouse=True)
    def _configure_env(self, monkeypatch):
        monkeypatch.setenv("HAM_CLOUD_TASKS_SERVICE_ACCOUNT", _VALID_SA)
        monkeypatch.setenv("HAM_DISPATCHER_AUDIENCE", _VALID_AUD)

    def test_400_on_non_json_body(self, tmp_path):
        app = _build_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        res = client.post(
            "/api/internal/dispatch-worker",
            content=b"not json",
            headers={
                "Authorization": f"Bearer {_valid_token()}",
                "Content-Type": "application/json",
            },
        )
        assert res.status_code == 400
        assert "DISPATCHER_BODY_INVALID" in res.text

    def test_400_on_extra_fields_in_envelope(self, tmp_path):
        envelope = _make_envelope()
        envelope["unexpected_field"] = "should fail"
        app = _build_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        set_builder_runtime_job_store_for_tests(BuilderRuntimeJobStore(store_path=tmp_path / "jobs.json"))
        try:
            res = client.post(
                "/api/internal/dispatch-worker",
                json=envelope,
                headers={"Authorization": f"Bearer {_valid_token()}"},
            )
            assert res.status_code == 400
            assert "DISPATCHER_ENVELOPE_INVALID" in res.text
        finally:
            set_builder_runtime_job_store_for_tests(None)

    def test_400_on_missing_required_envelope_field(self, tmp_path):
        bad_envelope = {"version": "1.0.0", "job_id": "crjb_bad"}  # Missing many required fields
        app = _build_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        res = client.post(
            "/api/internal/dispatch-worker",
            json=bad_envelope,
            headers={"Authorization": f"Bearer {_valid_token()}"},
        )
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# Dispatcher endpoint — happy path
# ---------------------------------------------------------------------------


class TestDispatcherHappyPath:
    @pytest.fixture(autouse=True)
    def _configure_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HAM_CLOUD_TASKS_SERVICE_ACCOUNT", _VALID_SA)
        monkeypatch.setenv("HAM_DISPATCHER_AUDIENCE", _VALID_AUD)
        self._scheduler = _OkScheduler()
        set_worker_pod_scheduler_for_tests(self._scheduler)
        self._job_store = BuilderRuntimeJobStore(store_path=tmp_path / "jobs.json")
        set_builder_runtime_job_store_for_tests(self._job_store)
        yield
        set_worker_pod_scheduler_for_tests(None)
        set_builder_runtime_job_store_for_tests(None)

    def test_returns_200_on_valid_request(self, tmp_path):
        app = _build_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        res = client.post(
            "/api/internal/dispatch-worker",
            json=_make_envelope(),
            headers={"Authorization": f"Bearer {_valid_token()}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert body["skipped"] is False

    def test_pod_scheduler_is_called(self, tmp_path):
        app = _build_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        env = _make_envelope(job_id="crjb_abc", plan_id="pln_abc")
        client.post(
            "/api/internal/dispatch-worker",
            json=env,
            headers={"Authorization": f"Bearer {_valid_token()}"},
        )
        assert len(self._scheduler.calls) == 1
        assert self._scheduler.calls[0]["job_id"] == "crjb_abc"

    def test_job_record_created_in_store(self, tmp_path):
        app = _build_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        env = _make_envelope(job_id="crjb_created", plan_id="pln_created")
        client.post(
            "/api/internal/dispatch-worker",
            json=env,
            headers={"Authorization": f"Bearer {_valid_token()}"},
        )
        job = self._job_store.get_cloud_runtime_job(
            workspace_id="ws_test",
            project_id="proj_test",
            job_id="crjb_created",
        )
        assert job is not None


# ---------------------------------------------------------------------------
# Dispatcher endpoint — idempotency
# ---------------------------------------------------------------------------


class TestDispatcherIdempotency:
    @pytest.fixture(autouse=True)
    def _configure_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HAM_CLOUD_TASKS_SERVICE_ACCOUNT", _VALID_SA)
        monkeypatch.setenv("HAM_DISPATCHER_AUDIENCE", _VALID_AUD)
        self._scheduler = _OkScheduler()
        set_worker_pod_scheduler_for_tests(self._scheduler)
        self._job_store = BuilderRuntimeJobStore(store_path=tmp_path / "jobs.json")
        set_builder_runtime_job_store_for_tests(self._job_store)
        yield
        set_worker_pod_scheduler_for_tests(None)
        set_builder_runtime_job_store_for_tests(None)

    def _seed_terminal_job(self, *, job_id: str, status: str) -> CloudRuntimeJob:
        job = CloudRuntimeJob(
            id=job_id,
            workspace_id="ws_test",
            project_id="proj_test",
            status=status,  # type: ignore[arg-type]
            metadata={"plan_id": "pln_test001"},
        )
        self._job_store.upsert_cloud_runtime_job(job)
        return job

    @pytest.mark.parametrize("terminal_status", ["completed", "failed", "cancelled"])
    def test_skips_when_job_already_terminal(self, tmp_path, terminal_status):
        self._seed_terminal_job(job_id="crjb_done", status=terminal_status)
        app = _build_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        env = _make_envelope(job_id="crjb_done", plan_id="pln_test001")
        res = client.post(
            "/api/internal/dispatch-worker",
            json=env,
            headers={"Authorization": f"Bearer {_valid_token()}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert body["skipped"] is True
        # Scheduler should NOT be called for terminal jobs
        assert len(self._scheduler.calls) == 0


# ---------------------------------------------------------------------------
# Dispatcher endpoint — scheduler failure
# ---------------------------------------------------------------------------


class TestDispatcherSchedulerFailure:
    @pytest.fixture(autouse=True)
    def _configure_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HAM_CLOUD_TASKS_SERVICE_ACCOUNT", _VALID_SA)
        monkeypatch.setenv("HAM_DISPATCHER_AUDIENCE", _VALID_AUD)
        set_worker_pod_scheduler_for_tests(_FailingScheduler())
        self._job_store = BuilderRuntimeJobStore(store_path=tmp_path / "jobs.json")
        set_builder_runtime_job_store_for_tests(self._job_store)
        yield
        set_worker_pod_scheduler_for_tests(None)
        set_builder_runtime_job_store_for_tests(None)

    def test_returns_500_on_scheduler_failure(self, tmp_path):
        app = _build_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        res = client.post(
            "/api/internal/dispatch-worker",
            json=_make_envelope(),
            headers={"Authorization": f"Bearer {_valid_token()}"},
        )
        assert res.status_code == 500
        assert "DISPATCHER_POD_SCHEDULE_FAILED" in res.text

    def test_job_marked_failed_on_scheduler_failure(self, tmp_path):
        app = _build_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        env = _make_envelope(job_id="crjb_failsched")
        client.post(
            "/api/internal/dispatch-worker",
            json=env,
            headers={"Authorization": f"Bearer {_valid_token()}"},
        )
        job = self._job_store.get_cloud_runtime_job(
            workspace_id="ws_test",
            project_id="proj_test",
            job_id="crjb_failsched",
        )
        assert job is not None
        assert job.status == "failed"
        assert job.last_error is not None
        assert job.last_error.error_code == "worker.worker_dispatch_failed"
