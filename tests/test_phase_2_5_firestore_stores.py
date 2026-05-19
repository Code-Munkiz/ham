"""Phase 2.5 — tests for the Firestore-backed builder stores.

Uses an in-memory fake Firestore client (extended from
``tests/test_firestore_control_plane_run_store.py`` patterns) to avoid
real GCP / network I/O.

Covers:

- :class:`FirestoreBuilderPlanStore` CRUD + nested-approval semantics
- :class:`FirestoreBuilderRuntimeJobStore` CRUD + ``get_by_id`` cross-workspace lookup
- :class:`FirestoreBuilderRunEventsStore` ``append`` / ``read_from`` /
  ``latest_seq`` + ``create()``-only duplicate-seq guardrail
- Backend selector env wiring for all three stores
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from src.ham.builder_plan import (
    HeartbeatPayload,
    Plan,
    PlanApprovalRecord,
    SSEEvent,
    Step,
)
from src.persistence.builder_plan_store import (
    BuilderPlanStore,
    build_builder_plan_store,
)
from src.persistence.builder_run_events_store import (
    BuilderRunEventsStore,
    build_builder_run_events_store,
)
from src.persistence.builder_runtime_job_store import (
    BuilderRuntimeJobStore,
    CloudRuntimeJob,
    build_builder_runtime_job_store,
)
from src.persistence.firestore_builder_plan_store import (
    FirestoreBuilderPlanStore,
)
from src.persistence.firestore_builder_run_events_store import (
    FirestoreBuilderRunEventsDuplicateSeq,
    FirestoreBuilderRunEventsStore,
)
from src.persistence.firestore_builder_runtime_job_store import (
    FirestoreBuilderRuntimeJobStore,
)


# ---------------------------------------------------------------------------
# Fake Firestore client with subcollection + create() support
# ---------------------------------------------------------------------------


class _AlreadyExistsError(Exception):
    """Mimics google.api_core.exceptions.AlreadyExists for the create-only test."""

    pass


# Make the fake class name match Firestore SDK's so the production code's
# ``exc.__class__.__name__ == "AlreadyExists"`` check still triggers.
_AlreadyExistsError.__name__ = "AlreadyExists"


@dataclass
class _FakeDocSnap:
    id: str
    _data: dict[str, Any] | None

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data) if self._data is not None else {}


@dataclass
class _FakeDocRef:
    root: "_FakeFirestoreClient"
    path: tuple[str, ...]  # alternating coll/doc/coll/doc...

    @property
    def id(self) -> str:
        return self.path[-1]

    def _store(self) -> tuple[dict[str, dict[str, Any]], str]:
        # Walk the nested path to find the parent collection bag for this doc.
        node = self.root.tree
        # path is coll, doc, coll, doc, ... — leaf is a doc.
        for i in range(0, len(self.path) - 1, 2):
            coll_name = self.path[i]
            doc_name = self.path[i + 1]
            coll_bag = node.setdefault(coll_name, {})
            if i + 2 < len(self.path):
                # descend through doc into nested subcollections
                doc_entry = coll_bag.setdefault(doc_name, {"_data": None, "_subs": {}})
                node = doc_entry["_subs"]
            else:
                return coll_bag, doc_name
        raise RuntimeError("unreachable")

    def set(self, data: dict[str, Any], merge: bool = False) -> None:
        coll_bag, doc_name = self._store()
        existing = coll_bag.get(doc_name)
        if existing is None:
            coll_bag[doc_name] = {"_data": dict(data), "_subs": {}}
            return
        if merge:
            merged = dict(existing.get("_data") or {})
            for k, v in data.items():
                # Nested-dict merge for one level so {approval: {...}} composes
                # the way Firestore merge=True does.
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged_sub = dict(merged[k])
                    merged_sub.update(v)
                    merged[k] = merged_sub
                else:
                    merged[k] = v
            existing["_data"] = merged
        else:
            existing["_data"] = dict(data)

    def create(self, data: dict[str, Any]) -> None:
        coll_bag, doc_name = self._store()
        existing = coll_bag.get(doc_name)
        if existing is not None and existing.get("_data") is not None:
            raise _AlreadyExistsError(f"document {doc_name} already exists")
        coll_bag[doc_name] = {"_data": dict(data), "_subs": {}}

    def get(self) -> _FakeDocSnap:
        coll_bag, doc_name = self._store()
        entry = coll_bag.get(doc_name)
        data = (entry or {}).get("_data")
        return _FakeDocSnap(doc_name, data)

    def collection(self, name: str) -> "_FakeCollection":
        # Ensure the doc exists in the tree so subcollection writes nest under it.
        coll_bag, doc_name = self._store()
        coll_bag.setdefault(doc_name, {"_data": None, "_subs": {}})
        return _FakeCollection(self.root, self.path + (name,))


@dataclass
class _FakeQuery:
    coll: "_FakeCollection"
    order_field: str | None = None
    direction: str = "ASCENDING"
    limit_n: int | None = None
    start_after_id: str | None = None

    def order_by(self, field_path: str, direction: str = "ASCENDING") -> "_FakeQuery":
        return _FakeQuery(
            coll=self.coll,
            order_field=field_path,
            direction=direction,
            limit_n=self.limit_n,
            start_after_id=self.start_after_id,
        )

    def limit(self, n: int) -> "_FakeQuery":
        return _FakeQuery(
            coll=self.coll,
            order_field=self.order_field,
            direction=self.direction,
            limit_n=n,
            start_after_id=self.start_after_id,
        )

    def start_after(self, cursor: Any) -> "_FakeQuery":
        # The store calls start_after({"__name__": cursor_doc_id}); we also
        # accept a bare string for symmetry.
        if isinstance(cursor, dict):
            sid = cursor.get("__name__") or ""
        else:
            sid = str(cursor)
        return _FakeQuery(
            coll=self.coll,
            order_field=self.order_field,
            direction=self.direction,
            limit_n=self.limit_n,
            start_after_id=sid,
        )

    def stream(self):
        items = list(self.coll._iter_snaps())  # noqa: SLF001
        if self.order_field == "__name__":
            items.sort(key=lambda s: s.id, reverse=(str(self.direction).upper().endswith("DESCENDING")))
        if self.start_after_id:
            items = [s for s in items if s.id > self.start_after_id]
        if self.limit_n is not None:
            items = items[: self.limit_n]
        yield from items


@dataclass
class _FakeCollection:
    root: "_FakeFirestoreClient"
    path: tuple[str, ...]

    def document(self, doc_id: str) -> _FakeDocRef:
        return _FakeDocRef(self.root, self.path + (doc_id,))

    def _coll_bag(self) -> dict[str, dict[str, Any]]:
        node = self.root.tree
        for i in range(0, len(self.path), 2):
            coll_name = self.path[i]
            coll_bag = node.setdefault(coll_name, {})
            if i + 1 < len(self.path):
                doc_name = self.path[i + 1]
                doc_entry = coll_bag.setdefault(doc_name, {"_data": None, "_subs": {}})
                node = doc_entry["_subs"]
            else:
                return coll_bag
        return node  # type: ignore[return-value]

    def _iter_snaps(self):
        bag = self._coll_bag()
        for doc_name, entry in bag.items():
            data = (entry or {}).get("_data")
            if data is not None:
                yield _FakeDocSnap(doc_name, data)

    def stream(self):
        yield from self._iter_snaps()

    def order_by(self, field_path: str, direction: str = "ASCENDING") -> _FakeQuery:
        return _FakeQuery(coll=self).order_by(field_path, direction=direction)


@dataclass
class _FakeFirestoreClient:
    tree: dict[str, Any] = field(default_factory=dict)

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self, (name,))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plan(
    *,
    plan_id: str = "pln_abcdef",
    workspace_id: str = "ws_demo",
    project_id: str = "proj_demo",
) -> Plan:
    return Plan(
        plan_id=plan_id,
        workspace_id=workspace_id,
        project_id=project_id,
        user_message="add a button",
        steps=[Step(title="step 1", description="do thing")],
        planner_confidence="high",
    )


def _make_job(
    *,
    job_id: str = "crjb_jobone",
    workspace_id: str = "ws_demo",
    project_id: str = "proj_demo",
) -> CloudRuntimeJob:
    return CloudRuntimeJob(
        id=job_id,
        workspace_id=workspace_id,
        project_id=project_id,
        metadata={"plan_id": "pln_abcdef"},
    )


def _make_event(*, job_id: str = "crjb_jobone", plan_id: str = "pln_abcdef") -> SSEEvent:
    return SSEEvent(
        seq=0,
        job_id=job_id,
        plan_id=plan_id,
        occurred_at="2026-05-19T00:00:00Z",
        event=HeartbeatPayload(),
    )


# ---------------------------------------------------------------------------
# Plan store
# ---------------------------------------------------------------------------


def test_plan_store_upsert_and_get() -> None:
    client = _FakeFirestoreClient()
    store = FirestoreBuilderPlanStore(client=client)

    plan = _make_plan()
    store.upsert_plan(plan)

    fetched = store.get_plan(plan_id=plan.plan_id)
    assert fetched is not None
    assert fetched.plan_id == plan.plan_id
    assert fetched.workspace_id == plan.workspace_id


def test_plan_store_approval_nested_and_does_not_clobber_plan() -> None:
    client = _FakeFirestoreClient()
    store = FirestoreBuilderPlanStore(client=client)

    plan = _make_plan()
    store.upsert_plan(plan)

    approval = PlanApprovalRecord(plan_id=plan.plan_id, state="approved")
    store.upsert_approval_record(approval)

    fetched_plan = store.get_plan(plan_id=plan.plan_id)
    fetched_approval = store.get_approval_record(plan_id=plan.plan_id)
    assert fetched_plan is not None
    assert fetched_plan.user_message == "add a button"
    assert fetched_approval is not None
    assert fetched_approval.state == "approved"
    assert fetched_approval.plan_id == plan.plan_id


def test_plan_store_get_approval_returns_none_when_absent() -> None:
    client = _FakeFirestoreClient()
    store = FirestoreBuilderPlanStore(client=client)

    plan = _make_plan()
    store.upsert_plan(plan)

    assert store.get_approval_record(plan_id=plan.plan_id) is None


def test_plan_store_list_filters_by_workspace_project() -> None:
    client = _FakeFirestoreClient()
    store = FirestoreBuilderPlanStore(client=client)

    store.upsert_plan(_make_plan(plan_id="pln_1", workspace_id="ws_a", project_id="proj_a"))
    store.upsert_plan(_make_plan(plan_id="pln_2", workspace_id="ws_a", project_id="proj_b"))
    store.upsert_plan(_make_plan(plan_id="pln_3", workspace_id="ws_b", project_id="proj_a"))

    listed = store.list_plans(workspace_id="ws_a", project_id="proj_a")
    assert [p.plan_id for p in listed] == ["pln_1"]


# ---------------------------------------------------------------------------
# Runtime job store
# ---------------------------------------------------------------------------


def test_runtime_job_store_upsert_and_get() -> None:
    client = _FakeFirestoreClient()
    store = FirestoreBuilderRuntimeJobStore(client=client)

    job = _make_job()
    store.upsert_cloud_runtime_job(job)

    fetched = store.get_cloud_runtime_job(
        workspace_id=job.workspace_id,
        project_id=job.project_id,
        job_id=job.id,
    )
    assert fetched is not None
    assert fetched.id == job.id


def test_runtime_job_store_get_returns_none_on_workspace_mismatch() -> None:
    client = _FakeFirestoreClient()
    store = FirestoreBuilderRuntimeJobStore(client=client)

    job = _make_job()
    store.upsert_cloud_runtime_job(job)

    fetched = store.get_cloud_runtime_job(
        workspace_id="ws_other",
        project_id=job.project_id,
        job_id=job.id,
    )
    assert fetched is None


def test_runtime_job_store_get_by_id_is_cross_workspace() -> None:
    client = _FakeFirestoreClient()
    store = FirestoreBuilderRuntimeJobStore(client=client)

    job = _make_job(workspace_id="ws_a")
    store.upsert_cloud_runtime_job(job)

    fetched = store.get_cloud_runtime_job_by_id(job_id=job.id)
    assert fetched is not None
    assert fetched.workspace_id == "ws_a"


def test_runtime_job_store_list_filters_and_sorts() -> None:
    client = _FakeFirestoreClient()
    store = FirestoreBuilderRuntimeJobStore(client=client)

    store.upsert_cloud_runtime_job(_make_job(job_id="crjb_a"))
    store.upsert_cloud_runtime_job(_make_job(job_id="crjb_b"))
    store.upsert_cloud_runtime_job(
        _make_job(job_id="crjb_c", workspace_id="ws_other")
    )

    listed = store.list_cloud_runtime_jobs(workspace_id="ws_demo", project_id="proj_demo")
    ids = {row.id for row in listed}
    assert ids == {"crjb_a", "crjb_b"}


# ---------------------------------------------------------------------------
# Events store
# ---------------------------------------------------------------------------


def test_events_store_append_assigns_monotonic_seq() -> None:
    client = _FakeFirestoreClient()
    store = FirestoreBuilderRunEventsStore(client=client)

    e1 = store.append(_make_event())
    e2 = store.append(_make_event())
    e3 = store.append(_make_event())

    assert e1.seq == 1
    assert e2.seq == 2
    assert e3.seq == 3


def test_events_store_create_only_blocks_duplicate_seq() -> None:
    client = _FakeFirestoreClient()
    store = FirestoreBuilderRunEventsStore(client=client)

    store.append(_make_event())

    # Simulate a second worker that thinks seq=1 is free (in-memory counter
    # reset). The on-disk create() must reject.
    rogue = FirestoreBuilderRunEventsStore(client=client)
    with pytest.raises(FirestoreBuilderRunEventsDuplicateSeq):
        rogue.append(_make_event())


def test_events_store_read_from_returns_only_above_cursor() -> None:
    client = _FakeFirestoreClient()
    store = FirestoreBuilderRunEventsStore(client=client)

    store.append(_make_event())  # seq=1
    store.append(_make_event())  # seq=2
    store.append(_make_event())  # seq=3

    later = store.read_from(job_id="crjb_jobone", since_seq=1)
    assert [e.seq for e in later] == [2, 3]


def test_events_store_latest_seq_returns_zero_for_empty() -> None:
    client = _FakeFirestoreClient()
    store = FirestoreBuilderRunEventsStore(client=client)
    assert store.latest_seq(job_id="crjb_jobone") == 0


def test_events_store_latest_seq_returns_max_for_populated() -> None:
    client = _FakeFirestoreClient()
    store = FirestoreBuilderRunEventsStore(client=client)

    store.append(_make_event())
    store.append(_make_event())
    store.append(_make_event())

    assert store.latest_seq(job_id="crjb_jobone") == 3


def test_events_store_latest_seq_seeds_counter_for_new_process() -> None:
    """A fresh store instance sees existing events and continues seq from there."""
    client = _FakeFirestoreClient()
    a = FirestoreBuilderRunEventsStore(client=client)
    a.append(_make_event())
    a.append(_make_event())

    b = FirestoreBuilderRunEventsStore(client=client)
    seeded = b.latest_seq(job_id="crjb_jobone")
    assert seeded == 2

    # Continuing append on `b` after seeding should not duplicate seq.
    e3 = b.append(_make_event())
    assert e3.seq == 3


# ---------------------------------------------------------------------------
# Backend selector wiring
# ---------------------------------------------------------------------------


def test_plan_store_factory_defaults_to_file_backend(monkeypatch) -> None:
    monkeypatch.delenv("HAM_BUILDER_PLAN_STORE_BACKEND", raising=False)
    store = build_builder_plan_store()
    assert isinstance(store, BuilderPlanStore)


def test_plan_store_factory_selects_firestore(monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_PLAN_STORE_BACKEND", "firestore")
    store = build_builder_plan_store()
    assert isinstance(store, FirestoreBuilderPlanStore)


def test_runtime_job_store_factory_defaults_to_file_backend(monkeypatch) -> None:
    monkeypatch.delenv("HAM_BUILDER_RUNTIME_JOB_STORE_BACKEND", raising=False)
    store = build_builder_runtime_job_store()
    assert isinstance(store, BuilderRuntimeJobStore)


def test_runtime_job_store_factory_selects_firestore(monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_RUNTIME_JOB_STORE_BACKEND", "firestore")
    store = build_builder_runtime_job_store()
    assert isinstance(store, FirestoreBuilderRuntimeJobStore)


def test_events_store_factory_defaults_to_file_backend(monkeypatch) -> None:
    monkeypatch.delenv("HAM_BUILDER_RUN_EVENTS_STORE_BACKEND", raising=False)
    store = build_builder_run_events_store()
    assert isinstance(store, BuilderRunEventsStore)


def test_events_store_factory_selects_firestore(monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_RUN_EVENTS_STORE_BACKEND", "firestore")
    store = build_builder_run_events_store()
    assert isinstance(store, FirestoreBuilderRunEventsStore)


# ---------------------------------------------------------------------------
# File-backed events store gets latest_seq too (Protocol parity)
# ---------------------------------------------------------------------------


def test_file_events_store_latest_seq(tmp_path) -> None:
    store_path = tmp_path / "events.json"
    store = BuilderRunEventsStore(store_path=store_path)
    assert store.latest_seq(job_id="crjb_jobone") == 0

    store.append(_make_event())
    store.append(_make_event())
    assert store.latest_seq(job_id="crjb_jobone") == 2
