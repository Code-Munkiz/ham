"""Job-level TTL janitor policies — Phase 1 #3 (ADR-0004).

Pure function ``evaluate(job, now) -> Decision`` encodes the TTL decision
rules so they are unit-testable without a GKE client or database.

Spec: docs/adr/0004-cancel-is-step-boundary-cooperative.md
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from src.persistence.builder_runtime_job_store import CloudRuntimeJob

Decision = Literal["keep", "cancel", "reap"]

# Statuses that mean the job finished but its pod may still need cleanup.
_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "unsupported"})
# Statuses that are still running and subject to TTL cancellation.
_ACTIVE_STATUSES = frozenset({"queued", "running"})


def _parse_iso_utc(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def evaluate(job: CloudRuntimeJob, now: datetime) -> Decision:
    """Return the janitor action appropriate for ``job`` at ``now``.

    Decision rules (in priority order):
    - ``reap``   — job is in a terminal state; pod may still exist
    - ``cancel`` — job is active and its TTL has elapsed
    - ``keep``   — job is healthy and within TTL (including ``cancelling``)
    """
    status = str(job.status or "")

    if status in _TERMINAL_STATUSES:
        return "reap"

    if status not in _ACTIVE_STATUSES:
        # "cancelling" or unknown — leave alone; the Worker or another signal
        # will drive it to a terminal state.
        return "keep"

    # Compute effective deadline: stored ttl_deadline preferred; fall back to
    # created_at + ttl_seconds so old records without ttl_deadline still work.
    deadline: datetime | None = _parse_iso_utc(job.ttl_deadline)
    if deadline is None:
        created = _parse_iso_utc(job.created_at)
        if created is not None and job.ttl_seconds > 0:
            deadline = created + timedelta(seconds=job.ttl_seconds)

    if deadline is not None and now >= deadline:
        return "cancel"

    return "keep"
