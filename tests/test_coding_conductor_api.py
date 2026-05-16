"""
Tests for ``POST /api/coding/conductor/preview``.

The conductor classifies + recommends; it never launches. These tests lock:

- Body validation and Clerk gate.
- Each task-kind → expected provider mapping under realistic readiness.
- Build candidate stays blocked when project policy / host policy are not
  satisfied; blocker copy is normie-safe (no env names, runner URLs,
  internal workflow ids).
- Response body never echoes ``safe_edit_low``, ``readonly_repo_audit``,
  ``low_edit``, ``--auto low``, argv, runner URLs, secret values, or env
  name strings (``HAM_DROID_EXEC_TOKEN``, ``CURSOR_API_KEY``,
  ``ANTHROPIC_API_KEY``).
- No launch route is mounted under ``/api/coding/`` in this PR.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.server import app, fastapi_app
from src.ham.clerk_auth import HamActor
from src.persistence.project_store import (
    ProjectStore,
    set_project_store_for_tests,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every provider env var so each test starts from a known posture."""
    for name in (
        "HAM_DROID_RUNNER_URL",
        "HAM_DROID_RUNNER_TOKEN",
        "HAM_DROID_EXEC_TOKEN",
        "CURSOR_API_KEY",
        "HAM_CURSOR_CREDENTIALS_FILE",
        "ANTHROPIC_API_KEY",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "ANTHROPIC_VERTEX_PROJECT_ID",
        "GCLOUD_PROJECT",
        "GOOGLE_CLOUD_PROJECT",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _block_droid_local_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default posture: no local droid binary, so audit/build need explicit env to be ready."""
    import src.ham.coding_router.readiness as readiness_mod

    monkeypatch.setattr(readiness_mod.shutil, "which", lambda _: None)


@pytest.fixture
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ProjectStore:
    monkeypatch.setenv("HAM_CURSOR_CREDENTIALS_FILE", str(tmp_path / "cursor_creds.json"))
    store = ProjectStore(store_path=tmp_path / "projects.json")
    set_project_store_for_tests(store)
    yield store
    set_project_store_for_tests(None)


@pytest.fixture
def cleanup_overrides() -> Any:
    yield
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def operator_actor() -> HamActor:
    return HamActor(
        user_id="user_op",
        org_id=None,
        session_id="sess_o",
        email="operator@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


@pytest.fixture
def normie_actor() -> HamActor:
    return HamActor(
        user_id="user_normie",
        org_id=None,
        session_id="sess_n",
        email="normie@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _client(actor: HamActor | None) -> TestClient:
    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: actor
    return TestClient(app)


def _make_build_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_URL", "https://runner.example/private")
    monkeypatch.setenv("HAM_DROID_RUNNER_TOKEN", "test-only-not-deployed-runner-token")
    monkeypatch.setenv("HAM_DROID_EXEC_TOKEN", "test-only-not-deployed")


def _make_audit_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_URL", "https://runner.example/private")
    monkeypatch.setenv("HAM_DROID_RUNNER_TOKEN", "test-only-not-deployed-runner-token")


def _make_cursor_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "cur_" + "z" * 40)


def _register_project(
    store: ProjectStore,
    *,
    name: str,
    root: Path,
    build_lane_enabled: bool = False,
    github_repo: str | None = None,
    output_target: str = "github_pr",
    workspace_id: str | None = None,
) -> Any:
    rec = store.make_record(name=name, root=str(root))
    rec = rec.model_copy(
        update={
            "build_lane_enabled": build_lane_enabled,
            "github_repo": github_repo,
            "output_target": output_target,
            "workspace_id": workspace_id,
        }
    )
    return store.register(rec)


_FORBIDDEN_TOKENS = (
    "safe_edit_low",
    "readonly_repo_audit",
    "low_edit",
    "--auto low",
    "ham_droid_exec_token",
    "ham_droid_runner_url",
    "ham_droid_runner_token",
    "anthropic_api_key",
    "cursor_api_key",
    "argv",
    "droid exec",
    "http://",
    "https://",
)


def _assert_no_secret_leakage(text: str) -> None:
    blob = text.lower()
    for forbidden in _FORBIDDEN_TOKENS:
        assert forbidden not in blob, f"response leaks {forbidden!r}: {blob}"


def _post(
    client: TestClient,
    *,
    user_prompt: str,
    project_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Any:
    body: dict[str, Any] = {"user_prompt": user_prompt}
    if project_id is not None:
        body["project_id"] = project_id
    if extra:
        body.update(extra)
    return client.post("/api/coding/conductor/preview", json=body)


# ---------------------------------------------------------------------------
# Body validation + Clerk gate
# ---------------------------------------------------------------------------


def test_preview_requires_clerk_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch, isolated_store: ProjectStore
) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "1")
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
    fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)
    res = TestClient(app).post(
        "/api/coding/conductor/preview", json={"user_prompt": "explain things"}
    )
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"


def test_preview_rejects_extra_fields(
    isolated_store: ProjectStore, normie_actor: HamActor, cleanup_overrides: None
) -> None:
    res = _client(normie_actor).post(
        "/api/coding/conductor/preview",
        json={
            "user_prompt": "explain auth flow",
            "workflow_id": "safe_edit_low",
        },
    )
    assert res.status_code == 422


def test_preview_rejects_empty_prompt(
    isolated_store: ProjectStore, normie_actor: HamActor, cleanup_overrides: None
) -> None:
    res = _client(normie_actor).post("/api/coding/conductor/preview", json={"user_prompt": ""})
    assert res.status_code == 422


def test_preview_unknown_project_returns_structured_blocker(
    isolated_store: ProjectStore, normie_actor: HamActor, cleanup_overrides: None
) -> None:
    res = _post(
        _client(normie_actor),
        user_prompt="audit security",
        project_id="project.unknown",
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["project"]["found"] is False
    assert any("Unknown project_id" in b for b in body["blockers"])


# ---------------------------------------------------------------------------
# Task-kind happy paths
# ---------------------------------------------------------------------------


def test_preview_explain_recommends_no_agent(
    isolated_store: ProjectStore, normie_actor: HamActor, cleanup_overrides: None
) -> None:
    res = _post(_client(normie_actor), user_prompt="Explain how the audit lane works.")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "coding_conductor_preview"
    assert body["task_kind"] == "explain"
    assert body["chosen"] is not None
    assert body["chosen"]["provider"] == "no_agent"
    assert body["chosen"]["output_kind"] == "answer"
    assert body["chosen"]["will_modify_code"] is False
    assert body["approval_kind"] == "none"


def test_preview_audit_recommends_factory_droid_audit_when_ready(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    _make_audit_ready(monkeypatch)
    rec = _register_project(isolated_store, name="p_audit", root=tmp_path)
    res = _post(
        _client(normie_actor),
        user_prompt="Audit the persistence layer.",
        project_id=rec.id,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["task_kind"] == "audit"
    assert body["chosen"] is not None
    assert body["chosen"]["provider"] == "factory_droid_audit"
    assert body["chosen"]["output_kind"] == "report"
    assert body["chosen"]["will_modify_code"] is False
    assert body["chosen"]["will_open_pull_request"] is False
    assert body["approval_kind"] == "confirm"


def test_preview_typo_recommends_factory_droid_build_only_when_ready(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    _make_build_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_build",
        root=tmp_path,
        build_lane_enabled=True,
        github_repo="Code-Munkiz/ham",
    )
    res = _post(
        _client(normie_actor),
        user_prompt="Fix typos in the README.",
        project_id=rec.id,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["task_kind"] == "typo_only"
    assert body["chosen"] is not None
    assert body["chosen"]["provider"] == "factory_droid_build"
    assert body["chosen"]["output_kind"] == "pull_request"
    assert body["chosen"]["will_modify_code"] is True
    assert body["chosen"]["will_open_pull_request"] is True
    assert body["chosen"]["requires_operator"] is True
    assert body["approval_kind"] == "confirm_and_accept_pr"
    # The user-facing label / reason never names the internal workflow.
    assert "safe_edit_low" not in body["chosen"]["label"].lower()
    assert "safe_edit_low" not in body["chosen"]["reason"].lower()


def test_preview_refactor_recommends_cursor_when_ready(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    _make_cursor_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_cursor",
        root=tmp_path,
        github_repo="Code-Munkiz/ham",
    )
    res = _post(
        _client(normie_actor),
        user_prompt="Refactor the chat router for clarity.",
        project_id=rec.id,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["task_kind"] == "refactor"
    assert body["chosen"] is not None
    assert body["chosen"]["provider"] == "cursor_cloud"
    assert body["chosen"]["will_open_pull_request"] is True
    assert body["approval_kind"] == "confirm"


# ---------------------------------------------------------------------------
# Build blockers (project + host) — locked separately from the recommender
# ---------------------------------------------------------------------------


def test_preview_build_blocked_when_project_lane_disabled(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    _make_build_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_disabled",
        root=tmp_path,
        build_lane_enabled=False,  # <-- key
        github_repo="Code-Munkiz/ham",
    )
    res = _post(
        _client(normie_actor),
        user_prompt="Add docstrings to ham_run_id helpers.",
        project_id=rec.id,
    )
    assert res.status_code == 200
    body = res.json()
    build = next(c for c in body["candidates"] if c["provider"] == "factory_droid_build")
    assert build["available"] is False
    assert any("Build lane is disabled for this project" in b for b in build["blockers"])
    # Chosen falls back to no_agent (or another approve-able candidate).
    assert body["chosen"] is None or body["chosen"]["provider"] != "factory_droid_build"


def test_preview_build_blocked_when_github_repo_missing(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    _make_build_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_norepo",
        root=tmp_path,
        build_lane_enabled=True,
        github_repo=None,  # <-- key
    )
    res = _post(
        _client(normie_actor),
        user_prompt="Tidy README documentation.",
        project_id=rec.id,
    )
    assert res.status_code == 200
    body = res.json()
    build = next(c for c in body["candidates"] if c["provider"] == "factory_droid_build")
    assert build["available"] is False
    assert any("GitHub repository" in b for b in build["blockers"])


def test_preview_build_blocked_when_host_token_absent_no_env_name_leakage(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    """Host-side mutation gate missing → blocked, but copy must NOT name the env var."""
    # Audit-ready (runner reachable) but no HAM_DROID_EXEC_TOKEN.
    _make_audit_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_host_block",
        root=tmp_path,
        build_lane_enabled=True,
        github_repo="Code-Munkiz/ham",
    )
    res = _post(
        _client(normie_actor),
        user_prompt="Tidy README documentation.",
        project_id=rec.id,
    )
    assert res.status_code == 200
    body = res.json()
    build = next(c for c in body["candidates"] if c["provider"] == "factory_droid_build")
    assert build["available"] is False
    assert any("build lane is not configured on this host" in b.lower() for b in build["blockers"])
    # Sanitisation: blocker copy never mentions the env var name.
    for b in build["blockers"]:
        assert "HAM_DROID_EXEC_TOKEN" not in b
        assert "safe_edit_low" not in b


# ---------------------------------------------------------------------------
# Unknown task kind safety
# ---------------------------------------------------------------------------


def test_preview_unknown_does_not_recommend_mutating_provider(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    """Even with every provider 'ready', unknown tasks must not pick a mutating provider."""
    _make_build_ready(monkeypatch)
    _make_cursor_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_unknown",
        root=tmp_path,
        build_lane_enabled=True,
        github_repo="Code-Munkiz/ham",
    )
    res = _post(
        _client(normie_actor),
        user_prompt="hello there how are you",
        project_id=rec.id,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["task_kind"] == "unknown"
    if body["chosen"] is not None:
        assert body["chosen"]["will_modify_code"] is False
    # Recommendation reason offers a path forward without claiming a mutating pick.
    rr = body["recommendation_reason"].lower()
    assert "not sure" in rr or "pick" in rr or "no coding agent" in rr


# ---------------------------------------------------------------------------
# Sanitisation locks
# ---------------------------------------------------------------------------


def test_preview_response_never_leaks_secrets_or_internals(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    """A maximally-configured host must still never echo internals in the response."""
    _make_build_ready(monkeypatch)
    _make_cursor_ready(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-only")
    rec = _register_project(
        isolated_store,
        name="p_sanitise",
        root=tmp_path,
        build_lane_enabled=True,
        github_repo="Code-Munkiz/ham",
    )
    for prompt in (
        "Explain auth flow.",
        "Audit the API.",
        "Fix typos in the README.",
        "Refactor the chat router.",
        "Implement a /api/whatever endpoint",
        "tweak this file's import order",
        "hello",
    ):
        res = _post(_client(normie_actor), user_prompt=prompt, project_id=rec.id)
        assert res.status_code == 200, res.text
        _assert_no_secret_leakage(res.text)
        # Specific value checks for defence in depth.
        blob = res.text.lower()
        assert "test-only-not-deployed" not in blob
        assert "sk-ant-test-only" not in blob
        assert "cur_" + "z" * 40 not in blob
        assert "runner.example/private" not in blob
        # And the github_repo string itself never appears.
        assert "code-munkiz/ham" not in blob


def test_preview_does_not_expose_internal_workflow_ids(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    _make_build_ready(monkeypatch)
    _make_audit_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_workflow_ids",
        root=tmp_path,
        build_lane_enabled=True,
        github_repo="Code-Munkiz/ham",
    )
    for prompt in ("Audit the API.", "Fix typos in README.", "Refactor chat router."):
        res = _post(_client(normie_actor), user_prompt=prompt, project_id=rec.id)
        assert res.status_code == 200
        blob = res.text.lower()
        assert "safe_edit_low" not in blob
        assert "readonly_repo_audit" not in blob
        assert "low_edit" not in blob


# ---------------------------------------------------------------------------
# Operator / non-operator
# ---------------------------------------------------------------------------


def test_non_operator_response_omits_operator_signals(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HAM_WORKSPACE_OPERATOR_EMAILS", "operator@example.test")
    res = _post(_client(normie_actor), user_prompt="Explain auth flow.")
    assert res.status_code == 200
    body = res.json()
    assert body["is_operator"] is False
    # Conductor candidates do not surface operator_signals at all.
    for c in body["candidates"]:
        assert "operator_signals" not in c


def test_operator_response_keeps_redaction_for_secret_values(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    operator_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HAM_WORKSPACE_OPERATOR_EMAILS", "operator@example.test")
    _make_build_ready(monkeypatch)
    _make_cursor_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_op_sanitise",
        root=tmp_path,
        build_lane_enabled=True,
        github_repo="Code-Munkiz/ham",
    )
    res = _post(_client(operator_actor), user_prompt="Audit the API.", project_id=rec.id)
    assert res.status_code == 200
    body = res.json()
    assert body["is_operator"] is True
    _assert_no_secret_leakage(res.text)


# ---------------------------------------------------------------------------
# preferred_provider handling (forward-compat; never bypasses blockers)
# ---------------------------------------------------------------------------


def test_preferred_provider_promotes_when_approveable(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    """When preferred_provider is approve-able, it ranks first; never bypasses blockers."""
    _make_audit_ready(monkeypatch)
    _make_cursor_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_prefer",
        root=tmp_path,
        github_repo="Code-Munkiz/ham",
    )
    # Refactor task: cursor_cloud is the natural pick. Prefer no_agent
    # explicitly; expect it to be promoted and chosen since no_agent is
    # always approve-able.
    res = _post(
        _client(normie_actor),
        user_prompt="Refactor the chat router.",
        project_id=rec.id,
        extra={"preferred_provider": "no_agent"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["candidates"][0]["provider"] == "no_agent"
    assert body["chosen"] is not None
    assert body["chosen"]["provider"] == "no_agent"


def test_preferred_provider_does_not_bypass_blockers(
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    """preferred_provider for a blocked candidate is ignored; chosen stays approve-able."""
    rec = _register_project(
        isolated_store,
        name="p_no_force",
        root=tmp_path,
        build_lane_enabled=False,
        github_repo=None,
    )
    res = _post(
        _client(normie_actor),
        user_prompt="Add docstrings to helpers.",
        project_id=rec.id,
        extra={"preferred_provider": "factory_droid_build"},
    )
    assert res.status_code == 200
    body = res.json()
    if body["chosen"] is not None:
        assert body["chosen"]["provider"] != "factory_droid_build"
    build = next(c for c in body["candidates"] if c["provider"] == "factory_droid_build")
    assert build["available"] is False
    assert build["blockers"]


# ---------------------------------------------------------------------------
# Managed-workspace smoke prompt (regression: routed to no_agent before this fix)
# ---------------------------------------------------------------------------


_MANAGED_SMOKE_PROMPT = (
    "Smoke test only. Make a tiny documentation/comment-only change in the "
    "managed workspace and create a managed snapshot. Do not change behavior, "
    "dependencies, secrets, CI, or configuration."
)


def test_preview_managed_smoke_prompt_recommends_factory_droid_build_when_ready(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    """The verbatim live-chat smoke prompt that previously fell through to
    ``no_agent`` / ``unknown`` must now route to ``factory_droid_build``
    for a fully-ready managed_workspace project.

    Regression captured: the legacy classifier required precise
    ``(verb, comments|docstrings)`` proximity; the user's natural-language
    "documentation/comment-only" did not match. Fix added hyphenated
    "-only" and slash-combined shapes plus a "managed snapshot" hint."""
    _make_build_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_managed_smoke",
        root=tmp_path,
        build_lane_enabled=True,
        output_target="managed_workspace",
        workspace_id="ws_managed_smoke",
    )
    res = _post(_client(normie_actor), user_prompt=_MANAGED_SMOKE_PROMPT, project_id=rec.id)
    assert res.status_code == 200, res.text
    body = res.json()

    # Routing lock.
    assert body["task_kind"] == "comments_only", body
    assert body["chosen"] is not None, body
    assert body["chosen"]["provider"] == "factory_droid_build", body
    # Managed-workspace target: no PR, no operator-only confirmation.
    assert body["chosen"]["will_modify_code"] is True
    assert body["chosen"]["will_open_pull_request"] is False
    assert body["chosen"]["requires_operator"] is False
    assert body["chosen"]["requires_confirmation"] is True
    # Approve-able: no blockers on the chosen candidate.
    assert body["chosen"]["available"] is True
    assert body["chosen"]["blockers"] == []
    # Approval contract: explicit accept required (PR #265 panel reads this).
    assert body["approval_kind"] == "confirm_and_accept_pr"
    # NOT a fallback any more.
    assert body["task_kind"] != "unknown"
    assert body["chosen"]["provider"] != "no_agent"
    # Recommendation reason does not claim conversational fallback.
    assert "conversational" not in body["recommendation_reason"].lower()

    # Sanitisation: no secret values, env names, workflow ids, or runner internals.
    _assert_no_secret_leakage(res.text)


def test_preview_managed_smoke_prompt_shows_safe_blockers_when_workspace_missing(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    """If the project has output_target=managed_workspace but no workspace_id,
    the build candidate must surface a friendly blocker instead of falling
    back to a conversational answer."""
    _make_build_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_managed_no_ws",
        root=tmp_path,
        build_lane_enabled=True,
        output_target="managed_workspace",
        workspace_id=None,
    )
    res = _post(_client(normie_actor), user_prompt=_MANAGED_SMOKE_PROMPT, project_id=rec.id)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["task_kind"] == "comments_only"
    build = next(c for c in body["candidates"] if c["provider"] == "factory_droid_build")
    assert build["available"] is False
    assert any("managed workspace" in b.lower() for b in build["blockers"])
    # Blocker copy never names the env var, the workflow id, or the token.
    for b in build["blockers"]:
        assert "HAM_DROID_EXEC_TOKEN" not in b
        assert "safe_edit_low" not in b
        assert "argv" not in b.lower()


def test_preview_managed_smoke_prompt_with_no_project_blocks_safely(
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    cleanup_overrides: None,
) -> None:
    """When project_id is omitted, factory_droid_build is blocked with
    'Pick a project...' — not silently demoted to no_agent / conversational."""
    res = _post(_client(normie_actor), user_prompt=_MANAGED_SMOKE_PROMPT)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["task_kind"] == "comments_only"
    build = next(c for c in body["candidates"] if c["provider"] == "factory_droid_build")
    assert build["available"] is False
    assert any("pick a project" in b.lower() for b in build["blockers"])
    _assert_no_secret_leakage(res.text)


# ---------------------------------------------------------------------------
# Diagnostic log shape (Cloud Run-observable; no secrets, no env names, no
# workflow ids, no provider internals).
# ---------------------------------------------------------------------------


def test_preview_emits_diagnostic_info_log_with_safe_shape(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Each preview emits one INFO line so operators can observe the decision
    shape from Cloud Run logs without inspecting response bodies.

    The line MUST include ``task_kind``, ``chosen_provider``, ``approval_kind``,
    project flags, and a blocker count; it MUST NOT include any prompt text,
    secret value, env name, workflow id, runner URL, or argv string.
    """
    _make_build_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_diag_log",
        root=tmp_path,
        build_lane_enabled=True,
        output_target="managed_workspace",
        workspace_id="ws_diag_log",
    )
    with caplog.at_level("INFO", logger="src.api.coding_conductor"):
        res = _post(_client(normie_actor), user_prompt=_MANAGED_SMOKE_PROMPT, project_id=rec.id)
    assert res.status_code == 200, res.text

    diag_records = [r for r in caplog.records if "coding_conductor_preview" in r.getMessage()]
    assert len(diag_records) == 1, (
        f"expected exactly one diagnostic line, got {len(diag_records)}: "
        f"{[r.getMessage() for r in diag_records]}"
    )
    msg = diag_records[0].getMessage()
    # Decision-shape fields are present and human-grep-able.
    for token in (
        "task_kind=comments_only",
        "chosen_provider=factory_droid_build",
        "chosen_available=True",
        "chosen_blocker_count=0",
        "approval_kind=confirm_and_accept_pr",
        "output_target=managed_workspace",
        "has_workspace_id=True",
        "build_lane_enabled=True",
        "project_found=True",
        "requires_approval=True",
    ):
        assert token in msg, f"diagnostic line missing {token!r}: {msg}"
    # Forbidden tokens: anything that would leak prompt text, secrets, env
    # names, workflow ids, runner internals, or auth headers.
    forbidden_in_log = (
        "Smoke test only",
        "documentation/comment",
        "managed snapshot.",
        "HAM_DROID_EXEC_TOKEN",
        "HAM_DROID_RUNNER_URL",
        "HAM_DROID_RUNNER_TOKEN",
        "CURSOR_API_KEY",
        "ANTHROPIC_API_KEY",
        "safe_edit_low",
        "readonly_repo_audit",
        "--auto low",
        "argv",
        "http://",
        "https://",
        "Bearer ",
        "test-only-not-deployed",
        "ws_diag_log",
        "p_diag_log",
        "user_prompt=",
        "preview_id=",
    )
    for token in forbidden_in_log:
        assert token not in msg, f"diagnostic line leaks {token!r}: {msg}"


