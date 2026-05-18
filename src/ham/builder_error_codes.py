"""Error code catalog + make_error() factory — Contract 5.

Every error producer in Phase 1+ must use constants from this module
and build ErrorEnvelopes via make_error(). Typos become AttributeError
at import time rather than silent miscoded strings at runtime.

Spec: docs/PHASE_0_CONTRACTS.md § Contract 5
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.ham.builder_plan import ErrorEnvelope


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# v1 error code catalog (15 codes)
# ---------------------------------------------------------------------------

# gate.*
GATE_PLAN_STALE = "gate.plan_stale"
GATE_PROJECT_BUSY = "gate.project_busy"
GATE_ENQUEUE_FAILED = "gate.enqueue_failed"

# worker.*
WORKER_DISPATCH_FAILED = "worker.worker_dispatch_failed"
WORKER_TIMEOUT = "worker.worker_timeout"
WORKER_OOM = "worker.worker_oom"

# step.*
STEP_FAILED = "step.step_failed"
STEP_TIMEOUT = "step.step_timeout"
STEP_TOOL_CALL_FAILED = "step.tool_call_failed"
STEP_MODEL_UNAVAILABLE = "step.model_unavailable"

# preview.*
PREVIEW_POD_CRASHED = "preview.preview_pod_crashed"
PREVIEW_POD_UNSCHEDULABLE = "preview.preview_pod_unschedulable"
PREVIEW_NETWORK_EGRESS_DENIED = "preview.network_egress_denied"
PREVIEW_PACKAGE_INSTALL_DENIED = "preview.package_install_denied"

# unprefixed
INTERNAL_ERROR = "internal_error"

ALL_CODES: frozenset[str] = frozenset(
    {
        GATE_PLAN_STALE,
        GATE_PROJECT_BUSY,
        GATE_ENQUEUE_FAILED,
        WORKER_DISPATCH_FAILED,
        WORKER_TIMEOUT,
        WORKER_OOM,
        STEP_FAILED,
        STEP_TIMEOUT,
        STEP_TOOL_CALL_FAILED,
        STEP_MODEL_UNAVAILABLE,
        PREVIEW_POD_CRASHED,
        PREVIEW_POD_UNSCHEDULABLE,
        PREVIEW_NETWORK_EGRESS_DENIED,
        PREVIEW_PACKAGE_INSTALL_DENIED,
        INTERNAL_ERROR,
    }
)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_error(
    code: str,
    message: str,
    *,
    fatal: bool,
    retriable: bool = False,
    details: dict[str, Any] | None = None,
) -> ErrorEnvelope:
    """Build a valid ErrorEnvelope with all fields populated.

    ``fatal`` is a required keyword argument — callers must be explicit.
    ``code`` is free-string per Contract 5; callers are expected to pass
    module constants (e.g. ``GATE_PLAN_STALE``).
    """
    return ErrorEnvelope(
        error_code=code,
        error_message=message,
        error_details=details,
        retriable=retriable,
        fatal=fatal,
        occurred_at=_utc_now_iso(),
    )
