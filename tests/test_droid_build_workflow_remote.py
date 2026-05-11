"""
Tests for the build-lane executor seam (``execute_droid_build_workflow_remote``).

These tests lock the API-side wiring contract:

- ``run_droid_build_argv`` is the **only** path used (never the audit-lane
  ``run_droid_argv``). Forces ``accept_pr=True`` and ``mode="build"``.
- PR fields (``pr_url`` / ``pr_branch`` / ``pr_commit_sha`` / ``build_outcome``)
  flow from the runner all the way into :class:`DroidBuildExecutionResult` and
  the persisted :class:`ControlPlaneRun`.
- A runner outcome other than ``pr_opened`` / ``nothing_to_change`` flips
  ``ok=False`` and persists a failed control-plane run.
- No real droid, git, or gh calls; all subprocess seams are mocked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.ham.droid_workflows.preview_launch import (
    DroidBuildExecutionResult,
    execute_droid_build_workflow_remote,
)
from src.integrations.droid_runner_client import (
    RemoteDroidBuildResult,
    RemoteRunnerError,
)
from src.persistence.control_plane_run import ControlPlaneRunStore
from src.tools.droid_executor import DroidExecutionRecord


def _execution(
    *,
    exit_code: int = 0,
    timed_out: bool = False,
    stdout: str = '{"result":"Tidy docs"}',
    stderr: str = "",
) -> DroidExecutionRecord:
    return DroidExecutionRecord(
        argv=["droid", "exec"],
        working_dir="/tmp/proj",
        exit_code=exit_code,
        timed_out=timed_out,
        stdout=stdout,
        stderr=stderr,
        stdout_truncated=False,
        stderr_truncated=False,
        started_at="t0",
        ended_at="t1",
        duration_ms=12,
    )


def _remote_result(
    *,
    exit_code: int = 0,
    pr_url: str | None = "https://github.com/Code-Munkiz/ham/pull/77",
    pr_branch: str | None = "ham-droid/aabbccdd",
    pr_commit_sha: str | None = "cafef00d",
    build_outcome: str | None = "pr_opened",
    build_error_summary: str | None = None,
    stdout: str = '{"result":"Tidy docs"}',
    stderr: str = "",
    timed_out: bool = False,
) -> RemoteDroidBuildResult:
    return RemoteDroidBuildResult(
        execution=_execution(
            exit_code=exit_code,
            timed_out=timed_out,
            stdout=stdout,
            stderr=stderr,
        ),
        pr_url=pr_url,
        pr_branch=pr_branch,
        pr_commit_sha=pr_commit_sha,
        build_outcome=build_outcome,
        build_error_summary=build_error_summary,
        runner_request_id="req-abc",
    )


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ControlPlaneRunStore:
    runs_dir = tmp_path / "runs"
    monkeypatch.setenv("HAM_CONTROL_PLANE_RUNS_DIR", str(runs_dir))
    return ControlPlaneRunStore(base_dir=runs_dir)


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    p = tmp_path / "proj"
    p.mkdir()
    return p


def test_build_remote_happy_path_pr_opened(
    project_root: Path,
    store: ControlPlaneRunStore,
) -> None:
    with patch(
        "src.ham.droid_workflows.preview_launch.run_droid_build_argv",
        return_value=_remote_result(),
    ) as mock_run:
        out = execute_droid_build_workflow_remote(
            workflow_id="safe_edit_low",
            project_root=project_root,
            user_prompt="Tidy docs",
            project_id="project.pilot",
            proposal_digest="a" * 64,
            control_plane_run_store=store,
        )
    assert isinstance(out, DroidBuildExecutionResult)
    assert out.ok is True
    assert out.build_outcome == "pr_opened"
    assert out.pr_url == "https://github.com/Code-Munkiz/ham/pull/77"
    assert out.pr_branch == "ham-droid/aabbccdd"
    assert out.pr_commit_sha == "cafef00d"
    assert out.control_plane_status == "succeeded"
    assert out.ham_run_id is not None

    # Runner client invoked with mode=build, accept_pr=true, and safe argv.
    kwargs = mock_run.call_args.kwargs
    assert kwargs["accept_pr"] is True
    assert kwargs["workflow_id"] == "safe_edit_low"
    assert kwargs["project_id"] == "project.pilot"
    assert kwargs["proposal_digest"] == "a" * 64
    argv_pos = mock_run.call_args.args[0]
    assert argv_pos[0] == "droid"
    assert "--auto" in argv_pos and "low" in argv_pos


def test_build_remote_persists_pr_fields_on_control_plane_run(
    project_root: Path,
    store: ControlPlaneRunStore,
) -> None:
    with patch(
        "src.ham.droid_workflows.preview_launch.run_droid_build_argv",
        return_value=_remote_result(),
    ):
        out = execute_droid_build_workflow_remote(
            workflow_id="safe_edit_low",
            project_root=project_root,
            user_prompt="Tidy docs",
            project_id="project.pilot",
            proposal_digest="b" * 64,
            control_plane_run_store=store,
        )
    assert out.ham_run_id is not None
    run = store.get(out.ham_run_id)
    assert run is not None
    assert run.build_outcome == "pr_opened"
    assert run.pr_url == "https://github.com/Code-Munkiz/ham/pull/77"
    assert run.pr_branch == "ham-droid/aabbccdd"
    assert run.pr_commit_sha == "cafef00d"
    assert run.workflow_id == "safe_edit_low"
    assert run.proposal_digest == "b" * 64


def test_build_remote_nothing_to_change_is_success(
    project_root: Path,
    store: ControlPlaneRunStore,
) -> None:
    rr = _remote_result(
        pr_url=None,
        pr_branch="ham-droid/abcdef01",
        pr_commit_sha=None,
        build_outcome="nothing_to_change",
    )
    with patch(
        "src.ham.droid_workflows.preview_launch.run_droid_build_argv",
        return_value=rr,
    ):
        out = execute_droid_build_workflow_remote(
            workflow_id="safe_edit_low",
            project_root=project_root,
            user_prompt="Tidy docs",
            project_id="project.pilot",
            proposal_digest="c" * 64,
            control_plane_run_store=store,
        )
    assert out.ok is True
    assert out.build_outcome == "nothing_to_change"
    assert out.pr_url is None
    assert out.pr_branch == "ham-droid/abcdef01"


def test_build_remote_push_blocked_is_failure(
    project_root: Path,
    store: ControlPlaneRunStore,
) -> None:
    rr = _remote_result(
        pr_url=None,
        pr_branch="ham-droid/aabbccdd",
        pr_commit_sha="cafe1234",
        build_outcome="push_blocked",
        build_error_summary="git push failed: branch protection rejected",
    )
    with patch(
        "src.ham.droid_workflows.preview_launch.run_droid_build_argv",
        return_value=rr,
    ):
        out = execute_droid_build_workflow_remote(
            workflow_id="safe_edit_low",
            project_root=project_root,
            user_prompt="Tidy docs",
            project_id="project.pilot",
            proposal_digest="d" * 64,
            control_plane_run_store=store,
        )
    assert out.ok is False
    assert out.build_outcome == "push_blocked"
    assert out.pr_url is None
    assert "branch protection" in (out.build_error_summary or "")
    assert out.control_plane_status == "failed"


def test_build_remote_droid_failure_skips_post_exec(
    project_root: Path,
    store: ControlPlaneRunStore,
) -> None:
    rr = _remote_result(
        exit_code=3,
        stdout="",
        stderr="droid failed",
        pr_url=None,
        pr_branch=None,
        pr_commit_sha=None,
        build_outcome=None,
        build_error_summary=None,
    )
    with patch(
        "src.ham.droid_workflows.preview_launch.run_droid_build_argv",
        return_value=rr,
    ):
        out = execute_droid_build_workflow_remote(
            workflow_id="safe_edit_low",
            project_root=project_root,
            user_prompt="Tidy docs",
            project_id="project.pilot",
            proposal_digest="e" * 64,
            control_plane_run_store=store,
        )
    assert out.ok is False
    assert out.build_outcome is None
    assert out.exit_code == 3
    assert "droid exec failed" in (out.blocking_reason or "")


def test_build_remote_runner_error_persists_failure(
    project_root: Path,
    store: ControlPlaneRunStore,
) -> None:
    with patch(
        "src.ham.droid_workflows.preview_launch.run_droid_build_argv",
        side_effect=RemoteRunnerError("connection refused", code="RUNNER_UNAVAILABLE"),
    ):
        out = execute_droid_build_workflow_remote(
            workflow_id="safe_edit_low",
            project_root=project_root,
            user_prompt="Tidy docs",
            project_id="project.pilot",
            proposal_digest="f" * 64,
            control_plane_run_store=store,
        )
    assert out.ok is False
    assert out.pr_url is None
    assert "connection refused" in (out.build_error_summary or "")
    assert out.control_plane_status == "failed"


def test_build_remote_rejects_non_mutating_workflow(
    project_root: Path,
    store: ControlPlaneRunStore,
) -> None:
    out = execute_droid_build_workflow_remote(
        workflow_id="readonly_repo_audit",
        project_root=project_root,
        user_prompt="anything",
        project_id="project.pilot",
        proposal_digest="0" * 64,
        control_plane_run_store=store,
    )
    assert out.ok is False
    assert "non-mutating" in (out.blocking_reason or "").lower() or "unknown" in (
        out.blocking_reason or ""
    ).lower()
    assert out.pr_url is None


def test_build_remote_rejects_unknown_workflow(
    project_root: Path,
    store: ControlPlaneRunStore,
) -> None:
    out = execute_droid_build_workflow_remote(
        workflow_id="evil_workflow",
        project_root=project_root,
        user_prompt="anything",
        project_id="project.pilot",
        proposal_digest="0" * 64,
        control_plane_run_store=store,
    )
    assert out.ok is False
    assert out.pr_url is None
    assert out.build_outcome is None
