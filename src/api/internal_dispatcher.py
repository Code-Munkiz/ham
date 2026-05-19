"""Phase 2 — Subsystem 2: Internal dispatcher endpoint.

POST /api/internal/dispatch-worker

Cloud Tasks pushes WorkerEnvelopes here after Plan approval.  The handler:
  1. Validates the OIDC token from Cloud Tasks.
  2. Parses body as WorkerEnvelope (extra="forbid").
  3. Idempotency: if job is already terminal, returns 200 and exits.
  4. Schedules a GKE Worker pod (passes job_id as HAM_WORKER_JOB_ID env).
  5. Returns 200 immediately (does NOT wait for the Worker).

Auth: OIDC token verification per the Cloud Tasks → Cloud Run pattern.
      HAM_CLOUD_TASKS_SERVICE_ACCOUNT env must match the token's email claim.
      HAM_DISPATCHER_AUDIENCE env must match the token's aud claim.
      When neither env is set the endpoint is disabled (returns 503).

Spec: docs/PHASE_2_DESIGN.md § Subsystem 2
ADR: docs/adr/0007-cloud-tasks-as-queue-transport.md
"""

from __future__ import annotations

import base64
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import ValidationError

from src.ham.builder_error_codes import WORKER_DISPATCH_FAILED, make_error
from src.ham.builder_plan import WorkerEnvelope
from src.persistence.builder_runtime_job_store import (
    BuilderRuntimeJobStoreProtocol,
    CloudRuntimeJob,
    get_builder_runtime_job_store,
)

_LOG = logging.getLogger(__name__)

router = APIRouter(tags=["internal"])

# Terminal statuses — idempotency guard
_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# OIDC token validation
# ---------------------------------------------------------------------------


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode the JWT payload section without signature verification.

    Raises ValueError on malformed tokens.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Not a valid JWT: expected 3 dot-separated parts")
    # Decode the payload (middle) segment
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        payload_bytes = base64.urlsafe_b64decode(padded)
        return json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"JWT payload decode failed: {exc}") from exc


def _verify_google_oidc_token(token: str, *, expected_aud: str) -> dict[str, Any]:
    """Verify token signature + standard claims using Google verifier."""
    try:
        from google.auth.transport.requests import Request  # noqa: PLC0415
        from google.oauth2 import id_token  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "DISPATCHER_AUTH_RUNTIME_MISSING",
                    "message": "google-auth runtime is required for OIDC verification.",
                }
            },
        ) from exc

    try:
        payload = id_token.verify_oauth2_token(token, Request(), audience=expected_aud)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "DISPATCHER_TOKEN_INVALID",
                    "message": f"OIDC token verification failed: {exc}",
                }
            },
        ) from exc

    # Defensive allowlist even though verify_oauth2_token checks issuer.
    issuer = str(payload.get("iss") or "")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "DISPATCHER_TOKEN_INVALID",
                    "message": "OIDC token issuer is not trusted.",
                }
            },
        )

    return payload


def _validate_oidc_token(authorization: str | None) -> dict[str, Any]:
    """Validate the Cloud Tasks OIDC Bearer token.

    Returns the decoded payload on success.
    Raises HTTPException(401) on failure.
    """
    expected_sa = (os.environ.get("HAM_CLOUD_TASKS_SERVICE_ACCOUNT") or "").strip()
    expected_aud = (os.environ.get("HAM_DISPATCHER_AUDIENCE") or "").strip()

    if not expected_sa or not expected_aud:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "DISPATCHER_NOT_CONFIGURED",
                    "message": (
                        "HAM_CLOUD_TASKS_SERVICE_ACCOUNT and HAM_DISPATCHER_AUDIENCE "
                        "must be set to enable the dispatcher endpoint."
                    ),
                }
            },
        )

    auth_header = (authorization or "").strip()
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "DISPATCHER_TOKEN_MISSING",
                    "message": "Authorization: Bearer <OIDC token> required.",
                }
            },
        )

    token = auth_header[7:].strip()
    payload = _verify_google_oidc_token(token, expected_aud=expected_aud)

    # Validate email claim (service account)
    email = str(payload.get("email") or "")
    if email != expected_sa:
        _LOG.warning("OIDC email mismatch: got %r, expected %r", email, expected_sa)
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "DISPATCHER_TOKEN_INVALID",
                    "message": "OIDC token email does not match expected service account.",
                }
            },
        )

    return payload


