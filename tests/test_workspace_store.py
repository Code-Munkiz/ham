"""Phase 1a: in-memory + file-backed WorkspaceStore behaviour + isolation."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.ham.workspace_models import (
    WORKSPACE_ID_PREFIX,
    MembershipRecord,
    OrgRecord,
    UserRecord,
    WorkspaceMember,
    WorkspaceRecord,
)
from src.persistence.workspace_store import (
    FileWorkspaceStore,
    InMemoryWorkspaceStore,
    WorkspaceNotFoundError,
    WorkspaceSlugConflict,
    WorkspaceStore,
    build_workspace_store,
    new_workspace_id,
    normalize_slug_input,
)


def _now() -> datetime:
    return datetime.now(UTC)


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
# new_workspace_id + slug helpers
# ---------------------------------------------------------------------------


def test_new_workspace_id_has_correct_shape_and_is_unique() -> None:
    ids = {new_workspace_id() for _ in range(50)}
    assert len(ids) == 50
    for wid in ids:
        assert wid.startswith(WORKSPACE_ID_PREFIX)
        assert wid.replace(WORKSPACE_ID_PREFIX, "").isalnum()


def test_normalize_slug_input_accepts_and_lowercases() -> None:
    assert normalize_slug_input("  ACME-Prod ") == "acme-prod"
    assert normalize_slug_input("bad slug") is None
    assert normalize_slug_input("") is None


# ---------------------------------------------------------------------------
# In-memory store: CRUD
# ---------------------------------------------------------------------------


def test_inmemory_user_org_membership_upsert_and_get() -> None:
    s = InMemoryWorkspaceStore()
    u = UserRecord(
        user_id="user_a",
        email="alice@example.com",
        display_name="Alice",
        photo_url=None,
        primary_org_id=None,
        created_at=_now(),
        last_seen_at=_now(),
    )
    s.upsert_user(u)
    assert s.get_user("user_a") == u
    assert s.get_user("user_x") is None

    o = OrgRecord(org_id="org_x", name="Acme", clerk_slug="acme", created_at=_now())
    s.upsert_org(o)
    assert s.get_org("org_x") == o

    m = MembershipRecord(
        user_id="user_a",
        org_id="org_x",
        org_role="org:admin",
        joined_at=_now(),
    )
    s.upsert_membership(m)
    assert s.list_memberships_for_user("user_a") == [m]
    assert s.list_memberships_for_user("user_b") == []


def test_inmemory_create_workspace_enforces_unique_slug_per_scope() -> None:
    s = InMemoryWorkspaceStore()
    wid_1 = new_workspace_id()
    wid_2 = new_workspace_id()
    s.create_workspace(_ws(workspace_id=wid_1, org_id="org_x", owner="user_a", slug="prod"))
    with pytest.raises(WorkspaceSlugConflict):
        s.create_workspace(
            _ws(workspace_id=wid_2, org_id="org_x", owner="user_b", slug="prod"),
        )


def test_inmemory_slug_unique_scope_is_per_org_and_per_personal_owner() -> None:
    s = InMemoryWorkspaceStore()
    wid_1 = new_workspace_id()
    wid_2 = new_workspace_id()
    wid_3 = new_workspace_id()
    wid_4 = new_workspace_id()
    s.create_workspace(_ws(workspace_id=wid_1, org_id="org_x", owner="user_a", slug="prod"))
    # Different org → no conflict.
    s.create_workspace(_ws(workspace_id=wid_2, org_id="org_y", owner="user_b", slug="prod"))
    # Personal workspaces are scoped by owner.
    s.create_workspace(_ws(workspace_id=wid_3, org_id=None, owner="user_a", slug="scratch"))
    s.create_workspace(_ws(workspace_id=wid_4, org_id=None, owner="user_b", slug="scratch"))


def test_inmemory_archived_workspace_releases_slug_for_reuse() -> None:
    s = InMemoryWorkspaceStore()
    wid_1 = new_workspace_id()
    wid_2 = new_workspace_id()
    s.create_workspace(_ws(workspace_id=wid_1, org_id="org_x", owner="user_a", slug="prod"))
    s.update_workspace(wid_1, status="archived")
    s.create_workspace(_ws(workspace_id=wid_2, org_id="org_x", owner="user_a", slug="prod"))


def test_inmemory_update_workspace_missing_raises() -> None:
    s = InMemoryWorkspaceStore()
    with pytest.raises(WorkspaceNotFoundError):
        s.update_workspace(new_workspace_id(), name="new")


def test_inmemory_list_workspaces_filters_by_org_and_archived() -> None:
    s = InMemoryWorkspaceStore()
    wid_active = new_workspace_id()
    wid_archived = new_workspace_id()
    wid_other_org = new_workspace_id()
    s.create_workspace(
        _ws(workspace_id=wid_active, org_id="org_x", owner="user_a", slug="active"),
    )
    s.create_workspace(
        _ws(workspace_id=wid_archived, org_id="org_x", owner="user_a", slug="archived"),
    )
    s.update_workspace(wid_archived, status="archived")
    s.create_workspace(
        _ws(workspace_id=wid_other_org, org_id="org_y", owner="user_a", slug="active"),
    )
    s.upsert_membership(
        MembershipRecord(
            user_id="user_a",
            org_id="org_x",
            org_role="org:admin",
            joined_at=_now(),
        ),
    )
    s.upsert_membership(
        MembershipRecord(
            user_id="user_a",
            org_id="org_y",
            org_role="org:member",
            joined_at=_now(),
        ),
    )

    ws = s.list_workspaces_for_user("user_a")
    ids = {w.workspace_id for w in ws}
    assert wid_active in ids
    assert wid_other_org in ids
    assert wid_archived not in ids

    ws_archived = s.list_workspaces_for_user("user_a", include_archived=True)
    assert wid_archived in {w.workspace_id for w in ws_archived}

    ws_org_y = s.list_workspaces_for_user("user_a", org_id="org_y")
    assert {w.workspace_id for w in ws_org_y} == {wid_other_org}


def test_inmemory_list_workspaces_isolates_users_with_no_overlap() -> None:
    s = InMemoryWorkspaceStore()
    wid_alice = new_workspace_id()
    wid_bob = new_workspace_id()
    s.create_workspace(
        _ws(workspace_id=wid_alice, org_id=None, owner="user_alice", slug="alice"),
    )
    s.create_workspace(
        _ws(workspace_id=wid_bob, org_id=None, owner="user_bob", slug="bob"),
    )
    alice_ws = s.list_workspaces_for_user("user_alice")
    bob_ws = s.list_workspaces_for_user("user_bob")
    assert {w.workspace_id for w in alice_ws} == {wid_alice}
    assert {w.workspace_id for w in bob_ws} == {wid_bob}


def test_inmemory_member_upsert_get_list_remove() -> None:
    s = InMemoryWorkspaceStore()
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
    assert s.get_member(wid, "user_b") == member
    assert s.list_members(wid) == [member]
    assert s.remove_member(wid, "user_b") is True
    assert s.get_member(wid, "user_b") is None
    assert s.remove_member(wid, "user_b") is False


def test_inmemory_member_upsert_into_unknown_workspace_raises() -> None:
    s = InMemoryWorkspaceStore()
    wid = new_workspace_id()
    member = WorkspaceMember(
        user_id="user_b",
        workspace_id=wid,
        role="member",
        added_by="user_a",
        added_at=_now(),
    )
    with pytest.raises(WorkspaceNotFoundError):
        s.upsert_member(member)


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def test_inmemory_create_workspace_race_yields_one_winner() -> None:
    s = InMemoryWorkspaceStore()
    successes: list[str] = []
    conflicts: list[Exception] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        wid = new_workspace_id()
        rec = _ws(workspace_id=wid, org_id="org_x", owner="user_a", slug="race")
        barrier.wait()
        try:
            s.create_workspace(rec)
            successes.append(wid)
        except WorkspaceSlugConflict as exc:
            conflicts.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(successes) == 1
    assert len(conflicts) == 7


# ---------------------------------------------------------------------------
# File-backed store
# ---------------------------------------------------------------------------


def test_file_workspace_store_persists_and_reloads(tmp_path: Path) -> None:
    p = tmp_path / "workspaces.json"
    s1 = FileWorkspaceStore(path=p)
    wid = new_workspace_id()
    rec = _ws(workspace_id=wid, org_id=None, owner="user_a", slug="dev")
    s1.create_workspace(rec)
    s1.upsert_user(
        UserRecord(
            user_id="user_a",
            email="a@x.com",
            display_name="A",
            photo_url=None,
            primary_org_id=None,
            created_at=_now(),
            last_seen_at=_now(),
        ),
    )
    assert p.is_file()

    s2 = FileWorkspaceStore(path=p)
    assert s2.get_workspace(wid) is not None
    assert s2.get_user("user_a") is not None


def test_file_workspace_store_default_path_respects_env(tmp_path, monkeypatch) -> None:
    target = tmp_path / "custom.json"
    monkeypatch.setenv("HAM_WORKSPACE_STORE_PATH", str(target))
    from src.persistence.workspace_store import default_file_store_path

    assert default_file_store_path() == target


# ---------------------------------------------------------------------------
# Builder + protocol
# ---------------------------------------------------------------------------


def test_build_workspace_store_default_is_file_backed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_WORKSPACE_STORE_PATH", str(tmp_path / "ws.json"))
    monkeypatch.delenv("HAM_WORKSPACE_STORE_BACKEND", raising=False)
    s = build_workspace_store()
    assert isinstance(s, FileWorkspaceStore)


def test_build_workspace_store_memory_backend(monkeypatch) -> None:
    monkeypatch.setenv("HAM_WORKSPACE_STORE_BACKEND", "memory")
    s = build_workspace_store()
    assert isinstance(s, InMemoryWorkspaceStore)


def test_build_workspace_store_firestore_backend_lazy_import(monkeypatch) -> None:
    monkeypatch.setenv("HAM_WORKSPACE_STORE_BACKEND", "firestore")
    s = build_workspace_store()
    # Should construct without contacting Firestore (lazy client).
    from src.persistence.firestore_workspace_store import FirestoreWorkspaceStore

    assert isinstance(s, FirestoreWorkspaceStore)


def test_protocol_runtime_check_in_memory_satisfies_workspace_store() -> None:
    s = InMemoryWorkspaceStore()
    assert isinstance(s, WorkspaceStore)
    f = FileWorkspaceStore(path=Path("/tmp/never-used.json"))
    assert isinstance(f, WorkspaceStore)
