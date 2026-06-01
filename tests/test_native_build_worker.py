"""HAM Native Builder v2 — durable out-of-process dispatch tests.

Covers the durable enqueue seam (no-op default + Cloud Tasks backend) and the
authenticated internal worker endpoint that executes a queued native build by
job id (loads the durable context, runs the executor, marks the job pollable).
"""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import src.ham.builder_native_hermes as native_hermes
from src.api.native_build_worker import router as worker_router
from src.ham.native_build_worker_enqueue import (
    NativeBuildEnqueueCloudTasks,
    NativeBuildEnqueueConfigError,
    NativeBuildExecuteEnvelope,
    _NoOpNativeBuildEnqueue,
    build_native_build_enqueue,
)
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    NativeBuildContext,
    set_builder_source_store_for_tests,
)

_FORBIDDEN_TOKENS = (
    "registry_v2",
    "proposal_digest",
    "base_revision",
    "hermes_native_build",
    "inline_files",
    "hermes-builder",
    "hermes_gateway",
    "openrouter",
    "upstream_timeout",
)

_VALID_SA = "cloud-tasks@my-project.iam.gserviceaccount.com"
_VALID_AUD = "https://ham-api.example.com"

_VALID_BUNDLE = {
    "status": "success",
    "summary": "Built.",
    "files": {
        "src/App.tsx": "export default function App() { return <main>Native build</main>; }\n",
        "src/main.tsx": (
            "import React from 'react';\n"
            "import ReactDOM from 'react-dom/client';\n"
            "import App from './App';\n"
            "ReactDOM.createRoot(document.getElementById('root')!).render(<App />);\n"
        ),
        "src/styles.css": "body { margin: 0; }\n",
    },
    "checks": ["renders"],
}


def _make_jwt_token(payload: dict[str, Any]) -> str:
    def _seg(obj: Any) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{_seg({'alg': 'RS256', 'typ': 'JWT'})}.{_seg(payload)}.{_seg('sig')}"


def _valid_token() -> str:
    return _make_jwt_token({"iss": "https://accounts.google.com", "aud": _VALID_AUD, "email": _VALID_SA})


@pytest.fixture(autouse=True)
def _stub_google_oidc_verifier(monkeypatch):
    """Keep tests offline by stubbing Google signature verification (shared verifier)."""
    import src.api.internal_dispatcher as internal_dispatcher

    def _fake_verify(token: str, *, expected_aud: str) -> dict[str, Any]:
        parts = token.split(".")
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if str(payload.get("aud") or "") != expected_aud:
            raise HTTPException(
                status_code=401,
                detail={"error": {"code": "DISPATCHER_TOKEN_INVALID", "message": "aud mismatch"}},
            )
        return payload

    monkeypatch.setattr(internal_dispatcher, "_verify_google_oidc_token", _fake_verify)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(worker_router)
    return app


def _configure_oidc(monkeypatch) -> None:
    monkeypatch.setenv("HAM_CLOUD_TASKS_SERVICE_ACCOUNT", _VALID_SA)
    monkeypatch.setenv("HAM_DISPATCHER_AUDIENCE", _VALID_AUD)


def _seed_context(store, *, job_id: str, workspace_id: str = "ws", project_id: str = "proj") -> None:
    store.create_import_job(
        workspace_id=workspace_id,
        project_id=project_id,
        created_by="user",
        phase=native_hermes.NATIVE_BUILD_PHASE_QUEUED,
        status="queued",
        metadata={"origin": native_hermes.NATIVE_BUILD_JOB_ORIGIN},
    )
    # The store assigns its own job id; rebuild context against the created job.
    job = store.list_import_jobs(workspace_id=workspace_id, project_id=project_id)[0]
    store.put_native_build_context(
        NativeBuildContext(
            import_job_id=job.id,
            workspace_id=workspace_id,
            project_id=project_id,
            session_id="sess",
            user_prompt="build a small native app",
            created_by="user",
        )
    )
    return job.id


# ---------------------------------------------------------------------------
# Enqueue seam — backend selection
# ---------------------------------------------------------------------------


def test_enqueue_default_is_noop(monkeypatch) -> None:
    monkeypatch.delenv("HAM_NATIVE_BUILD_DISPATCH", raising=False)
    enq = build_native_build_enqueue()
    assert isinstance(enq, _NoOpNativeBuildEnqueue)
    # The no-op never raises and never runs a build.
    enq.enqueue(NativeBuildExecuteEnvelope(import_job_id="ijob_x", workspace_id="ws", project_id="proj"))


