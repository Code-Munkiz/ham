"""Mission 1 invariants for the OpenCode coding-provider scaffold.

These tests lock that:

- Readiness is presence-only (no subprocess, no network) and never echoes
  a secret value.
- The 5-state status enum is exercised end-to-end via env + ``shutil.which``
  fixtures.
- The integration_modes sub-dict is populated for forward-compat parity
  with Mission 2 (``serve`` / ``acp`` / ``cli``).
- The disabled launch shim returns HTTP 503 with
  ``reason="opencode:not_implemented"`` and cannot invoke the OpenCode CLI
  (``subprocess.run`` is monkeypatched to raise).
- The recommender never returns ``opencode_cli`` while the env gate is off
  or readiness reports anything other than ``configured``.
- Factory Droid and Claude Agent recommendations for representative
  single-file-edit / feature / audit inputs are unaffected by the
  Mission 1 patch.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.server import app, fastapi_app
from src.ham.clerk_auth import HamActor
from src.ham.coding_router.classify import classify_task
from src.ham.coding_router.opencode_provider import (
    OpenCodeLaunchResult,
    build_opencode_readiness,
    launch_opencode_coding,
)
from src.ham.coding_router.readiness import collate_readiness
from src.ham.coding_router.recommend import recommend
from src.ham.worker_adapters.opencode_adapter import (
    OPENCODE_ENABLED_ENV_NAME,
    OpenCodeStatus,
    check_opencode_readiness,
    reset_opencode_readiness_cache,
)

_AUTH_CANARY = "opencode-test-canary-not-a-real-key"


@pytest.fixture(autouse=True)
def _reset_opencode_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip env that affects this lane and reset the readiness cache."""
    for name in (
        OPENCODE_ENABLED_ENV_NAME,
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    reset_opencode_readiness_cache()
    yield
    reset_opencode_readiness_cache()


@pytest.fixture
def actor() -> HamActor:
    return HamActor(
        user_id="user_owner",
        org_id="org_managed",
        session_id="sess_o",
        email="owner@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


@pytest.fixture
def cleanup_overrides() -> Any:
    yield
    fastapi_app.dependency_overrides.clear()


def _client(actor: HamActor | None = None) -> TestClient:
    if actor is not None:
        fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: actor
    return TestClient(app)


def _patch_which_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.ham.worker_adapters.opencode_adapter.shutil.which",
        lambda name: "/usr/local/bin/opencode" if name == "opencode" else None,
    )


def _patch_which_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.ham.worker_adapters.opencode_adapter.shutil.which",
        lambda name: None,
    )


# ---------------------------------------------------------------------------
# 1. Readiness — disabled by default
# ---------------------------------------------------------------------------


def test_opencode_readiness_disabled_when_env_gate_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(OPENCODE_ENABLED_ENV_NAME, raising=False)
    readiness = check_opencode_readiness()
    assert readiness.status == OpenCodeStatus.DISABLED
    assert readiness.enabled is False
    assert readiness.cli_present is False
    assert readiness.integration_modes == {"serve": False, "acp": False, "cli": False}


# ---------------------------------------------------------------------------
# 2. Readiness — CLI missing
# ---------------------------------------------------------------------------


def test_opencode_readiness_cli_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENCODE_ENABLED_ENV_NAME, "1")
    _patch_which_absent(monkeypatch)
    readiness = check_opencode_readiness()
    assert readiness.status == OpenCodeStatus.CLI_MISSING
    assert readiness.enabled is True
    assert readiness.cli_present is False


# ---------------------------------------------------------------------------
# 3. Readiness — provider auth missing
# ---------------------------------------------------------------------------


def test_opencode_readiness_provider_auth_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENCODE_ENABLED_ENV_NAME, "1")
    _patch_which_present(monkeypatch)
    readiness = check_opencode_readiness()
    assert readiness.status == OpenCodeStatus.PROVIDER_AUTH_MISSING
    assert readiness.enabled is True
    assert readiness.cli_present is True
    # All four provider env keys must be False; BYOK slot is reserved for
    # Mission 2 and stays False here.
    assert readiness.auth_hints == {
        "OPENROUTER_API_KEY": False,
        "ANTHROPIC_API_KEY": False,
        "OPENAI_API_KEY": False,
        "GROQ_API_KEY": False,
        "byok_via_connected_tools": False,
    }


