"""Phase 1b: ``GET /api/me`` contract tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from src.api.dependencies.workspace import LOCAL_DEV_USER_ID
from src.ham.workspace_models import (
    MembershipRecord,
    OrgRecord,
    UserRecord,
    WorkspaceMember,
    WorkspaceRecord,
)
from src.persistence.workspace_store import (
    InMemoryWorkspaceStore,
    WorkspaceStoreError,
    new_workspace_id,
)
from tests._helpers.workspace_api import (
    actor_for_user,
    assert_no_secret_keys,
    client_for,
    fresh_store,
    isolate_audit,
    isolate_envs,
    seed_two_workspaces,
)


@pytest.fixture(autouse=True)
def _envs(monkeypatch, tmp_path):
    isolate_envs(monkeypatch)
    isolate_audit(monkeypatch, tmp_path)


def test_me_401_when_no_actor_and_hosted_mode() -> None:
    """No Clerk session in hosted mode → 401 CLERK_SESSION_REQUIRED."""
    import os

    os.environ["HAM_CLERK_REQUIRE_AUTH"] = "true"
    try:
        store = fresh_store()
        client = client_for(store, actor=None)
        resp = client.get("/api/me")
    finally:
        os.environ.pop("HAM_CLERK_REQUIRE_AUTH", None)
    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"


def test_me_401_when_no_actor_and_no_bypass(monkeypatch) -> None:
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("HAM_LOCAL_DEV_WORKSPACE_BYPASS", raising=False)
    store = fresh_store()
    client = client_for(store, actor=None)
    resp = client.get("/api/me")
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "HAM_WORKSPACE_AUTH_REQUIRED"


def test_me_200_with_local_dev_bypass(monkeypatch) -> None:
    """Bypass on + actor=None → synthetic actor → 200 + auth_mode=local_dev_bypass."""
    monkeypatch.setenv("HAM_LOCAL_DEV_WORKSPACE_BYPASS", "true")
    store = fresh_store()
    client = client_for(store, actor=None)
    resp = client.get("/api/me")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["auth_mode"] == "local_dev_bypass"
    assert body["user"]["user_id"] == LOCAL_DEV_USER_ID


def test_me_200_with_clerk_actor() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    client = client_for(store, actor=actor)
    resp = client.get("/api/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["auth_mode"] == "clerk"
    assert body["user"]["user_id"] == ids["owner_a"]
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["primary_org_id"] == ids["org_a"]
    wids = {w["workspace_id"] for w in body["workspaces"]}
    assert ids["ws_a"] in wids
    assert ids["ws_personal"] in wids
    assert ids["ws_b"] not in wids  # cross-tenant isolation


def test_me_503_when_workspace_store_list_raises() -> None:
    """Unhandled WorkspaceStoreError must not surface as plaintext HTTP 500."""

    class FailList(InMemoryWorkspaceStore):
        def list_workspaces_for_user(self, user_id: str, **kwargs):  # type: ignore[no-untyped-def]
            raise WorkspaceStoreError("simulated store outage")

    store = FailList()
    ids = seed_two_workspaces(store)
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    client = client_for(store, actor=actor)
    resp = client.get("/api/me")
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["error"]["code"] == "HAM_WORKSPACE_STORE_UNAVAILABLE"


def test_me_default_workspace_prefers_owner() -> None:
    """Algorithm: most-recently-updated owner > admin > anything."""
    store = fresh_store()
    now = datetime.now(UTC)
    user_id = "user_x"
    org_id = "org_x"
    store.upsert_user(
        UserRecord(user_id=user_id, email="x@x.com", created_at=now, last_seen_at=now),
    )
    store.upsert_org(
        OrgRecord(org_id=org_id, name="X", clerk_slug="x", created_at=now),
    )
    store.upsert_membership(
        MembershipRecord(user_id=user_id, org_id=org_id, org_role="org:admin", joined_at=now),
    )
    # ws1: viewer role (org-fallback only)
    ws1 = new_workspace_id()
    store.create_workspace(
        WorkspaceRecord(
            workspace_id=ws1,
            org_id=org_id,
            owner_user_id="someone-else",
            name="Viewer Only",
            slug="viewer-only",
            created_by="someone-else",
            created_at=now,
            updated_at=now,
        ),
    )
    # ws2: explicit owner role
    ws2 = new_workspace_id()
    store.create_workspace(
        WorkspaceRecord(
            workspace_id=ws2,
            org_id=org_id,
            owner_user_id=user_id,
            name="My Owned",
            slug="my-owned",
            created_by=user_id,
            created_at=now,
            updated_at=now,
        ),
    )
    store.upsert_member(
        WorkspaceMember(
            user_id=user_id,
            workspace_id=ws2,
            role="owner",
            added_by=user_id,
            added_at=now,
        ),
    )
    actor = actor_for_user(user_id, email="x@x.com", org_id=org_id, org_role="org:admin")
    client = client_for(store, actor=actor)
    resp = client.get("/api/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["default_workspace_id"] == ws2


def test_me_default_workspace_none_when_empty() -> None:
    actor = actor_for_user("user_lonely", email="l@l.com")
    client = client_for(fresh_store(), actor=actor)
    body = client.get("/api/me").json()
    assert body["workspaces"] == []
    assert body["default_workspace_id"] is None


def test_me_mirror_writes_idempotent() -> None:
    """Repeated /api/me → user/org/membership rows mirrored once and updated."""
    store = fresh_store()
    actor = actor_for_user(
        "user_mirror",
        email="m@m.com",
        org_id="org_mirror",
        org_role="org:admin",
    )
    client = client_for(store, actor=actor)
    for _ in range(3):
        resp = client.get("/api/me")
        assert resp.status_code == 200
    # Single mirror row each
    assert store.get_user("user_mirror") is not None
    assert store.get_org("org_mirror") is not None
    memberships = store.list_memberships_for_user("user_mirror")
    assert len(memberships) == 1
    assert memberships[0].org_role == "org:admin"


def test_me_mirror_failure_does_not_block_response(monkeypatch) -> None:
    """If upsert_user blows up, /api/me still returns 200 (best-effort mirror)."""
    store = fresh_store()
    original = store.upsert_user

    def _boom(record):  # noqa: ANN001 — test-only stub
        raise RuntimeError("simulated firestore outage")

    store.upsert_user = _boom  # type: ignore[method-assign]
    actor = actor_for_user("user_resilient", email="r@r.com")
    client = client_for(store, actor=actor)
    resp = client.get("/api/me")
    assert resp.status_code == 200
    store.upsert_user = original  # type: ignore[method-assign]


def test_me_response_carries_no_secret_keys() -> None:
    store = fresh_store()
    seed_two_workspaces(store)
    actor = actor_for_user(
        "user_alice",
        email="alice@example.com",
        org_id="org_a",
        org_role="org:admin",
    )
    body = client_for(store, actor=actor).get("/api/me").json()
    assert_no_secret_keys(body)


def test_me_workspace_summary_shape() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    body = client_for(store, actor=actor).get("/api/me").json()
    summary = next(w for w in body["workspaces"] if w["workspace_id"] == ids["ws_a"])
    expected_keys = {
        "workspace_id",
        "org_id",
        "name",
        "slug",
        "description",
        "status",
        "role",
        "perms",
        "is_default",
        "created_at",
        "updated_at",
    }
    assert expected_keys.issubset(summary.keys())
    assert summary["role"] == "owner"
    assert "workspace:admin" in summary["perms"]


def test_me_list_excludes_archived_by_default() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    store.update_workspace(ids["ws_a"], status="archived")
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    body = client_for(store, actor=actor).get("/api/me").json()
    wids = {w["workspace_id"] for w in body["workspaces"]}
    assert ids["ws_a"] not in wids
    assert ids["ws_personal"] in wids


def test_me_audit_path_isolated(tmp_path) -> None:
    """The audit-path env knob is honored (the /api/me route itself doesn't audit,
    but the harness sets the env so the workspace router writes go to tmp)."""
    expected = tmp_path / "operator_actions.jsonl"
    # Trigger something that *does* audit so we can verify the harness:
    store = fresh_store()
    actor = actor_for_user("user_audit", email="a@a.com", org_id="org_audit", org_role="org:admin")
    client = client_for(store, actor=actor)
    resp = client.post(
        "/api/workspaces",
        json={"name": "Audit Test", "org_id": "org_audit"},
    )
    assert resp.status_code == 201, resp.text
    rows = [
        json.loads(line)
        for line in expected.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(r["action"] == "workspace.create" for r in rows)
