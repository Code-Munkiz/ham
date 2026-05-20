"""Focused unit tests for GKE worker Job manifest security posture."""

from __future__ import annotations

from typing import Any

import pytest

from src.api.internal_dispatcher_gke import WorkerPodSchedulerGKE, WorkerPodSchedulerGKEConfigError

_VALID_IMAGE_DIGEST = (
    "us-central1-docker.pkg.dev/p/ham/ham"
    "@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
)


class _FakeBatchV1Api:
    def __init__(self) -> None:
        self.existing_jobs: dict[str, dict[str, Any]] = {}
        self.created_jobs: list[dict[str, Any]] = []

    def read_namespaced_job(self, *, name: str, namespace: str) -> dict[str, Any]:
        key = f"{namespace}/{name}"
        if key not in self.existing_jobs:
            exc = Exception("not found")
            exc.status = 404  # type: ignore[attr-defined]
            raise exc
        return self.existing_jobs[key]

    def create_namespaced_job(self, *, namespace: str, body: dict[str, Any]) -> dict[str, Any]:
        key = f"{namespace}/{body['metadata']['name']}"
        self.existing_jobs[key] = body
        self.created_jobs.append(body)
        return body


def _worker_container(*, image: str = _VALID_IMAGE_DIGEST) -> dict:
    sched = WorkerPodSchedulerGKE(
        cluster_project="p",
        cluster_location="us-central1",
        cluster_name="ham-cluster",
        namespace="ham-worker",
        ksa="ham-worker",
        image=image,
        firestore_project="p",
        firestore_database="(default)",
    )
    manifest = sched._build_job_manifest(  # noqa: SLF001
        job_name="ham-worker-jobone",
        job_id="crjb_jobone",
        plan_id="pln_one",
        workspace_id="ws_demo",
        project_id="proj_demo",
    )
    return manifest["spec"]["template"]["spec"]["containers"][0]


def test_worker_container_run_as_non_root() -> None:
    sec = _worker_container()["securityContext"]
    assert sec["runAsNonRoot"] is True


def test_worker_container_run_as_user_and_group() -> None:
    sec = _worker_container()["securityContext"]
    assert sec["runAsUser"] == 10001
    assert sec["runAsGroup"] == 10001


def test_worker_container_hardening_flags() -> None:
    sec = _worker_container()["securityContext"]
    assert sec["allowPrivilegeEscalation"] is False
    assert sec["capabilities"]["drop"] == ["ALL"]


def test_worker_container_command_unchanged() -> None:
    container = _worker_container()
    assert container["command"] == ["python", "-m", "src.ham.worker_main"]


def test_worker_container_runtime_env_for_non_root_uid() -> None:
    env = {e["name"]: e["value"] for e in _worker_container()["env"]}
    assert env["HOME"] == "/tmp"
    assert env["XDG_CACHE_HOME"] == "/tmp/.cache"


def test_worker_image_digest_validation_still_required() -> None:
    api = _FakeBatchV1Api()
    sched = WorkerPodSchedulerGKE(
        cluster_project="p",
        cluster_location="us-central1",
        cluster_name="c",
        namespace="ham-worker",
        ksa="ham-worker",
        image="us-central1-docker.pkg.dev/p/ham/ham:latest",
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
