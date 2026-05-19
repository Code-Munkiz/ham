"""Worker pod entrypoint — Phase 2.5.

K8s Job ``CMD`` is ``["python", "-m", "src.ham.worker_main"]``. This module
reads identifying env vars, verifies the fetched
:class:`CloudRuntimeJob` and :class:`Plan` match the env-supplied
identifiers, applies the events-store startup guard (ADR-0013), and then
delegates to :class:`src.ham.builder_worker.BuilderWorker` for the actual
Plan execution.

## Env contract

| Var | Purpose |
|---|---|
| ``HAM_JOB_ID`` | Required. ``CloudRuntimeJob.id`` to execute. |
| ``HAM_PLAN_ID`` | Required. Verified against ``Job.metadata['plan_id']``. |
| ``HAM_WORKSPACE_ID`` | Required. Verified against ``Job.workspace_id``. |
| ``HAM_PROJECT_ID`` | Required. Verified against ``Job.project_id``. |
| ``HAM_WORKER_IMAGE`` | Required. Logged at startup as the build identity stamp. |
| ``HAM_*_STORE_BACKEND`` | Activates Firestore backends for the three stores. |
| ``HAM_FIRESTORE_PROJECT_ID``, ``HAM_FIRESTORE_DATABASE`` | Firestore connection. |

The legacy ``HAM_WORKER_JOB_ID`` is still honoured as a fallback so the
Phase 2 inline path (``HAM_BUILDER_WORKER_INLINE_RUN``) keeps working
without setting all four envs.

## Failure modes (all exit nonzero)

1. Any required env var missing.
2. Job not found in store.
3. Plan not found.
4. Env identifiers do not match the fetched Job/Plan (3c guardrail).
5. Events store reports prior events for this job (ADR-0013 startup guard).
6. Any unhandled exception during execution.

On failure modes 2–6, this module writes
``CloudRuntimeJob.status='failed'`` with an :class:`ErrorEnvelope` to
Firestore before exiting so the user-facing surface reflects the failure
without waiting for the K8s Job timeout (3b guardrail).
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime
from typing import NoReturn

from src.ham.builder_error_codes import INTERNAL_ERROR, make_error
from src.persistence.builder_plan_store import get_builder_plan_store
from src.persistence.builder_run_events_store import get_builder_run_events_store
from src.persistence.builder_runtime_job_store import (
    BuilderRuntimeJobStoreProtocol,
    get_builder_runtime_job_store,
)

_LOG = logging.getLogger(__name__)


_EXIT_OK = 0
_EXIT_CONFIG = 10
_EXIT_NOT_FOUND = 11
_EXIT_MISMATCH = 12
_EXIT_DIRTY_EVENTS = 13
_EXIT_UNHANDLED = 20


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _env_or_empty(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _resolved_job_id() -> str:
    # Phase 2.5 prefers HAM_JOB_ID; HAM_WORKER_JOB_ID is the legacy name
    # from Phase 2's inline path. Either is accepted.
    return _env_or_empty("HAM_JOB_ID") or _env_or_empty("HAM_WORKER_JOB_ID")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _exit_with_job_failure(
    *,
    job_id: str,
    error_code: str,
    error_message: str,
    exit_code: int,
    job_store: BuilderRuntimeJobStoreProtocol | None = None,
) -> NoReturn:
    """Write ``status=failed`` to Firestore (best-effort) then sys.exit.

    Used for terminal failures discovered during startup — we want the
    user-facing job state to reflect the failure even though K8s would
    eventually also mark the Job failed (3b guardrail).
    """
    err = make_error(error_code, error_message, fatal=True)
    store = job_store or get_builder_runtime_job_store()
    try:
        # Try by-id lookup (Firestore store has it; file store may also).
        existing = None
        if hasattr(store, "get_cloud_runtime_job_by_id"):
            existing = store.get_cloud_runtime_job_by_id(job_id=job_id)  # type: ignore[attr-defined]
        if existing is not None:
            now = _utc_now_iso()
            failed = existing.model_copy(
                update={
                    "status": "failed",
                    "last_error": err,
                    "updated_at": now,
                    "completed_at": now,
                }
            )
            store.upsert_cloud_runtime_job(failed)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning(
            "worker_main: could not persist failure status for %s: %s",
            job_id,
            exc,
        )
    _LOG.error("worker_main: %s (%s) — exiting %d", error_message, error_code, exit_code)
    sys.exit(exit_code)


def main() -> int:
    _setup_logging()

    # --- 1. Read env identifiers ---
    job_id = _resolved_job_id()
    plan_id = _env_or_empty("HAM_PLAN_ID")
    workspace_id = _env_or_empty("HAM_WORKSPACE_ID")
    project_id = _env_or_empty("HAM_PROJECT_ID")
    image_ref = _env_or_empty("HAM_WORKER_IMAGE")

    if not job_id:
        _LOG.error("worker_main: HAM_JOB_ID (or HAM_WORKER_JOB_ID) is required")
        return _EXIT_CONFIG
    if not plan_id:
        _LOG.error("worker_main: HAM_PLAN_ID is required")
        return _EXIT_CONFIG
    if not workspace_id:
        _LOG.error("worker_main: HAM_WORKSPACE_ID is required")
        return _EXIT_CONFIG
    if not project_id:
        _LOG.error("worker_main: HAM_PROJECT_ID is required")
        return _EXIT_CONFIG
    if not image_ref:
        _LOG.error("worker_main: HAM_WORKER_IMAGE is required")
        return _EXIT_CONFIG

    # --- 2. Build identity stamp ---
    _LOG.info(
        "HAM Worker starting: job_id=%s plan_id=%s workspace_id=%s project_id=%s image=%s",
        job_id,
        plan_id,
        workspace_id,
        project_id,
        image_ref,
    )

    # --- 3. Fetch Job and verify env match (3c guardrail) ---
    job_store = get_builder_runtime_job_store()
    job = None
    if hasattr(job_store, "get_cloud_runtime_job_by_id"):
        try:
            job = job_store.get_cloud_runtime_job_by_id(job_id=job_id)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            _LOG.error("worker_main: get_cloud_runtime_job_by_id failed: %s", exc)
            return _EXIT_NOT_FOUND
    else:
        # Fall back to context-scoped lookup using the env identifiers.
        try:
            job = job_store.get_cloud_runtime_job(
                workspace_id=workspace_id,
                project_id=project_id,
                job_id=job_id,
            )
        except Exception as exc:  # noqa: BLE001
            _LOG.error("worker_main: get_cloud_runtime_job failed: %s", exc)
            return _EXIT_NOT_FOUND

    if job is None:
        _LOG.error("worker_main: job %s not found", job_id)
        return _EXIT_NOT_FOUND

    if job.workspace_id != workspace_id:
        _exit_with_job_failure(
            job_id=job_id,
            error_code=INTERNAL_ERROR,
            error_message=(
                f"workspace_id mismatch: env={workspace_id!r} job={job.workspace_id!r}"
            ),
            exit_code=_EXIT_MISMATCH,
            job_store=job_store,
        )

    if job.project_id != project_id:
        _exit_with_job_failure(
            job_id=job_id,
            error_code=INTERNAL_ERROR,
            error_message=(
                f"project_id mismatch: env={project_id!r} job={job.project_id!r}"
            ),
            exit_code=_EXIT_MISMATCH,
            job_store=job_store,
        )

    job_plan_id = ""
    if job.metadata:
        job_plan_id = str(job.metadata.get("plan_id") or "")
    if job_plan_id != plan_id:
        _exit_with_job_failure(
            job_id=job_id,
            error_code=INTERNAL_ERROR,
            error_message=(
                f"plan_id mismatch: env={plan_id!r} job.metadata.plan_id={job_plan_id!r}"
            ),
            exit_code=_EXIT_MISMATCH,
            job_store=job_store,
        )

    # --- 4. Verify Plan exists ---
    plan_store = get_builder_plan_store()
    plan = plan_store.get_plan(plan_id=plan_id)
    if plan is None:
        _exit_with_job_failure(
            job_id=job_id,
            error_code=INTERNAL_ERROR,
            error_message=f"plan {plan_id!r} not found in store",
            exit_code=_EXIT_NOT_FOUND,
            job_store=job_store,
        )

    # --- 5. Startup guard: refuse to run if events already exist for this job ---
    events_store = get_builder_run_events_store()
    try:
        latest = events_store.latest_seq(job_id=job_id)
    except Exception as exc:  # noqa: BLE001
        _exit_with_job_failure(
            job_id=job_id,
            error_code=INTERNAL_ERROR,
            error_message=f"events_store.latest_seq failed: {exc}",
            exit_code=_EXIT_DIRTY_EVENTS,
            job_store=job_store,
        )

    if latest > 0:
        _exit_with_job_failure(
            job_id=job_id,
            error_code=INTERNAL_ERROR,
            error_message=(
                f"events already exist for job {job_id!r} (latest_seq={latest}); "
                "refusing to start — one-Worker-per-job invariant would be violated"
            ),
            exit_code=_EXIT_DIRTY_EVENTS,
            job_store=job_store,
        )

    # --- 6. Delegate to BuilderWorker ---
    try:
        from src.ham.builder_worker import BuilderWorker  # noqa: PLC0415

        worker = BuilderWorker(
            job_id,
            plan_store=plan_store,
            job_store=job_store,
            events_store=events_store,
        )
        worker.run()
    except Exception as exc:  # noqa: BLE001
        _LOG.exception("worker_main: unhandled exception: %s", exc)
        _exit_with_job_failure(
            job_id=job_id,
            error_code=INTERNAL_ERROR,
            error_message=f"unhandled exception in BuilderWorker.run(): {exc}",
            exit_code=_EXIT_UNHANDLED,
            job_store=job_store,
        )

    return _EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
