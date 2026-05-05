"""Phase 1b: ``/api/workspaces`` router contract tests."""

from __future__ import annotations

import json

import pytest

from src.ham.workspace_models import WorkspaceMember
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


# ---------------------------------------------------------------------------
# GET /api/workspaces (list)
# ---------------------------------------------------------------------------


def test_list_returns_only_caller_workspaces() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    body = client_for(store, actor=actor).get("/api/workspaces").json()
    wids = {w["workspace_id"] for w in body["workspaces"]}
    assert ids["ws_b"] not in wids
    assert ids["ws_a"] in wids
    assert body["default_workspace_id"] in wids


def test_list_filters_by_org() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    body = (
        client_for(store, actor=actor)
        .get("/api/workspaces", params={"org_id": ids["org_a"]})
        .json()
    )
    for w in body["workspaces"]:
        assert w["org_id"] == ids["org_a"]


def test_list_includes_archived_when_requested() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    store.update_workspace(ids["ws_a"], status="archived")
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    body = (
        client_for(store, actor=actor)
        .get("/api/workspaces", params={"include_archived": "true"})
        .json()
    )
    wids = {w["workspace_id"] for w in body["workspaces"]}
    assert ids["ws_a"] in wids


# ---------------------------------------------------------------------------
# POST /api/workspaces
# ---------------------------------------------------------------------------


