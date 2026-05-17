"""PR 4 — custom builder profiles surfaced in the conductor recommender.

These tests construct readiness snapshots, profile rows, and policies
in-memory; no env is read, no provider clients are imported, no network is
touched. The recommender must remain pure: ``recommend(...)`` with
``custom_builders=[profile]`` must not mutate ``os.environ`` or read any new
env variable.

The contract under test:

- Custom-builder candidates piggy-back on the bare ``opencode_cli`` lane,
  inheriting its readiness/project blockers and the same safety flags.
- The bare ``opencode_cli`` candidate stays in the list alongside builders.
- Intent-tag substring matches boost confidence by ``+0.05`` each, capped
  at ``+0.15``.
- At most three builder candidates are surfaced per call.
- ``prefer_open_custom`` adds an extra ``+0.05`` to the single best
  unblocked builder; other preference modes leave builders untouched.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from src.ham.coding_router import recommend
from src.ham.coding_router.types import (
    Candidate,
    CodingTask,
    ProjectFlags,
    ProviderKind,
    ProviderReadiness,
    WorkspaceAgentPolicy,
    WorkspaceReadiness,
)
from src.ham.custom_builder.profile import CustomBuilderProfile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _readiness(
    *,
    audit: bool = False,
    build: bool = False,
    cursor: bool = False,
    claude_code: bool = False,
    claude_agent: bool = False,
    opencode_available: bool = True,
    opencode_blockers: tuple[str, ...] = (),
    project: ProjectFlags | None = None,
) -> WorkspaceReadiness:
    providers = (
        ProviderReadiness(provider="no_agent", available=True),
        ProviderReadiness(
            provider="factory_droid_audit",
            available=audit,
            blockers=() if audit else ("Factory Droid not configured.",),
        ),
        ProviderReadiness(
            provider="factory_droid_build",
            available=build,
            blockers=() if build else ("Factory Droid build lane not configured.",),
        ),
        ProviderReadiness(
            provider="cursor_cloud",
            available=cursor,
            blockers=() if cursor else ("Cursor team key not configured.",),
        ),
        ProviderReadiness(
            provider="claude_code",
            available=claude_code,
            blockers=() if claude_code else ("Claude Code not available.",),
        ),
        ProviderReadiness(
            provider="claude_agent",
            available=claude_agent,
            blockers=() if claude_agent else ("Claude Agent not configured.",),
        ),
        ProviderReadiness(
            provider="opencode_cli",
            available=opencode_available,
            blockers=opencode_blockers
            if opencode_blockers
            else (() if opencode_available else ("OpenCode not configured.",)),
        ),
    )
    return WorkspaceReadiness(
        is_operator=False,
        providers=providers,
        project=project
        or ProjectFlags(
            found=True,
            project_id="project.demo",
            build_lane_enabled=True,
            has_github_repo=False,
            output_target="managed_workspace",
            has_workspace_id=True,
        ),
    )


def _managed_project(
    *,
    found: bool = True,
    build_lane_enabled: bool = True,
    has_workspace_id: bool = True,
) -> ProjectFlags:
    return ProjectFlags(
        found=found,
        project_id="project.demo-managed" if found else None,
        build_lane_enabled=build_lane_enabled,
        has_github_repo=False,
        output_target="managed_workspace",
        has_workspace_id=has_workspace_id,
    )


def _github_project() -> ProjectFlags:
    return ProjectFlags(
        found=True,
        project_id="project.demo-gh",
        build_lane_enabled=True,
        has_github_repo=True,
        output_target="github_pr",
        has_workspace_id=False,
    )


def _profile(
    builder_id: str = "game-builder",
    *,
    name: str = "Game Builder",
    intent_tags: list[str] | None = None,
    task_kinds: list[str] | None = None,
    enabled: bool = True,
    preferred_harness: str = "opencode_cli",
    allowed_harnesses: list[str] | None = None,
) -> CustomBuilderProfile:
    kwargs: dict[str, Any] = {
        "builder_id": builder_id,
        "workspace_id": "ws_abc",
        "owner_user_id": "user_owner",
        "name": name,
        "intent_tags": list(intent_tags or []),
        "task_kinds": list(task_kinds or []),
        "enabled": enabled,
        "preferred_harness": preferred_harness,
        "allowed_harnesses": list(allowed_harnesses or ["opencode_cli"]),
        "created_at": "2026-05-16T12:00:00Z",
        "updated_at": "2026-05-16T12:00:00Z",
        "updated_by": "user_owner",
    }
    return CustomBuilderProfile(**kwargs)


def _feature_task(prompt: str = "Build a new feature for the chat panel.") -> CodingTask:
    return CodingTask(
        user_prompt=prompt,
        project_id="project.demo-managed",
        kind="feature",
        confidence=0.9,
    )


def _audit_task() -> CodingTask:
    return CodingTask(
        user_prompt="Audit the persistence layer.",
        project_id="project.demo-managed",
        kind="audit",
        confidence=0.9,
    )


def _builder_candidates(out: list[Candidate]) -> list[Candidate]:
    return [c for c in out if c.builder_id is not None]


def _bare_opencode(out: list[Candidate]) -> Candidate | None:
    for c in out:
        if c.provider == "opencode_cli" and c.builder_id is None:
            return c
    return None


def _provider_candidate(out: list[Candidate], kind: ProviderKind) -> Candidate | None:
    for c in out:
        if c.provider == kind and c.builder_id is None:
            return c
    return None


# ---------------------------------------------------------------------------
# A. Candidate field shape
# ---------------------------------------------------------------------------


def test_normal_provider_candidate_has_no_builder_fields() -> None:
    proj = _managed_project()
    out = recommend(_feature_task(), _readiness(project=proj), project=proj)
    assert out, "expected candidates"
    for c in out:
        assert c.builder_id is None, c
        assert c.builder_name is None, c


def test_builder_candidate_carries_id_and_name() -> None:
    proj = _managed_project()
    builder = _profile(builder_id="puzzle-builder", name="Puzzle Builder", task_kinds=["feature"])
    out = recommend(
        _feature_task(),
        _readiness(project=proj),
        project=proj,
        custom_builders=[builder],
    )
    builders = _builder_candidates(out)
    assert len(builders) == 1
    assert builders[0].builder_id == "puzzle-builder"
    assert builders[0].builder_name == "Puzzle Builder"
    assert builders[0].provider == "opencode_cli"


# ---------------------------------------------------------------------------
# B. No workspace_id / no builders path
# ---------------------------------------------------------------------------


def test_no_custom_builders_kwarg_unchanged() -> None:
    proj = _managed_project()
    baseline = recommend(_feature_task(), _readiness(project=proj), project=proj)
    same = recommend(_feature_task(), _readiness(project=proj), project=proj)
    assert [c.provider for c in baseline] == [c.provider for c in same]
    assert [c.blockers for c in baseline] == [c.blockers for c in same]
    assert all(c.builder_id is None for c in baseline)


def test_empty_custom_builders_list_unchanged() -> None:
    proj = _managed_project()
    baseline = recommend(_feature_task(), _readiness(project=proj), project=proj)
    with_empty = recommend(
        _feature_task(),
        _readiness(project=proj),
        project=proj,
        custom_builders=[],
    )
    assert [c.provider for c in baseline] == [c.provider for c in with_empty]
    assert [c.confidence for c in baseline] == [c.confidence for c in with_empty]
    assert all(c.builder_id is None for c in with_empty)


# ---------------------------------------------------------------------------
# C. Match logic
# ---------------------------------------------------------------------------


def test_enabled_matching_builder_creates_candidate() -> None:
    proj = _managed_project()
    builder = _profile(task_kinds=["feature", "fix"])
    out = recommend(
        _feature_task(),
        _readiness(project=proj),
        project=proj,
        custom_builders=[builder],
    )
    assert len(_builder_candidates(out)) == 1


def test_disabled_builder_creates_no_candidate() -> None:
    proj = _managed_project()
    builder = _profile(task_kinds=["feature"], enabled=False)
    out = recommend(
        _feature_task(),
        _readiness(project=proj),
        project=proj,
        custom_builders=[builder],
    )
    assert _builder_candidates(out) == []


def test_non_matching_task_kind_creates_no_candidate() -> None:
    proj = _managed_project()
    builder = _profile(task_kinds=["refactor"], intent_tags=["nothing-matches"])
    out = recommend(
        _feature_task(prompt="Build a new feature."),
        _readiness(project=proj),
        project=proj,
        custom_builders=[builder],
    )
    assert _builder_candidates(out) == []


def test_empty_task_kinds_with_tag_match_creates_candidate() -> None:
    proj = _managed_project()
    builder = _profile(task_kinds=[], intent_tags=["chat"])
    out = recommend(
        _feature_task(prompt="Build a new feature for the chat panel."),
        _readiness(project=proj),
        project=proj,
        custom_builders=[builder],
    )
    builders = _builder_candidates(out)
    assert len(builders) == 1
    assert builders[0].builder_id == builder.builder_id


# ---------------------------------------------------------------------------
# D. Tag boost
# ---------------------------------------------------------------------------


def test_one_tag_match_gives_005_boost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    proj = _managed_project()
    builder = _profile(task_kinds=["feature"], intent_tags=["chat"])
    out = recommend(
        _feature_task(prompt="Build a new feature for the chat panel."),
        _readiness(project=proj),
        project=proj,
        custom_builders=[builder],
    )
    bare = _bare_opencode(out)
    builder_candidate = _builder_candidates(out)[0]
    assert bare is not None
    assert not bare.blockers
    assert builder_candidate.confidence == pytest.approx(bare.confidence + 0.05)


def test_three_tag_matches_cap_at_015_boost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    proj = _managed_project()
    builder = _profile(
        task_kinds=["feature"],
        intent_tags=["chat", "panel", "feature", "new"],
    )
    out = recommend(
        _feature_task(prompt="Build a new feature for the chat panel."),
        _readiness(project=proj),
        project=proj,
        custom_builders=[builder],
    )
    bare = _bare_opencode(out)
    builder_candidate = _builder_candidates(out)[0]
    assert bare is not None
    assert not bare.blockers
    assert builder_candidate.confidence == pytest.approx(bare.confidence + 0.15)


def test_boost_only_applies_to_unblocked_candidates() -> None:
    proj = _managed_project()
    builder = _profile(
        task_kinds=["feature"],
        intent_tags=["chat", "panel", "feature"],
    )
    # Block opencode lane via readiness blockers.
    blocked_readiness = _readiness(
        project=proj,
        opencode_available=False,
        opencode_blockers=("OpenCode is not ready.",),
    )
    out = recommend(
        _feature_task(prompt="Build a new feature for the chat panel."),
        blocked_readiness,
        project=proj,
        custom_builders=[builder],
    )
    bare = _bare_opencode(out)
    builder_candidate = _builder_candidates(out)[0]
    assert bare is not None
    assert bare.blockers
    assert builder_candidate.blockers
    assert builder_candidate.confidence == pytest.approx(bare.confidence)


# ---------------------------------------------------------------------------
# E. Cap
# ---------------------------------------------------------------------------


def test_max_three_builder_candidates_surfaced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    proj = _managed_project()
    builders = [
        _profile(
            builder_id=f"b{i}",
            name=f"Builder {i}",
            task_kinds=["feature"],
            intent_tags=["chat"] if i < 3 else [],
        )
        for i in range(5)
    ]
    out = recommend(
        _feature_task(prompt="Build a new feature for the chat panel."),
        _readiness(project=proj),
        project=proj,
        custom_builders=builders,
    )
    surfaced = _builder_candidates(out)
    assert len(surfaced) == 3
    # The top 3 must be the ones with the highest boost (i.e. those with the
    # "chat" intent tag in their profile).
    surfaced_ids = {c.builder_id for c in surfaced}
    assert surfaced_ids == {"b0", "b1", "b2"}


# ---------------------------------------------------------------------------
# F. Bare lane retention
# ---------------------------------------------------------------------------


def test_bare_opencode_remains_present_alongside_builders() -> None:
    proj = _managed_project()
    builders = [
        _profile(builder_id="b1", name="B1", task_kinds=["feature"]),
        _profile(builder_id="b2", name="B2", task_kinds=["feature"]),
    ]
    out = recommend(
        _feature_task(),
        _readiness(project=proj),
        project=proj,
        custom_builders=builders,
    )
    bare = [c for c in out if c.provider == "opencode_cli" and c.builder_id is None]
    assert len(bare) == 1
    assert len(_builder_candidates(out)) == 2


# ---------------------------------------------------------------------------
# G. Blocker inheritance
# ---------------------------------------------------------------------------


def test_builder_inherits_readiness_blockers() -> None:
    proj = _managed_project()
    builder = _profile(task_kinds=["feature"], intent_tags=["chat"])
    out = recommend(
        _feature_task(prompt="Build a new feature for the chat panel."),
        _readiness(
            project=proj,
            opencode_available=False,
            opencode_blockers=("foo",),
        ),
        project=proj,
        custom_builders=[builder],
    )
    builder_candidate = _builder_candidates(out)[0]
    assert "foo" in builder_candidate.blockers


def test_builder_inherits_project_blockers() -> None:
    proj = _github_project()
    builder = _profile(task_kinds=["feature"])
    out = recommend(
        _feature_task(),
        _readiness(project=proj),
        project=proj,
        custom_builders=[builder],
    )
    bare = _bare_opencode(out)
    builder_candidate = _builder_candidates(out)[0]
    assert bare is not None
    assert bare.blockers
    # Builder blockers must be a superset of bare lane blockers.
    for b in bare.blockers:
        assert b in builder_candidate.blockers


def test_allow_opencode_false_blocks_builder() -> None:
    proj = _managed_project()
    builder = _profile(task_kinds=["feature"], intent_tags=["chat"])
    policy = WorkspaceAgentPolicy(allow_opencode=False)
    # Simulate readiness collation already disabling opencode by policy.
    blocked_readiness = _readiness(
        project=proj,
        opencode_available=False,
        opencode_blockers=(
            "This builder is not enabled for this workspace. Update builder settings to turn it on.",
        ),
    )
    out = recommend(
        _feature_task(prompt="Build a new feature for the chat panel."),
        blocked_readiness,
        project=proj,
        workspace_policy=policy,
        custom_builders=[builder],
    )
    bare = _bare_opencode(out)
    builder_candidate = _builder_candidates(out)[0]
    assert bare is not None
    assert bare.blockers
    assert builder_candidate.blockers
    assert len(builder_candidate.blockers) >= len(bare.blockers)


# ---------------------------------------------------------------------------
# H. Preference modes
# ---------------------------------------------------------------------------


def test_prefer_open_custom_boosts_best_matching_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    proj = _managed_project()
    builders = [
        _profile(builder_id="b1", name="B1", task_kinds=["feature"], intent_tags=["chat"]),
        _profile(builder_id="b2", name="B2", task_kinds=["feature"]),
    ]
    policy = WorkspaceAgentPolicy(
        allow_opencode=True,
        preference_mode="prefer_open_custom",
    )
    out = recommend(
        _feature_task(prompt="Build a new feature for the chat panel."),
        _readiness(project=proj),
        project=proj,
        workspace_policy=policy,
        custom_builders=builders,
    )
    surfaced = _builder_candidates(out)
    by_id = {c.builder_id: c for c in surfaced}
    bare = _bare_opencode(out)
    assert bare is not None
    base = 0.65  # opencode_cli for feature
    # Bare lane gets existing +0.15 boost.
    assert bare.confidence == pytest.approx(base + 0.15)
    # Best (tag-matching) builder gets tag boost +0.05 + extra +0.05.
    assert by_id["b1"].confidence == pytest.approx(base + 0.05 + 0.05)
    # The other builder gets no extra boost from the preference mode.
    assert by_id["b2"].confidence == pytest.approx(base)


def test_prefer_premium_reasoning_does_not_boost_builders() -> None:
    proj = _managed_project()
    builder = _profile(task_kinds=["feature"], intent_tags=["chat"])
    policy = WorkspaceAgentPolicy(
        allow_opencode=True,
        allow_claude_agent=True,
        preference_mode="prefer_premium_reasoning",
    )
    out_with = recommend(
        _feature_task(prompt="Build a new feature for the chat panel."),
        _readiness(project=proj),
        project=proj,
        workspace_policy=policy,
        custom_builders=[builder],
    )
    out_recommended = recommend(
        _feature_task(prompt="Build a new feature for the chat panel."),
        _readiness(project=proj),
        project=proj,
        custom_builders=[builder],
    )
    b_with = _builder_candidates(out_with)[0]
    b_rec = _builder_candidates(out_recommended)[0]
    assert b_with.confidence == pytest.approx(b_rec.confidence)


def test_prefer_connected_repo_does_not_make_builder_eligible() -> None:
    proj = _github_project()
    builder = _profile(task_kinds=["feature"], intent_tags=["chat"])
    policy = WorkspaceAgentPolicy(
        allow_opencode=True,
        preference_mode="prefer_connected_repo",
    )
    out = recommend(
        _feature_task(prompt="Build a new feature for the chat panel."),
        _readiness(project=proj, cursor=True),
        project=proj,
        workspace_policy=policy,
        custom_builders=[builder],
    )
    bare = _bare_opencode(out)
    builder_candidate = _builder_candidates(out)[0]
    assert bare is not None
    assert bare.blockers, "bare opencode must be blocked for github_pr"
    assert builder_candidate.blockers, "builder must inherit bare lane blockers"
    # Only one bare opencode_cli candidate exists in the list.
    assert len([c for c in out if c.provider == "opencode_cli" and c.builder_id is None]) == 1


def test_recommended_mode_no_extra_boost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    proj = _managed_project()
    builder = _profile(task_kinds=["feature"], intent_tags=["chat"])
    policy = WorkspaceAgentPolicy(
        allow_opencode=True,
        preference_mode="recommended",
    )
    out = recommend(
        _feature_task(prompt="Build a new feature for the chat panel."),
        _readiness(project=proj),
        project=proj,
        workspace_policy=policy,
        custom_builders=[builder],
    )
    bare = _bare_opencode(out)
    builder_candidate = _builder_candidates(out)[0]
    assert bare is not None
    # Tag boost applied, but no preference-mode boost on top of bare lane.
    assert builder_candidate.confidence == pytest.approx(bare.confidence + 0.05)


# ---------------------------------------------------------------------------
# I. Regression / purity lock
# ---------------------------------------------------------------------------


def test_recommender_does_not_load_store() -> None:
    """``recommend(...)`` must not mutate os.environ at any point."""
    proj = _managed_project()
    builder = _profile(task_kinds=["feature"], intent_tags=["chat"])
    snapshot_env = os.environ.copy()
    out = recommend(
        _feature_task(prompt="Build a new feature for the chat panel."),
        _readiness(project=proj),
        project=proj,
        custom_builders=[builder],
    )
    assert os.environ == snapshot_env
    assert _builder_candidates(out)
