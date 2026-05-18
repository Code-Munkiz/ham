"""Plan approval state machine — Contract 2.

Centralizes PROPOSED → APPROVED / STALE transitions so every Phase 1+
call site uses one validator instead of re-implementing the rules.

Spec: docs/PHASE_0_CONTRACTS.md § Contract 2
ADR: docs/adr/0001-plan-is-unit-of-work.md
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from src.ham.builder_plan import PlanApprovalRecord


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def transition(
    record: PlanApprovalRecord,
    action: Literal["approve", "mark_stale"],
    *,
    stale_reason: str | None = None,
) -> PlanApprovalRecord:
    """Apply *action* to *record* and return a NEW PlanApprovalRecord.

    Raises ValueError for illegal transitions:
    - STALE + approve (the STALE wall; Contract 2)
    - APPROVED + anything (post-approval immutability; ADR-0001)
    """
    if record.state == "approved":
        raise ValueError(
            f"Cannot transition from 'approved': post-approval records are immutable (action={action!r})"
        )

    if record.state == "stale":
        if action == "approve":
            raise ValueError("Cannot approve a stale plan — must replan first")
        raise ValueError(
            f"Cannot transition from terminal state 'stale' (action={action!r})"
        )

    # state == "proposed"
    if action == "approve":
        return record.model_copy(
            update={"state": "approved", "approved_at": _utc_now_iso()}
        )

    if action == "mark_stale":
        return record.model_copy(
            update={
                "state": "stale",
                "stale_at": _utc_now_iso(),
                "stale_reason": stale_reason,
            }
        )

    raise ValueError(f"Unknown action: {action!r}")
