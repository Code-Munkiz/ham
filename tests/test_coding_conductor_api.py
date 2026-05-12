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
    # Negative locks: no launch / dispatch / run / execute under /api/coding.
    for p in paths:
        assert "/launch" not in p, f"unexpected launch route: {p}"
        assert "/dispatch" not in p, f"unexpected dispatch route: {p}"
        assert "/execute" not in p, f"unexpected execute route: {p}"
        for _, methods in routes:
            for m in methods:
                assert m in ("GET", "POST", "HEAD"), f"unexpected verb {m} on {p}"
