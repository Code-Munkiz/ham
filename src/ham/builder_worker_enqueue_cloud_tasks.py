"""Cloud Tasks implementation of :class:`WorkerEnqueueProtocol` — Phase 2.5.

Replaces the ``_NoOpWorkerEnqueue`` stub when
``HAM_WORKER_ENQUEUE_BACKEND=cloud_tasks``. The default remains the no-op
so local dev and tests work without any GCP setup.

## Wire path

Plan approval → :func:`approve_plan` → :class:`BuilderWorkerEnqueueCloudTasks`
→ Cloud Tasks queue → HTTP push → ``POST /api/internal/dispatch-worker``
on Cloud Run → :class:`WorkerPodSchedulerGKE` → GKE Job.

The task body is the :class:`WorkerEnvelope` JSON; the task uses
``oidcToken`` so the dispatcher's existing
:func:`_validate_oidc_token` accepts it.

## Idempotency

The task name is derived from ``job_id``. Cloud Tasks rejects creation of a
task with a name that was used in the last hour with ``AlreadyExists``; we
treat that as success (the previous enqueue won the race). The dispatcher
plus the GKE scheduler form two further idempotency layers (status
transition + Job get-before-create).

## Env vars

- ``HAM_CLOUD_TASKS_PROJECT_ID``       — GCP project hosting the queue
- ``HAM_CLOUD_TASKS_LOCATION``         — e.g. ``us-central1``
- ``HAM_CLOUD_TASKS_QUEUE``            — queue name
- ``HAM_CLOUD_TASKS_SERVICE_ACCOUNT``  — SA email used for OIDC minting
                                         (must match what the dispatcher
                                         validates; same env var both sides)
- ``HAM_DISPATCHER_URL``               — HTTP push target (Cloud Run URL)
- ``HAM_DISPATCHER_AUDIENCE``          — OIDC ``aud`` claim (must match
                                         dispatcher validation)

See ADR-0007, docs/PHASE_2_5_DESIGN.md.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from src.ham.builder_plan import WorkerEnvelope
from src.persistence.builder_runtime_job_store import CloudRuntimeJob

_LOG = logging.getLogger(__name__)

_PROJECT_ENV = "HAM_CLOUD_TASKS_PROJECT_ID"
_LOCATION_ENV = "HAM_CLOUD_TASKS_LOCATION"
_QUEUE_ENV = "HAM_CLOUD_TASKS_QUEUE"
_SA_ENV = "HAM_CLOUD_TASKS_SERVICE_ACCOUNT"
_DISPATCHER_URL_ENV = "HAM_DISPATCHER_URL"
_DISPATCHER_AUDIENCE_ENV = "HAM_DISPATCHER_AUDIENCE"


class CloudTasksEnqueueError(RuntimeError):
    """Wrapper for unexpected errors from the Cloud Tasks SDK."""


class CloudTasksEnqueueConfigError(CloudTasksEnqueueError):
    """Raised when the Cloud Tasks backend is selected but env is incomplete."""


def _require_env(name: str) -> str:
    val = (os.environ.get(name) or "").strip()
    if not val:
        raise CloudTasksEnqueueConfigError(
            f"{name} is required when HAM_WORKER_ENQUEUE_BACKEND=cloud_tasks"
        )
    return val


class BuilderWorkerEnqueueCloudTasks:
    """Push a :class:`WorkerEnvelope` to the configured Cloud Tasks queue.

    The :class:`google.cloud.tasks_v2.CloudTasksClient` is constructed lazily
    on first call so importing this module never contacts Google.
    """

    def __init__(
        self,
        *,
        project: str | None = None,
        location: str | None = None,
        queue: str | None = None,
        service_account_email: str | None = None,
        dispatcher_url: str | None = None,
        dispatcher_audience: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._project = (project or os.environ.get(_PROJECT_ENV) or "").strip() or None
        self._location = (location or os.environ.get(_LOCATION_ENV) or "").strip() or None
        self._queue = (queue or os.environ.get(_QUEUE_ENV) or "").strip() or None
        self._service_account_email = (
            service_account_email or os.environ.get(_SA_ENV) or ""
        ).strip() or None
        self._dispatcher_url = (
            dispatcher_url or os.environ.get(_DISPATCHER_URL_ENV) or ""
        ).strip() or None
        self._dispatcher_audience = (
            dispatcher_audience or os.environ.get(_DISPATCHER_AUDIENCE_ENV) or ""
        ).strip() or None
        self._client = client

    # ------------------------------------------------------------------
    # Lazy client
    # ------------------------------------------------------------------

    def _ensure_config(self) -> None:
        if not self._project:
            self._project = _require_env(_PROJECT_ENV)
        if not self._location:
            self._location = _require_env(_LOCATION_ENV)
        if not self._queue:
            self._queue = _require_env(_QUEUE_ENV)
        if not self._service_account_email:
            self._service_account_email = _require_env(_SA_ENV)
        if not self._dispatcher_url:
            self._dispatcher_url = _require_env(_DISPATCHER_URL_ENV)
        if not self._dispatcher_audience:
            self._dispatcher_audience = _require_env(_DISPATCHER_AUDIENCE_ENV)
        if not str(self._dispatcher_url).startswith("https://"):
            raise CloudTasksEnqueueConfigError(
                f"{_DISPATCHER_URL_ENV} must be an https URL."
            )
        if not str(self._dispatcher_audience).startswith("https://"):
            raise CloudTasksEnqueueConfigError(
                f"{_DISPATCHER_AUDIENCE_ENV} must be an https audience."
            )

    def validate_config(self) -> None:
        """Public config check for startup fail-fast paths."""
        self._ensure_config()

    def _tasks_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.cloud import tasks_v2  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            raise CloudTasksEnqueueError(
                "google-cloud-tasks is required when "
                "HAM_WORKER_ENQUEUE_BACKEND=cloud_tasks."
            ) from exc
        self._client = tasks_v2.CloudTasksClient()
        return self._client

    def _queue_path(self) -> str:
        client = self._tasks_client()
        if hasattr(client, "queue_path"):
            return client.queue_path(self._project, self._location, self._queue)
        return (
            f"projects/{self._project}/locations/{self._location}/queues/{self._queue}"
        )

    @staticmethod
    def _task_name(queue_path: str, job_id: str) -> str:
        # Cloud Tasks task name regex: ^[A-Za-z0-9_-]{1,500}$. job_id is
        # ``crjb_<32 hex>`` — well within the constraint.
        return f"{queue_path}/tasks/{job_id}"

    # ------------------------------------------------------------------
    # WorkerEnqueueProtocol
    # ------------------------------------------------------------------

    def enqueue(self, envelope: WorkerEnvelope, *, job: CloudRuntimeJob) -> None:
        self._ensure_config()
        if envelope.job_id != job.id:
            raise CloudTasksEnqueueError(
                f"envelope/job mismatch: envelope.job_id={envelope.job_id!r} "
                f"job.id={job.id!r}"
            )
        queue_path = self._queue_path()
        body_bytes = envelope.model_dump_json().encode("utf-8")
        task: dict[str, Any] = {
            "name": self._task_name(queue_path, envelope.job_id),
            "http_request": {
                "http_method": "POST",
                "url": self._dispatcher_url,
                "headers": {"Content-Type": "application/json"},
                "body": body_bytes,
                "oidc_token": {
                    "service_account_email": self._service_account_email,
                    "audience": self._dispatcher_audience,
                },
            },
        }

        try:
            client = self._tasks_client()
            client.create_task(request={"parent": queue_path, "task": task})
            _LOG.info(
                "cloud-tasks: enqueued job_id=%s plan_id=%s",
                envelope.job_id,
                envelope.plan_id,
            )
        except Exception as exc:  # noqa: BLE001
            # AlreadyExists means a previous enqueue won the race — that's
            # exactly the dedupe semantic we want. Treat as success.
            if exc.__class__.__name__ == "AlreadyExists":
                _LOG.info(
                    "cloud-tasks: task %s already exists — idempotent skip",
                    envelope.job_id,
                )
                return
            _LOG.warning(
                "cloud-tasks: enqueue failed for job_id=%s: %s",
                envelope.job_id,
                exc,
            )
            raise CloudTasksEnqueueError(
                f"cloud tasks create_task failed: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Public builder — used by builder_plan_approval_service.build_worker_enqueue
# ---------------------------------------------------------------------------


def build_cloud_tasks_worker_enqueue() -> BuilderWorkerEnqueueCloudTasks:
    """Construct an enqueue using env-only config; raises if any var missing."""
    enq = BuilderWorkerEnqueueCloudTasks()
    # Fail fast at construction so misconfiguration shows up before the first
    # approval rather than at the next user click.
    enq.validate_config()
    return enq
