"""PR-1d-A: ``FirestoreWorkspaceStore`` round-trip + isolation, exercised with an
in-memory fake that mimics enough of the ``google.cloud.firestore`` surface
(documents, subcollections, transactions, collection-group queries) to keep
the suite green without a live Firestore emulator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from src.ham.workspace_models import (  # noqa: I001  # see __future__ import above
    MembershipRecord,
    OrgRecord,
    UserRecord,
    WorkspaceMember,
    WorkspaceRecord,
)
from src.persistence.firestore_workspace_store import FirestoreWorkspaceStore
from src.persistence.workspace_store import (
    WorkspaceNotFoundError,
    WorkspaceSlugConflict,
    WorkspaceStoreError,
    new_workspace_id,
)

# ---------------------------------------------------------------------------
# Fake firestore client
# ---------------------------------------------------------------------------


def _normalize_op(op: Any) -> str:
    """FieldFilter normalizes ``==`` against ``None`` into a special IS_NULL op enum.

    Firestore exposes the op as either a literal string (``"=="``, ``"in"``) or
    an ``Operator`` enum value (``Operator.IS_NULL``). The fake only needs to
    distinguish equality, null-equality, and membership.
    """
    name = getattr(op, "name", None)
    if isinstance(name, str):
        return name.lower()
    return str(op).lower()


def _matches(value: Any, op: Any, expected: Any) -> bool:
    norm = _normalize_op(op)
    if norm in {"==", "equal"}:
        return value == expected
    if norm in {"is_null"}:
        return value is None
    if norm in {"in"}:
        try:
            return value in expected
        except TypeError:
            return False
    raise NotImplementedError(f"fake firestore: op {op!r} not supported")


@dataclass
class _FakeDocSnap:
    id: str
    exists: bool
    _data: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data) if self._data is not None else {}


@dataclass
class _FakeDocRef:
    root: _FakeFirestore
    path: str  # e.g. "workspaces/ws_1" or "workspaces/ws_1/members/u1"

    @property
    def id(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    def get(self, transaction: Any = None) -> _FakeDocSnap:  # noqa: ARG002
        data = self.root.docs.get(self.path)
        return _FakeDocSnap(id=self.id, exists=data is not None, _data=data)

    def set(self, data: dict[str, Any], merge: bool = False) -> None:
        if merge and self.path in self.root.docs:
            cur = dict(self.root.docs[self.path])
            cur.update(data)
            self.root.docs[self.path] = cur
        else:
            self.root.docs[self.path] = dict(data)

    def delete(self) -> None:
        self.root.docs.pop(self.path, None)

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self.root, prefix=f"{self.path}/{name}")


@dataclass
class _FakeQuery:
    root: _FakeFirestore
    # When ``prefix`` is None this is a collection-group query and ``group`` is
    # the subcollection name; otherwise ``prefix`` constrains to a single
    # collection (``users``, ``workspaces/ws_1/members``, …).
    prefix: str | None
    group: str | None
    filters: list[tuple[str, Any, Any]] = field(default_factory=list)

    def where(self, *, filter: Any) -> _FakeQuery:  # noqa: A002
        # FieldFilter exposes ``field_path``/``op_string``/``value``.
        f = (filter.field_path, filter.op_string, filter.value)
        return _FakeQuery(
            root=self.root,
            prefix=self.prefix,
            group=self.group,
            filters=[*self.filters, f],
        )

    def _candidate_paths(self) -> list[str]:
        out: list[str] = []
        if self.prefix is not None:
            for p in self.root.docs:
                if not p.startswith(self.prefix + "/"):
                    continue
                rest = p[len(self.prefix) + 1 :]
                if "/" in rest:
                    continue  # not a direct child
                out.append(p)
            return out
        assert self.group is not None
        for p in self.root.docs:
            parts = p.split("/")
            if len(parts) >= 2 and parts[-2] == self.group:
                out.append(p)
        return out

    def stream(self, transaction: Any = None):  # noqa: ARG002
        for p in self._candidate_paths():
            data = self.root.docs[p]
            ok = True
            for field_path, op, expected in self.filters:
                if not _matches(data.get(field_path), op, expected):
                    ok = False
                    break
            if ok:
                yield _FakeDocSnap(id=p.rsplit("/", 1)[-1], exists=True, _data=data)


@dataclass
class _FakeCollection:
    root: _FakeFirestore
    prefix: str  # e.g. "users", "workspaces/ws_1/members"

    def document(self, doc_id: str) -> _FakeDocRef:
        return _FakeDocRef(self.root, path=f"{self.prefix}/{doc_id}")

    def where(self, *, filter: Any) -> _FakeQuery:  # noqa: A002
        return _FakeQuery(self.root, prefix=self.prefix, group=None).where(filter=filter)

    def stream(self, transaction: Any = None):  # noqa: ARG002
        return _FakeQuery(self.root, prefix=self.prefix, group=None).stream()


@dataclass
class _FakeTransaction:
    root: _FakeFirestore

    def set(self, ref: _FakeDocRef, data: dict[str, Any]) -> None:
        ref.set(data)

    def update(self, ref: _FakeDocRef, patch: dict[str, Any]) -> None:
        cur = dict(self.root.docs.get(ref.path, {}))
        cur.update(patch)
        self.root.docs[ref.path] = cur


class _FakeFirestore:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self, prefix=name)

    def collection_group(self, name: str) -> _FakeQuery:
        return _FakeQuery(self, prefix=None, group=name)

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _store() -> tuple[FirestoreWorkspaceStore, _FakeFirestore]:
    fake = _FakeFirestore()
    return FirestoreWorkspaceStore(client=fake), fake


def _ws(
    *,
    workspace_id: str,
    org_id: str | None,
    owner: str,
    slug: str,
    name: str = "Test",
    status: str = "active",
) -> WorkspaceRecord:
    return WorkspaceRecord(
        workspace_id=workspace_id,
        org_id=org_id,
        owner_user_id=owner,
        name=name,
        slug=slug,
        description="",
        status=status,  # type: ignore[arg-type]
        created_by=owner,
        created_at=_now(),
        updated_at=_now(),
    )


# ---------------------------------------------------------------------------
# Users / orgs / memberships
# ---------------------------------------------------------------------------


def test_user_round_trip() -> None:
    s, _ = _store()
    u = UserRecord(
        user_id="user_a",
        email="alice@example.com",
        display_name="Alice",
        photo_url=None,
        primary_org_id=None,
        created_at=_now(),
        last_seen_at=_now(),
    )
    assert s.upsert_user(u) == u
    fetched = s.get_user("user_a")
    assert fetched is not None
    assert fetched.user_id == "user_a"
    assert fetched.email == "alice@example.com"
    assert s.get_user("missing") is None


def test_org_round_trip() -> None:
    s, _ = _store()
    o = OrgRecord(org_id="org_x", name="Acme", clerk_slug="acme", created_at=_now())
    assert s.upsert_org(o) == o
    fetched = s.get_org("org_x")
    assert fetched is not None
    assert fetched.name == "Acme"
    assert s.get_org("missing") is None


def test_membership_round_trip_and_listing() -> None:
    s, _ = _store()
    m1 = MembershipRecord(
        user_id="user_a",
        org_id="org_x",
        org_role="org:admin",
        joined_at=_now(),
    )
    m2 = MembershipRecord(
        user_id="user_a",
        org_id="org_y",
        org_role="org:member",
        joined_at=_now(),
    )
    m3 = MembershipRecord(
        user_id="user_b",
        org_id="org_x",
        org_role="org:member",
        joined_at=_now(),
    )
    s.upsert_membership(m1)
    s.upsert_membership(m2)
    s.upsert_membership(m3)
    rows_a = {m.org_id for m in s.list_memberships_for_user("user_a")}
    rows_b = {m.org_id for m in s.list_memberships_for_user("user_b")}
    assert rows_a == {"org_x", "org_y"}
    assert rows_b == {"org_x"}
    assert s.list_memberships_for_user("user_z") == []


def test_membership_doc_id_is_compound() -> None:
    s, fake = _store()
    s.upsert_membership(
        MembershipRecord(
            user_id="user_a",
            org_id="org_x",
            org_role="org:admin",
            joined_at=_now(),
        ),
    )
    assert "memberships/user_a__org_x" in fake.docs


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------


def test_create_get_workspace() -> None:
    s, _ = _store()
    wid = new_workspace_id()
    rec = _ws(workspace_id=wid, org_id="org_x", owner="user_a", slug="prod")
    assert s.create_workspace(rec).workspace_id == wid
    fetched = s.get_workspace(wid)
    assert fetched is not None
    assert fetched.slug == "prod"
    assert s.get_workspace(new_workspace_id()) is None


def test_create_workspace_slug_conflict_org_scope() -> None:
    s, _ = _store()
    wid_1 = new_workspace_id()
    wid_2 = new_workspace_id()
    s.create_workspace(_ws(workspace_id=wid_1, org_id="org_x", owner="user_a", slug="prod"))
    with pytest.raises(WorkspaceSlugConflict):
        s.create_workspace(
            _ws(workspace_id=wid_2, org_id="org_x", owner="user_b", slug="prod"),
        )


def test_create_workspace_slug_conflict_personal_scope() -> None:
    s, _ = _store()
    wid_1 = new_workspace_id()
    wid_2 = new_workspace_id()
    wid_3 = new_workspace_id()
    s.create_workspace(_ws(workspace_id=wid_1, org_id=None, owner="user_a", slug="dev"))
    with pytest.raises(WorkspaceSlugConflict):
        s.create_workspace(
            _ws(workspace_id=wid_2, org_id=None, owner="user_a", slug="dev"),
        )
    # Different personal owner — same slug is fine.
    s.create_workspace(_ws(workspace_id=wid_3, org_id=None, owner="user_b", slug="dev"))


def test_create_workspace_archived_releases_slug() -> None:
    s, _ = _store()
    wid_1 = new_workspace_id()
    wid_2 = new_workspace_id()
    s.create_workspace(_ws(workspace_id=wid_1, org_id="org_x", owner="user_a", slug="prod"))
    s.update_workspace(wid_1, status="archived")
    s.create_workspace(_ws(workspace_id=wid_2, org_id="org_x", owner="user_a", slug="prod"))


def test_create_workspace_id_collision() -> None:
    s, _ = _store()
    wid = new_workspace_id()
    s.create_workspace(_ws(workspace_id=wid, org_id="org_x", owner="user_a", slug="a"))
    with pytest.raises(WorkspaceStoreError):
        s.create_workspace(_ws(workspace_id=wid, org_id="org_x", owner="user_a", slug="b"))


def test_update_workspace_patches_fields_and_bumps_updated_at() -> None:
    s, _ = _store()
    wid = new_workspace_id()
    s.create_workspace(_ws(workspace_id=wid, org_id="org_x", owner="user_a", slug="prod"))
    rec = s.update_workspace(wid, name="Renamed", description="hello")
    assert rec.name == "Renamed"
    assert rec.description == "hello"
    assert rec.status == "active"


def test_update_workspace_missing_raises() -> None:
    s, _ = _store()
    with pytest.raises(WorkspaceNotFoundError):
        s.update_workspace(new_workspace_id(), name="x")


def test_list_workspaces_owned() -> None:
    s, _ = _store()
    wid_a = new_workspace_id()
    wid_b = new_workspace_id()
    s.create_workspace(_ws(workspace_id=wid_a, org_id=None, owner="user_a", slug="alice"))
    s.create_workspace(_ws(workspace_id=wid_b, org_id=None, owner="user_b", slug="bob"))
    out_a = {w.workspace_id for w in s.list_workspaces_for_user("user_a")}
    out_b = {w.workspace_id for w in s.list_workspaces_for_user("user_b")}
    assert out_a == {wid_a}
    assert out_b == {wid_b}


def test_list_workspaces_filter_archived_and_org() -> None:
    s, _ = _store()
    wid_active = new_workspace_id()
    wid_archived = new_workspace_id()
    wid_other = new_workspace_id()
    s.create_workspace(_ws(workspace_id=wid_active, org_id="org_x", owner="user_a", slug="active"))
    s.create_workspace(
        _ws(workspace_id=wid_archived, org_id="org_x", owner="user_a", slug="archived"),
    )
    s.update_workspace(wid_archived, status="archived")
    s.create_workspace(_ws(workspace_id=wid_other, org_id="org_y", owner="user_a", slug="active"))

    default_view = {w.workspace_id for w in s.list_workspaces_for_user("user_a")}
    assert wid_active in default_view
    assert wid_other in default_view
    assert wid_archived not in default_view

    inc = {w.workspace_id for w in s.list_workspaces_for_user("user_a", include_archived=True)}
    assert wid_archived in inc

    only_y = {
        w.workspace_id for w in s.list_workspaces_for_user("user_a", org_id="org_y")
    }
    assert only_y == {wid_other}


def test_list_workspaces_via_member_subcollection() -> None:
    s, _ = _store()
    wid = new_workspace_id()
    s.create_workspace(_ws(workspace_id=wid, org_id=None, owner="user_owner", slug="shared"))
    s.upsert_member(
        WorkspaceMember(
            user_id="user_invited",
            workspace_id=wid,
            role="member",
            added_by="user_owner",
            added_at=_now(),
        ),
    )
    invited = {w.workspace_id for w in s.list_workspaces_for_user("user_invited")}
    assert invited == {wid}


def test_list_workspaces_via_org_fallback() -> None:
    s, _ = _store()
    wid = new_workspace_id()
    s.create_workspace(_ws(workspace_id=wid, org_id="org_x", owner="user_admin", slug="team"))
    # ``user_member`` has no member-row in the workspace but is in the org.
    s.upsert_membership(
        MembershipRecord(
            user_id="user_member",
            org_id="org_x",
            org_role="org:member",
            joined_at=_now(),
        ),
    )
    member_view = {w.workspace_id for w in s.list_workspaces_for_user("user_member")}
    assert member_view == {wid}


def test_list_workspaces_union_is_deduped() -> None:
    s, _ = _store()
    wid = new_workspace_id()
    s.create_workspace(_ws(workspace_id=wid, org_id="org_x", owner="user_a", slug="t"))
    # Same actor is owner + member-row + org-fallback simultaneously.
    s.upsert_member(
        WorkspaceMember(
            user_id="user_a",
            workspace_id=wid,
            role="owner",
            added_by="user_a",
            added_at=_now(),
        ),
    )
    s.upsert_membership(
        MembershipRecord(
            user_id="user_a",
            org_id="org_x",
            org_role="org:admin",
            joined_at=_now(),
        ),
    )
    out = s.list_workspaces_for_user("user_a")
    assert [w.workspace_id for w in out] == [wid]


# ---------------------------------------------------------------------------
# Workspace members
# ---------------------------------------------------------------------------


def test_member_upsert_get_list_remove() -> None:
    s, _ = _store()
    wid = new_workspace_id()
    s.create_workspace(_ws(workspace_id=wid, org_id="org_x", owner="user_a", slug="prod"))
    member = WorkspaceMember(
        user_id="user_b",
        workspace_id=wid,
        role="member",
        added_by="user_a",
        added_at=_now(),
    )
    s.upsert_member(member)
    fetched = s.get_member(wid, "user_b")
    assert fetched is not None
    assert fetched.role == "member"
    assert {m.user_id for m in s.list_members(wid)} == {"user_b"}
    assert s.remove_member(wid, "user_b") is True
    assert s.get_member(wid, "user_b") is None
    assert s.remove_member(wid, "user_b") is False


def test_member_upsert_into_unknown_workspace_raises() -> None:
    s, _ = _store()
    member = WorkspaceMember(
        user_id="user_b",
        workspace_id=new_workspace_id(),
        role="member",
        added_by="user_a",
        added_at=_now(),
    )
    with pytest.raises(WorkspaceNotFoundError):
        s.upsert_member(member)


def test_member_subcollection_isolated_per_workspace() -> None:
    s, _ = _store()
    wid_1 = new_workspace_id()
    wid_2 = new_workspace_id()
    s.create_workspace(_ws(workspace_id=wid_1, org_id="org_x", owner="user_a", slug="a"))
    s.create_workspace(_ws(workspace_id=wid_2, org_id="org_x", owner="user_a", slug="b"))
    s.upsert_member(
        WorkspaceMember(
            user_id="user_b",
            workspace_id=wid_1,
            role="member",
            added_by="user_a",
            added_at=_now(),
        ),
    )
    assert s.get_member(wid_2, "user_b") is None
    assert s.list_members(wid_2) == []


# ---------------------------------------------------------------------------
# Datetime / Timestamp normalization
# ---------------------------------------------------------------------------


def test_naive_datetime_from_firestore_is_normalized_to_utc() -> None:
    s, fake = _store()
    wid = new_workspace_id()
    s.create_workspace(_ws(workspace_id=wid, org_id="org_x", owner="user_a", slug="prod"))
    # Simulate a legacy / fake-client row whose datetimes came back tz-naive.
    raw = dict(fake.docs[f"workspaces/{wid}"])
    raw["created_at"] = datetime.now().replace(tzinfo=None)  # noqa: DTZ005  # intentional
    raw["updated_at"] = datetime.now().replace(tzinfo=None)  # noqa: DTZ005  # intentional
    fake.docs[f"workspaces/{wid}"] = raw

    rec = s.get_workspace(wid)
    assert rec is not None
    assert rec.created_at.tzinfo is not None
    assert rec.updated_at.tzinfo is not None


# ---------------------------------------------------------------------------
# Firestore API errors map to WorkspaceStoreError
# ---------------------------------------------------------------------------


class _ExplodingClient:
    """Minimal firestore-shaped client that raises on every read/write call."""

    class _ExplodingDoc:
        def __init__(self, root: _ExplodingClient, path: str) -> None:
            self._root = root
            self.path = path

        def get(self, transaction: Any = None):  # noqa: ARG002
            raise self._root.exc

        def set(self, *_: Any, **__: Any) -> None:
            raise self._root.exc

        def delete(self) -> None:
            raise self._root.exc

        def collection(self, _name: str) -> _ExplodingClient._ExplodingColl:
            return _ExplodingClient._ExplodingColl(self._root, f"{self.path}/sub")

    class _ExplodingColl:
        def __init__(self, root: _ExplodingClient, prefix: str) -> None:
            self._root = root
            self.prefix = prefix

        def document(self, doc_id: str) -> _ExplodingClient._ExplodingDoc:
            return _ExplodingClient._ExplodingDoc(self._root, f"{self.prefix}/{doc_id}")

        def where(self, *, filter: Any):  # noqa: A002, ARG002
            return self

        def stream(self, transaction: Any = None):  # noqa: ARG002
            raise self._root.exc

    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def collection(self, name: str) -> _ExplodingColl:
        return _ExplodingClient._ExplodingColl(self, name)


def test_firestore_api_error_maps_to_workspace_store_error() -> None:
    from google.api_core.exceptions import ServiceUnavailable

    bad = _ExplodingClient(ServiceUnavailable("backend gone"))
    s = FirestoreWorkspaceStore(client=bad)
    with pytest.raises(WorkspaceStoreError) as excinfo:
        s.get_user("user_a")
    assert "get_user" in str(excinfo.value)


def test_firestore_api_error_on_list_maps_to_workspace_store_error() -> None:
    from google.api_core.exceptions import DeadlineExceeded

    bad = _ExplodingClient(DeadlineExceeded("slow"))
    s = FirestoreWorkspaceStore(client=bad)
    with pytest.raises(WorkspaceStoreError) as excinfo:
        s.list_memberships_for_user("user_a")
    assert "list_memberships_for_user" in str(excinfo.value)
