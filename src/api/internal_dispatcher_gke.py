"""GKE implementation of :class:`WorkerPodSchedulerProtocol` — Phase 2.5.

Replaces the ``_DisabledPodScheduler`` stub when
``HAM_WORKER_POD_SCHEDULER_BACKEND=gke``. The default remains the
disabled scheduler so local dev and tests work without a live cluster.

## Pod spec (ADR-0014)

The Worker runs as a Kubernetes ``Job`` (not raw Pod) with:

- ``restartPolicy: Never``
- ``backoffLimit: 0``
- ``ttlSecondsAfterFinished: 3600``

Same image as the API (per ADR-0014). The ``CMD`` is overridden to
``["python", "-m", "src.ham.worker_main"]``. The image is supplied via
``HAM_WORKER_IMAGE`` and must be a digest-pinned ref
(``...@sha256:...``) — the scheduler refuses to launch without it.

## Idempotency (3e guardrail)

Job name is deterministic: ``ham-worker-{job_id[:12]}``. ``get`` before
``create`` so Cloud Tasks redelivery doesn't create a duplicate Job. The
dispatcher additionally transitions ``CloudRuntimeJob.status`` from
``queued → scheduled`` before calling this scheduler.

## Auth

The Cloud Run service's GCP service account is bound to a namespace-scoped
Kubernetes ``Role`` (verbs ``create, get, list`` on ``jobs``). No
``ClusterRole``. The ``kubernetes`` client uses ``google-auth`` to mint
short-lived GKE access tokens; no JSON keys.

## Env vars

- ``HAM_GKE_CLUSTER_PROJECT_ID``
- ``HAM_GKE_CLUSTER_LOCATION``      (zone or region)
- ``HAM_GKE_CLUSTER_NAME``
- ``HAM_WORKER_NAMESPACE``           (must exist; created via deploy/k8s/)
- ``HAM_WORKER_KSA``                 (Kubernetes SA name in the namespace)
- ``HAM_WORKER_IMAGE``               (full digest ref)
- ``HAM_FIRESTORE_PROJECT_ID``       (passed through to Worker pod env)
- ``HAM_FIRESTORE_DATABASE``         (passed through to Worker pod env)
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from src.api.internal_dispatcher import WorkerPodSchedulerProtocol

_LOG = logging.getLogger(__name__)

_CLUSTER_PROJECT_ENV = "HAM_GKE_CLUSTER_PROJECT_ID"
_CLUSTER_LOCATION_ENV = "HAM_GKE_CLUSTER_LOCATION"
_CLUSTER_NAME_ENV = "HAM_GKE_CLUSTER_NAME"
_NAMESPACE_ENV = "HAM_WORKER_NAMESPACE"
_KSA_ENV = "HAM_WORKER_KSA"
_IMAGE_ENV = "HAM_WORKER_IMAGE"
_FIRESTORE_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FIRESTORE_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"

_TTL_SECONDS_AFTER_FINISHED = 3600
_BACKOFF_LIMIT = 0
_RESTART_POLICY = "Never"
_WORKER_RUN_AS_USER = 10001
_WORKER_RUN_AS_GROUP = 10001

_DIGEST_REF_PATTERN = re.compile(r"^[A-Za-z0-9._/:-]+@sha256:[0-9a-f]{64}$")


class WorkerPodSchedulerGKEError(RuntimeError):
    pass


class WorkerPodSchedulerGKEConfigError(WorkerPodSchedulerGKEError):
    pass


def _require_env(name: str) -> str:
    val = (os.environ.get(name) or "").strip()
    if not val:
        raise WorkerPodSchedulerGKEConfigError(
            f"{name} is required when HAM_WORKER_POD_SCHEDULER_BACKEND=gke"
        )
    return val


def _short_job_id(job_id: str, *, max_len: int = 12) -> str:
    """First 12 chars after the ``crjb_`` prefix — keeps Job names short."""
    base = (job_id or "").strip()
    if base.startswith("crjb_"):
        base = base[5:]
    return base[:max_len]


class WorkerPodSchedulerGKE(WorkerPodSchedulerProtocol):
    """GKE-backed Worker pod scheduler.

    The :mod:`kubernetes` client and GCP credentials are constructed lazily
    so importing this module never contacts Google.
    """

    def __init__(
        self,
        *,
        cluster_project: str | None = None,
        cluster_location: str | None = None,
        cluster_name: str | None = None,
        namespace: str | None = None,
        ksa: str | None = None,
        image: str | None = None,
        firestore_project: str | None = None,
        firestore_database: str | None = None,
        batch_api_client: Any | None = None,
    ) -> None:
        self._cluster_project = (cluster_project or os.environ.get(_CLUSTER_PROJECT_ENV) or "").strip() or None
        self._cluster_location = (cluster_location or os.environ.get(_CLUSTER_LOCATION_ENV) or "").strip() or None
        self._cluster_name = (cluster_name or os.environ.get(_CLUSTER_NAME_ENV) or "").strip() or None
        self._namespace = (namespace or os.environ.get(_NAMESPACE_ENV) or "").strip() or None
        self._ksa = (ksa or os.environ.get(_KSA_ENV) or "").strip() or None
        self._image = (image or os.environ.get(_IMAGE_ENV) or "").strip() or None
        self._firestore_project = (
            firestore_project or os.environ.get(_FIRESTORE_PROJECT_ENV) or ""
        ).strip() or None
        self._firestore_database = (
            firestore_database or os.environ.get(_FIRESTORE_DATABASE_ENV) or ""
        ).strip() or None
        self._batch_api = batch_api_client

    # ------------------------------------------------------------------
    # Config validation
    # ------------------------------------------------------------------

    def _ensure_config(self) -> None:
        if not self._cluster_project:
            self._cluster_project = _require_env(_CLUSTER_PROJECT_ENV)
        if not self._cluster_location:
            self._cluster_location = _require_env(_CLUSTER_LOCATION_ENV)
        if not self._cluster_name:
            self._cluster_name = _require_env(_CLUSTER_NAME_ENV)
        if not self._namespace:
            self._namespace = _require_env(_NAMESPACE_ENV)
        if not self._ksa:
            self._ksa = _require_env(_KSA_ENV)
        if not self._image:
            self._image = _require_env(_IMAGE_ENV)
        if not _DIGEST_REF_PATTERN.match(self._image):
            raise WorkerPodSchedulerGKEConfigError(
                f"{_IMAGE_ENV} must be a digest-pinned ref (image@sha256:...); "
                f"got {self._image!r}"
            )
        if not self._firestore_project:
            self._firestore_project = _require_env(_FIRESTORE_PROJECT_ENV)
        # firestore database is optional (Firestore default DB is "(default)")

    # ------------------------------------------------------------------
    # Lazy kubernetes client wired via GKE access tokens
    # ------------------------------------------------------------------

    def _build_batch_api(self) -> Any:
        if self._batch_api is not None:
            return self._batch_api
        try:
            from kubernetes import client as k8s_client  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            raise WorkerPodSchedulerGKEError(
                "kubernetes is required when HAM_WORKER_POD_SCHEDULER_BACKEND=gke"
            ) from exc

        config = self._build_kube_config()
        api_client = k8s_client.ApiClient(configuration=config)
        self._batch_api = k8s_client.BatchV1Api(api_client=api_client)
        return self._batch_api

    def _build_kube_config(self) -> Any:
        """Construct a kubernetes.client.Configuration pointing at the cluster.

        Uses Workload Identity Federation / Cloud Run's attached service
        account via ``google.auth.default()`` to mint short-lived access
        tokens. No JSON keys.
        """
        try:
            import base64  # noqa: PLC0415

            import google.auth  # noqa: PLC0415
            import google.auth.transport.requests  # noqa: PLC0415
            from google.cloud import container_v1  # noqa: PLC0415
            from kubernetes import client as k8s_client  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            raise WorkerPodSchedulerGKEError(
                "google-cloud-container + kubernetes are required when "
                "HAM_WORKER_POD_SCHEDULER_BACKEND=gke"
            ) from exc

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        credentials.refresh(google.auth.transport.requests.Request())

        cluster_path = (
            f"projects/{self._cluster_project}"
            f"/locations/{self._cluster_location}"
            f"/clusters/{self._cluster_name}"
        )
        cluster_client = container_v1.ClusterManagerClient(credentials=credentials)
        cluster = cluster_client.get_cluster(name=cluster_path)

        # Write the CA cert to an in-memory temp file path the kubernetes
        # client can read. urllib3 wants a real file path for SSL.
        import tempfile  # noqa: PLC0415

        ca_data = base64.b64decode(cluster.master_auth.cluster_ca_certificate)
        ca_file = tempfile.NamedTemporaryFile(  # noqa: SIM115 - kept alive by the Configuration
            delete=False,
            suffix=".crt",
        )
        ca_file.write(ca_data)
        ca_file.flush()
        ca_file.close()

        config = k8s_client.Configuration()
        config.host = f"https://{cluster.endpoint}"
        config.api_key = {"authorization": f"Bearer {credentials.token}"}
        config.ssl_ca_cert = ca_file.name
        return config

    # ------------------------------------------------------------------
    # Job spec construction
    # ------------------------------------------------------------------

    def _job_name(self, job_id: str) -> str:
        return f"ham-worker-{_short_job_id(job_id)}"

    def _build_env(
        self,
        *,
        job_id: str,
        plan_id: str,
        workspace_id: str,
        project_id: str,
    ) -> list[dict[str, str]]:
        env: list[dict[str, str]] = [
            {"name": "HAM_JOB_ID", "value": job_id},
            {"name": "HAM_PLAN_ID", "value": plan_id},
            {"name": "HAM_WORKSPACE_ID", "value": workspace_id},
            {"name": "HAM_PROJECT_ID", "value": project_id},
            {"name": "HAM_WORKER_IMAGE", "value": self._image or ""},
            {"name": "HAM_BUILDER_PLAN_STORE_BACKEND", "value": "firestore"},
            {"name": "HAM_BUILDER_SOURCE_STORE_BACKEND", "value": "firestore"},
            {"name": "HAM_NATIVE_BUILD_CONTEXT_STORE_BACKEND", "value": "firestore"},
            {"name": "HAM_BUILDER_RUNTIME_STORE_BACKEND", "value": "firestore"},
            {"name": "HAM_BUILDER_RUNTIME_JOB_STORE_BACKEND", "value": "firestore"},
            {"name": "HAM_BUILDER_RUN_EVENTS_STORE_BACKEND", "value": "firestore"},
            {"name": "HAM_FIRESTORE_PROJECT_ID", "value": self._firestore_project or ""},
        ]
        if self._firestore_database:
            env.append({"name": "HAM_FIRESTORE_DATABASE", "value": self._firestore_database})
        env.extend(
            [
                {"name": "HOME", "value": "/tmp"},
                {"name": "XDG_CACHE_HOME", "value": "/tmp/.cache"},
            ]
        )
        return env

    def _build_job_manifest(
        self,
        *,
        job_name: str,
        job_id: str,
        plan_id: str,
        workspace_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        """Build the v1.Job manifest. Pure-data so unit tests can assert."""
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": job_name,
                "namespace": self._namespace,
                "labels": {
                    "app.kubernetes.io/name": "ham-worker",
                    "ham.dev/job-id": job_id,
                    "ham.dev/plan-id": plan_id,
                },
            },
            "spec": {
                "backoffLimit": _BACKOFF_LIMIT,
                "ttlSecondsAfterFinished": _TTL_SECONDS_AFTER_FINISHED,
                "template": {
                    "metadata": {
                        "labels": {
                            "app.kubernetes.io/name": "ham-worker",
                            "ham.dev/job-id": job_id,
                        },
                    },
                    "spec": {
                        "restartPolicy": _RESTART_POLICY,
                        "serviceAccountName": self._ksa,
                        "automountServiceAccountToken": True,
                        "containers": [
                            {
                                "name": "worker",
                                "image": self._image,
                                "imagePullPolicy": "IfNotPresent",
                                "command": ["python", "-m", "src.ham.worker_main"],
                                "env": self._build_env(
                                    job_id=job_id,
                                    plan_id=plan_id,
                                    workspace_id=workspace_id,
                                    project_id=project_id,
                                ),
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "readOnlyRootFilesystem": False,
                                    "runAsNonRoot": True,
                                    "runAsUser": _WORKER_RUN_AS_USER,
                                    "runAsGroup": _WORKER_RUN_AS_GROUP,
                                    "capabilities": {"drop": ["ALL"]},
                                },
                            },
                        ],
                    },
                },
            },
        }

    # ------------------------------------------------------------------
    # WorkerPodSchedulerProtocol
    # ------------------------------------------------------------------

    def schedule_worker_pod(
        self,
        *,
        job_id: str,
        plan_id: str,
        workspace_id: str,
        project_id: str,
    ) -> str:
        self._ensure_config()
        job_name = self._job_name(job_id)
        manifest = self._build_job_manifest(
            job_name=job_name,
            job_id=job_id,
            plan_id=plan_id,
            workspace_id=workspace_id,
            project_id=project_id,
        )

        api = self._build_batch_api()
        # get-before-create idempotency
        try:
            api.read_namespaced_job(name=job_name, namespace=self._namespace)
            _LOG.info("gke-scheduler: job %s already exists — idempotent skip", job_name)
            return job_name
        except Exception as exc:  # noqa: BLE001
            # 404 is the expected "does not exist" path; anything else is real.
            status = getattr(exc, "status", None)
            if status not in (404, None):
                raise WorkerPodSchedulerGKEError(
                    f"read_namespaced_job failed: {exc}"
                ) from exc

        try:
            api.create_namespaced_job(namespace=self._namespace, body=manifest)
            _LOG.info(
                "gke-scheduler: created job %s for job_id=%s plan_id=%s",
                job_name,
                job_id,
                plan_id,
            )
        except Exception as exc:  # noqa: BLE001
            # AlreadyExists means a concurrent create won — treat as success.
            status = getattr(exc, "status", None)
            if status == 409 or exc.__class__.__name__ == "AlreadyExists":
                _LOG.info(
                    "gke-scheduler: job %s created by another worker — idempotent",
                    job_name,
                )
                return job_name
            raise WorkerPodSchedulerGKEError(
                f"create_namespaced_job failed: {exc}"
            ) from exc

        return job_name


# ---------------------------------------------------------------------------
# Public builder — used by internal_dispatcher.build_worker_pod_scheduler
# ---------------------------------------------------------------------------


def build_gke_worker_pod_scheduler() -> WorkerPodSchedulerGKE:
    sched = WorkerPodSchedulerGKE()
    sched._ensure_config()  # noqa: SLF001
    return sched
