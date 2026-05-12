"""Tests for the output-target abstraction introduced in PR-A.

Covers:

- :class:`OutputAdapter` Protocol satisfied by both concrete adapters.
- :class:`GithubPrAdapter` parity with :func:`execute_build_lane_post_exec`
  (the GitHub-PR-specific logic remains untouched; the adapter is a thin lift).
- :class:`ManagedWorkspaceAdapter` delegates to the managed snapshot emitter.
- :func:`select_output_adapter` dispatch (default github_pr; managed_workspace;
  unknown raises ``ValueError``).
- :func:`neutral_to_legacy_github_outcome` mapping.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.ham.droid_runner.build_lane import BuildLaneInputs
from src.ham.droid_runner.build_lane_output import (
    BUILD_OUTCOMES,
    GithubPrAdapter,
    ManagedWorkspaceAdapter,
    OutputAdapter,
    PostExecCommon,
    neutral_to_legacy_github_outcome,
    select_output_adapter,
)


def _mk_proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=("git",),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _make_pr_inputs(tmp_path: Path) -> BuildLaneInputs:
    return BuildLaneInputs(
        project_root=tmp_path,
        branch_name="ham-droid/abcd-1234-test",
        commit_message="chore(droid-build): test",
        pr_title="HAM Droid build: test",
        pr_body="body",
        base_ref="origin/main",
    )


def _common(tmp_path: Path, *, pr_inputs: BuildLaneInputs | None = None) -> PostExecCommon:
    return PostExecCommon(
        project_id="proj-test",
        project_root=tmp_path,
        summary="ok",
        change_id="change-1",
        pr_inputs=pr_inputs,
    )


# ---------------------------------------------------------------------------
# Adapter Protocol contract
# ---------------------------------------------------------------------------


def test_both_adapters_satisfy_output_adapter_protocol() -> None:
    assert isinstance(GithubPrAdapter(), OutputAdapter)
    assert isinstance(ManagedWorkspaceAdapter(), OutputAdapter)


def test_adapter_target_attribute_values() -> None:
    assert GithubPrAdapter().target == "github_pr"
    assert ManagedWorkspaceAdapter().target == "managed_workspace"


# ---------------------------------------------------------------------------
# select_output_adapter
# ---------------------------------------------------------------------------


def test_select_output_adapter_defaults_to_github_pr() -> None:
    a = select_output_adapter(None)
    assert isinstance(a, GithubPrAdapter)


def test_select_output_adapter_managed_workspace() -> None:
    a = select_output_adapter("managed_workspace")
    assert isinstance(a, ManagedWorkspaceAdapter)


def test_select_output_adapter_github_pr_explicit() -> None:
    a = select_output_adapter("github_pr")
    assert isinstance(a, GithubPrAdapter)


def test_select_output_adapter_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown output_target"):
        select_output_adapter("vercel_deploy")


# ---------------------------------------------------------------------------
# ManagedWorkspaceAdapter (delegates to snapshot emitter)
# ---------------------------------------------------------------------------


def test_managed_adapter_requires_ids(tmp_path: Path) -> None:
    res = ManagedWorkspaceAdapter().emit(_common(tmp_path))
    assert res.build_outcome == "failed"
    assert res.error_summary is not None


# ---------------------------------------------------------------------------
# GithubPrAdapter
# ---------------------------------------------------------------------------


def test_github_pr_adapter_requires_pr_inputs(tmp_path: Path) -> None:
    res = GithubPrAdapter().emit(_common(tmp_path), runner=lambda _a: _mk_proc())
    assert res.target == "github_pr"
    assert res.build_outcome == "failed"
    assert res.error_summary == "GithubPrAdapter requires PostExecCommon.pr_inputs"


def test_github_pr_adapter_requires_runner(tmp_path: Path) -> None:
    pr_inputs = _make_pr_inputs(tmp_path)
    res = GithubPrAdapter().emit(_common(tmp_path, pr_inputs=pr_inputs), runner=None)
    assert res.target == "github_pr"
    assert res.build_outcome == "failed"
    assert res.error_summary == "GithubPrAdapter requires a non-None subprocess runner"


def test_github_pr_adapter_nothing_to_change(tmp_path: Path) -> None:
    """Empty ``git status`` lifts the legacy ``nothing_to_change`` to neutral form."""
    (tmp_path / ".git").mkdir()
    pr_inputs = _make_pr_inputs(tmp_path)

    def runner(argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        if argv[:3] == ("git", "status", "--porcelain"):
            return _mk_proc(stdout="")
        raise AssertionError(f"unexpected runner call: {argv!r}")

    res = GithubPrAdapter().emit(_common(tmp_path, pr_inputs=pr_inputs), runner=runner)
    assert res.target == "github_pr"
    assert res.build_outcome == "nothing_to_change"
    assert res.error_summary is None
    assert res.pr_branch == pr_inputs.branch_name
    assert res.pr_url is None


def test_github_pr_adapter_unsafe_branch_blocked(tmp_path: Path) -> None:
    bad = BuildLaneInputs(
        project_root=tmp_path,
        branch_name="not-allowed-prefix",
        commit_message="m",
        pr_title="t",
        pr_body="b",
        base_ref="origin/main",
    )

    def runner(_a: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        raise AssertionError("runner should not be invoked for unsafe branch")

    res = GithubPrAdapter().emit(_common(tmp_path, pr_inputs=bad), runner=runner)
    assert res.target == "github_pr"
    assert res.build_outcome == "failed"
    assert "unsafe branch" in (res.error_summary or "")


# ---------------------------------------------------------------------------
# neutral_to_legacy_github_outcome
# ---------------------------------------------------------------------------


def test_neutral_to_legacy_mapping() -> None:
    assert neutral_to_legacy_github_outcome("succeeded") == "pr_opened"
    assert neutral_to_legacy_github_outcome("nothing_to_change") == "nothing_to_change"
    assert neutral_to_legacy_github_outcome("blocked") == "push_blocked"
    assert neutral_to_legacy_github_outcome("failed") == "pr_failed"


def test_build_outcomes_vocabulary() -> None:
    assert set(BUILD_OUTCOMES) == {"succeeded", "nothing_to_change", "blocked", "failed"}
