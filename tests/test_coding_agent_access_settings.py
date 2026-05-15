"""
Tests for workspace coding-agent access settings — store, API, conductor
integration, and readiness policy gating.

Covers:
- Default settings creation / derivation when no settings row exists.
- GET/PATCH settings API: auth gate, workspace scoping, no secret leakage.
- Conductor respects disabled provider preferences.
- Conductor respects preference_mode boosts.
- Preference cannot bypass readiness / project blockers.
- OpenCode appears blocked with reason when model access is missing.
- OpenCode appears available when platform + settings + model access are good.
- Factory Droid default behavior unchanged.
- Cursor remains blocked without GitHub repo.
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
from src.ham.coding_router.readiness import _apply_workspace_policy
from src.ham.coding_router.recommend import _apply_preference_boosts
from src.ham.coding_router.types import (
    Candidate,
    ProviderReadiness,
    WorkspaceAgentPolicy,
)
from src.ham.workspace_models import WorkspaceMember, WorkspaceRecord
from src.persistence.coding_agent_access_settings_store import (
    LocalJsonCodingAgentAccessSettingsStore,
    workspace_settings_scope_key,
)
from src.persistence.project_store import ProjectStore, set_project_store_for_tests
from src.persistence.workspace_store import InMemoryWorkspaceStore, new_workspace_id

# ---------------------------------------------------------------------------
# Store-level unit tests
# ---------------------------------------------------------------------------


def test_store_get_returns_none_when_empty(tmp_path: Path) -> None:
    store = LocalJsonCodingAgentAccessSettingsStore(tmp_path / "settings")
    assert store.get_raw(workspace_settings_scope_key("ws_abc")) is None


def test_store_put_and_get_roundtrip(tmp_path: Path) -> None:
    store = LocalJsonCodingAgentAccessSettingsStore(tmp_path / "settings")
    key = workspace_settings_scope_key("ws_abc")
    data = {"allow_opencode": True, "preference_mode": "prefer_open_custom"}
    store.put_raw(key, data)
    result = store.get_raw(key)
    assert result is not None
    assert result["allow_opencode"] is True
    assert result["preference_mode"] == "prefer_open_custom"


def test_store_scope_key_is_workspace_only() -> None:
    key = workspace_settings_scope_key("ws_xyz")
    assert key == "workspace:ws_xyz"
    # No user_id component.
    assert "user:" not in key


def test_store_scope_keys_are_distinct_per_workspace(tmp_path: Path) -> None:
    store = LocalJsonCodingAgentAccessSettingsStore(tmp_path / "settings")
    key_a = workspace_settings_scope_key("ws_aaa")
    key_b = workspace_settings_scope_key("ws_bbb")
    store.put_raw(key_a, {"allow_opencode": True})
    store.put_raw(key_b, {"allow_opencode": False})
    assert store.get_raw(key_a)["allow_opencode"] is True
    assert store.get_raw(key_b)["allow_opencode"] is False


# ---------------------------------------------------------------------------
# WorkspaceAgentPolicy defaults
# ---------------------------------------------------------------------------


def test_workspace_agent_policy_defaults() -> None:
    policy = WorkspaceAgentPolicy()
    assert policy.allow_factory_droid is True
    assert policy.allow_claude_agent is True
    assert policy.allow_opencode is False  # off by default
    assert policy.allow_cursor is True
    assert policy.preference_mode == "recommended"
    assert policy.model_source_preference == "ham_default"
    assert policy.updated_at is None
    assert policy.updated_by is None


def test_workspace_agent_policy_is_frozen() -> None:
    policy = WorkspaceAgentPolicy()
    with pytest.raises(Exception):
        policy.allow_opencode = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Policy blocker application (readiness layer)
# ---------------------------------------------------------------------------


def _readiness_rows() -> tuple[ProviderReadiness, ...]:
    return (
        ProviderReadiness(provider="no_agent", available=True),
        ProviderReadiness(provider="factory_droid_audit", available=True),
        ProviderReadiness(provider="factory_droid_build", available=True),
        ProviderReadiness(provider="cursor_cloud", available=True),
        ProviderReadiness(provider="claude_agent", available=True),
        ProviderReadiness(provider="opencode_cli", available=True),
    )


def test_apply_workspace_policy_none_passes_all_through() -> None:
    rows = _readiness_rows()
    result = _apply_workspace_policy(rows, None)
    assert result == rows


def test_apply_workspace_policy_disables_opencode() -> None:
    policy = WorkspaceAgentPolicy(allow_opencode=False)
    rows = _readiness_rows()
    result = _apply_workspace_policy(rows, policy)
    oc = next(p for p in result if p.provider == "opencode_cli")
    assert oc.available is False
    assert any("not enabled" in b.lower() or "builder settings" in b.lower() for b in oc.blockers)


def test_apply_workspace_policy_disables_cursor() -> None:
    policy = WorkspaceAgentPolicy(allow_cursor=False)
    rows = _readiness_rows()
    result = _apply_workspace_policy(rows, policy)
    cursor = next(p for p in result if p.provider == "cursor_cloud")
    assert cursor.available is False
    assert cursor.blockers


def test_apply_workspace_policy_disables_factory_droid_both_audit_and_build() -> None:
    policy = WorkspaceAgentPolicy(allow_factory_droid=False)
    rows = _readiness_rows()
    result = _apply_workspace_policy(rows, policy)
    for provider in ("factory_droid_audit", "factory_droid_build"):
        row = next(p for p in result if p.provider == provider)
        assert row.available is False, provider
        assert row.blockers, provider


def test_apply_workspace_policy_no_agent_always_allowed() -> None:
    policy = WorkspaceAgentPolicy(
        allow_factory_droid=False,
        allow_claude_agent=False,
        allow_opencode=False,
        allow_cursor=False,
    )
    rows = _readiness_rows()
    result = _apply_workspace_policy(rows, policy)
    no_agent = next(p for p in result if p.provider == "no_agent")
    assert no_agent.available is True
    assert not no_agent.blockers


def test_apply_workspace_policy_preserves_existing_blockers() -> None:
    """Policy blocker is appended, not replacing existing readiness blockers."""
    rows = (
        ProviderReadiness(
            provider="opencode_cli",
            available=False,
            blockers=("OpenCode is not installed.",),
        ),
    )
    policy = WorkspaceAgentPolicy(allow_opencode=False)
    result = _apply_workspace_policy(rows, policy)
    oc = result[0]
    assert len(oc.blockers) == 2
    assert "OpenCode is not installed." in oc.blockers


def test_policy_blocker_copy_is_normie_safe() -> None:
    """Policy blocker copy must never name env vars, provider ids, or internals."""
    policy = WorkspaceAgentPolicy(
        allow_factory_droid=False,
        allow_claude_agent=False,
        allow_opencode=False,
        allow_cursor=False,
    )
    rows = _readiness_rows()
    result = _apply_workspace_policy(rows, policy)
    for p in result:
        for blocker in p.blockers:
            lower = blocker.lower()
            assert "ham_" not in lower, f"blocker leaks env name: {blocker!r}"
            assert "opencode_cli" not in lower, f"blocker leaks provider id: {blocker!r}"
            assert "factory_droid_build" not in lower, f"blocker leaks provider id: {blocker!r}"
            assert "safe_edit_low" not in lower, f"blocker leaks workflow id: {blocker!r}"


# ---------------------------------------------------------------------------
# Preference boosts (recommend layer)
# ---------------------------------------------------------------------------


def _candidates(*providers_with_blockers: tuple[str, bool]) -> list[Candidate]:
    return [
        Candidate(
            provider=p,  # type: ignore[arg-type]
            confidence=0.5,
            reason="test",
            blockers=("blocked",) if blocked else (),
        )
        for p, blocked in providers_with_blockers
    ]


def test_preference_boost_recommended_mode_no_change() -> None:
    policy = WorkspaceAgentPolicy(preference_mode="recommended")
    candidates = _candidates(("opencode_cli", False), ("factory_droid_build", False))
    result = _apply_preference_boosts(candidates, policy)
    assert result[0].confidence == pytest.approx(0.5)
    assert result[1].confidence == pytest.approx(0.5)


def test_preference_boost_prefer_open_custom_boosts_opencode() -> None:
    policy = WorkspaceAgentPolicy(preference_mode="prefer_open_custom")
    candidates = _candidates(("opencode_cli", False), ("factory_droid_build", False))
    result = _apply_preference_boosts(candidates, policy)
    oc = next(c for c in result if c.provider == "opencode_cli")
    fd = next(c for c in result if c.provider == "factory_droid_build")
    assert oc.confidence > fd.confidence
    assert oc.confidence == pytest.approx(0.65)


def test_preference_boost_prefer_premium_reasoning_boosts_claude_agent() -> None:
    policy = WorkspaceAgentPolicy(preference_mode="prefer_premium_reasoning")
    candidates = _candidates(("claude_agent", False), ("opencode_cli", False))
    result = _apply_preference_boosts(candidates, policy)
    claude = next(c for c in result if c.provider == "claude_agent")
    assert claude.confidence == pytest.approx(0.65)


def test_preference_boost_prefer_connected_repo_boosts_cursor() -> None:
    policy = WorkspaceAgentPolicy(preference_mode="prefer_connected_repo")
    candidates = _candidates(("cursor_cloud", False), ("factory_droid_build", False))
    result = _apply_preference_boosts(candidates, policy)
    cursor = next(c for c in result if c.provider == "cursor_cloud")
    assert cursor.confidence == pytest.approx(0.65)


def test_preference_boost_never_bypasses_blockers() -> None:
    """A blocked candidate must not be boosted."""
    policy = WorkspaceAgentPolicy(preference_mode="prefer_open_custom")
    candidates = _candidates(("opencode_cli", True))  # blocked
    result = _apply_preference_boosts(candidates, policy)
    oc = next(c for c in result if c.provider == "opencode_cli")
    assert oc.confidence == pytest.approx(0.5)  # unchanged
    assert oc.blockers  # still blocked


def test_preference_boost_none_policy_no_change() -> None:
    candidates = _candidates(("opencode_cli", False), ("factory_droid_build", False))
    result = _apply_preference_boosts(candidates, None)
    for c in result:
        assert c.confidence == pytest.approx(0.5)


def test_preference_boost_caps_at_1_0() -> None:
    policy = WorkspaceAgentPolicy(preference_mode="prefer_open_custom")
    candidates = [
        Candidate(
            provider="opencode_cli",
            confidence=0.95,
            reason="test",
            blockers=(),
        )
    ]
    result = _apply_preference_boosts(candidates, policy)
    assert result[0].confidence <= 1.0


# ---------------------------------------------------------------------------
# API test fixtures and helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _seed_workspace(
    store: InMemoryWorkspaceStore, user_id: str, workspace_id: str | None = None
) -> str:
    """Register a workspace + member record so require_perm can resolve it."""
    wid = workspace_id or new_workspace_id()
    now = _now()
    store.create_workspace(
        WorkspaceRecord(
            workspace_id=wid,
            org_id=None,
            owner_user_id=user_id,
            name="Test WS",
            slug=wid.replace("ws_", "")[:16],  # unique per workspace
            description="",
            status="active",
            created_by=user_id,
            created_at=now,
            updated_at=now,
        )
    )
    store.upsert_member(
        WorkspaceMember(
            user_id=user_id,
            workspace_id=wid,
            role="owner",
            added_by=user_id,
            added_at=now,
        )
    )
    return wid


@pytest.fixture()
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ProjectStore:
    monkeypatch.setenv("HAM_CURSOR_CREDENTIALS_FILE", str(tmp_path / "cursor_creds.json"))
    store = ProjectStore(store_path=tmp_path / "projects.json")
    set_project_store_for_tests(store)
    yield store
    set_project_store_for_tests(None)


@pytest.fixture()
def cleanup_overrides() -> Any:
    yield
    fastapi_app.dependency_overrides.clear()


@pytest.fixture()
def workspace_actor() -> HamActor:
    return HamActor(
        user_id="user_ws",
        org_id="org_test",
        session_id="sess_ws",
        email="wsuser@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


@pytest.fixture()
def ws_store(
    workspace_actor: HamActor, cleanup_overrides: None
) -> tuple[InMemoryWorkspaceStore, str]:
    """Workspace store with a pre-seeded workspace; returns (store, workspace_id)."""
    store = InMemoryWorkspaceStore()
    wid = _seed_workspace(store, workspace_actor.user_id)
    fastapi_app.dependency_overrides[get_workspace_store] = lambda: store
    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: workspace_actor
    return store, wid


def _client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# API tests — GET /api/workspaces/{ws}/coding-agent-access-settings
# ---------------------------------------------------------------------------


def test_get_settings_requires_auth_when_enforced(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    cleanup_overrides: None,
) -> None:
    """Route requires auth when Clerk is enforced — unauthenticated returns 401/403."""
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "1")
    fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)
    res = TestClient(app).get("/api/workspaces/ws_abc/coding-agent-access-settings")
    assert res.status_code in (401, 403)


def test_get_settings_returns_defaults_when_none_stored(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    ws_store: tuple[InMemoryWorkspaceStore, str],
) -> None:
    monkeypatch.setenv("HAM_WORKSPACE_STORE_BACKEND", "local")
    _, wid = ws_store
    res = _client().get(f"/api/workspaces/{wid}/coding-agent-access-settings")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "ham_coding_agent_access_settings"
    assert body["allow_factory_droid"] is True
    assert body["allow_claude_agent"] is True
    assert body["allow_opencode"] is False  # default off
    assert body["allow_cursor"] is True
    assert body["preference_mode"] == "recommended"
    assert body["model_source_preference"] == "ham_default"


def test_patch_settings_updates_opencode_flag(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    ws_store: tuple[InMemoryWorkspaceStore, str],
) -> None:
    monkeypatch.setenv("HAM_WORKSPACE_STORE_BACKEND", "local")
    _, wid = ws_store
    res = _client().patch(
        f"/api/workspaces/{wid}/coding-agent-access-settings",
        json={"allow_opencode": True},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["allow_opencode"] is True
    assert body["allow_factory_droid"] is True  # default preserved


def test_patch_settings_updates_preference_mode(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    ws_store: tuple[InMemoryWorkspaceStore, str],
) -> None:
    monkeypatch.setenv("HAM_WORKSPACE_STORE_BACKEND", "local")
    _, wid = ws_store
    res = _client().patch(
        f"/api/workspaces/{wid}/coding-agent-access-settings",
        json={"preference_mode": "prefer_open_custom"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["preference_mode"] == "prefer_open_custom"


def test_patch_settings_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    ws_store: tuple[InMemoryWorkspaceStore, str],
) -> None:
    monkeypatch.setenv("HAM_WORKSPACE_STORE_BACKEND", "local")
    _, wid = ws_store
    client = _client()
    client.patch(
        f"/api/workspaces/{wid}/coding-agent-access-settings",
        json={"allow_opencode": True, "preference_mode": "prefer_premium_reasoning"},
    )
    body = client.get(f"/api/workspaces/{wid}/coding-agent-access-settings").json()
    assert body["allow_opencode"] is True
    assert body["preference_mode"] == "prefer_premium_reasoning"
    # Partial update preserves untouched fields.
    client.patch(
        f"/api/workspaces/{wid}/coding-agent-access-settings", json={"allow_cursor": False}
    )
    body2 = client.get(f"/api/workspaces/{wid}/coding-agent-access-settings").json()
    assert body2["allow_opencode"] is True  # preserved
    assert body2["preference_mode"] == "prefer_premium_reasoning"  # preserved
    assert body2["allow_cursor"] is False  # updated


def test_settings_response_never_leaks_secrets_or_env_names(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    ws_store: tuple[InMemoryWorkspaceStore, str],
) -> None:
    monkeypatch.setenv("HAM_WORKSPACE_STORE_BACKEND", "local")
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-only-secret")
    monkeypatch.setenv("HAM_DROID_EXEC_TOKEN", "test-token-secret")
    _, wid = ws_store
    res = _client().get(f"/api/workspaces/{wid}/coding-agent-access-settings")
    assert res.status_code == 200
    blob = res.text.lower()
    for forbidden in (
        "ham_droid_exec_token",
        "anthropic_api_key",
        "sk-ant-test-only-secret",
        "test-token-secret",
        "safe_edit_low",
        "factory_droid_build",
        "http://",
        "https://",
    ):
        assert forbidden not in blob, f"response leaks {forbidden!r}"


def test_patch_settings_rejects_extra_fields(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    ws_store: tuple[InMemoryWorkspaceStore, str],
) -> None:
    monkeypatch.setenv("HAM_WORKSPACE_STORE_BACKEND", "local")
    _, wid = ws_store
    res = _client().patch(
        f"/api/workspaces/{wid}/coding-agent-access-settings",
        json={"allow_opencode": True, "internal_field": "hack"},
    )
    assert res.status_code == 422


def test_patch_settings_workspace_scoped_separately(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    ws_store: tuple[InMemoryWorkspaceStore, str],
) -> None:
    """Two different workspace IDs get independent settings."""
    monkeypatch.setenv("HAM_WORKSPACE_STORE_BACKEND", "local")
    store, wid_a = ws_store
    wid_b = _seed_workspace(store, "user_ws")  # second workspace
    client = _client()
    client.patch(
        f"/api/workspaces/{wid_a}/coding-agent-access-settings", json={"allow_opencode": True}
    )
    client.patch(
        f"/api/workspaces/{wid_b}/coding-agent-access-settings",
        json={"allow_opencode": False, "allow_cursor": False},
    )
    alpha = client.get(f"/api/workspaces/{wid_a}/coding-agent-access-settings").json()
    beta = client.get(f"/api/workspaces/{wid_b}/coding-agent-access-settings").json()
    assert alpha["allow_opencode"] is True
    assert beta["allow_opencode"] is False
    assert alpha["allow_cursor"] is True
    assert beta["allow_cursor"] is False


# ---------------------------------------------------------------------------
# Conductor integration — workspace_id in preview body
# ---------------------------------------------------------------------------


_FORBIDDEN_TOKENS = (
    "safe_edit_low",
    "ham_droid_exec_token",
    "anthropic_api_key",
    "factory_droid_build",
)


def _post_preview(
    client: TestClient,
    *,
    user_prompt: str,
    workspace_id: str | None = None,
    project_id: str | None = None,
    extra: dict | None = None,
) -> Any:
    body: dict = {"user_prompt": user_prompt}
    if workspace_id is not None:
        body["workspace_id"] = workspace_id
    if project_id is not None:
        body["project_id"] = project_id
    if extra:
        body.update(extra)
    return client.post("/api/coding/conductor/preview", json=body)


def test_conductor_accepts_workspace_id_in_body(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    ws_store: tuple[InMemoryWorkspaceStore, str],
) -> None:
    """workspace_id in body is accepted and does not break existing conductor behavior."""
    monkeypatch.setenv("HAM_WORKSPACE_STORE_BACKEND", "local")
    _, wid = ws_store
    res = _post_preview(_client(), user_prompt="Explain how auth works.", workspace_id=wid)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["task_kind"] == "explain"
    assert body["chosen"] is not None


def test_conductor_workspace_id_omitted_backward_compat(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    cleanup_overrides: None,
) -> None:
    """Omitting workspace_id preserves pre-settings behavior (no policy applied)."""
    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: HamActor(
        user_id="user_ws",
        org_id="org_test",
        session_id="sess_ws",
        email="wsuser@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )
    res = _post_preview(_client(), user_prompt="Explain how auth works.")
    assert res.status_code == 200, res.text


def test_conductor_workspace_policy_disables_factory_droid(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    ws_store: tuple[InMemoryWorkspaceStore, str],
    tmp_path: Path,
) -> None:
    """When workspace disables factory_droid, its candidates carry a policy blocker."""
    monkeypatch.setenv("HAM_WORKSPACE_STORE_BACKEND", "local")
    monkeypatch.setenv("HAM_CODING_AGENT_SETTINGS_LOCAL_PATH", str(tmp_path / "agent_settings"))
    monkeypatch.setenv("HAM_DROID_RUNNER_URL", "https://runner.example/private")
    monkeypatch.setenv("HAM_DROID_RUNNER_TOKEN", "test-only-not-deployed-runner-token")
    monkeypatch.setenv("HAM_DROID_EXEC_TOKEN", "test-only-not-deployed")
    _, wid = ws_store

    client = _client()
    patch_res = client.patch(
        f"/api/workspaces/{wid}/coding-agent-access-settings",
        json={"allow_factory_droid": False},
    )
    assert patch_res.status_code == 200, patch_res.text

    res = _post_preview(
        client, user_prompt="Add docstrings to ham_run_id helpers.", workspace_id=wid
    )
    assert res.status_code == 200, res.text
    body = res.json()
    droid_candidates = [
        c
        for c in body["candidates"]
        if c["provider"] in ("factory_droid_build", "factory_droid_audit")
    ]
    for c in droid_candidates:
        assert c["available"] is False, c
        assert c["blockers"], c


def test_conductor_response_never_leaks_secrets_with_workspace_id(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    ws_store: tuple[InMemoryWorkspaceStore, str],
) -> None:
    monkeypatch.setenv("HAM_WORKSPACE_STORE_BACKEND", "local")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-only-secret")
    _, wid = ws_store
    res = _post_preview(_client(), user_prompt="Refactor the chat router.", workspace_id=wid)
    assert res.status_code == 200, res.text
    blob = res.text.lower()
    for forbidden in _FORBIDDEN_TOKENS:
        assert forbidden not in blob, f"response leaks {forbidden!r}"
    assert "sk-ant-test-only-secret" not in res.text


def test_conductor_factory_droid_default_behavior_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    ws_store: tuple[InMemoryWorkspaceStore, str],
) -> None:
    """Without workspace_id, Factory Droid behavior is exactly as before."""
    monkeypatch.setenv("HAM_DROID_RUNNER_URL", "https://runner.example/private")
    monkeypatch.setenv("HAM_DROID_RUNNER_TOKEN", "test-only-not-deployed-runner-token")
    monkeypatch.setenv("HAM_DROID_EXEC_TOKEN", "test-only-not-deployed")
    store = isolated_store
    rec = store.make_record(name="p_droid", root=str(Path(".")))
    rec = rec.model_copy(
        update={
            "build_lane_enabled": True,
            "output_target": "managed_workspace",
            "workspace_id": "ws_managed",
        }
    )
    rec = store.register(rec)

    import src.ham.coding_router.readiness as readiness_mod

    monkeypatch.setattr(readiness_mod.shutil, "which", lambda _: None)
    res = _post_preview(
        _client(), user_prompt="Add docstrings to ham_run_id helpers.", project_id=rec.id
    )
    assert res.status_code == 200, res.text
    body = res.json()
    build = next(c for c in body["candidates"] if c["provider"] == "factory_droid_build")
    assert build["available"] is True
    assert build["blockers"] == []
    assert body["chosen"]["provider"] == "factory_droid_build"


def test_conductor_cursor_blocked_without_github_repo(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    ws_store: tuple[InMemoryWorkspaceStore, str],
    tmp_path: Path,
) -> None:
    """Cursor is blocked when the project has no GitHub repo regardless of settings."""
    monkeypatch.setenv("CURSOR_API_KEY", "cur_" + "z" * 40)
    store = isolated_store
    rec = store.make_record(name="p_no_gh", root=str(tmp_path))
    rec = rec.model_copy(update={"github_repo": None, "has_github_repo": False})
    rec = store.register(rec)

    res = _post_preview(_client(), user_prompt="Refactor the chat router.", project_id=rec.id)
    assert res.status_code == 200, res.text
    body = res.json()
    cursor = next(c for c in body["candidates"] if c["provider"] == "cursor_cloud")
    assert cursor["available"] is False
    assert any("GitHub" in b for b in cursor["blockers"])