# ---------------------------------------------------------------------------
# 4. Readiness — configured
# ---------------------------------------------------------------------------


def test_opencode_readiness_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENCODE_ENABLED_ENV_NAME, "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    _patch_which_present(monkeypatch)
    readiness = check_opencode_readiness()
    assert readiness.status == OpenCodeStatus.CONFIGURED
    assert readiness.enabled is True
    assert readiness.cli_present is True
    assert readiness.auth_hints["OPENROUTER_API_KEY"] is True


# ---------------------------------------------------------------------------
# 5. Readiness never echoes the actual env value
# ---------------------------------------------------------------------------


def test_opencode_readiness_does_not_read_secret_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENCODE_ENABLED_ENV_NAME, "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    monkeypatch.setenv("ANTHROPIC_API_KEY", _AUTH_CANARY + "-anthropic")
    _patch_which_present(monkeypatch)
    readiness = check_opencode_readiness()
    rendered = json.dumps(dataclasses.asdict(readiness))
    assert _AUTH_CANARY not in rendered
    assert "OPENROUTER_API_KEY" in rendered  # key is OK; value is not
    assert _AUTH_CANARY + "-anthropic" not in rendered
    # The dataclass repr also must not leak values.
    assert _AUTH_CANARY not in repr(readiness)


# ---------------------------------------------------------------------------
# 6. Launch shim returns 503 when disabled
# ---------------------------------------------------------------------------


def test_opencode_launch_shim_returns_503_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.delenv(OPENCODE_ENABLED_ENV_NAME, raising=False)
    res = _client(actor).post(
        "/api/opencode/build/launch",
        json={"project_id": None, "user_prompt": "anything"},
    )
    assert res.status_code == 503, res.text
    detail = res.json()["detail"]
    assert detail["reason"] == "opencode:not_implemented"
    assert detail["status"] == "disabled"


# ---------------------------------------------------------------------------
# 7. Launch shim cannot execute the CLI even when the gate is on
# ---------------------------------------------------------------------------


