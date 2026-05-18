"""Tests for src/persistence/builder_run_events_store.py — SSE event log."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ham.builder_plan import SSEEvent
from src.persistence.builder_run_events_store import BuilderRunEventsStore

_TS = "2026-05-18T12:00:00Z"


@pytest.fixture()
def store(tmp_path: Path) -> BuilderRunEventsStore:
    return BuilderRunEventsStore(store_path=tmp_path / "events.json")


def _make_event(*, job_id: str = "crjb_1", plan_id: str = "pln_1", seq: int = 0) -> SSEEvent:
    return SSEEvent(
        seq=seq,
        job_id=job_id,
        plan_id=plan_id,
        occurred_at=_TS,
        event={"type": "heartbeat"},
    )


# ── Seq monotonicity ──────────────────────────────────────────────


class TestSeqMonotonicity:
    def test_first_append_assigns_seq_1(self, store: BuilderRunEventsStore):
        evt = _make_event()
        result = store.append(evt)
        assert result.seq == 1

    def test_sequential_appends_increment(self, store: BuilderRunEventsStore):
        for i in range(5):
            result = store.append(_make_event())
            assert result.seq == i + 1

    def test_independent_seq_per_job(self, store: BuilderRunEventsStore):
        r1 = store.append(_make_event(job_id="crjb_a"))
        r2 = store.append(_make_event(job_id="crjb_b"))
        r3 = store.append(_make_event(job_id="crjb_a"))
        assert r1.seq == 1
        assert r2.seq == 1
        assert r3.seq == 2


# ── read_from replay ──────────────────────────────────────────────


class TestReadFrom:
    def test_read_all(self, store: BuilderRunEventsStore):
        for _ in range(3):
            store.append(_make_event())
        events = store.read_from(job_id="crjb_1")
        assert len(events) == 3
        assert [e.seq for e in events] == [1, 2, 3]

    def test_read_from_since_seq(self, store: BuilderRunEventsStore):
        for _ in range(5):
            store.append(_make_event())
        events = store.read_from(job_id="crjb_1", since_seq=3)
        assert len(events) == 2
        assert [e.seq for e in events] == [4, 5]

    def test_read_from_nonexistent_job(self, store: BuilderRunEventsStore):
        assert store.read_from(job_id="crjb_nope") == []

    def test_events_returned_in_seq_order(self, store: BuilderRunEventsStore):
        for _ in range(10):
            store.append(_make_event())
        events = store.read_from(job_id="crjb_1")
        seqs = [e.seq for e in events]
        assert seqs == sorted(seqs)