def test_preview_diagnostic_log_for_no_agent_fallback_is_redacted(
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    cleanup_overrides: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When no project_id is supplied and host is empty, the diagnostic line
    must still emit and must still be free of any sensitive content."""
    with caplog.at_level("INFO", logger="src.api.coding_conductor"):
        res = _post(_client(normie_actor), user_prompt="hello there")
    assert res.status_code == 200
    diag_records = [r for r in caplog.records if "coding_conductor_preview" in r.getMessage()]
    assert len(diag_records) == 1
    msg = diag_records[0].getMessage()
    assert "project_found=False" in msg
    assert "project_id_present=False" in msg
    assert "chosen_provider" in msg
    # Free-text prompt content never appears in the log line.
    assert "hello there" not in msg


# ---------------------------------------------------------------------------
# Route inventory lock
# ---------------------------------------------------------------------------


def test_no_launch_endpoint_under_coding_namespace() -> None:
    """Lock: no /api/coding/conductor/launch (or /dispatch / /run) route exists."""
    routes = {
        (r.path, tuple(sorted(r.methods or ())))
        for r in fastapi_app.routes
        if hasattr(r, "path") and "/api/coding" in getattr(r, "path", "")
    }
    paths = {p for p, _ in routes}
    assert "/api/coding/readiness" in paths
    assert "/api/coding/conductor/preview" in paths
    # Negative locks: no conductor launch / dispatch / run / execute under
    # /api/coding. The /api/coding/* namespace is for read/discovery
    # routes (preview, readiness, conductor) only; launches live under
    # /api/{provider}/build/* (e.g. /api/opencode/build/launch_proxy).
    for p in paths:
        assert "/launch" not in p, f"unexpected launch route: {p}"
        assert "/dispatch" not in p, f"unexpected dispatch route: {p}"
        assert "/execute" not in p, f"unexpected execute route: {p}"
        for _, methods in routes:
            for m in methods:
                assert m in ("GET", "POST", "HEAD"), f"unexpected verb {m} on {p}"


# ---------------------------------------------------------------------------
# OpenCode lane in conductor preview
# ---------------------------------------------------------------------------


def _make_opencode_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure env + adapter so opencode_cli readiness reports available."""
    from src.ham.worker_adapters import opencode_adapter as _opencode_adapter

    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", "test-opencode-exec-token")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-opencode-canary")
    monkeypatch.setattr(
        _opencode_adapter.shutil,
        "which",
        lambda name: "/usr/local/bin/opencode" if name == "opencode" else None,
    )
    _opencode_adapter.reset_opencode_readiness_cache()


