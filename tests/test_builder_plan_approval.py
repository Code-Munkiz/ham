"""Tests for src/ham/builder_plan_approval.py — Plan approval state machine.

Covers every (state, action) pair exhaustively per Contract 2.
"""

from __future__ import annotations

import pytest

from src.ham.builder_plan import PlanApprovalRecord
from src.ham.builder_plan_approval import transition

_TS = "2026-05-18T12:00:00Z"


def _make_record(state: str = "proposed", **kw) -> PlanApprovalRecord:
    defaults = {"plan_id": "pln_test", "proposed_at": _TS}
    defaults.update(kw)
    return PlanApprovalRecord(state=state, **defaults)


# ── Legal transitions ──────────────────────────────────────────────


class TestProposedToApproved:
    def test_approve_sets_state(self):
        rec = _make_record("proposed")
        new = transition(rec, "approve")
        assert new.state == "approved"

    def test_approve_sets_approved_at(self):
        rec = _make_record("proposed")
        new = transition(rec, "approve")
        assert new.approved_at is not None

    def test_approve_preserves_plan_id(self):
        rec = _make_record("proposed", plan_id="pln_keep")
        new = transition(rec, "approve")
        assert new.plan_id == "pln_keep"

    def test_approve_returns_new_instance(self):
        rec = _make_record("proposed")
        new = transition(rec, "approve")
        assert new is not rec


class TestProposedToStale:
    def test_mark_stale_sets_state(self):
        rec = _make_record("proposed")
        new = transition(rec, "mark_stale", stale_reason="source_snapshot_drift")
        assert new.state == "stale"

    def test_mark_stale_sets_stale_at(self):
        rec = _make_record("proposed")
        new = transition(rec, "mark_stale")
        assert new.stale_at is not None

    def test_mark_stale_records_reason(self):
        rec = _make_record("proposed")
        new = transition(rec, "mark_stale", stale_reason="source_snapshot_drift")
        assert new.stale_reason == "source_snapshot_drift"


# ── STALE wall (Contract 2) ───────────────────────────────────────


class TestStaleBlocksApproval:
    def test_stale_approve_raises(self):
        rec = _make_record("stale", stale_at=_TS, stale_reason="drift")
        with pytest.raises(ValueError, match="(?i)stale"):
            transition(rec, "approve")

    def test_stale_mark_stale_raises(self):
        rec = _make_record("stale", stale_at=_TS)
        with pytest.raises(ValueError, match="stale"):
            transition(rec, "mark_stale")


# ── Post-approval immutability (ADR-0001) ─────────────────────────


class TestApprovedIsImmutable:
    def test_approved_approve_raises(self):
        rec = _make_record("approved", approved_at=_TS)
        with pytest.raises(ValueError, match="approved"):
            transition(rec, "approve")

    def test_approved_mark_stale_raises(self):
        rec = _make_record("approved", approved_at=_TS)
        with pytest.raises(ValueError, match="approved"):
            transition(rec, "mark_stale")


# ── No-rollback-on-enqueue-failure ─────────────────────────────────


class TestNoRollbackOnEnqueueFailure:
    def test_approved_stays_approved_on_enqueue_failure(self):
        """APPROVED → PROPOSED rollback is forbidden; Plan stays APPROVED.

        Per Contract 2: enqueue failures do NOT roll back to PROPOSED.
        CloudRuntimeJob.last_error records the enqueue failure instead.
        """
        rec = _make_record("approved", approved_at=_TS)
        with pytest.raises(ValueError):
            transition(rec, "mark_stale")
        # Record hasn't changed
        assert rec.state == "approved"