def test_cloud_tasks_backend_requires_config(monkeypatch) -> None:
    monkeypatch.setenv("HAM_NATIVE_BUILD_DISPATCH", "cloud_tasks")
    for var in (
        "HAM_CLOUD_TASKS_PROJECT_ID",
        "HAM_CLOUD_TASKS_LOCATION",
        "HAM_NATIVE_BUILD_TASKS_QUEUE",
        "HAM_NATIVE_BUILD_WORKER_URL",
    ):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(NativeBuildEnqueueConfigError):
        build_native_build_enqueue()


class _FakeAlreadyExists(Exception):
    pass


_FakeAlreadyExists.__name__ = "AlreadyExists"


class _FakeTasksClient:
    def __init__(self, *, raise_already_exists: bool = False) -> None:
        self.created: list[dict[str, Any]] = []
        self._raise_already_exists = raise_already_exists

    def queue_path(self, project: str, location: str, queue: str) -> str:
        return f"projects/{project}/locations/{location}/queues/{queue}"

    def create_task(self, *, request: dict[str, Any]) -> Any:
        if self._raise_already_exists:
            raise _FakeAlreadyExists("dup")
        self.created.append(request)
        return {"name": request["task"]["name"]}


def _configure_cloud_tasks(monkeypatch) -> None:
    monkeypatch.setenv("HAM_NATIVE_BUILD_DISPATCH", "cloud_tasks")
    monkeypatch.setenv("HAM_CLOUD_TASKS_PROJECT_ID", "proj-gcp")
    monkeypatch.setenv("HAM_CLOUD_TASKS_LOCATION", "us-central1")
    monkeypatch.setenv("HAM_NATIVE_BUILD_TASKS_QUEUE", "ham-native-builds")
    monkeypatch.setenv("HAM_CLOUD_TASKS_SERVICE_ACCOUNT", _VALID_SA)
    monkeypatch.setenv("HAM_NATIVE_BUILD_WORKER_URL", f"{_VALID_AUD}/api/internal/native-build/execute")
    monkeypatch.setenv("HAM_DISPATCHER_AUDIENCE", _VALID_AUD)


def test_cloud_tasks_enqueue_builds_expected_task(monkeypatch) -> None:
    _configure_cloud_tasks(monkeypatch)
    client = _FakeTasksClient()
    enq = NativeBuildEnqueueCloudTasks(client=client)
    enq.enqueue(NativeBuildExecuteEnvelope(import_job_id="ijob_abc", workspace_id="ws", project_id="proj"))
    assert len(client.created) == 1
    task = client.created[0]["task"]
    assert task["name"].endswith("/tasks/ijob_abc")
    http = task["http_request"]
    assert http["url"] == f"{_VALID_AUD}/api/internal/native-build/execute"
    assert http["oidc_token"]["service_account_email"] == _VALID_SA
    assert http["oidc_token"]["audience"] == _VALID_AUD
    body = json.loads(http["body"].decode("utf-8"))
    assert body["import_job_id"] == "ijob_abc"
    assert body["workspace_id"] == "ws"


def test_cloud_tasks_enqueue_treats_already_exists_as_success(monkeypatch) -> None:
    _configure_cloud_tasks(monkeypatch)
    enq = NativeBuildEnqueueCloudTasks(client=_FakeTasksClient(raise_already_exists=True))
    # No raise: a prior enqueue won the race (idempotent).
    enq.enqueue(NativeBuildExecuteEnvelope(import_job_id="ijob_dup", workspace_id="ws", project_id="proj"))


# ---------------------------------------------------------------------------
# Worker endpoint — auth + validation
# ---------------------------------------------------------------------------


def test_worker_503_when_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("HAM_CLOUD_TASKS_SERVICE_ACCOUNT", raising=False)
    monkeypatch.delenv("HAM_DISPATCHER_AUDIENCE", raising=False)
    client = TestClient(_build_app(), raise_server_exceptions=False)
    res = client.post(
        "/api/internal/native-build/execute",
        json={"import_job_id": "ijob_x", "workspace_id": "ws", "project_id": "proj"},
        headers={"Authorization": f"Bearer {_valid_token()}"},
    )
    assert res.status_code == 503
    assert res.json()["detail"]["error"]["code"] == "DISPATCHER_NOT_CONFIGURED"