def test_preview_managed_workspace_feature_includes_opencode_candidate_when_ready(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    _make_build_ready(monkeypatch)
    _make_opencode_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_opencode_feature",
        root=tmp_path,
        build_lane_enabled=True,
        output_target="managed_workspace",
        workspace_id="ws_opencode_a",
    )
    # Use a comments_only task so factory_droid_build is in the table
    # alongside opencode_cli; the plan locks that Droid stays chosen here.
    res = _post(
        _client(normie_actor),
        user_prompt="Add docstrings to ham_run_id helpers.",
        project_id=rec.id,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    providers = {c["provider"] for c in body["candidates"]}
    assert "opencode_cli" in providers
    assert "factory_droid_build" in providers
    oc = next(c for c in body["candidates"] if c["provider"] == "opencode_cli")
    assert oc["available"] is True
    assert oc["blockers"] == []
    assert oc["will_open_pull_request"] is False
    # Chosen stays factory_droid_build (Droid-first ranking policy).
    assert body["chosen"] is not None
    assert body["chosen"]["provider"] == "factory_droid_build"


def test_preview_opencode_blocked_when_output_target_github_pr(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    """output_target=github_pr → opencode_cli appears as blocked candidate, not absent."""
    _make_opencode_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_opencode_github",
        root=tmp_path,
        build_lane_enabled=True,
        github_repo="Code-Munkiz/ham",
        output_target="github_pr",
    )
    res = _post(
        _client(normie_actor),
        user_prompt="Build a new feature for the chat panel.",
        project_id=rec.id,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    oc = next((c for c in body["candidates"] if c["provider"] == "opencode_cli"), None)
    assert oc is not None, "opencode_cli must appear as a blocked candidate, not be absent"
    assert oc["available"] is False
    assert oc["blockers"], (
        "opencode_cli must carry a blocker when output_target != managed_workspace"
    )
    assert any("managed workspace" in b.lower() for b in oc["blockers"])
    # Never chosen when blocked.
    assert body["chosen"] is None or body["chosen"]["provider"] != "opencode_cli"
    _assert_no_secret_leakage(res.text)


def test_preview_opencode_blocked_when_env_disabled(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    """Env gates not set → opencode_cli appears as blocked candidate, not absent."""
    from src.ham.worker_adapters import opencode_adapter as _opencode_adapter

    monkeypatch.delenv("HAM_OPENCODE_ENABLED", raising=False)
    monkeypatch.delenv("HAM_OPENCODE_EXECUTION_ENABLED", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-opencode-canary")
    monkeypatch.setattr(
        _opencode_adapter.shutil,
        "which",
        lambda name: "/usr/local/bin/opencode" if name == "opencode" else None,
    )
    _opencode_adapter.reset_opencode_readiness_cache()

    rec = _register_project(
        isolated_store,
        name="p_opencode_envoff",
        root=tmp_path,
        build_lane_enabled=True,
        output_target="managed_workspace",
        workspace_id="ws_opencode_off",
    )
    res = _post(
        _client(normie_actor),
        user_prompt="Build a new feature for the chat panel.",
        project_id=rec.id,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    oc = next((c for c in body["candidates"] if c["provider"] == "opencode_cli"), None)
    assert oc is not None, "opencode_cli must appear as a blocked candidate, not be absent"
    assert oc["available"] is False
    assert oc["blockers"], "opencode_cli must carry a blocker when env gates are off"
    # Never chosen when blocked.
    assert body["chosen"] is None or body["chosen"]["provider"] != "opencode_cli"
    _assert_no_secret_leakage(res.text)


def test_preview_opencode_blocked_when_exec_token_absent(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    """All env gates on + CLI present + auth set, but no exec token → opencode_cli blocked."""
    from src.ham.worker_adapters import opencode_adapter as _opencode_adapter

    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    # Deliberately omit HAM_OPENCODE_EXEC_TOKEN.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-opencode-canary")
    monkeypatch.setattr(
        _opencode_adapter.shutil,
        "which",
        lambda name: "/usr/local/bin/opencode" if name == "opencode" else None,
    )
    _opencode_adapter.reset_opencode_readiness_cache()
    rec = _register_project(
        isolated_store,
        name="p_opencode_notoken",
        root=tmp_path,
        build_lane_enabled=True,
        output_target="managed_workspace",
        workspace_id="ws_opencode_notoken",
    )
    res = _post(
        _client(normie_actor),
        user_prompt="Build a new feature for the chat panel.",
        project_id=rec.id,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    oc = next((c for c in body["candidates"] if c["provider"] == "opencode_cli"), None)
    assert oc is not None, "opencode_cli must appear as a blocked candidate, not be absent"
    assert oc["available"] is False
    assert oc["blockers"], "opencode_cli must carry a blocker when exec token is absent"
    # The blocker copy must never reveal the env var name or token value.
    for blocker in oc["blockers"]:
        assert "HAM_OPENCODE_EXEC_TOKEN" not in blocker
        assert "HAM_OPENCODE" not in blocker
    # Never chosen when blocked.
    assert body["chosen"] is None or body["chosen"]["provider"] != "opencode_cli"
    _assert_no_secret_leakage(res.text)


def test_preview_opencode_preferred_provider_promotes_when_approveable(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    _make_opencode_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_opencode_prefer",
        root=tmp_path,
        build_lane_enabled=True,
        output_target="managed_workspace",
        workspace_id="ws_opencode_prefer",
    )
    res = _post(
        _client(normie_actor),
        user_prompt="Refactor the chat router.",
        project_id=rec.id,
        extra={"preferred_provider": "opencode_cli"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["chosen"] is not None
    assert body["chosen"]["provider"] == "opencode_cli"
    assert body["chosen"]["available"] is True


def test_preview_opencode_preferred_provider_cannot_bypass_managed_workspace_gate(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    """preferred_provider=opencode_cli must not bypass blockers.

    When output_target=github_pr, opencode_cli appears as blocked in candidates
    but preferred_provider must not promote it to chosen.
    """
    _make_opencode_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_opencode_prefer_block",
        root=tmp_path,
        build_lane_enabled=True,
        github_repo="Code-Munkiz/ham",
        output_target="github_pr",
    )
    res = _post(
        _client(normie_actor),
        user_prompt="Refactor the chat router.",
        project_id=rec.id,
        extra={"preferred_provider": "opencode_cli"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    # opencode_cli appears in candidates but is blocked.
    oc = next((c for c in body["candidates"] if c["provider"] == "opencode_cli"), None)
    assert oc is not None, "opencode_cli must be visible as a blocked candidate"
    assert oc["available"] is False
    assert oc["blockers"]
    # preferred_provider must not promote a blocked candidate.
    if body["chosen"] is not None:
        assert body["chosen"]["provider"] != "opencode_cli"


def test_preview_body_never_leaks_opencode_env_names(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    # Require Clerk auth so normie_actor is not auto-promoted to operator.
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HAM_WORKSPACE_OPERATOR_EMAILS", "operator@example.test")
    _make_opencode_ready(monkeypatch)
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", "test-opencode-exec-token-canary")
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/should-not-appear")
    rec = _register_project(
        isolated_store,
        name="p_opencode_sanitise",
        root=tmp_path,
        build_lane_enabled=True,
        output_target="managed_workspace",
        workspace_id="ws_opencode_sanitise",
    )
    for prompt in (
        "Build a new feature for the chat panel.",
        "Refactor the chat router.",
        "Add docstrings to ham_run_id helpers.",
        "Fix typos in the README.",
    ):
        res = _post(_client(normie_actor), user_prompt=prompt, project_id=rec.id)
        assert res.status_code == 200, res.text
        blob = res.text
        lower = blob.lower()
        for forbidden in (
            "HAM_OPENCODE_ENABLED",
            "HAM_OPENCODE_EXEC_TOKEN",
            "HAM_OPENCODE_EXECUTION_ENABLED",
            "OPENROUTER_API_KEY",
            "XDG_DATA_HOME",
            "opencode serve",
            "test-opencode-canary",
            "test-opencode-exec-token-canary",
        ):
            assert forbidden not in blob, f"response leaks {forbidden!r}: {blob}"
            assert forbidden.lower() not in lower, f"response leaks {forbidden!r}: {blob}"


# ---------------------------------------------------------------------------
# Operator diagnostics — provider_diagnostics.opencode_cli
# ---------------------------------------------------------------------------


def test_preview_normie_receives_no_provider_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    normie_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    """Non-operator responses must not include provider_diagnostics."""
    # Require Clerk auth so normie_actor is not auto-promoted to operator.
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HAM_WORKSPACE_OPERATOR_EMAILS", "operator@example.test")
    _make_opencode_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_diag_normie",
        root=tmp_path,
        build_lane_enabled=True,
        output_target="managed_workspace",
        workspace_id="ws_diag_normie",
    )
    res = _post(
        _client(normie_actor),
        user_prompt="Build a new feature for the chat panel.",
        project_id=rec.id,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_operator"] is False
    assert "provider_diagnostics" not in body


def test_preview_operator_diagnostics_opencode_eligible(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    operator_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    """When OpenCode is eligible, diagnostics must report opencode:eligible."""
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HAM_WORKSPACE_OPERATOR_EMAILS", "operator@example.test")
    _make_opencode_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_diag_eligible",
        root=tmp_path,
        build_lane_enabled=True,
        output_target="managed_workspace",
        workspace_id="ws_diag_eligible",
    )
    res = _post(
        _client(operator_actor),
        user_prompt="Build a new feature for the chat panel.",
        project_id=rec.id,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_operator"] is True
    diag = body["provider_diagnostics"]["opencode_cli"]
    assert diag["gate_states"]["opencode_enabled"] is True
    assert diag["gate_states"]["opencode_execution_enabled"] is True
    assert diag["readiness_available"] is True
    assert diag["project_found"] is True
    assert diag["is_managed_workspace"] is True
    assert diag["exclusion_reason"] == "opencode:eligible"


def test_preview_operator_diagnostics_opencode_gates_disabled(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    operator_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    """When gates are off, diagnostics must report opencode:gates_disabled."""
    from src.ham.worker_adapters import opencode_adapter as _opencode_adapter

    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HAM_WORKSPACE_OPERATOR_EMAILS", "operator@example.test")
    monkeypatch.delenv("HAM_OPENCODE_ENABLED", raising=False)
    monkeypatch.delenv("HAM_OPENCODE_EXECUTION_ENABLED", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-opencode-canary")
    monkeypatch.setattr(
        _opencode_adapter.shutil,
        "which",
        lambda name: "/usr/local/bin/opencode" if name == "opencode" else None,
    )
    _opencode_adapter.reset_opencode_readiness_cache()
    rec = _register_project(
        isolated_store,
        name="p_diag_gates_off",
        root=tmp_path,
        build_lane_enabled=True,
        output_target="managed_workspace",
        workspace_id="ws_diag_gates_off",
    )
    res = _post(
        _client(operator_actor),
        user_prompt="Build a new feature for the chat panel.",
        project_id=rec.id,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_operator"] is True
    diag = body["provider_diagnostics"]["opencode_cli"]
    assert diag["gate_states"]["opencode_enabled"] is False
    assert diag["exclusion_reason"] == "opencode:gates_disabled"
    assert diag["project_found"] is True
    assert diag["is_managed_workspace"] is True


def test_preview_operator_diagnostics_opencode_not_managed_workspace(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    operator_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    """When output_target=github_pr, diagnostics must report opencode:not_managed_workspace."""
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HAM_WORKSPACE_OPERATOR_EMAILS", "operator@example.test")
    _make_opencode_ready(monkeypatch)
    rec = _register_project(
        isolated_store,
        name="p_diag_not_managed",
        root=tmp_path,
        build_lane_enabled=True,
        github_repo="Code-Munkiz/ham",
        output_target="github_pr",
    )
    res = _post(
        _client(operator_actor),
        user_prompt="Build a new feature for the chat panel.",
        project_id=rec.id,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    diag = body["provider_diagnostics"]["opencode_cli"]
    assert diag["gate_states"]["opencode_enabled"] is True
    assert diag["gate_states"]["opencode_execution_enabled"] is True
    assert diag["readiness_available"] is True
    assert diag["is_managed_workspace"] is False
    assert diag["exclusion_reason"] == "opencode:not_managed_workspace"


def test_preview_operator_diagnostics_opencode_project_not_found(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    operator_actor: HamActor,
    cleanup_overrides: None,
) -> None:
    """When project_id is missing, diagnostics must report opencode:project_not_found."""
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HAM_WORKSPACE_OPERATOR_EMAILS", "operator@example.test")
    _make_opencode_ready(monkeypatch)
    res = _post(
        _client(operator_actor),
        user_prompt="Build a new feature for the chat panel.",
    )
    assert res.status_code == 200, res.text
    body = res.json()
    diag = body["provider_diagnostics"]["opencode_cli"]
    assert diag["project_found"] is False
    assert diag["exclusion_reason"] == "opencode:project_not_found"


def test_preview_operator_diagnostics_no_secrets(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: ProjectStore,
    operator_actor: HamActor,
    tmp_path: Path,
    cleanup_overrides: None,
) -> None:
    """provider_diagnostics must never contain secret values, tokens, or env values."""
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HAM_WORKSPACE_OPERATOR_EMAILS", "operator@example.test")
    _make_opencode_ready(monkeypatch)
    monkeypatch.setenv("HAM_OPENCODE_EXEC_TOKEN", "test-opencode-exec-token-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-opencode-canary-secret")
    rec = _register_project(
        isolated_store,
        name="p_diag_secrets",
        root=tmp_path,
        build_lane_enabled=True,
        output_target="managed_workspace",
        workspace_id="ws_diag_secrets",
    )
    res = _post(
        _client(operator_actor),
        user_prompt="Build a new feature for the chat panel.",
        project_id=rec.id,
    )
    assert res.status_code == 200, res.text
    blob = res.text
    # No secret values.
    assert "test-opencode-exec-token-secret" not in blob
    assert "test-opencode-canary-secret" not in blob
    assert "test-opencode-canary" not in blob
    # No env variable values (only bool presence flags are allowed).
    assert "opencode serve" not in blob.lower()
    # Diagnostics are present (operator gets them).
    body = res.json()
    assert "provider_diagnostics" in body
    diag = body["provider_diagnostics"]["opencode_cli"]
    # gate_states values must be booleans, not the actual env string values.
    assert isinstance(diag["gate_states"]["opencode_enabled"], bool)
    assert isinstance(diag["gate_states"]["opencode_execution_enabled"], bool)