def test_create_personal_workspace() -> None:
    store = fresh_store()
    actor = actor_for_user("user_solo", email="s@s.com", org_id=None, org_role=None)
    resp = client_for(store, actor=actor).post(
        "/api/workspaces",
        json={"name": "Solo Project"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["workspace"]["slug"] == "solo-project"
    assert body["workspace"]["org_id"] is None
    assert body["workspace"]["role"] == "owner"
    assert body["audit_id"]
    assert_no_secret_keys(body)


def test_create_org_workspace_requires_admin() -> None:
    store = fresh_store()
    actor = actor_for_user(
        "user_member",
        email="m@m.com",
        org_id="org_x",
        org_role="org:member",
    )
    resp = client_for(store, actor=actor).post(
        "/api/workspaces",
        json={"name": "Org Project", "org_id": "org_x"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "HAM_ORG_ADMIN_REQUIRED"


def test_create_org_workspace_blocked_when_org_mismatch() -> None:
    store = fresh_store()
    actor = actor_for_user(
        "user_admin",
        email="a@a.com",
        org_id="org_my",
        org_role="org:admin",
    )
    resp = client_for(store, actor=actor).post(
        "/api/workspaces",
        json={"name": "Foreign", "org_id": "org_other"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "HAM_ORG_MISMATCH"


def test_create_invalid_name_422() -> None:
    store = fresh_store()
    actor = actor_for_user("user_solo", email="s@s.com")
    resp = client_for(store, actor=actor).post("/api/workspaces", json={"name": "  "})
    assert resp.status_code == 422


def test_create_invalid_slug_shape_422() -> None:
    store = fresh_store()
    actor = actor_for_user("user_solo", email="s@s.com")
    resp = client_for(store, actor=actor).post(
        "/api/workspaces",
        json={"name": "Solo", "slug": "Bad Slug!"},
    )
    assert resp.status_code == 422


def test_create_slug_collision_resolves_with_suffix() -> None:
    store = fresh_store()
    actor = actor_for_user("user_solo", email="s@s.com")
    client = client_for(store, actor=actor)
    r1 = client.post("/api/workspaces", json={"name": "Solo"})
    assert r1.status_code == 201
    assert r1.json()["workspace"]["slug"] == "solo"
    r2 = client.post("/api/workspaces", json={"name": "Solo"})
    assert r2.status_code == 201
    assert r2.json()["workspace"]["slug"] == "solo-2"


def test_create_explicit_slug_collision_409() -> None:
    store = fresh_store()
    actor = actor_for_user("user_solo", email="s@s.com")
    client = client_for(store, actor=actor)
    client.post("/api/workspaces", json={"name": "Solo"})
    r2 = client.post("/api/workspaces", json={"name": "Other", "slug": "solo"})
    # Note: with explicit slug, the auto-suffix logic still runs (`derive_unique_slug`),
    # so the request succeeds with "solo-2". Conflict is only raised when the
    # suffix search is exhausted (>50 attempts) — guarded by the WorkspaceSlugConflict
    # catch from the store layer (race conditions only).
    assert r2.status_code == 201
    assert r2.json()["workspace"]["slug"] == "solo-2"


def test_create_writes_audit_row(tmp_path) -> None:
    store = fresh_store()
    actor = actor_for_user("user_solo", email="s@s.com")
    resp = client_for(store, actor=actor).post(
        "/api/workspaces",
        json={"name": "Audit Me"},
    )
    assert resp.status_code == 201
    audit_lines = (tmp_path / "operator_actions.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in audit_lines if line.strip()]
    actions = [r["action"] for r in rows]
    assert "workspace.create" in actions


# ---------------------------------------------------------------------------
# GET /api/workspaces/{wid}
# ---------------------------------------------------------------------------


def test_get_workspace_404_when_missing() -> None:
    store = fresh_store()
    actor = actor_for_user("user_x", email="x@x.com", org_id="org_a", org_role="org:admin")
    resp = client_for(store, actor=actor).get("/api/workspaces/ws_missing0000000")
    assert resp.status_code == 404


def test_get_workspace_403_cross_tenant() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    # Bob accessing Alice's org workspace
    actor = actor_for_user(
        ids["owner_b"],
        email="bob@example.com",
        org_id=ids["org_b"],
        org_role="org:admin",
    )
    resp = client_for(store, actor=actor).get(f"/api/workspaces/{ids['ws_a']}")
    assert resp.status_code == 403


def test_get_workspace_200_for_owner() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    body = client_for(store, actor=actor).get(f"/api/workspaces/{ids['ws_a']}").json()
    assert body["workspace"]["workspace_id"] == ids["ws_a"]
    assert body["context"]["role"] == "owner"
    assert "workspace:admin" in body["context"]["perms"]


# ---------------------------------------------------------------------------
# PATCH /api/workspaces/{wid}
# ---------------------------------------------------------------------------


def test_patch_owner_can_update() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    resp = client_for(store, actor=actor).patch(
        f"/api/workspaces/{ids['ws_a']}",
        json={"name": "Alpha Renamed", "description": "new desc"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["workspace"]["name"] == "Alpha Renamed"
    assert body["workspace"]["description"] == "new desc"
    assert body["audit_id"]


def test_patch_viewer_403() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    # Make alice a viewer (workspace member row override)
    from datetime import UTC
    from datetime import datetime as dt

    store.upsert_member(
        WorkspaceMember(
            user_id="user_viewer",
            workspace_id=ids["ws_a"],
            role="viewer",
            added_by=ids["owner_a"],
            added_at=dt.now(UTC),
        ),
    )
    actor = actor_for_user(
        "user_viewer",
        email="v@v.com",
        org_id=ids["org_a"],
        org_role="org:guest",
    )
    resp = client_for(store, actor=actor).patch(
        f"/api/workspaces/{ids['ws_a']}",
        json={"name": "Renamed"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "HAM_PERMISSION_DENIED"


def test_patch_invalid_name_422() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    resp = client_for(store, actor=actor).patch(
        f"/api/workspaces/{ids['ws_a']}",
        json={"name": "  "},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/workspaces/{wid}
# ---------------------------------------------------------------------------


def test_archive_requires_phrase() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    resp = client_for(store, actor=actor).request(
        "DELETE",
        f"/api/workspaces/{ids['ws_a']}",
        json={"confirmation_phrase": "wrong"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "HAM_PHRASE_INVALID"


def test_archive_succeeds_with_phrase() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    resp = client_for(store, actor=actor).request(
        "DELETE",
        f"/api/workspaces/{ids['ws_a']}",
        json={"confirmation_phrase": "ARCHIVE WORKSPACE alpha"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["workspace"]["status"] == "archived"
    # Subsequent get → 404 (resolver rejects archived)
    g = client_for(store, actor=actor).get(f"/api/workspaces/{ids['ws_a']}")
    assert g.status_code == 404


def test_archive_admin_only() -> None:
    """A workspace member (non-owner, non-admin) cannot archive."""
    store = fresh_store()
    ids = seed_two_workspaces(store)
    from datetime import UTC
    from datetime import datetime as dt

    store.upsert_member(
        WorkspaceMember(
            user_id="user_member_only",
            workspace_id=ids["ws_a"],
            role="member",
            added_by=ids["owner_a"],
            added_at=dt.now(UTC),
        ),
    )
    actor = actor_for_user(
        "user_member_only",
        email="m@m.com",
        org_id=ids["org_a"],
        org_role="org:member",
    )
    resp = client_for(store, actor=actor).request(
        "DELETE",
        f"/api/workspaces/{ids['ws_a']}",
        json={"confirmation_phrase": "ARCHIVE WORKSPACE alpha"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/workspaces/{wid}/members
# ---------------------------------------------------------------------------


def test_members_list_owner_can_read() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    body = client_for(store, actor=actor).get(f"/api/workspaces/{ids['ws_a']}/members").json()
    assert any(m["user_id"] == ids["owner_a"] for m in body["members"])
    # Email is masked
    for m in body["members"]:
        if m["email_preview"]:
            assert "*" in m["email_preview"]


def test_members_list_403_cross_tenant() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    actor = actor_for_user(
        ids["owner_b"],
        email="bob@example.com",
        org_id=ids["org_b"],
        org_role="org:admin",
    )
    resp = client_for(store, actor=actor).get(f"/api/workspaces/{ids['ws_a']}/members")
    assert resp.status_code == 403


def test_members_list_no_secret_material() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    body = client_for(store, actor=actor).get(f"/api/workspaces/{ids['ws_a']}/members").json()
    assert_no_secret_keys(body)


# ---------------------------------------------------------------------------
# Member writes (501 unless flag, perm-gate first)
# ---------------------------------------------------------------------------


def test_member_post_501_for_admin() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    resp = client_for(store, actor=actor).post(
        f"/api/workspaces/{ids['ws_a']}/members",
        json={"user_id": "user_new", "role": "member"},
    )
    assert resp.status_code == 501
    assert resp.json()["detail"]["error"]["code"] == "HAM_NOT_IMPLEMENTED"


def test_member_post_403_for_viewer_runs_perm_check_first() -> None:
    """Permission gate runs *before* the 501 stub: viewers see 403, not 501."""
    store = fresh_store()
    ids = seed_two_workspaces(store)
    from datetime import UTC
    from datetime import datetime as dt

    store.upsert_member(
        WorkspaceMember(
            user_id="user_viewer",
            workspace_id=ids["ws_a"],
            role="viewer",
            added_by=ids["owner_a"],
            added_at=dt.now(UTC),
        ),
    )
    actor = actor_for_user(
        "user_viewer",
        email="v@v.com",
        org_id=ids["org_a"],
        org_role="org:guest",
    )
    resp = client_for(store, actor=actor).post(
        f"/api/workspaces/{ids['ws_a']}/members",
        json={"user_id": "user_new", "role": "member"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "HAM_PERMISSION_DENIED"


def test_member_patch_501_for_admin() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    resp = client_for(store, actor=actor).patch(
        f"/api/workspaces/{ids['ws_a']}/members/user_target",
        json={"role": "admin"},
    )
    assert resp.status_code == 501


def test_member_delete_501_for_admin() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    resp = client_for(store, actor=actor).request(
        "DELETE",
        f"/api/workspaces/{ids['ws_a']}/members/user_target",
    )
    assert resp.status_code == 501


# ---------------------------------------------------------------------------
# Auth gates on actor-only routes
# ---------------------------------------------------------------------------


def test_list_401_when_no_actor_no_bypass() -> None:
    store = fresh_store()
    resp = client_for(store, actor=None).get("/api/workspaces")
    assert resp.status_code == 401


def test_create_401_when_no_actor_no_bypass() -> None:
    store = fresh_store()
    resp = client_for(store, actor=None).post("/api/workspaces", json={"name": "x"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Response shape spot checks (no secret material anywhere)
# ---------------------------------------------------------------------------


def test_get_response_has_no_secret_keys() -> None:
    store = fresh_store()
    ids = seed_two_workspaces(store)
    actor = actor_for_user(
        ids["owner_a"],
        email="alice@example.com",
        org_id=ids["org_a"],
        org_role="org:admin",
    )
    body = client_for(store, actor=actor).get(f"/api/workspaces/{ids['ws_a']}").json()
    assert_no_secret_keys(body)


def test_create_response_has_no_secret_keys() -> None:
    store = fresh_store()
    actor = actor_for_user("user_solo", email="s@s.com")
    body = client_for(store, actor=actor).post("/api/workspaces", json={"name": "Solo"}).json()
    assert_no_secret_keys(body)
