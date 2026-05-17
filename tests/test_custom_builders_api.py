"""Tests for the workspace-scoped Custom Builder API (PR 2).

Mirrors the fixture pattern from ``tests/test_coding_agent_access_settings.py``:
:func:`_seed_workspace` builds an in-memory workspace + member row,
dependency overrides supply the store and the actor.

Hard contracts locked here:

- Read routes work without write tokens or feature gate.
- Mutating routes require workspace-admin (effectively ``owner`` role)
  plus the feature gate (``HAM_CUSTOM_BUILDER_ENABLED``) and a valid
  ``HAM_CUSTOM_BUILDER_WRITE_TOKEN``.
- Soft delete keeps the row; subsequent GETs still resolve it.
- Response bodies never echo secrets, env names, runner URLs, provider ids.
- ``model_ref`` starting with ``byok:`` is masked for non-operator viewers.
- Operator role (``owner``) sees a ``technical_details`` block with the
  unmasked ``model_ref``; non-operator (``member``) never does.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.dependencies.workspace import get_workspace_store
from src.api.server import app, fastapi_app
from src.ham.clerk_auth import HamActor
from src.ham.workspace_models import (
    WorkspaceMember,
    WorkspaceRecord,
    WorkspaceRole,
)
from src.persistence.workspace_store import InMemoryWorkspaceStore, new_workspace_id

_WRITE_TOKEN = "test-write-token-bogus"


def _now() -> datetime:
    return datetime.now(UTC)


def _seed_workspace(
    store: InMemoryWorkspaceStore,
    actor_user_id: str,
    *,
    role: WorkspaceRole = "owner",
    workspace_id: str | None = None,
) -> str:
    wid = workspace_id or new_workspace_id()
    now = _now()
    owner_id = actor_user_id if role == "owner" else "user_owner_other"
    store.create_workspace(
        WorkspaceRecord(
            workspace_id=wid,
            org_id=None if role == "owner" else "org_test",
            owner_user_id=owner_id,
            name="Test WS",
            slug=wid.replace("ws_", "")[:16],
            description="",
            status="active",
            created_by=owner_id,
            created_at=now,
            updated_at=now,
        )
    )
    store.upsert_member(
        WorkspaceMember(
            user_id=actor_user_id,
            workspace_id=wid,
            role=role,
            added_by=owner_id,
            added_at=now,
        )
    )
    return wid


def _actor(user_id: str = "user_ws") -> HamActor:
    return HamActor(
        user_id=user_id,
        org_id="org_test",
        session_id="sess_ws",
        email=f"{user_id}@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


@pytest.fixture()
def cleanup_overrides() -> Any:
    yield
    fastapi_app.dependency_overrides.clear()


@pytest.fixture()
def isolated_store_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_STORE", "local")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_LOCAL_PATH", str(tmp_path / "custom_builders"))
    return tmp_path


def _seed_owner(
    cleanup_overrides: None,
) -> tuple[InMemoryWorkspaceStore, str]:
    actor = _actor()
    store = InMemoryWorkspaceStore()
    wid = _seed_workspace(store, actor.user_id, role="owner")
    fastapi_app.dependency_overrides[get_workspace_store] = lambda: store
    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: actor
    return store, wid


def _seed_member(
    cleanup_overrides: None,
) -> tuple[InMemoryWorkspaceStore, str]:
    actor = _actor()
    store = InMemoryWorkspaceStore()
    wid = _seed_workspace(store, actor.user_id, role="member")
    fastapi_app.dependency_overrides[get_workspace_store] = lambda: store
    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: actor
    return store, wid


def _client() -> TestClient:
    return TestClient(app)


def _minimal_create_body(builder_id: str = "game-builder", **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "builder_id": builder_id,
        "name": "Game Builder",
        "description": "Small 2D games.",
        "intent_tags": ["game", "puzzle"],
        "task_kinds": ["feature", "fix"],
        "permission_preset": "game_build",
    }
    base.update(over)
    return base


def _minimal_preview_body(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "Game Builder",
        "description": "Small 2D games.",
        "permission_preset": "game_build",
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Auth + workspace gating
# ---------------------------------------------------------------------------


def test_get_list_unauthenticated_returns_401_when_clerk_enforced(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "1")
    fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)
    res = _client().get("/api/workspaces/ws_abc/custom-builders")
    assert res.status_code in (401, 403)


def test_get_list_member_returns_empty_when_no_builders(
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    _, wid = _seed_member(cleanup_overrides)
    res = _client().get(f"/api/workspaces/{wid}/custom-builders")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body == {"workspace_id": wid, "builders": []}


def test_get_one_returns_404_when_missing(
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    _, wid = _seed_owner(cleanup_overrides)
    res = _client().get(f"/api/workspaces/{wid}/custom-builders/missing-one")
    assert res.status_code == 404, res.text
    body = res.json()
    assert body["detail"]["error"]["code"] == "CUSTOM_BUILDER_NOT_FOUND"


# ---------------------------------------------------------------------------
# Create gating
# ---------------------------------------------------------------------------


def test_create_requires_admin_perm(
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    _, wid = _seed_member(cleanup_overrides)
    res = _client().post(
        f"/api/workspaces/{wid}/custom-builders",
        json=_minimal_create_body(),
    )
    assert res.status_code == 403, res.text


def test_create_requires_feature_flag(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.delenv("HAM_CUSTOM_BUILDER_ENABLED", raising=False)
    _, wid = _seed_owner(cleanup_overrides)
    res = _client().post(
        f"/api/workspaces/{wid}/custom-builders",
        json=_minimal_create_body(),
    )
    assert res.status_code == 503, res.text
    assert res.json()["detail"]["error"]["code"] == "CUSTOM_BUILDER_FEATURE_DISABLED"


def test_create_requires_write_token_when_feature_enabled(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_ENABLED", "1")
    monkeypatch.delenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", raising=False)
    _, wid = _seed_owner(cleanup_overrides)
    res = _client().post(
        f"/api/workspaces/{wid}/custom-builders",
        json=_minimal_create_body(),
    )
    assert res.status_code == 403, res.text
    assert res.json()["detail"]["error"]["code"] == "CUSTOM_BUILDER_WRITES_DISABLED"


def test_create_requires_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_ENABLED", "1")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", _WRITE_TOKEN)
    _, wid = _seed_owner(cleanup_overrides)
    res = _client().post(
        f"/api/workspaces/{wid}/custom-builders",
        json=_minimal_create_body(),
    )
    assert res.status_code == 401, res.text
    assert res.json()["detail"]["error"]["code"] == "CUSTOM_BUILDER_AUTH_REQUIRED"


def test_create_rejects_wrong_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_ENABLED", "1")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", _WRITE_TOKEN)
    _, wid = _seed_owner(cleanup_overrides)
    res = _client().post(
        f"/api/workspaces/{wid}/custom-builders",
        json=_minimal_create_body(),
        headers={"Authorization": "Bearer wrong-token-bogus"},
    )
    assert res.status_code == 403, res.text
    assert res.json()["detail"]["error"]["code"] == "CUSTOM_BUILDER_AUTH_INVALID"


# ---------------------------------------------------------------------------
# Happy path + create-time semantics
# ---------------------------------------------------------------------------


def test_create_happy_path_with_valid_token(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_ENABLED", "1")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", _WRITE_TOKEN)
    _, wid = _seed_owner(cleanup_overrides)
    client = _client()
    res = client.post(
        f"/api/workspaces/{wid}/custom-builders",
        json=_minimal_create_body(),
        headers={"Authorization": f"Bearer {_WRITE_TOKEN}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["builder_id"] == "game-builder"
    assert body["name"] == "Game Builder"
    assert body["enabled"] is True
    list_res = client.get(f"/api/workspaces/{wid}/custom-builders")
    assert list_res.status_code == 200
    builders = list_res.json()["builders"]
    assert len(builders) == 1
    assert builders[0]["builder_id"] == "game-builder"


def test_create_duplicate_returns_409(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_ENABLED", "1")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", _WRITE_TOKEN)
    _, wid = _seed_owner(cleanup_overrides)
    client = _client()
    headers = {"Authorization": f"Bearer {_WRITE_TOKEN}"}
    r1 = client.post(
        f"/api/workspaces/{wid}/custom-builders",
        json=_minimal_create_body(),
        headers=headers,
    )
    assert r1.status_code == 200, r1.text
    r2 = client.post(
        f"/api/workspaces/{wid}/custom-builders",
        json=_minimal_create_body(),
        headers=headers,
    )
    assert r2.status_code == 409, r2.text
    assert r2.json()["detail"]["error"]["code"] == "CUSTOM_BUILDER_CONFLICT"


def test_create_rejects_secret_looking_model_ref(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_ENABLED", "1")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", _WRITE_TOKEN)
    _, wid = _seed_owner(cleanup_overrides)
    body = _minimal_create_body(model_ref="abc123XYZ" * 4)
    res = _client().post(
        f"/api/workspaces/{wid}/custom-builders",
        json=body,
        headers={"Authorization": f"Bearer {_WRITE_TOKEN}"},
    )
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["error"]["code"] == "CUSTOM_BUILDER_VALIDATION"


def test_create_request_rejects_extra_fields(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_ENABLED", "1")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", _WRITE_TOKEN)
    _, wid = _seed_owner(cleanup_overrides)
    body = _minimal_create_body()
    body["totally_not_a_field"] = "hack"
    res = _client().post(
        f"/api/workspaces/{wid}/custom-builders",
        json=body,
        headers={"Authorization": f"Bearer {_WRITE_TOKEN}"},
    )
    assert res.status_code == 422, res.text


# ---------------------------------------------------------------------------
# Patch semantics
# ---------------------------------------------------------------------------


def _create_one(client: TestClient, wid: str, **over: Any) -> dict[str, Any]:
    res = client.post(
        f"/api/workspaces/{wid}/custom-builders",
        json=_minimal_create_body(**over),
        headers={"Authorization": f"Bearer {_WRITE_TOKEN}"},
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_patch_partial_update(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_ENABLED", "1")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", _WRITE_TOKEN)
    _, wid = _seed_owner(cleanup_overrides)
    client = _client()
    _create_one(client, wid)
    res = client.patch(
        f"/api/workspaces/{wid}/custom-builders/game-builder",
        json={"description": "Now updated."},
        headers={"Authorization": f"Bearer {_WRITE_TOKEN}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["description"] == "Now updated."
    assert body["name"] == "Game Builder"
    assert body["permission_preset"] == "game_build"


def test_patch_returns_404_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_ENABLED", "1")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", _WRITE_TOKEN)
    _, wid = _seed_owner(cleanup_overrides)
    res = _client().patch(
        f"/api/workspaces/{wid}/custom-builders/missing-one",
        json={"description": "nope"},
        headers={"Authorization": f"Bearer {_WRITE_TOKEN}"},
    )
    assert res.status_code == 404, res.text
    assert res.json()["detail"]["error"]["code"] == "CUSTOM_BUILDER_NOT_FOUND"


def test_patch_revalidates_full_profile(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_ENABLED", "1")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", _WRITE_TOKEN)
    _, wid = _seed_owner(cleanup_overrides)
    client = _client()
    _create_one(client, wid)
    res = client.patch(
        f"/api/workspaces/{wid}/custom-builders/game-builder",
        json={
            "permission_preset": "custom",
            "allowed_paths": [],
            "denied_paths": [],
            "denied_operations": [],
        },
        headers={"Authorization": f"Bearer {_WRITE_TOKEN}"},
    )
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["error"]["code"] == "CUSTOM_BUILDER_VALIDATION"


# ---------------------------------------------------------------------------
# Soft-delete
# ---------------------------------------------------------------------------


def test_delete_soft_deletes_and_keeps_row(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_ENABLED", "1")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", _WRITE_TOKEN)
    _, wid = _seed_owner(cleanup_overrides)
    client = _client()
    _create_one(client, wid)
    res = client.delete(
        f"/api/workspaces/{wid}/custom-builders/game-builder",
        headers={"Authorization": f"Bearer {_WRITE_TOKEN}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["enabled"] is False
    assert body["soft_deleted"] is True

    # The row is still readable.
    single = client.get(f"/api/workspaces/{wid}/custom-builders/game-builder")
    assert single.status_code == 200, single.text
    assert single.json()["enabled"] is False

    # And still listed.
    listed = client.get(f"/api/workspaces/{wid}/custom-builders").json()
    assert len(listed["builders"]) == 1
    assert listed["builders"][0]["enabled"] is False


def test_delete_returns_404_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_ENABLED", "1")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", _WRITE_TOKEN)
    _, wid = _seed_owner(cleanup_overrides)
    res = _client().delete(
        f"/api/workspaces/{wid}/custom-builders/missing-one",
        headers={"Authorization": f"Bearer {_WRITE_TOKEN}"},
    )
    assert res.status_code == 404, res.text


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


def test_preview_valid_draft_no_persistence(
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    _, wid = _seed_owner(cleanup_overrides)
    client = _client()
    res = client.post(
        f"/api/workspaces/{wid}/custom-builders/preview",
        json=_minimal_preview_body(),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["valid"] is True
    assert body["errors"] == []
    assert body["summary"]["name"] == "Game Builder"
    assert body["summary"]["permission_preset"] == "game_build"

    # No persistence
    listed = client.get(f"/api/workspaces/{wid}/custom-builders").json()
    assert listed["builders"] == []


def test_preview_invalid_draft_returns_errors(
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    _, wid = _seed_owner(cleanup_overrides)
    client = _client()
    res = client.post(
        f"/api/workspaces/{wid}/custom-builders/preview",
        json=_minimal_preview_body(name="x" * 200),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["valid"] is False
    assert body["errors"], body
    # No persistence
    listed = client.get(f"/api/workspaces/{wid}/custom-builders").json()
    assert listed["builders"] == []


def test_preview_does_not_require_write_token(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.delenv("HAM_CUSTOM_BUILDER_ENABLED", raising=False)
    monkeypatch.delenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", raising=False)
    _, wid = _seed_member(cleanup_overrides)
    res = _client().post(
        f"/api/workspaces/{wid}/custom-builders/preview",
        json=_minimal_preview_body(),
    )
    assert res.status_code == 200, res.text
    assert res.json()["valid"] is True


# ---------------------------------------------------------------------------
# Test-plan
# ---------------------------------------------------------------------------


def test_test_plan_returns_stub_candidates_with_note(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_ENABLED", "1")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", _WRITE_TOKEN)
    _, wid = _seed_owner(cleanup_overrides)
    client = _client()
    _create_one(client, wid)
    res = client.post(
        f"/api/workspaces/{wid}/custom-builders/game-builder/test-plan",
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["workspace_id"] == wid
    assert body["builder_id"] == "game-builder"
    assert body["note"] == "Conductor integration lands in PR 4."
    assert body["candidates"]
    candidate = body["candidates"][0]
    assert candidate["builder_id"] == "game-builder"
    assert candidate["builder_name"] == "Game Builder"
    assert candidate["task_kind"] == "feature"
    assert candidate["would_be_chosen"] is True


# ---------------------------------------------------------------------------
# Secret hygiene + operator masking
# ---------------------------------------------------------------------------


def test_response_no_secret_leak(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_ENABLED", "1")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", _WRITE_TOKEN)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-only-bogus")
    monkeypatch.setenv("HAM_DROID_EXEC_TOKEN", "ham-droid-bogus-only")

    owner_actor = _actor("user_owner")
    member_actor = _actor("user_member")
    store = InMemoryWorkspaceStore()
    wid = _seed_workspace(store, owner_actor.user_id, role="owner")
    store.upsert_member(
        WorkspaceMember(
            user_id=member_actor.user_id,
            workspace_id=wid,
            role="member",
            added_by=owner_actor.user_id,
            added_at=_now(),
        )
    )
    fastapi_app.dependency_overrides[get_workspace_store] = lambda: store
    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: owner_actor

    client = _client()
    _create_one(client, wid)

    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: member_actor

    forbidden_substrings = (
        "sk-ant-test-only-bogus",
        "ham-droid-bogus-only",
        _WRITE_TOKEN,
        "ANTHROPIC_API_KEY",
        "HAM_DROID_EXEC_TOKEN",
        "HAM_CUSTOM_BUILDER_WRITE_TOKEN",
        "opencode_cli",
        "safe_edit_low",
        "http://",
        "https://",
    )

    routes = (
        f"/api/workspaces/{wid}/custom-builders",
        f"/api/workspaces/{wid}/custom-builders/game-builder",
        f"/api/workspaces/{wid}/custom-builders/game-builder/test-plan",
    )
    for route in routes:
        if route.endswith("/test-plan"):
            res = client.post(route)
        else:
            res = client.get(route)
        assert res.status_code == 200, (route, res.text)
        blob = res.text
        for substring in forbidden_substrings:
            assert substring not in blob, (route, substring)


def test_byok_model_ref_masked_in_response(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_ENABLED", "1")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", _WRITE_TOKEN)

    # First create as owner (only owner can write), then switch the actor
    # to a member to see the non-operator response shape.
    owner_actor = _actor("user_owner")
    member_actor = _actor("user_member")
    store = InMemoryWorkspaceStore()
    wid = _seed_workspace(store, owner_actor.user_id, role="owner")
    # Add a member row for member_actor on the same workspace.
    store.upsert_member(
        WorkspaceMember(
            user_id=member_actor.user_id,
            workspace_id=wid,
            role="member",
            added_by=owner_actor.user_id,
            added_at=_now(),
        )
    )
    fastapi_app.dependency_overrides[get_workspace_store] = lambda: store
    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: owner_actor

    client = _client()
    body = _minimal_create_body(model_ref="byok:abc123-record")
    res = client.post(
        f"/api/workspaces/{wid}/custom-builders",
        json=body,
        headers={"Authorization": f"Bearer {_WRITE_TOKEN}"},
    )
    assert res.status_code == 200, res.text
    owner_view = res.json()
    # Operator (owner) sees unmasked model_ref under technical_details.
    assert owner_view["technical_details"]["model_ref"] == "byok:abc123-record"
    # Top-level model_ref is masked even for operator.
    assert owner_view["model_ref"] == "byok:••••"

    # Switch to member actor.
    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: member_actor
    res2 = client.get(f"/api/workspaces/{wid}/custom-builders/game-builder")
    assert res2.status_code == 200, res2.text
    member_view = res2.json()
    assert member_view["model_ref"] == "byok:••••"
    assert "abc123-record" not in res2.text
    assert "technical_details" not in member_view


def test_operator_role_sees_technical_details(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_ENABLED", "1")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", _WRITE_TOKEN)
    _, wid = _seed_owner(cleanup_overrides)
    client = _client()
    _create_one(client, wid)
    res = client.get(f"/api/workspaces/{wid}/custom-builders/game-builder")
    assert res.status_code == 200, res.text
    body = res.json()
    assert "technical_details" in body
    td = body["technical_details"]
    assert td["harness"] == "opencode_cli"
    assert td["compiled_permission_summary"]


def test_member_role_does_not_see_technical_details(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_ENABLED", "1")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_WRITE_TOKEN", _WRITE_TOKEN)
    # Owner seeds + creates; member then reads.
    owner_actor = _actor("user_owner")
    member_actor = _actor("user_member")
    store = InMemoryWorkspaceStore()
    wid = _seed_workspace(store, owner_actor.user_id, role="owner")
    store.upsert_member(
        WorkspaceMember(
            user_id=member_actor.user_id,
            workspace_id=wid,
            role="member",
            added_by=owner_actor.user_id,
            added_at=_now(),
        )
    )
    fastapi_app.dependency_overrides[get_workspace_store] = lambda: store
    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: owner_actor

    client = _client()
    _create_one(client, wid)

    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: member_actor
    res = client.get(f"/api/workspaces/{wid}/custom-builders/game-builder")
    assert res.status_code == 200, res.text
    body = res.json()
    assert "technical_details" not in body
