"""Phase 2.5 — tests for the Worker enqueue / scheduler / entrypoint trio.

Covers:

- Cloud Tasks enqueue builds the expected task payload + uses ``job_id`` as the
  idempotency key + treats ``AlreadyExists`` as success.
- GKE scheduler builds a Job manifest with ``backoffLimit: 0`` /
  ``restartPolicy: Never`` / ``ttlSecondsAfterFinished: 3600`` and uses
  get-before-create idempotency.
- ``src/ham/worker_main.py`` env-vs-Job mismatch detection (3c guardrail) and
  events-store startup guard (ADR-0013).
- Dispatcher ``phase=scheduled`` idempotent short-circuit returns the cached
  pod name (3e guardrail).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

import pytest

from src.ham.builder_plan import Plan, Step, WorkerEnvelope
from src.ham.builder_worker_enqueue_cloud_tasks import (
    BuilderWorkerEnqueueCloudTasks,
    CloudTasksEnqueueConfigError,
    CloudTasksEnqueueError,
)
from src.api.internal_dispatcher_gke import (
    WorkerPodSchedulerGKE,
    WorkerPodSchedulerGKEConfigError,
)
from src.persistence.builder_runtime_job_store import CloudRuntimeJob


# ---------------------------------------------------------------------------
# Cloud Tasks enqueue
# ---------------------------------------------------------------------------


class _FakeCloudTasksAlreadyExists(Exception):
    pass


_FakeCloudTasksAlreadyExists.__name__ = "AlreadyExists"


@dataclass
class _FakeCloudTasksClient:
    created: list[dict[str, Any]] = field(default_factory=list)
    raise_on_create: bool = False

    def queue_path(self, project: str, location: str, queue: str) -> str:
        return f"projects/{project}/locations/{location}/queues/{queue}"

    def create_task(self, *, request: dict[str, Any]) -> None:
        if self.raise_on_create:
            raise _FakeCloudTasksAlreadyExists("duplicate")
        self.created.append(request)


def _make_envelope(*, job_id: str = "crjb_envelope_one") -> WorkerEnvelope:
    return WorkerEnvelope(
        plan_id="pln_envone",
        job_id=job_id,
        workspace_id="ws_demo",
        project_id="proj_demo",
        requested_by="user@example",
        correlation_id=job_id,
    )


def _make_job() -> CloudRuntimeJob:
    return CloudRuntimeJob(
        id="crjb_envelope_one",
        workspace_id="ws_demo",
        project_id="proj_demo",
        metadata={"plan_id": "pln_envone"},
    )


def test_cloud_tasks_enqueue_builds_expected_payload() -> None:
    client = _FakeCloudTasksClient()
    enq = BuilderWorkerEnqueueCloudTasks(
        project="p",
        location="us-central1",
        queue="ham-builder-worker",
        service_account_email="ham-dispatcher@p.iam.gserviceaccount.com",
        dispatcher_url="https://ham-api.example/api/internal/dispatch-worker",
        dispatcher_audience="https://ham-api.example",
        client=client,
    )

    envelope = _make_envelope()
    enq.enqueue(envelope, job=_make_job())

    assert len(client.created) == 1
    req = client.created[0]
    assert req["parent"] == "projects/p/locations/us-central1/queues/ham-builder-worker"
    task = req["task"]
    assert task["name"].endswith(f"/tasks/{envelope.job_id}")
    http = task["http_request"]
    assert http["http_method"] == "POST"
    assert http["url"] == "https://ham-api.example/api/internal/dispatch-worker"
    assert http["headers"]["Content-Type"] == "application/json"
    assert http["oidc_token"]["service_account_email"] == "ham-dispatcher@p.iam.gserviceaccount.com"
    assert http["oidc_token"]["audience"] == "https://ham-api.example"
    # Body is the envelope JSON
    body = http["body"]
    assert isinstance(body, (bytes, bytearray))
    assert envelope.job_id.encode() in body


def test_cloud_tasks_enqueue_treats_already_exists_as_success() -> None:
    client = _FakeCloudTasksClient(raise_on_create=True)
    enq = BuilderWorkerEnqueueCloudTasks(
        project="p",
        location="us-central1",
        queue="q",
        service_account_email="sa@p.iam.gserviceaccount.com",
        dispatcher_url="https://example/api/internal/dispatch-worker",
        dispatcher_audience="https://example",
        client=client,
    )

    # Should NOT raise — AlreadyExists is the dedupe semantic.
    enq.enqueue(_make_envelope(), job=_make_job())


def test_cloud_tasks_enqueue_raises_on_other_failure() -> None:
    class _OtherError(Exception):
        pass

    class _FailingClient:
        def queue_path(self, project: str, location: str, queue: str) -> str:
            return f"projects/{project}/locations/{location}/queues/{queue}"

        def create_task(self, *, request: dict[str, Any]) -> None:
            raise _OtherError("network blip")

    enq = BuilderWorkerEnqueueCloudTasks(
        project="p",
        location="us-central1",
        queue="q",
        service_account_email="sa@p.iam.gserviceaccount.com",
        dispatcher_url="https://example",
        dispatcher_audience="https://example",
        client=_FailingClient(),
    )

    with pytest.raises(CloudTasksEnqueueError):
        enq.enqueue(_make_envelope(), job=_make_job())


def test_cloud_tasks_enqueue_requires_https_dispatcher_endpoints() -> None:
    enq = BuilderWorkerEnqueueCloudTasks(
        project="p",
        location="us-central1",
        queue="q",
        service_account_email="sa@p.iam.gserviceaccount.com",
        dispatcher_url="http://example/api/internal/dispatch-worker",
        dispatcher_audience="https://example",
        client=_FakeCloudTasksClient(),
    )
    with pytest.raises(CloudTasksEnqueueConfigError):
        enq.enqueue(_make_envelope(), job=_make_job())


# ---------------------------------------------------------------------------
# GKE scheduler
# ---------------------------------------------------------------------------


class _FakeK8sApiException(Exception):
    def __init__(self, status: int, message: str = "") -> None:
        super().__init__(message)
        self.status = status


@dataclass
class _FakeBatchV1Api:
    """Minimal fake of kubernetes.client.BatchV1Api used by the scheduler."""

    existing_jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    created_jobs: list[dict[str, Any]] = field(default_factory=list)

    def read_namespaced_job(self, *, name: str, namespace: str) -> dict[str, Any]:
        key = f"{namespace}/{name}"
        if key in self.existing_jobs:
            return self.existing_jobs[key]
        raise _FakeK8sApiException(status=404, message="not found")

    def create_namespaced_job(self, *, namespace: str, body: dict[str, Any]) -> dict[str, Any]:
        name = body["metadata"]["name"]
        key = f"{namespace}/{name}"
        if key in self.existing_jobs:
            raise _FakeK8sApiException(status=409, message="exists")
        self.existing_jobs[key] = body
        self.created_jobs.append(body)
        return body


_VALID_IMAGE_DIGEST = (
    "us-central1-docker.pkg.dev/p/ham/ham"
    "@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
)


def _make_scheduler(*, batch_api: _FakeBatchV1Api) -> WorkerPodSchedulerGKE:
    return WorkerPodSchedulerGKE(
        cluster_project="p",
        cluster_location="us-central1",
        cluster_name="ham-cluster",
        namespace="ham-worker",
        ksa="ham-worker",
        image=_VALID_IMAGE_DIGEST,
        firestore_project="p",
        firestore_database="(default)",
        batch_api_client=batch_api,
    )


def test_gke_scheduler_creates_job_with_required_spec() -> None:
    api = _FakeBatchV1Api()
    sched = _make_scheduler(batch_api=api)

    pod_name = sched.schedule_worker_pod(
        job_id="crjb_jobone",
        plan_id="pln_one",
        workspace_id="ws_demo",
        project_id="proj_demo",
    )

    assert pod_name == "ham-worker-jobone"
    assert len(api.created_jobs) == 1
    body = api.created_jobs[0]

    assert body["apiVersion"] == "batch/v1"
    assert body["kind"] == "Job"
    spec = body["spec"]
    assert spec["backoffLimit"] == 0
    assert spec["ttlSecondsAfterFinished"] == 3600
    pod_spec = spec["template"]["spec"]
    assert pod_spec["restartPolicy"] == "Never"
    assert pod_spec["serviceAccountName"] == "ham-worker"

    container = pod_spec["containers"][0]
    assert container["image"] == _VALID_IMAGE_DIGEST
    assert container["command"] == ["python", "-m", "src.ham.worker_main"]

    env = {e["name"]: e["value"] for e in container["env"]}
    assert env["HAM_JOB_ID"] == "crjb_jobone"
    assert env["HAM_PLAN_ID"] == "pln_one"
    assert env["HAM_WORKSPACE_ID"] == "ws_demo"
    assert env["HAM_PROJECT_ID"] == "proj_demo"
    assert env["HAM_WORKER_IMAGE"] == _VALID_IMAGE_DIGEST
    assert env["HAM_BUILDER_PLAN_STORE_BACKEND"] == "firestore"
    assert env["HAM_BUILDER_RUNTIME_JOB_STORE_BACKEND"] == "firestore"
    assert env["HAM_BUILDER_RUN_EVENTS_STORE_BACKEND"] == "firestore"

    sec = container["securityContext"]
    assert sec["allowPrivilegeEscalation"] is False
    assert sec["runAsNonRoot"] is True
    assert sec["capabilities"]["drop"] == ["ALL"]


def test_gke_scheduler_get_before_create_is_idempotent() -> None:
    api = _FakeBatchV1Api()
    sched = _make_scheduler(batch_api=api)

    # Pre-populate as if a prior delivery already created the Job.
    name = "ham-worker-jobone"
    api.existing_jobs[f"ham-worker/{name}"] = {"metadata": {"name": name, "namespace": "ham-worker"}}

    pod_name = sched.schedule_worker_pod(
        job_id="crjb_jobone",
        plan_id="pln_one",
        workspace_id="ws_demo",
        project_id="proj_demo",
    )

    assert pod_name == name
    assert api.created_jobs == []  # we never called create


def test_gke_scheduler_refuses_non_digest_image() -> None:
    api = _FakeBatchV1Api()
    sched = WorkerPodSchedulerGKE(
        cluster_project="p",
        cluster_location="us-central1",
        cluster_name="c",
        namespace="ham-worker",
        ksa="ham-worker",
        image="us-central1-docker.pkg.dev/p/ham/ham:latest",  # tag, not digest
        firestore_project="p",
        batch_api_client=api,
    )

    with pytest.raises(WorkerPodSchedulerGKEConfigError):
        sched.schedule_worker_pod(
            job_id="crjb_x",
            plan_id="pln_x",
            workspace_id="ws",
            project_id="proj",
        )


# ---------------------------------------------------------------------------
# worker_main env-vs-Job mismatch + startup guard
# ---------------------------------------------------------------------------


class _FakeJobStore:
    def __init__(self, jobs: dict[str, CloudRuntimeJob]) -> None:
        self._jobs = dict(jobs)
        self.upserts: list[CloudRuntimeJob] = []

    def get_cloud_runtime_job_by_id(self, *, job_id: str) -> CloudRuntimeJob | None:
        return self._jobs.get(job_id)

    def get_cloud_runtime_job(
        self,
        *,
        workspace_id: str,
        project_id: str,
        job_id: str,
    ) -> CloudRuntimeJob | None:
        row = self._jobs.get(job_id)
        if row is None:
            return None
        if row.workspace_id != workspace_id or row.project_id != project_id:
            return None
        return row

    def list_cloud_runtime_jobs(self, *, workspace_id: str, project_id: str) -> list[CloudRuntimeJob]:
        return [
            row for row in self._jobs.values()
            if row.workspace_id == workspace_id and row.project_id == project_id
        ]

    def upsert_cloud_runtime_job(self, record: CloudRuntimeJob) -> CloudRuntimeJob:
        self._jobs[record.id] = record
        self.upserts.append(record)
        return record


class _FakePlanStore:
    def __init__(self, plans: dict[str, Plan]) -> None:
        self._plans = dict(plans)

    def list_plans(self, *, workspace_id: str, project_id: str) -> list[Plan]:
        return [
            p for p in self._plans.values()
            if p.workspace_id == workspace_id and p.project_id == project_id
        ]

    def get_plan(self, *, plan_id: str) -> Plan | None:
        return self._plans.get(plan_id)

    def upsert_plan(self, plan: Plan) -> Plan:
        self._plans[plan.plan_id] = plan
        return plan

    def get_approval_record(self, *, plan_id: str):  # noqa: ANN201
        return None

    def upsert_approval_record(self, record):  # noqa: ANN001, ANN201
        return record


class _FakeEventsStore:
    def __init__(self, *, latest: int = 0) -> None:
        self._latest = latest
        self._appended: list[Any] = []

    def append(self, event):  # noqa: ANN001, ANN201
        self._appended.append(event)
        return event

    def read_from(self, *, job_id: str, since_seq: int = 0):  # noqa: ANN201
        return []

    def latest_seq(self, *, job_id: str) -> int:
        return self._latest


def _install_worker_main_stores(
    monkeypatch,
    *,
    jobs: dict[str, CloudRuntimeJob],
    plans: dict[str, Plan],
    events_latest: int = 0,
) -> tuple[_FakeJobStore, _FakePlanStore, _FakeEventsStore]:
    job_store = _FakeJobStore(jobs)
    plan_store = _FakePlanStore(plans)
    events_store = _FakeEventsStore(latest=events_latest)

    import src.ham.worker_main as worker_main  # noqa: PLC0415

    monkeypatch.setattr(worker_main, "get_builder_runtime_job_store", lambda: job_store)
    monkeypatch.setattr(worker_main, "get_builder_plan_store", lambda: plan_store)
    monkeypatch.setattr(worker_main, "get_builder_run_events_store", lambda: events_store)
    return job_store, plan_store, events_store


def _set_worker_env(monkeypatch, **kwargs) -> None:
    base = {
        "HAM_JOB_ID": "crjb_x",
        "HAM_PLAN_ID": "pln_x",
        "HAM_WORKSPACE_ID": "ws_x",
        "HAM_PROJECT_ID": "proj_x",
        "HAM_WORKER_IMAGE": _VALID_IMAGE_DIGEST,
    }
    base.update(kwargs)
    for k in ("HAM_JOB_ID", "HAM_PLAN_ID", "HAM_WORKSPACE_ID", "HAM_PROJECT_ID", "HAM_WORKER_IMAGE", "HAM_WORKER_JOB_ID"):
        monkeypatch.delenv(k, raising=False)
    for k, v in base.items():
        monkeypatch.setenv(k, v)


def test_worker_main_missing_required_env_returns_config_exit(monkeypatch) -> None:
    from src.ham.worker_main import main  # noqa: PLC0415

    monkeypatch.delenv("HAM_JOB_ID", raising=False)
    monkeypatch.delenv("HAM_WORKER_JOB_ID", raising=False)
    # All others unset too.
    for k in ("HAM_PLAN_ID", "HAM_WORKSPACE_ID", "HAM_PROJECT_ID", "HAM_WORKER_IMAGE"):
        monkeypatch.delenv(k, raising=False)

    exit_code = main()
    assert exit_code == 10  # _EXIT_CONFIG


def test_worker_main_workspace_mismatch_exits_and_marks_failed(monkeypatch) -> None:
    from src.ham.worker_main import main  # noqa: PLC0415

    job = CloudRuntimeJob(
        id="crjb_x",
        workspace_id="ws_actual",
        project_id="proj_x",
        metadata={"plan_id": "pln_x"},
    )
    plan = Plan(
        plan_id="pln_x",
        workspace_id="ws_actual",
        project_id="proj_x",
        user_message="x",
        steps=[Step(title="t", description="d")],
        planner_confidence="high",
    )
    job_store, _plan_store, _evts = _install_worker_main_stores(
        monkeypatch, jobs={"crjb_x": job}, plans={"pln_x": plan}
    )
    _set_worker_env(monkeypatch, HAM_WORKSPACE_ID="ws_expected")

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 12  # _EXIT_MISMATCH

    # Must have marked the Firestore job failed (3b guardrail).
    assert any(row.status == "failed" for row in job_store.upserts)


def test_worker_main_dirty_events_exits(monkeypatch) -> None:
    from src.ham.worker_main import main  # noqa: PLC0415

    job = CloudRuntimeJob(
        id="crjb_x",
        workspace_id="ws_x",
        project_id="proj_x",
        metadata={"plan_id": "pln_x"},
    )
    plan = Plan(
        plan_id="pln_x",
        workspace_id="ws_x",
        project_id="proj_x",
        user_message="x",
        steps=[Step(title="t", description="d")],
        planner_confidence="high",
    )
    _install_worker_main_stores(
        monkeypatch, jobs={"crjb_x": job}, plans={"pln_x": plan}, events_latest=5
    )
    _set_worker_env(monkeypatch)

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 13  # _EXIT_DIRTY_EVENTS


def test_worker_main_happy_path_delegates_to_builder_worker(monkeypatch) -> None:
    from src.ham.worker_main import main  # noqa: PLC0415

    job = CloudRuntimeJob(
        id="crjb_x",
        workspace_id="ws_x",
        project_id="proj_x",
        metadata={"plan_id": "pln_x"},
    )
    plan = Plan(
        plan_id="pln_x",
        workspace_id="ws_x",
        project_id="proj_x",
        user_message="x",
        steps=[Step(title="t", description="d")],
        planner_confidence="high",
    )
    _install_worker_main_stores(
        monkeypatch, jobs={"crjb_x": job}, plans={"pln_x": plan}
    )
    _set_worker_env(monkeypatch)

    # Replace BuilderWorker with a recorder.
    recorded: dict[str, Any] = {}

    class _RecordingWorker:
        def __init__(self, job_id: str, **_kwargs: Any) -> None:
            recorded["job_id"] = job_id

        def run(self) -> None:
            recorded["ran"] = True

    import src.ham.builder_worker as builder_worker  # noqa: PLC0415
    monkeypatch.setattr(builder_worker, "BuilderWorker", _RecordingWorker)

    exit_code = main()
    assert exit_code == 0
    assert recorded == {"job_id": "crjb_x", "ran": True}


# ---------------------------------------------------------------------------
# Dispatcher phase=scheduled idempotency
# ---------------------------------------------------------------------------


def test_dispatcher_idempotent_skip_returns_cached_pod_name(monkeypatch) -> None:
    """Re-delivery sees phase=scheduled and returns the cached pod_name without
    touching the scheduler."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api import internal_dispatcher

    job = CloudRuntimeJob(
        id="crjb_dispatch",
        workspace_id="ws_x",
        project_id="proj_x",
        status="queued",
        phase="scheduled",
        metadata={"plan_id": "pln_x", "pod_name": "ham-worker-cached"},
    )

    class _StubJobStore(_FakeJobStore):
        pass

    store = _StubJobStore({"crjb_dispatch": job})
    monkeypatch.setattr(
        internal_dispatcher, "get_builder_runtime_job_store", lambda: store
    )

    # Bypass OIDC validation for the test.
    monkeypatch.setattr(internal_dispatcher, "_validate_oidc_token", lambda _h: {"email": "x"})

    # If the scheduler is called, fail the test loudly.
    class _BoomScheduler:
        def schedule_worker_pod(self, **_kwargs: Any) -> str:
            raise AssertionError("scheduler should not be called when phase=scheduled")

    monkeypatch.setattr(internal_dispatcher, "get_worker_pod_scheduler", lambda: _BoomScheduler())

    app = FastAPI()
    app.include_router(internal_dispatcher.router)
    client = TestClient(app)

    envelope = WorkerEnvelope(
        plan_id="pln_x",
        job_id="crjb_dispatch",
        workspace_id="ws_x",
        project_id="proj_x",
        requested_by="x",
        correlation_id="crjb_dispatch",
    )

    resp = client.post(
        "/api/internal/dispatch-worker",
        headers={"Authorization": "Bearer fake"},
        content=envelope.model_dump_json(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["skipped"] is True
    assert body["pod_name"] == "ham-worker-cached"


def test_dispatcher_writes_phase_scheduled_after_successful_create(monkeypatch) -> None:
    """First-time dispatch transitions phase=scheduled and caches pod_name."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api import internal_dispatcher

    job = CloudRuntimeJob(
        id="crjb_first",
        workspace_id="ws_x",
        project_id="proj_x",
        status="queued",
        phase="received",
        metadata={"plan_id": "pln_x"},
    )

    store = _FakeJobStore({"crjb_first": job})
    monkeypatch.setattr(
        internal_dispatcher, "get_builder_runtime_job_store", lambda: store
    )
    monkeypatch.setattr(internal_dispatcher, "_validate_oidc_token", lambda _h: {"email": "x"})

    class _OkScheduler:
        def schedule_worker_pod(self, **_kwargs: Any) -> str:
            return "ham-worker-first"

    monkeypatch.setattr(internal_dispatcher, "get_worker_pod_scheduler", lambda: _OkScheduler())

    app = FastAPI()
    app.include_router(internal_dispatcher.router)
    client = TestClient(app)

    envelope = WorkerEnvelope(
        plan_id="pln_x",
        job_id="crjb_first",
        workspace_id="ws_x",
        project_id="proj_x",
        requested_by="x",
        correlation_id="crjb_first",
    )
    resp = client.post(
        "/api/internal/dispatch-worker",
        headers={"Authorization": "Bearer fake"},
        content=envelope.model_dump_json(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pod_name"] == "ham-worker-first"
    assert body["skipped"] is False

    # The store must have been updated with phase=scheduled + metadata.pod_name
    scheduled_writes = [w for w in store.upserts if w.phase == "scheduled"]
    assert len(scheduled_writes) == 1
    assert scheduled_writes[0].metadata.get("pod_name") == "ham-worker-first"


# ---------------------------------------------------------------------------
# Manifests + ops docs sanity
# ---------------------------------------------------------------------------


def _read(rel: str) -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, rel), encoding="utf-8") as f:
        return f.read()


def test_rbac_is_namespace_scoped_no_clusterrole() -> None:
    rbac = _read("deploy/k8s/worker-rbac.yaml")
    assert "kind: Role" in rbac
    assert "kind: RoleBinding" in rbac
    assert "kind: ClusterRole" not in rbac
    assert "kind: ClusterRoleBinding" not in rbac


def test_rbac_grants_minimum_verbs_only() -> None:
    rbac = _read("deploy/k8s/worker-rbac.yaml")
    # Allowed verbs only — no delete, no patch.
    assert re.search(r"verbs:\s*\[\"create\", \"get\", \"list\", \"watch\"\]", rbac)
    assert "\"delete\"" not in rbac
    assert "\"patch\"" not in rbac


def test_no_static_secret_material_in_manifests_or_ops() -> None:
    # Manifests should NOT mount Secret volumes or reference SA key JSON.
    for rel in (
        "deploy/k8s/worker-namespace.yaml",
        "deploy/k8s/worker-ksa.yaml",
        "deploy/k8s/worker-rbac.yaml",
        "docs/PHASE_2_5_OPS.md",
    ):
        content = _read(rel)
        # Sanity: never instruct anyone to use a service-account key JSON.
        assert "service-account-key" not in content.lower()
        assert "key.json" not in content.lower()
        # The ops runbook should reference Workload Identity, not raw keys.

    # The ops runbook explicitly calls out the GSA binding pattern.
    ops = _read("docs/PHASE_2_5_OPS.md")
    assert "Workload Identity" in ops
