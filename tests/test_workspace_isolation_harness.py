"""Phase 1b: cross-tenant isolation regression harness.

Builds a deliberately busy in-memory store with three orgs and a personal
workspace. For each (caller, target) pair, the parametrized test asserts
the expected verdict (200/403/404) for each of the protected endpoints.

This catches regressions where a future refactor accidentally widens the
visibility surface of one router but not the other.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from src.ham.workspace_models import (
    MembershipRecord,
    OrgRecord,
    UserRecord,
    WorkspaceMember,
    WorkspaceRecord,
)
from src.persistence.workspace_store import (
    InMemoryWorkspaceStore,
    new_workspace_id,
)
from tests._helpers.workspace_api import (
    actor_for_user,
    client_for,
    isolate_audit,
    isolate_envs,
)


@pytest.fixture(autouse=True)
def _envs(monkeypatch, tmp_path):
    isolate_envs(monkeypatch)
    isolate_audit(monkeypatch, tmp_path)


@pytest.fixture
def world():
    """Three orgs, six users, three workspaces. Returns a dict + store."""
    store = InMemoryWorkspaceStore()
    now = datetime.now(UTC)

    # Orgs
    for org_id, name in (("org_x", "X"), ("org_y", "Y"), ("org_z", "Z")):
        store.upsert_org(OrgRecord(org_id=org_id, name=name, clerk_slug=org_id, created_at=now))

    # Users + memberships
    users: dict[str, dict[str, Any]] = {
        "alice_x": {"org": "org_x", "role": "org:admin", "email": "alice@x.com"},
        "bob_x": {"org": "org_x", "role": "org:member", "email": "bob@x.com"},
        "carol_y": {"org": "org_y", "role": "org:admin", "email": "carol@y.com"},
        "dave_y": {"org": "org_y", "role": "org:member", "email": "dave@y.com"},
        "eve_z": {"org": "org_z", "role": "org:guest", "email": "eve@z.com"},
        "frank_solo": {"org": None, "role": None, "email": "frank@solo.com"},
    }
    for uid, meta in users.items():
        store.upsert_user(
            UserRecord(
                user_id=uid,
                email=meta["email"],
                primary_org_id=meta["org"],
                created_at=now,
                last_seen_at=now,
            ),
        )
        if meta["org"]:
            store.upsert_membership(
                MembershipRecord(
                    user_id=uid,
                    org_id=meta["org"],
                    org_role=meta["role"],
                    joined_at=now,
                ),
            )

    # Workspaces
    ws_x = new_workspace_id()
    ws_y = new_workspace_id()
    ws_personal = new_workspace_id()
    store.create_workspace(
        WorkspaceRecord(
            workspace_id=ws_x,
            org_id="org_x",
            owner_user_id="alice_x",
            name="X-shared",
            slug="x-shared",
            created_by="alice_x",
            created_at=now,
            updated_at=now,
        ),
    )
    store.upsert_member(
        WorkspaceMember(
            user_id="alice_x",
            workspace_id=ws_x,
            role="owner",
            added_by="alice_x",
            added_at=now,
        ),
    )
    store.create_workspace(
        WorkspaceRecord(
            workspace_id=ws_y,
            org_id="org_y",
            owner_user_id="carol_y",
            name="Y-shared",
            slug="y-shared",
            created_by="carol_y",
            created_at=now,
            updated_at=now,
        ),
    )
    store.upsert_member(
        WorkspaceMember(
            user_id="carol_y",
            workspace_id=ws_y,
            role="owner",
            added_by="carol_y",
            added_at=now,
        ),
    )
    store.create_workspace(
        WorkspaceRecord(
            workspace_id=ws_personal,
            org_id=None,
            owner_user_id="frank_solo",
            name="Frank Solo",
            slug="frank-solo",
            created_by="frank_solo",
            created_at=now,
            updated_at=now,
        ),
    )
    store.upsert_member(
        WorkspaceMember(
            user_id="frank_solo",
            workspace_id=ws_personal,
            role="owner",
            added_by="frank_solo",
            added_at=now,
        ),
    )
    return {
        "store": store,
        "users": users,
        "ws_x": ws_x,
        "ws_y": ws_y,
        "ws_personal": ws_personal,
    }


@pytest.mark.parametrize(
    ("caller", "target_key", "expected_get", "expected_patch"),
    [
        # Owner of x-shared (workspace member row) → owner role; full access
        ("alice_x", "ws_x", 200, 200),
        # org:member fallback → "member" role: read-only (workspace:write NOT granted)
        ("bob_x", "ws_x", 200, 403),
        # Cross-tenant: org_y caller cannot see ws_x
        ("carol_y", "ws_x", 403, 403),
        ("dave_y", "ws_x", 403, 403),
        # Different org entirely
        ("eve_z", "ws_x", 403, 403),
        # Personal workspace owner
        ("frank_solo", "ws_personal", 200, 200),
        # Non-owner cannot access personal workspaces
        ("alice_x", "ws_personal", 403, 403),
        ("eve_z", "ws_personal", 403, 403),
        # Y-side: carol_y is owner row + org:admin; dave_y is org:member fallback
        ("carol_y", "ws_y", 200, 200),
        ("dave_y", "ws_y", 200, 403),
        ("alice_x", "ws_y", 403, 403),
        ("eve_z", "ws_y", 403, 403),
        # Frank solo cannot read someone else's org workspace
        ("frank_solo", "ws_x", 403, 403),
    ],
)
def test_isolation_get_and_patch(world, caller, target_key, expected_get, expected_patch) -> None:
    store = world["store"]
    target = world[target_key]
    meta = world["users"][caller]
    actor = actor_for_user(
        caller,
        email=meta["email"],
        org_id=meta["org"],
        org_role=meta["role"],
    )
    client = client_for(store, actor=actor)

    g = client.get(f"/api/workspaces/{target}")
    assert g.status_code == expected_get, (
        f"GET caller={caller} target={target_key} → {g.status_code}, expected {expected_get}: {g.text}"
    )

    p = client.patch(f"/api/workspaces/{target}", json={"description": "updated"})
    assert p.status_code == expected_patch, (
        f"PATCH caller={caller} target={target_key} → {p.status_code}, expected {expected_patch}: {p.text}"
    )


def test_list_excludes_other_orgs(world) -> None:
    store = world["store"]
    # alice_x sees only ws_x; carol_y sees only ws_y
    alice = actor_for_user(
        "alice_x",
        email="alice@x.com",
        org_id="org_x",
        org_role="org:admin",
    )
    body = client_for(store, actor=alice).get("/api/workspaces").json()
    wids = {w["workspace_id"] for w in body["workspaces"]}
    assert world["ws_x"] in wids
    assert world["ws_y"] not in wids
    assert world["ws_personal"] not in wids


def test_personal_workspace_invisible_to_others(world) -> None:
    store = world["store"]
    actor = actor_for_user("alice_x", email="alice@x.com", org_id="org_x", org_role="org:admin")
    body = client_for(store, actor=actor).get("/api/workspaces").json()
    wids = {w["workspace_id"] for w in body["workspaces"]}
    assert world["ws_personal"] not in wids
