"""Phase 2 — Subsystem 3: Worker pod orchestration.

The BuilderWorker executes one approved Plan end-to-end:
  1. Load Plan from BuilderPlanStore.
  2. Load CloudRuntimeJob from BuilderRuntimeJobStore.
  3. Emit job_started SSEEvent.
  4. Iterate Steps sequentially; for each:
     a. Emit step_started.
     b. Delegate to _execute_step (CLI-agentic runtime per AGENTS.md).
     c. Emit step_completed or step_failed.
     d. Check cancel signal at step boundary (ADR-0004).
  5. On all Steps success: invoke builder_verifier.
  6. Emit job_completed / job_failed / job_cancelled.
  7. Update CloudRuntimeJob to terminal status.

Pod entrypoint: reads HAM_WORKER_JOB_ID env var (set by dispatcher),
calls BuilderWorker(job_id).run(), exits.

Spec: docs/PHASE_2_DESIGN.md § Subsystem 3
ADR: docs/adr/0001-plan-is-unit-of-work.md
ADR: docs/adr/0004-cancel-is-step-boundary-cooperative.md
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Callable

from src.ham.builder_error_codes import (
    INTERNAL_ERROR,
    STEP_FAILED,
    STEP_VERIFICATION_FAILED,
    make_error,
)
from src.ham.builder_plan import (
    CancelAcknowledgedPayload,
    ErrorEnvelope,
    JobCancelledPayload,
    JobCompletedPayload,
    JobFailedPayload,
    JobStartedPayload,
    Plan,
    SSEEvent,
    Step,
    StepCompletedPayload,
    StepFailedPayload,
    StepLogPayload,
    StepStartedPayload,
)
from src.ham.builder_verifier import VerifierOutcome, verify
from src.persistence.builder_plan_store import (
    BuilderPlanStoreProtocol,
    get_builder_plan_store,
)
from src.persistence.builder_run_events_store import (
    BuilderRunEventsStoreProtocol,
    get_builder_run_events_store,
)
from src.persistence.builder_runtime_job_store import (
    BuilderRuntimeJobStoreProtocol,
    CloudRuntimeJob,
    get_builder_runtime_job_store,
)

_LOG = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Step result
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    success: bool
    log_text: str = ""
    error_envelope: ErrorEnvelope | None = None


# ---------------------------------------------------------------------------
# BuilderWorker
# ---------------------------------------------------------------------------


class BuilderWorker:
    """Orchestrates execution of one approved Plan inside a Worker pod.

    Stores are injected for testing; production uses the module-level singletons.
    """

    def __init__(
        self,
        job_id: str,
        *,
        plan_store: BuilderPlanStoreProtocol | None = None,
        job_store: BuilderRuntimeJobStoreProtocol | None = None,
        events_store: BuilderRunEventsStoreProtocol | None = None,
        preview_url: str = "",
    ) -> None:
        self._job_id = job_id
        self._plan_store = plan_store or get_builder_plan_store()
        self._job_store = job_store or get_builder_runtime_job_store()
        self._events_store = events_store or get_builder_run_events_store()
        self._preview_url = preview_url
        # Populated during run()
        self._job: CloudRuntimeJob | None = None
        self._plan: Plan | None = None

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def run(self) -> None:
        """Full Worker lifecycle: load → execute → verify → terminal status."""
        _LOG.info("BuilderWorker starting for job_id=%s", self._job_id)

        # --- Load job record ---
        job = self._load_job()
        if job is None:
            _LOG.error("Job not found: %s — exiting", self._job_id)
            return
        self._job = job

        # --- Load plan ---
        plan = self._load_plan()
        if plan is None:
            _LOG.error(
                "Plan not found for job %s (plan_id not set in metadata) — failing job",
                self._job_id,
            )
            err = make_error(
                INTERNAL_ERROR,
                f"Plan not found for job {self._job_id}",
                fatal=True,
            )
            self._update_job_status("failed", last_error=err)
            self._emit_job_failed(err)
            return
        self._plan = plan

        # --- Transition job to running ---
        self._update_job_status("running")
        self._emit(JobStartedPayload(), plan_id=plan.plan_id)

        # --- Execute steps ---
        cancelled_at_step_id: str | None = None
        last_error: ErrorEnvelope | None = None

        for idx, step in enumerate(plan.steps):
            # Cancel check at step boundary (ADR-0004)
            if self._check_cancel():
                _LOG.info("Cancel detected before step %d — acknowledging", idx)
                self._emit(CancelAcknowledgedPayload(), plan_id=plan.plan_id)
                cancelled_at_step_id = step.step_id
                self._update_job_status("cancelled")
                self._emit(
                    JobCancelledPayload(cancelled_at_step_id=cancelled_at_step_id),
                    plan_id=plan.plan_id,
                )
                return

            # Emit step_started
            self._emit(
                StepStartedPayload(step_id=step.step_id, step_index=idx, title=step.title),
                plan_id=plan.plan_id,
            )

            # Execute step
            result = self._execute_step(step, step_index=idx, cancel_check=self._check_cancel)

            if result.log_text:
                self._emit(
                    StepLogPayload(step_id=step.step_id, text=result.log_text),
                    plan_id=plan.plan_id,
                )

            if not result.success:
                err = result.error_envelope or make_error(
                    STEP_FAILED,
                    f"Step '{step.title}' failed",
                    fatal=True,
                )
                self._emit(
                    StepFailedPayload(step_id=step.step_id, step_index=idx, error=err),
                    plan_id=plan.plan_id,
                )
                last_error = err
                self._update_job_status("failed", last_error=err)
                self._emit_job_failed(err)
                return

            self._emit(
                StepCompletedPayload(step_id=step.step_id, step_index=idx),
                plan_id=plan.plan_id,
            )

        # --- All steps done — run verifier ---
        if self._preview_url:
            outcome = self._run_verifier(plan)
            if not outcome.success and outcome.error_envelope is not None:
                err = outcome.error_envelope
                _LOG.warning("Verifier failed for plan %s: %s", plan.plan_id, err.error_message)
                # Attribute to "final verification step"
                if plan.steps:
                    last_step = plan.steps[-1]
                    self._emit(
                        StepFailedPayload(
                            step_id=last_step.step_id,
                            step_index=len(plan.steps) - 1,
                            error=err,
                        ),
                        plan_id=plan.plan_id,
                    )
                self._update_job_status("failed", last_error=err)
                self._emit_job_failed(err)
                return

        # --- Success ---
        self._update_job_status("completed")
        self._emit(JobCompletedPayload(), plan_id=plan.plan_id)
        _LOG.info("BuilderWorker completed job_id=%s successfully", self._job_id)

    def _execute_step(
        self,
        step: Step,
        *,
        step_index: int = 0,
        cancel_check: Callable[[], bool] | None = None,
    ) -> StepResult:
        """Execute a single Step via the Step executor.

        PR 1: Delegates to droid_executor with a no-op command so the Worker
        skeleton is functional.  Real routing (per-kind executor selection) lands
        in subsequent PRs when the Planner is wired into chat and Step kinds are
        defined.

        The cancel_check callable may be polled by long-running executors to
        honour ADR-0004's 5-second acknowledgement target.
        """
        _LOG.info("Executing step[%d] %s: %s", step_index, step.step_id, step.title)

        # PR1 stub: log the step title and return success.
        # Real CLI executor dispatch (droid_executor / Hermes adapter) lands in
        # subsequent PRs when the Planner is wired into chat and Step kinds are
        # defined (per AGENTS.md "CLI-first execution surface").
        log_text = f"[ham-worker] executing step: {step.title}"
        _LOG.info("%s", log_text)
        return StepResult(success=True, log_text=log_text)

    def _check_cancel(self) -> bool:
        """Check whether the job has been signalled for cancellation.

        Reads the job record from the store.  Returns True if status is
        'cancelling' or 'cancelled' (ADR-0004: step-boundary cooperative cancel).
        """
        if self._job is None:
            return False
        try:
            refreshed = self._job_store.get_cloud_runtime_job(
                workspace_id=self._job.workspace_id,
                project_id=self._job.project_id,
                job_id=self._job_id,
            )
            if refreshed is None:
                return False
            return refreshed.status in ("cancelling", "cancelled")
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("_check_cancel: store read failed (%s) — assuming not cancelled", exc)
            return False

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _load_job(self) -> CloudRuntimeJob | None:
        # The dispatcher writes the job before scheduling the pod.
        # We do a broad scan since we don't have workspace/project handy yet.
        try:
            from src.persistence.builder_runtime_job_store import BuilderRuntimeJobStore
            # Direct low-level scan: iterate all workspace-agnostic
            store = self._job_store
            # Try the protocol method — stores that support scan-by-id
            if hasattr(store, "get_cloud_runtime_job_by_id"):
                return store.get_cloud_runtime_job_by_id(job_id=self._job_id)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

        # Fallback: load from metadata injected into job record
        # The dispatcher is expected to set workspace_id + project_id on the job.
        # For the stub, we try a well-known pattern used by the test harness.
        return None

    def _load_job_with_context(
        self,
        *,
        workspace_id: str,
        project_id: str,
    ) -> CloudRuntimeJob | None:
        return self._job_store.get_cloud_runtime_job(
            workspace_id=workspace_id,
            project_id=project_id,
            job_id=self._job_id,
        )

    def _load_plan(self) -> Plan | None:
        if self._job is None:
            return None
        plan_id: str | None = self._job.metadata.get("plan_id") if self._job.metadata else None
        if not plan_id:
            _LOG.error("No plan_id in job %s metadata", self._job_id)
            return None
        return self._plan_store.get_plan(plan_id=plan_id)

    def _emit(self, payload: object, *, plan_id: str) -> SSEEvent:
        """Append an SSEEvent to the events store and return it."""
        event = SSEEvent(
            seq=0,  # store assigns the real seq
            job_id=self._job_id,
            plan_id=plan_id,
            occurred_at=_utc_now_iso(),
            event=payload,  # type: ignore[arg-type]
        )
        return self._events_store.append(event)

    def _emit_job_failed(self, err: ErrorEnvelope, *, plan_id: str | None = None) -> None:
        effective_plan_id = (
            plan_id
            or (self._plan.plan_id if self._plan is not None else None)
            or (self._job.metadata.get("plan_id") if self._job and self._job.metadata else None)
            or "pln_unknown"
        )
        self._emit(JobFailedPayload(error=err), plan_id=effective_plan_id)

    def _update_job_status(
        self,
        status: str,
        *,
        last_error: ErrorEnvelope | None = None,
    ) -> None:
        if self._job is None:
            return
        updated = self._job.model_copy(
            update={
                "status": status,
                "updated_at": _utc_now_iso(),
                "last_error": last_error,
            }
        )
        if status in ("completed", "failed", "cancelled"):
            updated = updated.model_copy(update={"completed_at": _utc_now_iso()})
        self._job = self._job_store.upsert_cloud_runtime_job(updated)

    def _run_verifier(self, plan: Plan) -> VerifierOutcome:
        try:
            return verify(plan, self._preview_url)
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("Verifier raised %s: %s", type(exc).__name__, exc)
            err = make_error(
                STEP_VERIFICATION_FAILED,
                f"Verifier raised {type(exc).__name__}: {exc}",
                fatal=False,
                retriable=True,
            )
            return VerifierOutcome(success=False, error_envelope=err)


# ---------------------------------------------------------------------------
# Pod entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    """Worker pod entrypoint.

    Reads HAM_WORKER_JOB_ID from env, calls BuilderWorker(job_id).run().
    The dispatcher sets this env var when scheduling the pod.
    """
    job_id = os.environ.get("HAM_WORKER_JOB_ID", "").strip()
    if not job_id:
        print("ERROR: HAM_WORKER_JOB_ID env var is not set", file=sys.stderr)
        sys.exit(1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _LOG.info("HAM Worker pod starting: job_id=%s", job_id)
    try:
        BuilderWorker(job_id).run()
    except Exception as exc:  # noqa: BLE001
        _LOG.exception("Worker pod unhandled exception: %s", exc)
        sys.exit(2)


if __name__ == "__main__":
    main()