# ---------------------------------------------------------------------------
# GKE pod scheduler (Protocol + singleton)
# ---------------------------------------------------------------------------


class WorkerPodSchedulerProtocol:
    """Interface for scheduling a Worker pod.

    Production implementation wraps the GKE client.
    Tests substitute a fake.
    """

    def schedule_worker_pod(self, *, job_id: str, plan_id: str, workspace_id: str, project_id: str) -> str:
        """Schedule a Worker pod and return its pod name."""
        raise NotImplementedError


class _DisabledPodScheduler(WorkerPodSchedulerProtocol):
    """Default scheduler when GKE client is not configured.

    Returns a stub pod name so the dispatcher can be tested end-to-end
    without a live cluster.
    """

    def schedule_worker_pod(
        self,
        *,
        job_id: str,
        plan_id: str,
        workspace_id: str,
        project_id: str,
    ) -> str:
        _LOG.info(
            "DisabledPodScheduler: would schedule pod for job_id=%s plan_id=%s",
            job_id,
            plan_id,
        )
        return f"ham-worker-{job_id[:12]}"


_SCHEDULER_SINGLETON: list[WorkerPodSchedulerProtocol | None] = [None]

_WORKER_POD_SCHEDULER_BACKEND_ENV = "HAM_WORKER_POD_SCHEDULER_BACKEND"


def build_worker_pod_scheduler() -> WorkerPodSchedulerProtocol:
    """Pick the worker pod scheduler backend based on env.

    Defaults to :class:`_DisabledPodScheduler`. When
    ``HAM_WORKER_POD_SCHEDULER_BACKEND=gke`` is set, returns the GKE
    implementation; misconfiguration raises at construction.
    """
    backend = (os.environ.get(_WORKER_POD_SCHEDULER_BACKEND_ENV) or "").strip().lower()
    if backend == "gke":
        from src.api.internal_dispatcher_gke import (  # noqa: PLC0415
            build_gke_worker_pod_scheduler,
        )

        return build_gke_worker_pod_scheduler()
    return _DisabledPodScheduler()


def get_worker_pod_scheduler() -> WorkerPodSchedulerProtocol:
    if _SCHEDULER_SINGLETON[0] is None:
        _SCHEDULER_SINGLETON[0] = build_worker_pod_scheduler()
    return _SCHEDULER_SINGLETON[0]


def set_worker_pod_scheduler_for_tests(scheduler: WorkerPodSchedulerProtocol | None) -> None:
    _SCHEDULER_SINGLETON[0] = scheduler


# ---------------------------------------------------------------------------
# Dispatcher endpoint
# ---------------------------------------------------------------------------


