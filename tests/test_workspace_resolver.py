"""Phase 1a: workspace resolver decision tree + claim augmentation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.ham.clerk_auth import HamActor
from src.ham.workspace_models import (
    WORKSPACE_ID_PREFIX,
    WorkspaceMember,
    WorkspaceRecord,
)
from src.ham.workspace_perms import ROLE_PERMS
from src.ham.workspace_resolver import (
    WorkspaceForbidden,
    WorkspaceNotFound,
    perms_from_clerk_workspaces_claim,
    resolve_workspace_context,
)
from src.persistence.workspace_store import InMemoryWorkspaceStore, new_workspace_id


def _now() -> datetime:
    return datetime.now(UTC)


def _actor(
    *,
    user_id: str,
    org_id: str | None = None,
    org_role: str | None = None,
    workspaces_claim=None,
) -> HamActor:
    return HamActor(
        user_id=user_id,
        org_id=org_id,
        session_id=None,
        email=f"{user_id}@example.com",
        permissions=frozenset(),
        org_role=org_role,
        raw_permission_claim=None,
        workspaces_claim=workspaces_claim or {},
    )


def _make_workspace(
    store: InMemoryWorkspaceStore,
    *,
    org_id: str | None,
    owner: str,
    slug: str = "prod",
    archived: bool = False,
) -> WorkspaceRecord:
    wid = new_workspace_id()
    rec = WorkspaceRecord(
        workspace_id=wid,
        org_id=org_id,
        owner_user_id=owner,
        name="Test",
        slug=slug,
        description="",
        status="active",
        created_by=owner,
        created_at=_now(),
        updated_at=_now(),
    )
    store.create_workspace(rec)
    if archived:
        return store.update_workspace(wid, status="archived")
    return rec


# ---------------------------------------------------------------------------
# Workspace-level membership wins
# ---------------------------------------------------------------------------


def test_resolve_uses_workspace_membership_when_present() -> None:
    s = InMemoryWorkspaceStore()
    ws = _make_workspace(s, org_id="org_x", owner="user_a")
    s.upsert_member(
        WorkspaceMember(
            user_id="user_b",
            workspace_id=ws.workspace_id,
            role="admin",
            added_by="user_a",
            added_at=_now(),
        ),
    )
    actor = _actor(user_id="user_b", org_id="org_x", org_role="org:guest")
    ctx = resolve_workspace_context(actor, ws.workspace_id, s)
    assert ctx.role == "admin"
    assert ctx.perms == ROLE_PERMS["admin"]
    assert ctx.workspace_id == ws.workspace_id
    assert ctx.org_id == "org_x"


def test_resolve_workspace_member_overrides_org_admin() -> None:
    s = InMemoryWorkspaceStore()
    ws = _make_workspace(s, org_id="org_x", owner="user_a")
    s.upsert_member(
        WorkspaceMember(
            user_id="user_b",
            workspace_id=ws.workspace_id,
            role="viewer",
            added_by="user_a",
            added_at=_now(),
        ),
    )
    actor = _actor(user_id="user_b", org_id="org_x", org_role="org:admin")
    ctx = resolve_workspace_context(actor, ws.workspace_id, s)
    assert ctx.role == "viewer"


# ---------------------------------------------------------------------------
# Org-level fallback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "org_role, expected_role",
    [("org:admin", "admin"), ("org:member", "member"), ("org:guest", "viewer")],
)
def test_resolve_org_fallback_when_no_workspace_member_row(
    org_role: str, expected_role: str
) -> None:
    s = InMemoryWorkspaceStore()
    ws = _make_workspace(s, org_id="org_x", owner="user_a")
    actor = _actor(user_id="user_b", org_id="org_x", org_role=org_role)
    ctx = resolve_workspace_context(actor, ws.workspace_id, s)
    assert ctx.role == expected_role


def test_resolve_unknown_org_role_falls_back_to_viewer() -> None:
    s = InMemoryWorkspaceStore()
    ws = _make_workspace(s, org_id="org_x", owner="user_a")
    actor = _actor(user_id="user_b", org_id="org_x", org_role="org:unknown")
    ctx = resolve_workspace_context(actor, ws.workspace_id, s)
    assert ctx.role == "viewer"


# ---------------------------------------------------------------------------
# Forbidden / not-found
# ---------------------------------------------------------------------------


def test_resolve_404_when_workspace_missing() -> None:
    s = InMemoryWorkspaceStore()
    actor = _actor(user_id="user_a")
    with pytest.raises(WorkspaceNotFound):
        resolve_workspace_context(
            actor,
            f"{WORKSPACE_ID_PREFIX}abcdefgh12345678",
            s,
        )


def test_resolve_404_when_workspace_archived() -> None:
    s = InMemoryWorkspaceStore()
    ws = _make_workspace(s, org_id="org_x", owner="user_a", archived=True)
    actor = _actor(user_id="user_a", org_id="org_x", org_role="org:admin")
    with pytest.raises(WorkspaceNotFound):
        resolve_workspace_context(actor, ws.workspace_id, s)


def test_resolve_403_cross_tenant() -> None:
    s = InMemoryWorkspaceStore()
    ws = _make_workspace(s, org_id="org_alice", owner="user_alice")
    actor_bob = _actor(user_id="user_bob", org_id="org_bob", org_role="org:admin")
    with pytest.raises(WorkspaceForbidden):
        resolve_workspace_context(actor_bob, ws.workspace_id, s)


def test_resolve_403_actor_with_no_org_against_org_workspace() -> None:
    s = InMemoryWorkspaceStore()
    ws = _make_workspace(s, org_id="org_x", owner="user_alice")
    actor = _actor(user_id="user_bob", org_id=None)
    with pytest.raises(WorkspaceForbidden):
        resolve_workspace_context(actor, ws.workspace_id, s)


def test_resolve_personal_workspace_owner_only() -> None:
    s = InMemoryWorkspaceStore()
    ws = _make_workspace(s, org_id=None, owner="user_alice")
    actor_alice = _actor(user_id="user_alice")
    ctx = resolve_workspace_context(actor_alice, ws.workspace_id, s)
    assert ctx.role == "owner"
    assert ctx.org_id is None

    actor_bob = _actor(user_id="user_bob")
    with pytest.raises(WorkspaceForbidden):
        resolve_workspace_context(actor_bob, ws.workspace_id, s)


# ---------------------------------------------------------------------------
# Custom workspaces claim augmentation (cannot grant access alone)
# ---------------------------------------------------------------------------


def test_workspaces_claim_with_role_string_is_advisory_only() -> None:
    s = InMemoryWorkspaceStore()
    ws = _make_workspace(s, org_id="org_x", owner="user_alice")
    # Bob has no membership row and is not in org_x, but his JWT claims admin
    # for this workspace_id. The resolver MUST still 403 him.
    actor_bob = _actor(
        user_id="user_bob",
        org_id="org_other",
        org_role="org:admin",
        workspaces_claim={ws.workspace_id: "owner"},
    )
    with pytest.raises(WorkspaceForbidden):
        resolve_workspace_context(actor_bob, ws.workspace_id, s)


def test_workspaces_claim_augments_perms_for_authorized_actor() -> None:
    s = InMemoryWorkspaceStore()
    ws = _make_workspace(s, org_id="org_x", owner="user_alice")
    s.upsert_member(
        WorkspaceMember(
            user_id="user_bob",
            workspace_id=ws.workspace_id,
            role="viewer",
            added_by="user_alice",
            added_at=_now(),
        ),
    )
    # Custom permissions list (advisory) — adds `audit:read` on top of viewer.
    actor = _actor(
        user_id="user_bob",
        workspaces_claim={ws.workspace_id: ["audit:read"]},
    )
    ctx = resolve_workspace_context(actor, ws.workspace_id, s)
    assert ctx.role == "viewer"
    assert "workspace:read" in ctx.perms
    assert "audit:read" in ctx.perms  # additive


def test_perms_from_clerk_workspaces_claim_handles_bad_input() -> None:
    actor_no_attr = _actor(user_id="x")
    object.__setattr__(actor_no_attr, "workspaces_claim", "garbage")
    assert perms_from_clerk_workspaces_claim(actor_no_attr, "ws_x") == frozenset()
    actor_dict_no_match = _actor(user_id="x", workspaces_claim={"ws_other": "admin"})
    assert perms_from_clerk_workspaces_claim(actor_dict_no_match, "ws_x") == frozenset()
    actor_unknown_role = _actor(user_id="x", workspaces_claim={"ws_x": "godmode"})
    assert perms_from_clerk_workspaces_claim(actor_unknown_role, "ws_x") == frozenset()


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


def test_resolve_rejects_blank_workspace_id() -> None:
    s = InMemoryWorkspaceStore()
    actor = _actor(user_id="user_a")
    with pytest.raises(WorkspaceForbidden):
        resolve_workspace_context(actor, "", s)
    with pytest.raises(WorkspaceForbidden):
        resolve_workspace_context(actor, "   ", s)