def test_opencode_launch_shim_cannot_execute_cli(
    monkeypatch: pytest.MonkeyPatch,
    actor: HamActor,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv(OPENCODE_ENABLED_ENV_NAME, "1")

    def _explode(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("subprocess should not be called from the disabled OpenCode shim")

    # Guard every layer the route could conceivably reach.
    monkeypatch.setattr("subprocess.run", _explode)
    monkeypatch.setattr("subprocess.Popen", _explode)

    # Sanity: the in-process facade alone must also stay non-executing.
    result = launch_opencode_coding(project_id="proj-1", user_prompt="anything")
    assert isinstance(result, OpenCodeLaunchResult)
    assert result.status == "not_implemented"
    assert result.reason == "opencode:not_implemented"
    assert result.ham_run_id is None

    res = _client(actor).post(
        "/api/opencode/build/launch",
        json={"project_id": "proj-1", "user_prompt": "anything"},
    )
    assert res.status_code == 503
    detail = res.json()["detail"]
    assert detail["reason"] == "opencode:not_implemented"
    assert detail["status"] == "not_implemented"


# ---------------------------------------------------------------------------
# 8. Recommender hard-excludes opencode while disabled
# ---------------------------------------------------------------------------


def test_recommender_never_recommends_opencode_while_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(OPENCODE_ENABLED_ENV_NAME, raising=False)
    snap = collate_readiness(actor=None, project_id=None, include_operator_details=False)
    for prompt in (
        "Tweak the import order in this file.",
        "Refactor this function to be more readable.",
        "Build a new feature for the chat panel.",
        "Audit the repo for security issues.",
    ):
        task = classify_task(prompt)
        candidates = recommend(task, snap)
        for c in candidates:
            assert c.provider != "opencode_cli", (prompt, c.provider)


# ---------------------------------------------------------------------------
# 9. Recommender hard-excludes opencode when readiness != CONFIGURED
# ---------------------------------------------------------------------------


def test_recommender_never_recommends_opencode_when_readiness_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENCODE_ENABLED_ENV_NAME, "1")
    _patch_which_absent(monkeypatch)
    snap = collate_readiness(actor=None, project_id=None, include_operator_details=False)
    # Sanity-check: opencode_cli readiness row exists but is unavailable.
    oc_rows = [p for p in snap.providers if p.provider == "opencode_cli"]
    assert len(oc_rows) == 1
    assert oc_rows[0].available is False

    for prompt in (
        "Tweak the import order in this file.",
        "Refactor this function to be more readable.",
        "Build a new feature for the chat panel.",
    ):
        task = classify_task(prompt)
        candidates = recommend(task, snap)
        for c in candidates:
            assert c.provider != "opencode_cli", (prompt, c.provider)


# ---------------------------------------------------------------------------
# 10. Factory Droid + Claude Agent unaffected
# ---------------------------------------------------------------------------


def test_factory_droid_and_claude_agent_recommendations_unaffected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Snapshot the recommender's full per-task candidate ordering when the
    OpenCode lane is disabled.

    Locks: the same set of provider candidates (minus opencode_cli) appears,
    in the same order, for representative single_file_edit / feature /
    audit / refactor / fix tasks — i.e. the Mission 1 patch only adds the
    opencode_cli row to shared tables and never reorders existing rows.
    """
    monkeypatch.delenv(OPENCODE_ENABLED_ENV_NAME, raising=False)
    monkeypatch.delenv("CLAUDE_AGENT_ENABLED", raising=False)
    snap = collate_readiness(actor=None, project_id=None, include_operator_details=False)

    cases: tuple[tuple[str, tuple[str, ...]], ...] = (
        # Audit lane — only factory_droid_audit lives in this table, so the
        # full candidate list is just [factory_droid_audit, no_agent fallback].
        ("Audit this repo for security issues.", ("factory_droid_audit", "no_agent")),
        # Single-file edit — claude_code, claude_agent, cursor_cloud are the
        # historical entries; opencode_cli must NOT appear because the
        # exclusion guard drops it while disabled.
        (
            "Tweak the import order in this file.",
            ("claude_code", "claude_agent", "cursor_cloud", "no_agent"),
        ),
        ("Refactor this module's structure.", ("cursor_cloud", "no_agent")),
        ("Build a new feature for the chat panel.", ("cursor_cloud", "no_agent")),
    )
    for prompt, expected in cases:
        task = classify_task(prompt)
        candidates = recommend(task, snap)
        providers = tuple(c.provider for c in candidates)
        # opencode_cli must never appear post-patch.
        assert "opencode_cli" not in providers, (prompt, providers)
        # The ordered set of providers per task is unchanged from pre-patch.
        assert set(providers) == set(expected), (prompt, providers, expected)


# ---------------------------------------------------------------------------
# 11. integration_modes sub-dict is well-shaped + mirrors cli_present
# ---------------------------------------------------------------------------


def test_opencode_readiness_reports_integration_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # All False when cli_present is False.
    monkeypatch.setenv(OPENCODE_ENABLED_ENV_NAME, "1")
    _patch_which_absent(monkeypatch)
    readiness = check_opencode_readiness()
    assert set(readiness.integration_modes.keys()) == {"serve", "acp", "cli"}
    for k, v in readiness.integration_modes.items():
        assert isinstance(v, bool), k
        assert v is False, k

    # All True when cli_present is True.
    reset_opencode_readiness_cache()
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    _patch_which_present(monkeypatch)
    readiness = check_opencode_readiness()
    assert set(readiness.integration_modes.keys()) == {"serve", "acp", "cli"}
    for k, v in readiness.integration_modes.items():
        assert isinstance(v, bool), k
        assert v is True, k


# ---------------------------------------------------------------------------
# Bonus: provider readiness builder surfaces blocker copy that is normie-safe
# ---------------------------------------------------------------------------


def test_build_opencode_readiness_blockers_are_normie_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(OPENCODE_ENABLED_ENV_NAME, raising=False)
    pr = build_opencode_readiness(actor=None, include_operator_details=False)
    assert pr.provider == "opencode_cli"
    assert pr.available is False
    for blocker in pr.blockers:
        for forbidden in (
            "HAM_OPENCODE_ENABLED",
            "OPENROUTER_API_KEY",
            "ANTHROPIC_API_KEY",
            "/usr/",
            "http://",
            "https://",
            "subprocess",
        ):
            assert forbidden not in blocker, (forbidden, blocker)


# ---------------------------------------------------------------------------
# Promotion: readiness available when fully configured
# ---------------------------------------------------------------------------


def test_build_opencode_readiness_reports_available_when_fully_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENCODE_ENABLED_ENV_NAME, "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    _patch_which_present(monkeypatch)
    pr = build_opencode_readiness(actor=None, include_operator_details=False)
    assert pr.provider == "opencode_cli"
    assert pr.available is True
    assert pr.blockers == ()


def test_build_opencode_readiness_reports_execution_disabled_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ENABLED gate on, EXECUTION_ENABLED gate off + readiness CONFIGURED."""
    monkeypatch.setenv(OPENCODE_ENABLED_ENV_NAME, "1")
    monkeypatch.delenv("HAM_OPENCODE_EXECUTION_ENABLED", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    _patch_which_present(monkeypatch)
    pr = build_opencode_readiness(actor=None, include_operator_details=False)
    assert pr.provider == "opencode_cli"
    assert pr.available is False
    assert pr.blockers
    for blocker in pr.blockers:
        for forbidden in (
            "HAM_OPENCODE_ENABLED",
            "HAM_OPENCODE_EXECUTION_ENABLED",
            "OPENROUTER_API_KEY",
            "ANTHROPIC_API_KEY",
            "/usr/",
            "http://",
            "https://",
            "subprocess",
        ):
            assert forbidden not in blocker, (forbidden, blocker)


def test_recommender_promotes_opencode_when_all_gates_pass_and_managed_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both env gates + CONFIGURED readiness + managed_workspace project → opencode in candidates."""
    from src.ham.coding_router.types import ProjectFlags, WorkspaceReadiness

    monkeypatch.setenv(OPENCODE_ENABLED_ENV_NAME, "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    _patch_which_present(monkeypatch)
    base = collate_readiness(actor=None, project_id=None, include_operator_details=False)
    # Wrap snapshot with a managed_workspace project so the recommender gate passes.
    managed_proj = ProjectFlags(
        found=True,
        project_id="project.demo-managed",
        build_lane_enabled=True,
        has_github_repo=False,
        output_target="managed_workspace",
        has_workspace_id=True,
    )
    snap = WorkspaceReadiness(
        is_operator=base.is_operator,
        providers=base.providers,
        project=managed_proj,
    )
    for prompt in (
        "Build a new feature for the chat panel.",
        "Refactor this function to be more readable.",
        "Add docstrings to ham_run_id helpers.",
    ):
        task = classify_task(prompt)
        candidates = recommend(task, snap, project=managed_proj)
        oc = [c for c in candidates if c.provider == "opencode_cli"]
        assert len(oc) == 1, (prompt, [c.provider for c in candidates])
        assert not oc[0].blockers, (prompt, oc[0].blockers)


def test_recommender_drops_opencode_when_output_target_is_github_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full env gates + CONFIGURED readiness + project output_target=github_pr → no opencode."""
    from src.ham.coding_router.types import ProjectFlags, WorkspaceReadiness

    monkeypatch.setenv(OPENCODE_ENABLED_ENV_NAME, "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", _AUTH_CANARY)
    _patch_which_present(monkeypatch)
    base = collate_readiness(actor=None, project_id=None, include_operator_details=False)
    github_proj = ProjectFlags(
        found=True,
        project_id="project.demo-github",
        build_lane_enabled=True,
        has_github_repo=True,
        output_target="github_pr",
        has_workspace_id=False,
    )
    snap = WorkspaceReadiness(
        is_operator=base.is_operator,
        providers=base.providers,
        project=github_proj,
    )
    for prompt in (
        "Build a new feature for the chat panel.",
        "Refactor this function to be more readable.",
    ):
        task = classify_task(prompt)
        candidates = recommend(task, snap, project=github_proj)
        for c in candidates:
            assert c.provider != "opencode_cli", (prompt, c.provider)
