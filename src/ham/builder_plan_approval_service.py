"""Plan approval gate — Phase 0 Contract 2 + ADR-0003.

Validates per-project serialization and snapshot drift, transitions the
PlanApprovalRecord, creates a CloudRuntimeJob, and enqueues a WorkerEnvelope.

Spec: docs/PHASE_0_CONTRACTS.md § Contract 2
ADR: docs/adr/0003-approval-gate-enforces-per-project-serialization.md
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, runtime_checkable

from src.ham.builder_error_codes import GATE_ENQUEUE_FAILED, make_error
from src.ham.builder_plan import Plan, PlanApprovalRecord, WorkerEnvelope
from src.ham.builder_plan_approval import transition
from src.persistence.builder_plan_store import BuilderPlanStoreProtocol, get_builder_plan_store
from src.persistence.builder_runtime_job_store import (
    BuilderRuntimeJobStoreProtocol,
    CloudRuntimeJob,
    get_builder_runtime_job_store,
)
from src.persistence.builder_source_store import get_builder_source_store

_LOG = logging.getLogger(__name__)

_ACTIVE_JOB_STATUSES = frozenset({"queued", "running", "cancelling"})


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_job_id() -> str:
    return f"crjb_{uuid.uuid4().hex}"


def resolve_current_source_snapshot_id(*, workspace_id: str, project_id: str) -> str | None:
    """Best-effort current snapshot for staleness checks at the approval gate."""
    sources = get_builder_source_store().list_project_sources(
        workspace_id=workspace_id,
        project_id=project_id,
    )
    for src in sources:
        if str(src.status or "").strip().lower() == "ready":
            sid = str(src.active_snapshot_id or "").strip()
            if sid:
                return sid
    for src in sources:
        sid = str(src.active_snapshot_id or "").strip()
        if sid:
            return sid
    return None


ApprovePlanErrorCode = Literal["not_found", "plan_stale", "project_busy", "enqueue_failed"]


@dataclass(frozen=True)
class ApprovePlanError(Exception):
    code: ApprovePlanErrorCode
    message: str
    details: dict[str, str] | None = None

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class ApprovePlanResult:
    plan_id: str
    job_id: str
    approval_state: str


@runtime_checkable
class WorkerEnqueueProtocol(Protocol):
    def enqueue(self, envelope: WorkerEnvelope, *, job: CloudRuntimeJob) -> None: ...


class _NoOpWorkerEnqueue:
    """Default: persist job only; dispatcher/worker wiring is environment-specific."""

    def enqueue(self, envelope: WorkerEnvelope, *, job: CloudRuntimeJob) -> None:
        _LOG.info(
            "Plan approved: job_id=%s plan_id=%s (no enqueue hook configured)",
            envelope.job_id,
            envelope.plan_id,
        )


_ENQUEUE_SINGLETON: list[WorkerEnqueueProtocol | None] = [None]


def get_worker_enqueue() -> WorkerEnqueueProtocol:
    if _ENQUEUE_SINGLETON[0] is None:
        _ENQUEUE_SINGLETON[0] = _NoOpWorkerEnqueue()
    return _ENQUEUE_SINGLETON[0]


def set_worker_enqueue_for_tests(enqueue: WorkerEnqueueProtocol | None) -> None:
    _ENQUEUE_SINGLETON[0] = enqueue


def _find_blocking_job(
    *,
    workspace_id: str,
    project_id: str,
    job_store: BuilderRuntimeJobStoreProtocol,
) -> CloudRuntimeJob | None:
    for row in job_store.list_cloud_runtime_jobs(workspace_id=workspace_id, project_id=project_id):
        status = str(row.status or "").strip().lower()
        if status == "succeeded":
            status = "completed"
        if status in _ACTIVE_JOB_STATUSES:
            return row
    return None


def approve_plan(
    *,
    plan_id: str,
    requested_by: str,
    plan_store: BuilderPlanStoreProtocol | None = None,
    job_store: BuilderRuntimeJobStoreProtocol | None = None,
    enqueue: WorkerEnqueueProtocol | None = None,
) -> ApprovePlanResult:
    """Run the approval gate for *plan_id*.

    Raises :class:`ApprovePlanError` with ``code`` matching HTTP 404/409 cases.
    """
    plan_store = plan_store or get_builder_plan_store()
    job_store = job_store or get_builder_runtime_job_store()
    enqueue_impl = enqueue or get_worker_enqueue()

    plan = plan_store.get_plan(plan_id=plan_id)
    if plan is None:
        raise ApprovePlanError("not_found", f"Plan {plan_id!r} not found")

    record = plan_store.get_approval_record(plan_id=plan_id)
    if record is None:
        record = PlanApprovalRecord(plan_id=plan_id, state="proposed", proposed_at=_utc_now_iso())
        plan_store.upsert_approval_record(record)

    if record.state == "approved":
        for row in job_store.list_cloud_runtime_jobs(
            workspace_id=plan.workspace_id,
            project_id=plan.project_id,
        ):
            meta = row.metadata or {}
            if str(meta.get("plan_id") or "") == plan_id:
                return ApprovePlanResult(
                    plan_id=plan_id,
                    job_id=row.id,
                    approval_state="approved",
                )
        raise ApprovePlanError(
            "not_found",
            f"Plan {plan_id!r} is approved but no CloudRuntimeJob was found",
        )

    if record.state == "stale":
        raise ApprovePlanError(
            "plan_stale",
            "Project has changed since this plan was created; ask me again",
            details={"stale_reason": record.stale_reason or "source_snapshot_drift"},
        )

    current_snapshot = resolve_current_source_snapshot_id(
        workspace_id=plan.workspace_id,
        project_id=plan.project_id,
    )
    plan_snapshot = str(plan.source_snapshot_id or "").strip() or None
    if plan_snapshot and current_snapshot and plan_snapshot != current_snapshot:
        stale_record = transition(
            record,
            "mark_stale",
            stale_reason="source_snapshot_drift",
        )
        plan_store.upsert_approval_record(stale_record)
        raise ApprovePlanError(
            "plan_stale",
            "Project has changed since this plan was created; ask me again",
            details={
                "original_snapshot_id": plan_snapshot,
                "current_snapshot_id": current_snapshot,
            },
        )

    blocking = _find_blocking_job(
        workspace_id=plan.workspace_id,
        project_id=plan.project_id,
        job_store=job_store,
    )
    if blocking is not None:
        raise ApprovePlanError(
            "project_busy",
            "Another build is running for this project; cancel it first",
            details={"blocking_job_id": blocking.id},
        )

    try:
        approved_record = transition(record, "approve")
    except ValueError as exc:
        raise ApprovePlanError("plan_stale", str(exc)) from exc
    plan_store.upsert_approval_record(approved_record)

    job_id = _new_job_id()
    job = CloudRuntimeJob(
        id=job_id,
        workspace_id=plan.workspace_id,
        project_id=plan.project_id,
        source_snapshot_id=plan.source_snapshot_id,
        status="queued",
        phase="received",
        provider="gcp_gke_worker",
        requested_by=requested_by or None,
        metadata={
            "plan_id": plan.plan_id,
            "approval_gate": "phase0_v1",
        },
    )
    job_store.upsert_cloud_runtime_job(job)

    envelope = WorkerEnvelope(
        plan_id=plan.plan_id,
        job_id=job_id,
        workspace_id=plan.workspace_id,
        project_id=plan.project_id,
        requested_by=requested_by or "unknown",
        correlation_id=job_id,
    )

    try:
        enqueue_impl.enqueue(envelope, job=job)
    except Exception as exc:
        _LOG.warning("enqueue failed for plan %s job %s: %s", plan_id, job_id, exc)
        err = make_error(
            GATE_ENQUEUE_FAILED,
            f"Failed to enqueue worker for plan {plan_id}: {exc}",
            fatal=True,
        )
        failed_job = job.model_copy(
            update={
                "status": "failed",
                "last_error": err,
                "updated_at": _utc_now_iso(),
                "completed_at": _utc_now_iso(),
            }
        )
        job_store.upsert_cloud_runtime_job(failed_job)
        raise ApprovePlanError(
            "enqueue_failed",
            "Plan was approved but the worker could not be enqueued",
            details={"job_id": job_id, "error_code": GATE_ENQUEUE_FAILED},
        ) from exc

    if os.environ.get("HAM_BUILDER_WORKER_INLINE_RUN", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        try:
            from src.ham.builder_worker import BuilderWorker

            BuilderWorker(job_id).run()
        except Exception as exc:
            _LOG.warning("inline worker run failed for %s: %s", job_id, exc)

    return ApprovePlanResult(plan_id=plan_id, job_id=job_id, approval_state="approved")