@router.post("/api/internal/dispatch-worker")
async def dispatch_worker(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Receive a WorkerEnvelope from Cloud Tasks and schedule a Worker pod.

    Returns 200 immediately after scheduling; does NOT wait for the pod.
    """
    # 1. Validate OIDC token
    _validate_oidc_token(authorization)

    # 2. Parse body as WorkerEnvelope
    try:
        body_bytes = await request.body()
        body_json = json.loads(body_bytes.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "DISPATCHER_BODY_INVALID",
                    "message": f"Request body is not valid JSON: {exc}",
                }
            },
        ) from exc

    try:
        envelope = WorkerEnvelope.model_validate(body_json)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "DISPATCHER_ENVELOPE_INVALID",
                    "message": f"Request body does not match WorkerEnvelope schema: {exc}",
                }
            },
        ) from exc

    job_store: BuilderRuntimeJobStoreProtocol = get_builder_runtime_job_store()

    # 3. Idempotency: load job; if already terminal, return 200 and skip
    existing = job_store.get_cloud_runtime_job(
        workspace_id=envelope.workspace_id,
        project_id=envelope.project_id,
        job_id=envelope.job_id,
    )

    if existing is None:
        # Create the job record if it doesn't already exist
        new_job = CloudRuntimeJob(
            id=envelope.job_id,
            workspace_id=envelope.workspace_id,
            project_id=envelope.project_id,
            status="queued",
            phase="received",
            provider="gcp_gke_worker",
            requested_by=envelope.requested_by,
            metadata={"plan_id": envelope.plan_id, "envelope_id": envelope.envelope_id},
        )
        job_store.upsert_cloud_runtime_job(new_job)
        existing = new_job

    if existing.status in _TERMINAL_STATUSES:
        _LOG.info(
            "dispatch_worker: job %s already terminal (%s) — idempotent skip",
            envelope.job_id,
            existing.status,
        )
        return {
            "ok": True,
            "job_id": envelope.job_id,
            "status": existing.status,
            "skipped": True,
        }

    # 3b. Phase-based idempotency: if a prior delivery already scheduled the
    # pod, return the cached name (3e guardrail per docs/PHASE_2_5_DESIGN.md).
    if str(existing.phase or "").strip().lower() == "scheduled":
        cached_pod_name = ""
        if existing.metadata:
            cached_pod_name = str(existing.metadata.get("pod_name") or "")
        if cached_pod_name:
            _LOG.info(
                "dispatch_worker: job %s already scheduled as pod %s — idempotent skip",
                envelope.job_id,
                cached_pod_name,
            )
            return {
                "ok": True,
                "job_id": envelope.job_id,
                "pod_name": cached_pod_name,
                "skipped": True,
            }

    # 4. Schedule GKE Worker pod
    scheduler = get_worker_pod_scheduler()
    try:
        pod_name = scheduler.schedule_worker_pod(
            job_id=envelope.job_id,
            plan_id=envelope.plan_id,
            workspace_id=envelope.workspace_id,
            project_id=envelope.project_id,
        )
    except Exception as exc:
        _LOG.error(
            "dispatch_worker: pod scheduling failed for job %s: %s",
            envelope.job_id,
            exc,
            exc_info=True,
        )
        err = make_error(
            WORKER_DISPATCH_FAILED,
            f"Worker pod scheduling failed: {exc}",
            fatal=True,
        )
        failed_job = existing.model_copy(
            update={
                "status": "failed",
                "last_error": err,
                "updated_at": _utc_now_iso(),
                "completed_at": _utc_now_iso(),
            }
        )
        job_store.upsert_cloud_runtime_job(failed_job)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "DISPATCHER_POD_SCHEDULE_FAILED",
                    "message": "Worker pod scheduling failed; Cloud Tasks will retry.",
                }
            },
        ) from exc

    # 4b. Persist phase=scheduled + cached pod_name so redelivery short-circuits.
    updated_metadata = dict(existing.metadata or {})
    updated_metadata["pod_name"] = pod_name
    scheduled_job = existing.model_copy(
        update={
            "phase": "scheduled",
            "metadata": updated_metadata,
            "updated_at": _utc_now_iso(),
        }
    )
    try:
        job_store.upsert_cloud_runtime_job(scheduled_job)
    except Exception as exc:  # noqa: BLE001
        # Don't fail the dispatch if the marker write fails — K8s Job
        # get-before-create is the second line of defence. Just log.
        _LOG.warning(
            "dispatch_worker: failed to persist phase=scheduled for job %s: %s",
            envelope.job_id,
            exc,
        )

    # 5. Return 200 immediately
    _LOG.info(
        "dispatch_worker: scheduled pod %s for job_id=%s plan_id=%s",
        pod_name,
        envelope.job_id,
        envelope.plan_id,
    )
    return {
        "ok": True,
        "job_id": envelope.job_id,
        "pod_name": pod_name,
        "skipped": False,
    }
