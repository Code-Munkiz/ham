"""Durable dispatch seam for HAM Native Builder v2 — out-of-process execution.

`start_native_build_job` persists the job + a durable execution context and then
hands the job id to this seam instead of running the build in a request-scoped
daemon thread (Cloud Run throttles CPU after the response returns, so a thread is
not durable for a multi-second Hermes build).

Wire path (durable / production)::

    chat turn -> start_native_build_job -> NativeBuildEnqueueCloudTasks
        -> Cloud Tasks queue -> HTTP push (OIDC)
        -> POST /api/internal/native-build/execute
        -> execute_native_build_job(import_job_id) (off the request path)

The default backend is :class:`_NoOpNativeBuildEnqueue` so local dev and tests run
without any GCP setup: the job is persisted + queued and a worker (or an explicit
inline/thread dispatch in dev) drives it. The Cloud Tasks backend is selected with
``HAM_NATIVE_BUILD_DISPATCH=cloud_tasks`` and mirrors the existing plan-approval
worker pipeline (``builder_worker_enqueue_cloud_tasks`` ->
``/api/internal/dispatch-worker``), reusing the same OIDC service account /
audience so the worker endpoint validates pushes with the established verifier.

Env vars (Cloud Tasks backend only)::

- ``HAM_CLOUD_TASKS_PROJECT_ID``       GCP project hosting the queue (shared)
- ``HAM_CLOUD_TASKS_LOCATION``         e.g. ``us-central1`` (shared)
- ``HAM_NATIVE_BUILD_TASKS_QUEUE``     queue name for native build tasks
- ``HAM_CLOUD_TASKS_SERVICE_ACCOUNT``  SA email used to mint the OIDC token (shared)
- ``HAM_NATIVE_BUILD_WORKER_URL``      https push target (the worker endpoint URL)
- ``HAM_DISPATCHER_AUDIENCE``          OIDC ``aud`` claim (shared with the dispatcher)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

_LOG = logging.getLogger(__name__)

_DISPATCH_ENV = "HAM_NATIVE_BUILD_DISPATCH"

_PROJECT_ENV = "HAM_CLOUD_TASKS_PROJECT_ID"
_LOCATION_ENV = "HAM_CLOUD_TASKS_LOCATION"
_QUEUE_ENV = "HAM_NATIVE_BUILD_TASKS_QUEUE"
_SA_ENV = "HAM_CLOUD_TASKS_SERVICE_ACCOUNT"
_WORKER_URL_ENV = "HAM_NATIVE_BUILD_WORKER_URL"
_AUDIENCE_ENV = "HAM_DISPATCHER_AUDIENCE"


class NativeBuildExecuteEnvelope(BaseModel):
    """Body pushed to the native-build worker endpoint (no build-kit internals)."""

    model_config = ConfigDict(extra="forbid")

    version: str = "1.0.0"
    import_job_id: str
    workspace_id: str
    project_id: str


class NativeBuildEnqueueError(RuntimeError):
    """Wrapper for unexpected errors from the Cloud Tasks SDK."""


class NativeBuildEnqueueConfigError(NativeBuildEnqueueError):
    """Raised when the Cloud Tasks backend is selected but env is incomplete."""


@runtime_checkable
class NativeBuildEnqueueProtocol(Protocol):
    def enqueue(self, envelope: NativeBuildExecuteEnvelope) -> None: ...


class _NoOpNativeBuildEnqueue:
    """Default: the job + context are persisted; worker wiring is environment-specific.

    Leaves the job queued (pollable) rather than running it inline, so the default
    is durable and never a request-scoped daemon thread. A worker (or an explicit
    ``HAM_NATIVE_BUILD_DISPATCH=inline``/``thread`` in dev) drives it from there.
    """

    def enqueue(self, envelope: NativeBuildExecuteEnvelope) -> None:
        _LOG.info(
            "native-build enqueue: import_job_id=%s queued (no durable backend configured)",
            envelope.import_job_id,
        )


def _require_env(name: str) -> str:
    val = (os.environ.get(name) or "").strip()
    if not val:
        raise NativeBuildEnqueueConfigError(
            f"{name} is required when {_DISPATCH_ENV}=cloud_tasks"
        )
    return val


class NativeBuildEnqueueCloudTasks:
    """Push a :class:`NativeBuildExecuteEnvelope` to the configured Cloud Tasks queue.

    The :class:`google.cloud.tasks_v2.CloudTasksClient` is constructed lazily on
    first use so importing this module never contacts Google. The task name is
    derived from ``import_job_id`` so a redelivered enqueue is deduped by Cloud
    Tasks (``AlreadyExists`` -> treated as success).
    """

    def __init__(self, *, client: Any | None = None) -> None:
        self._project = (os.environ.get(_PROJECT_ENV) or "").strip() or None
        self._location = (os.environ.get(_LOCATION_ENV) or "").strip() or None
        self._queue = (os.environ.get(_QUEUE_ENV) or "").strip() or None
        self._service_account_email = (os.environ.get(_SA_ENV) or "").strip() or None
        self._worker_url = (os.environ.get(_WORKER_URL_ENV) or "").strip() or None
        self._audience = (os.environ.get(_AUDIENCE_ENV) or "").strip() or None
        self._client = client

    def _ensure_config(self) -> None:
        if not self._project:
            self._project = _require_env(_PROJECT_ENV)
        if not self._location:
            self._location = _require_env(_LOCATION_ENV)
        if not self._queue:
            self._queue = _require_env(_QUEUE_ENV)
        if not self._service_account_email:
            self._service_account_email = _require_env(_SA_ENV)
        if not self._worker_url:
            self._worker_url = _require_env(_WORKER_URL_ENV)
        if not self._audience:
            self._audience = _require_env(_AUDIENCE_ENV)
        if not str(self._worker_url).startswith("https://"):
            raise NativeBuildEnqueueConfigError(f"{_WORKER_URL_ENV} must be an https URL.")
        if not str(self._audience).startswith("https://"):
            raise NativeBuildEnqueueConfigError(f"{_AUDIENCE_ENV} must be an https audience.")

    def validate_config(self) -> None:
        """Public config check for startup / construction fail-fast paths."""
        self._ensure_config()

    def _tasks_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.cloud import tasks_v2  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            raise NativeBuildEnqueueError(
                f"google-cloud-tasks is required when {_DISPATCH_ENV}=cloud_tasks."
            ) from exc
        self._client = tasks_v2.CloudTasksClient()
        return self._client

    def _queue_path(self) -> str:
        client = self._tasks_client()
        if hasattr(client, "queue_path"):
            return client.queue_path(self._project, self._location, self._queue)
        return f"projects/{self._project}/locations/{self._location}/queues/{self._queue}"

    def enqueue(self, envelope: NativeBuildExecuteEnvelope) -> None:
        self._ensure_config()
        queue_path = self._queue_path()
        task: dict[str, Any] = {
            "name": f"{queue_path}/tasks/{envelope.import_job_id}",
            "http_request": {
                "http_method": "POST",
                "url": self._worker_url,
                "headers": {"Content-Type": "application/json"},
                "body": envelope.model_dump_json().encode("utf-8"),
                "oidc_token": {
                    "service_account_email": self._service_account_email,
                    "audience": self._audience,
                },
            },
        }
        try:
            client = self._tasks_client()
            client.create_task(request={"parent": queue_path, "task": task})
            _LOG.info("native-build enqueue: cloud-tasks job import_job_id=%s", envelope.import_job_id)
        except Exception as exc:  # noqa: BLE001
            if exc.__class__.__name__ == "AlreadyExists":
                _LOG.info(
                    "native-build enqueue: task %s already exists — idempotent skip",
                    envelope.import_job_id,
                )
                return
            raise NativeBuildEnqueueError(f"cloud tasks create_task failed: {exc}") from exc


def build_cloud_tasks_native_build_enqueue() -> NativeBuildEnqueueCloudTasks:
    """Construct a Cloud Tasks enqueue from env; raises if any var is missing."""
    enq = NativeBuildEnqueueCloudTasks()
    enq.validate_config()
    return enq


def build_native_build_enqueue() -> NativeBuildEnqueueProtocol:
    """Pick the native-build enqueue backend based on env.

    Defaults to :class:`_NoOpNativeBuildEnqueue`. When
    ``HAM_NATIVE_BUILD_DISPATCH=cloud_tasks`` is set, returns the Cloud Tasks
    implementation; misconfiguration raises at construction.
    """
    backend = (os.environ.get(_DISPATCH_ENV) or "").strip().lower()
    if backend == "cloud_tasks":
        return build_cloud_tasks_native_build_enqueue()
    return _NoOpNativeBuildEnqueue()


_ENQUEUE_SINGLETON: list[NativeBuildEnqueueProtocol | None] = [None]


def get_native_build_enqueue() -> NativeBuildEnqueueProtocol:
    if _ENQUEUE_SINGLETON[0] is None:
        _ENQUEUE_SINGLETON[0] = build_native_build_enqueue()
    return _ENQUEUE_SINGLETON[0]


def set_native_build_enqueue_for_tests(enqueue: NativeBuildEnqueueProtocol | None) -> None:
    _ENQUEUE_SINGLETON[0] = enqueue