def test_worker_401_on_wrong_audience(monkeypatch) -> None:
    _configure_oidc(monkeypatch)
    bad = _make_jwt_token({"aud": "https://wrong.example.com", "email": _VALID_SA})
    client = TestClient(_build_app(), raise_server_exceptions=False)
    res = client.post(
        "/api/internal/native-build/execute",
        json={"import_job_id": "ijob_x", "workspace_id": "ws", "project_id": "proj"},
        headers={"Authorization": f"Bearer {bad}"},
    )
    assert res.status_code == 401


def test_worker_400_on_extra_envelope_field(monkeypatch) -> None:
    _configure_oidc(monkeypatch)
    client = TestClient(_build_app(), raise_server_exceptions=False)
    res = client.post(
        "/api/internal/native-build/execute",
        json={"import_job_id": "ijob_x", "workspace_id": "ws", "project_id": "proj", "x": 1},
        headers={"Authorization": f"Bearer {_valid_token()}"},
    )
    assert res.status_code == 400
    assert "NATIVE_BUILD_WORKER_ENVELOPE_INVALID" in res.text


# ---------------------------------------------------------------------------
# Worker endpoint — execution by id
# ---------------------------------------------------------------------------


def test_worker_skips_when_no_context(monkeypatch, tmp_path) -> None:
    _configure_oidc(monkeypatch)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "s.json"))
    try:
        client = TestClient(_build_app(), raise_server_exceptions=False)
        res = client.post(
            "/api/internal/native-build/execute",
            json={"import_job_id": "ijob_missing", "workspace_id": "ws", "project_id": "proj"},
            headers={"Authorization": f"Bearer {_valid_token()}"},
        )
    finally:
        set_builder_source_store_for_tests(None)
    assert res.status_code == 200
    assert res.json()["skipped"] is True


def test_worker_executes_job_by_id_and_materializes_snapshot(monkeypatch, tmp_path) -> None:
    _configure_oidc(monkeypatch)
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "disabled")
    monkeypatch.setattr(native_hermes, "complete_artifact_turn", lambda *_a, **_k: json.dumps(_VALID_BUNDLE))
    store = BuilderSourceStore(store_path=tmp_path / "s.json")
    set_builder_source_store_for_tests(store)
    try:
        job_id = _seed_context(store, job_id="seed")
        client = TestClient(_build_app(), raise_server_exceptions=False)
        res = client.post(
            "/api/internal/native-build/execute",
            json={"import_job_id": job_id, "workspace_id": "ws", "project_id": "proj"},
            headers={"Authorization": f"Bearer {_valid_token()}"},
        )
        body = res.json()
        assert res.status_code == 200
        assert body["status"] == "succeeded"
        assert body["skipped"] is False
        # Status is pollable and terminal-succeeded; snapshot materialized server-side.
        jobs = store.list_import_jobs(workspace_id="ws", project_id="proj")
        assert jobs[0].status == "succeeded"
        assert jobs[0].phase == native_hermes.NATIVE_BUILD_PHASE_SUCCEEDED
        snaps = store.list_source_snapshots(workspace_id="ws", project_id="proj")
        assert snaps[0].manifest["kind"] == "inline_text_bundle"
        # No internals leak into the worker response or the pollable job record.
        haystack = (json.dumps(body) + json.dumps(jobs[0].model_dump(mode="json"))).lower()
        for token in _FORBIDDEN_TOKENS:
            assert token not in haystack
    finally:
        set_builder_source_store_for_tests(None)


def test_worker_idempotent_skip_when_terminal(monkeypatch, tmp_path) -> None:
    _configure_oidc(monkeypatch)

    def _must_not_run(*_a, **_k):
        raise AssertionError("executor must not run for a terminal job")

    monkeypatch.setattr(native_hermes, "complete_artifact_turn", _must_not_run)
    store = BuilderSourceStore(store_path=tmp_path / "s.json")
    set_builder_source_store_for_tests(store)
    try:
        job_id = _seed_context(store, job_id="seed")
        # Drive the job to a terminal state.
        store.mark_import_job_succeeded(
            import_job_id=job_id,
            phase=native_hermes.NATIVE_BUILD_PHASE_SUCCEEDED,
            source_snapshot_id="ssnp_x",
        )
        client = TestClient(_build_app(), raise_server_exceptions=False)
        res = client.post(
            "/api/internal/native-build/execute",
            json={"import_job_id": job_id, "workspace_id": "ws", "project_id": "proj"},
            headers={"Authorization": f"Bearer {_valid_token()}"},
        )
    finally:
        set_builder_source_store_for_tests(None)
    assert res.status_code == 200
    assert res.json()["skipped"] is True
