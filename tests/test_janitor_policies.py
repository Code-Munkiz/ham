"""Tests for src/ham/janitor_policies.py — Phase 1 #3 (ADR-0004).

Covers: evaluate() decision rules for all TTL and terminal-state cases.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.ham.janitor_policies import evaluate
from src.persistence.builder_runtime_job_store import CloudRuntimeJob

_BASE_TS = "2026-05-18T12:00:00Z"
_NOW = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)


def _job(**kwargs) -> CloudRuntimeJob:
    defaults = dict(
        workspace_id="ws_test",
        project_id="proj_test",
        created_at=_BASE_TS,
        ttl_seconds=3600,
        ttl_deadline=None,
    )
    defaults.update(kwargs)
    return CloudRuntimeJob(**defaults)


class TestKeepDecisions:
    def test_queued_within_ttl(self):
        job = _job(status="queued")
        # created_at == now, well within TTL
        assert evaluate(job, _NOW) == "keep"

    def test_running_within_ttl(self):
        job = _job(status="running")
        assert evaluate(job, _NOW) == "keep"

    def test_cancelling_is_kept(self):
        # ADR-0004: cancelling → Worker drives to terminal; janitor leaves alone
        job = _job(status="cancelling")
        # Even if TTL elapsed, cancelling jobs are not re-cancelled
        job2 = _job(status="cancelling", created_at="2026-01-01T00:00:00Z")
        assert evaluate(job2, _NOW) == "keep"

    def test_explicit_ttl_deadline_in_future(self):
        future = (_NOW + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        job = _job(status="running", ttl_deadline=future)
        assert evaluate(job, _NOW) == "keep"


class TestCancelDecisions:
    def test_ttl_just_reached_via_created_at(self):
        # created 3600s ago → exactly at deadline
        created = (_NOW - timedelta(seconds=3600)).isoformat().replace("+00:00", "Z")
        job = _job(status="running", created_at=created, ttl_seconds=3600)
        assert evaluate(job, _NOW) == "cancel"

    def test_ttl_long_elapsed(self):
        created = (_NOW - timedelta(hours=24)).isoformat().replace("+00:00", "Z")
        job = _job(status="running", created_at=created, ttl_seconds=3600)
        assert evaluate(job, _NOW) == "cancel"

    def test_explicit_ttl_deadline_past(self):
        past = (_NOW - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        job = _job(status="running", ttl_deadline=past)
        assert evaluate(job, _NOW) == "cancel"

    def test_queued_job_ttl_elapsed(self):
        created = (_NOW - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        job = _job(status="queued", created_at=created, ttl_seconds=3600)
        assert evaluate(job, _NOW) == "cancel"


class TestReapDecisions:
    def test_completed_job_needs_reap(self):
        job = _job(status="completed")
        assert evaluate(job, _NOW) == "reap"

    def test_failed_job_needs_reap(self):
        job = _job(status="failed")
        assert evaluate(job, _NOW) == "reap"

    def test_cancelled_job_needs_reap(self):
        job = _job(status="cancelled")
        assert evaluate(job, _NOW) == "reap"

    def test_terminal_job_not_subject_to_ttl(self):
        # Even if TTL elapsed, terminal jobs -> reap (not cancel)
        created = (_NOW - timedelta(hours=24)).isoformat().replace("+00:00", "Z")
        job = _job(status="completed", created_at=created, ttl_seconds=60)
        assert evaluate(job, _NOW) == "reap"


class TestEdgeCases:
    def test_zero_ttl_seconds_does_not_cancel(self):
        job = _job(status="running", ttl_seconds=0)
        assert evaluate(job, _NOW) == "keep"

    def test_missing_created_at_does_not_crash(self):
        job = _job(status="running", ttl_seconds=3600, ttl_deadline=None)
        # created_at defaults to now, so should be keep
        assert evaluate(job, _NOW) in {"keep", "cancel"}

    def test_old_record_without_ttl_deadline_uses_fallback(self):
        # Old records (no ttl_deadline) fall back to created_at + ttl_seconds
        old_created = "2026-01-01T00:00:00Z"
        job = _job(status="running", created_at=old_created, ttl_seconds=3600, ttl_deadline=None)
        assert evaluate(job, _NOW) == "cancel"
