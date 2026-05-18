"""CloudRuntimeJob post-approval status transitions — Contract 6.

Centralizes which (from_status, to_status) pairs are legal so every
Phase 1+ call site uses one validator.

Spec: docs/PHASE_0_CONTRACTS.md § Contract 6
ADR: docs/adr/0004-cancel-is-step-boundary-cooperative.md
"""

from __future__ import annotations

from src.ham.builder_plan import CloudRuntimeJobStatus

_TERMINAL: frozenset[str] = frozenset({"cancelled", "completed", "failed"})

_LEGAL_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("queued", "running"),
        ("queued", "cancelled"),
        ("queued", "failed"),
        ("running", "cancelling"),
        ("running", "completed"),
        ("running", "failed"),
        ("cancelling", "cancelled"),
    }
)


def validate_transition(
    from_status: CloudRuntimeJobStatus,
    to_status: CloudRuntimeJobStatus,
) -> None:
    """Raise ValueError if the transition is illegal.

    Legal transitions (per Contract 6):
      queued    → running | cancelled | failed
      running   → cancelling | completed | failed
      cancelling → cancelled
    Terminal states (cancelled, completed, failed) cannot transition.
    """
    if (from_status, to_status) in _LEGAL_TRANSITIONS:
        return

    if from_status in _TERMINAL:
        raise ValueError(
            f"Cannot transition from terminal state {from_status!r} to {to_status!r}"
        )

    raise ValueError(
        f"Illegal status transition: {from_status!r} → {to_status!r}"
    )
