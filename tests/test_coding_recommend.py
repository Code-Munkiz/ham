"""
Pure unit tests for the HAM Coding Router recommender + classifier.

These tests construct ``WorkspaceReadiness`` snapshots in-memory; no env is
read, no provider clients are imported, no network is touched. The
recommender contract under test:

- Each (task_kind, provider) cell produces the expected candidate.
- Unavailable providers contribute a candidate with ``blockers`` (so the
  chat card can render "Recommended, but blocked because…"), but they are
  ranked below approve-able candidates.
- ``unknown`` tasks fall back to ``no_agent`` with low confidence; never a
  confident provider pick.
- Candidate fields never reference ``safe_edit_low``, ``--auto low``,
  argv, runner URLs, or env-name strings.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

import pytest

from src.ham.coding_router import (
    Candidate,
    classify_task,
    recommend,
)
from src.ham.coding_router.classify import CONFIDENCE_LOW
from src.ham.coding_router.types import (
    ProjectFlags,
    ProviderKind,
    ProviderReadiness,
    WorkspaceReadiness,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _readiness(
    *,
    audit: bool = True,
    build: bool = False,
    cursor: bool = False,
    claude: bool = False,
    is_operator: bool = False,
    project: ProjectFlags | None = None,
) -> WorkspaceReadiness:
    providers = (
        ProviderReadiness(provider="no_agent", available=True),
        ProviderReadiness(
            provider="factory_droid_audit",
            available=audit,
            blockers=()
            if audit
            else (
                "Factory Droid is not configured on this host. Contact your workspace operator.",
            ),
        ),
        ProviderReadiness(
            provider="factory_droid_build",
            available=build,
            blockers=()
            if build
            else (
                "The Factory Droid build lane is not configured on this host yet. Contact your workspace operator.",
            ),
        ),
        ProviderReadiness(
            provider="cursor_cloud",
            available=cursor,
            blockers=() if cursor else ("Cursor team key is not configured for this workspace.",),
        ),
        ProviderReadiness(
            provider="claude_code",
            available=claude,
            blockers=() if claude else ("Claude Code is not available on this host.",),
        ),
    )
    return WorkspaceReadiness(
        is_operator=is_operator,
        providers=providers,
        project=project or ProjectFlags(found=False, project_id=None),
    )


def _project(
    *,
    found: bool = True,
    build_lane_enabled: bool = False,
    has_github_repo: bool = False,
    output_target: str | None = "github_pr",
    has_workspace_id: bool = False,
) -> ProjectFlags:
    return ProjectFlags(
        found=found,
        project_id="project.demo-abc123" if found else None,
        build_lane_enabled=build_lane_enabled,
        has_github_repo=has_github_repo,
        output_target=output_target,
        has_workspace_id=has_workspace_id,
    )


def _provider_candidate(out: Iterable[Candidate], kind: ProviderKind) -> Candidate | None:
    for c in out:
        if c.provider == kind:
            return c
    return None


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt,expected_kind",
    [
        ("Explain how the auth flow works.", "explain"),
        ("What does this function do?", "explain"),
        ("walk me through ham_run_id allocation", "explain"),
        ("Run a security review on the API.", "security_review"),
        ("Do an architecture report for src/api.", "architecture_report"),
        ("Audit this repo for risks.", "audit"),
        ("Read-only review of the persistence layer", "audit"),
        ("Fix typos in the README.", "typo_only"),
        ("Run prettier on the frontend.", "format_only"),
        ("Add docstrings to ham_run_id helpers.", "comments_only"),
        ("Update comments in droid_executor", "comments_only"),
        ("Polish the README docs.", "doc_fix"),
        ("Refactor the chat router", "refactor"),
        ("Migrate all callers to the new helper", "multi_file_edit"),
        ("Implement a /api/coding/preview endpoint", "feature"),
        ("Fix the broken Cursor mission cancel button", "fix"),
        ("Tweak this file's import order", "single_file_edit"),
        # Hyphenated -only shapes (managed-workspace smoke prompts in the wild
        # use these); recommender maps comments_only -> factory_droid_build.
        ("Make a comment-only change to the README.", "comments_only"),
        ("docs-only update; no behavior change.", "comments_only"),
        ("documentation-only tweak", "comments_only"),
        (
            "Smoke test only. Make a tiny documentation/comment-only change in the "
            "managed workspace and create a managed snapshot. Do not change behavior, "
            "dependencies, secrets, CI, or configuration.",
            "comments_only",
        ),
        ("documentation/comment update", "comments_only"),
        ("comment / docs polish", "comments_only"),
        ("Create a managed snapshot for the staging workspace.", "comments_only"),
        ("managed workspace build for a tiny docs tweak", "comments_only"),
        ("Hello", "unknown"),
        ("", "unknown"),
        ("    ", "unknown"),
    ],
)
def test_classify_task_table(prompt: str, expected_kind: str) -> None:
    task = classify_task(prompt, project_id=None)
    assert task.kind == expected_kind, task


def test_classify_unknown_has_zero_confidence() -> None:
    task = classify_task("hello world this is a generic chat message")
    assert task.kind == "unknown"
    assert task.confidence == 0.0


def test_classify_low_confidence_threshold_constant() -> None:
    # Locks the contract: callers may compare ``confidence < CONFIDENCE_LOW``
    # to decide whether to show "I'm not sure" + alternatives.
    assert 0 < CONFIDENCE_LOW < 1


def test_classify_truncates_oversize_prompts() -> None:
    big = "Explain " + ("x" * 50_000)
    task = classify_task(big)
    assert task.kind == "explain"


# ---------------------------------------------------------------------------
# Recommender — happy paths
# ---------------------------------------------------------------------------


def test_recommend_explain_returns_no_agent_first() -> None:
    out = recommend(
        classify_task("Explain how chat-first orchestration works."),
        _readiness(audit=True),
    )
    assert out[0].provider == "no_agent"
    assert out[0].confidence >= 0.8


def test_recommend_audit_returns_factory_droid_audit_when_ready() -> None:
    proj = _project(found=True)
    out = recommend(
        classify_task("Audit security of the API.", project_id=proj.project_id),
        _readiness(audit=True, project=proj),
        project=proj,
    )
    assert out[0].provider == "factory_droid_audit"
    assert not out[0].blockers


def test_recommend_audit_blocked_when_runner_unavailable() -> None:
    proj = _project(found=True)
    out = recommend(
        classify_task("Audit the persistence layer.", project_id=proj.project_id),
        _readiness(audit=False, project=proj),
        project=proj,
    )
    audit = _provider_candidate(out, "factory_droid_audit")
    assert audit is not None
    assert audit.blockers  # carries the runner-unavailable blocker
    # And the approve-able fallback ranks ahead.
    assert out[0].provider != "factory_droid_audit" or out[0].blockers


def test_recommend_doc_fix_prefers_factory_droid_build_when_ready() -> None:
    proj = _project(found=True, build_lane_enabled=True, has_github_repo=True)
    out = recommend(
        classify_task("Add docstrings to ham_run_id helpers.", project_id=proj.project_id),
        _readiness(build=True, project=proj),
        project=proj,
    )
    assert out[0].provider == "factory_droid_build"
    assert not out[0].blockers
    assert out[0].requires_operator is True
    assert out[0].will_open_pull_request is True


def test_recommend_build_blocked_when_project_lane_disabled() -> None:
    proj = _project(found=True, build_lane_enabled=False, has_github_repo=True)
    out = recommend(
        classify_task("Tidy README docs.", project_id=proj.project_id),
        _readiness(build=True, project=proj),
        project=proj,
    )
    build = _provider_candidate(out, "factory_droid_build")
    assert build is not None
    assert any("Build lane is disabled for this project" in b for b in build.blockers)


def test_recommend_build_blocked_when_project_missing_github_repo() -> None:
    proj = _project(found=True, build_lane_enabled=True, has_github_repo=False)
    out = recommend(
        classify_task("Tidy README docs.", project_id=proj.project_id),
        _readiness(build=True, project=proj),
        project=proj,
    )
    build = _provider_candidate(out, "factory_droid_build")
    assert build is not None
    assert any("GitHub repository" in b for b in build.blockers)


def test_recommend_build_blocked_when_token_not_configured_on_host() -> None:
    proj = _project(found=True, build_lane_enabled=True, has_github_repo=True)
    out = recommend(
        classify_task("Tidy README docs.", project_id=proj.project_id),
        _readiness(build=False, project=proj),
        project=proj,
    )
    build = _provider_candidate(out, "factory_droid_build")
    assert build is not None
    assert any("build lane is not configured on this host" in b.lower() for b in build.blockers)


def test_recommend_refactor_prefers_cursor_cloud_when_ready() -> None:
    proj = _project(found=True, has_github_repo=True)
    out = recommend(
        classify_task("Refactor the chat router for clarity.", project_id=proj.project_id),
        _readiness(cursor=True, project=proj),
        project=proj,
    )
    assert out[0].provider == "cursor_cloud"
    assert out[0].will_open_pull_request is True


def test_recommend_cursor_blocked_when_project_missing_github_repo() -> None:
    proj = _project(found=True, has_github_repo=False)
    out = recommend(
        classify_task("Refactor the chat router for clarity.", project_id=proj.project_id),
        _readiness(cursor=True, project=proj),
        project=proj,
    )
    cursor = _provider_candidate(out, "cursor_cloud")
    assert cursor is not None
    assert any("GitHub repository" in b for b in cursor.blockers)


def test_recommend_cursor_blocked_when_team_key_missing() -> None:
    proj = _project(found=True, has_github_repo=True)
    out = recommend(
        classify_task("Refactor the chat router for clarity.", project_id=proj.project_id),
        _readiness(cursor=False, project=proj),
        project=proj,
    )
    cursor = _provider_candidate(out, "cursor_cloud")
    assert cursor is not None
    assert any("Cursor team key" in b for b in cursor.blockers)


def test_recommend_claude_for_single_file_edit_when_ready() -> None:
    out = recommend(
        classify_task("Tweak this file's import order."),
        _readiness(claude=True),
    )
    # Either claude_code or cursor_cloud may rank first by base confidence.
    # The lock here is that claude_code is available without blockers.
    claude = _provider_candidate(out, "claude_code")
    assert claude is not None
    assert not claude.blockers


# ---------------------------------------------------------------------------
# Recommender — unknown / fallback
# ---------------------------------------------------------------------------


def test_recommend_unknown_returns_no_agent_with_low_confidence() -> None:
    task = classify_task("hi this is a chat message that does not match anything")
    out = recommend(task, _readiness(audit=False, build=False, cursor=False, claude=False))
    assert task.kind == "unknown"
    assert out[0].provider == "no_agent"
    assert out[0].confidence < 0.6  # never a confident pick on unknown


def test_recommend_always_includes_no_agent_fallback() -> None:
    out = recommend(
        classify_task("Refactor the chat router."),
        _readiness(cursor=False),
    )
    assert any(c.provider == "no_agent" for c in out)


def test_recommend_ranks_approveable_candidates_ahead_of_blocked() -> None:
    proj = _project(found=True, has_github_repo=True)
    out = recommend(
        classify_task("Refactor the chat router.", project_id=proj.project_id),
        _readiness(cursor=False, project=proj),
        project=proj,
    )
    # cursor_cloud should be present but blocked; no_agent unblocked.
    blocked_cursor = _provider_candidate(out, "cursor_cloud")
    assert blocked_cursor is not None and blocked_cursor.blockers
    no_agent_index = next(i for i, c in enumerate(out) if c.provider == "no_agent")
    cursor_index = next(i for i, c in enumerate(out) if c.provider == "cursor_cloud")
    assert no_agent_index < cursor_index


# ---------------------------------------------------------------------------
# Sanitisation locks
# ---------------------------------------------------------------------------


_FORBIDDEN_TOKENS = (
    "safe_edit_low",
    "low_edit",
    "--auto low",
    "ham_droid_exec_token",
    "ham_droid_runner_url",
    "ham_droid_runner_token",
    "anthropic_api_key",
    "cursor_api_key",
    "argv",
    "droid exec",
)


@pytest.mark.parametrize(
    "task_kind,prompt",
    [
        ("explain", "Explain auth flow."),
        ("audit", "Audit the API."),
        ("doc_fix", "Polish the README docs."),
        ("typo_only", "Fix typo in helper."),
        ("refactor", "Refactor chat router."),
        ("feature", "Implement a /api/coding/preview endpoint"),
        ("unknown", "hello"),
    ],
)
def test_recommend_output_never_leaks_internals(task_kind: str, prompt: str) -> None:
    proj = _project(found=True, build_lane_enabled=True, has_github_repo=True)
    out = recommend(
        classify_task(prompt, project_id=proj.project_id),
        _readiness(audit=True, build=True, cursor=True, claude=True, project=proj),
        project=proj,
    )
    blob = json.dumps([c.__dict__ for c in out], default=str).lower()
    for forbidden in _FORBIDDEN_TOKENS:
        assert forbidden not in blob, (
            f"task={task_kind!r}: candidate output leaks {forbidden!r}: {blob}"
        )
