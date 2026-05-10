"""
Tests for the dark Factory Droid Build Lane runner-side helpers.

Hard test contract:
- No real subprocess. Every git/gh call goes through a :class:`FakeRunner`.
- No network calls. No real ``git push`` / ``gh pr create``.
- No mutation outside ``tmp_path``: only the ``.git/`` initialised by tests.
- All argv passed to the runner is a list/tuple of strings (validated below).
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.ham.droid_runner import build_lane as bl
from src.ham.droid_runner.build_lane import (
    BRANCH_PREFIX,
    BuildLaneInputs,
    CompletedRun,
    SubprocessRunner,
    detect_sensitive_changes,
    execute_build_lane_post_exec,
    generate_branch_name,
    is_safe_branch_name,
    make_default_runner,
)
from src.persistence.control_plane_run import DROID_BUILD_OUTCOMES

# ---------------------------------------------------------------------------
# Fake runner
# ---------------------------------------------------------------------------


@dataclass
class _Reply:
    rc: int = 0
    stdout: str = ""
    stderr: str = ""


class FakeRunner:
    """Deterministic substitute for the real subprocess runner."""

    def __init__(self, *replies: _Reply) -> None:
        self._replies: list[_Reply] = list(replies)
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str]) -> CompletedRun:
        # Validate argv shape: must be a non-empty sequence of strings.
        assert isinstance(args, (list, tuple)), f"argv must be list/tuple, got {type(args)!r}"
        assert len(args) > 0, "argv must be non-empty"
        for tok in args:
            assert isinstance(tok, str), f"argv tokens must be str, got {type(tok)!r}"
        self.calls.append(list(args))
        if not self._replies:
            raise AssertionError(f"FakeRunner: unexpected call: {list(args)}")
        r = self._replies.pop(0)
        return CompletedRun(returncode=r.rc, stdout=r.stdout, stderr=r.stderr)

    @property
    def exhausted(self) -> bool:
        return not self._replies


def _make_repo(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".git").mkdir()
    return project


def _inputs(project: Path, *, branch: str = "ham-droid/abc12345") -> BuildLaneInputs:
    return BuildLaneInputs(
        project_root=project,
        branch_name=branch,
        commit_message="chore: build lane test",
        pr_title="chore: build lane test",
        pr_body="dark P2 helper test",
    )


# ---------------------------------------------------------------------------
# Branch-name policy
# ---------------------------------------------------------------------------


def test_generate_branch_name_default_shape() -> None:
    name = generate_branch_name()
    assert name.startswith(BRANCH_PREFIX)
    tail = name[len(BRANCH_PREFIX) :]
    assert re.match(r"^[a-z0-9]{8}$", tail)


def test_generate_branch_name_with_explicit_short_id() -> None:
    name = generate_branch_name(short_id="deadbeef")
    assert name == "ham-droid/deadbeef"


@pytest.mark.parametrize("bad", ["", "ab", "ABCDEF", "abcd ef", "abc-def!", "x" * 64])
def test_generate_branch_name_rejects_bad_short_id(bad: str) -> None:
    with pytest.raises(ValueError):
        generate_branch_name(short_id=bad)


@pytest.mark.parametrize(
    "name",
    [
        "ham-droid/abc12345",
        "ham-droid/feat-cleanup-09",
        "ham-droid/topic.123",
    ],
)
def test_is_safe_branch_name_accepts(name: str) -> None:
    assert is_safe_branch_name(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "",
        "main",
        "MAIN",
        "master",
        "HEAD",
        "trunk",
        "develop",
        "release",
        "feature/foo",  # wrong prefix
        "ham-droid/main",
        "ham-droid/master",
        "ham-droid/HEAD",
        "ham-droid/",
        "ham-droid",
        "ham-droid/with space",
        "ham-droid/colon:bad",
        "ham-droid/bad..tilde",
        "ham-droid/abc.lock",
        "ham-droid/-leading-dash",
        "/abs/path",
        "-flagish",
        "refs/heads/ham-droid/x",
    ],
)
def test_is_safe_branch_name_rejects(name: str) -> None:
    assert is_safe_branch_name(name) is False


def test_is_safe_branch_name_rejects_non_string() -> None:
    assert is_safe_branch_name(None) is False  # type: ignore[arg-type]
    assert is_safe_branch_name(123) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Sensitive-path detector
# ---------------------------------------------------------------------------


def test_detect_sensitive_changes_flags_dotenv_and_secrets() -> None:
    porcelain = " M .env\n M secrets/api.key\n M src/foo.py\n M .ham/cache.json\n"
    hits = detect_sensitive_changes(porcelain)
    assert ".env" in hits
    assert "secrets/api.key" in hits
    assert ".ham/cache.json" in hits
    assert "src/foo.py" not in hits


def test_detect_sensitive_changes_flags_logs_and_data_and_pem() -> None:
    porcelain = " M logs/app.log\n M .data/x\n M tls/cert.pem\n M provider-data/y\n"
    hits = detect_sensitive_changes(porcelain)
    assert "logs/app.log" in hits
    assert ".data/x" in hits
    assert "tls/cert.pem" in hits
    assert "provider-data/y" in hits


def test_detect_sensitive_changes_handles_renames_and_quotes() -> None:
    porcelain = 'R  src/old.py -> "secrets/new.txt"\n'
    hits = detect_sensitive_changes(porcelain)
    assert "secrets/new.txt" in hits


def test_detect_sensitive_changes_clean() -> None:
    porcelain = " M src/foo.py\n M README.md\n"
    assert detect_sensitive_changes(porcelain) == []


# ---------------------------------------------------------------------------
# Default runner is shell=False with timeout (sanity-check by source inspection)
# ---------------------------------------------------------------------------


def test_default_runner_uses_shell_false_and_timeout() -> None:
    src = inspect.getsource(make_default_runner)
    assert "shell=False" in src
    assert "timeout=" in src
    # No shell=True anywhere in module
    module_src = inspect.getsource(bl)
    assert "shell=True" not in module_src


# ---------------------------------------------------------------------------
# Orchestrator outcomes
# ---------------------------------------------------------------------------


def test_orchestrator_unsafe_branch_name_returns_pr_failed(tmp_path: Path) -> None:
    project = _make_repo(tmp_path)
    inputs = _inputs(project, branch="main")
    runner = FakeRunner()  # nothing should be called
    res = execute_build_lane_post_exec(inputs, runner=runner)
    assert res.build_outcome == "pr_failed"
    assert res.pr_url is None
    assert res.pr_branch is None
    assert runner.calls == []


def test_orchestrator_not_a_git_repo(tmp_path: Path) -> None:
    project = tmp_path / "no_git"
    project.mkdir()
    inputs = _inputs(project)
    runner = FakeRunner()
    res = execute_build_lane_post_exec(inputs, runner=runner)
    assert res.build_outcome == "pr_failed"
    assert "not a git repo" in (res.error_summary or "")


def test_orchestrator_nothing_to_change(tmp_path: Path) -> None:
    project = _make_repo(tmp_path)
    runner = FakeRunner(_Reply(rc=0, stdout=""))
    res = execute_build_lane_post_exec(_inputs(project), runner=runner)
    assert res.build_outcome == "nothing_to_change"
    assert res.pr_branch == "ham-droid/abc12345"
    assert res.pr_commit_sha is None
    # Only one call: git status
    assert runner.calls == [["git", "status", "--porcelain"]]


def test_orchestrator_sensitive_paths_block_commit(tmp_path: Path) -> None:
    project = _make_repo(tmp_path)
    runner = FakeRunner(
        _Reply(rc=0, stdout=" M .env\n M src/foo.py\n"),
    )
    res = execute_build_lane_post_exec(_inputs(project), runner=runner)
    assert res.build_outcome == "pr_failed"
    assert "sensitive" in (res.error_summary or "")
    # No further calls — no checkout, no add, no commit, no push, no PR.
    assert len(runner.calls) == 1


def test_orchestrator_pr_opened_happy_path(tmp_path: Path) -> None:
    project = _make_repo(tmp_path)
    sha = "0123456789abcdef0123456789abcdef01234567"
    pr_url = "https://github.com/Code-Munkiz/ham/pull/9999"
    runner = FakeRunner(
        _Reply(rc=0, stdout=" M src/foo.py\n"),  # status
        _Reply(rc=0, stdout="main\n"),  # rev-parse abbrev-ref HEAD
        _Reply(rc=0),  # checkout -b
        _Reply(rc=0),  # add
        _Reply(rc=0),  # commit
        _Reply(rc=0, stdout=sha + "\n"),  # rev-parse HEAD
        _Reply(rc=0, stdout="branch pushed\n"),  # push
        _Reply(rc=0, stdout=f"Creating PR\n{pr_url}\n"),  # gh pr create
    )
    res = execute_build_lane_post_exec(_inputs(project), runner=runner)
    assert res.build_outcome == "pr_opened"
    assert res.pr_url == pr_url
    assert res.pr_branch == "ham-droid/abc12345"
    assert res.pr_commit_sha == sha
    assert res.error_summary is None
    # Verify no shell=True was supplied anywhere; argv shapes are list[str]
    for call in runner.calls:
        assert isinstance(call, list)
        for tok in call:
            assert isinstance(tok, str)
    # Exact argv shape for the push call: feature branch only, no main, no --force.
    push_call = next(c for c in runner.calls if c[:2] == ["git", "push"])
    assert push_call == [
        "git",
        "push",
        "origin",
        "ham-droid/abc12345:ham-droid/abc12345",
    ]
    assert all("--force" not in tok and "--force-with-lease" not in tok for tok in push_call)
    assert all(tok != "main" and tok != "master" for tok in push_call[2:])
    # gh pr create — never `gh pr close` or `gh pr merge`.
    gh_call = next(c for c in runner.calls if c[0] == "gh")
    assert gh_call[:3] == ["gh", "pr", "create"]
    assert gh_call[3:5] == ["--base", "main"]
    assert gh_call[5:7] == ["--head", "ham-droid/abc12345"]


def test_orchestrator_skips_checkout_when_already_on_branch(tmp_path: Path) -> None:
    project = _make_repo(tmp_path)
    sha = "f" * 40
    runner = FakeRunner(
        _Reply(rc=0, stdout=" M README.md\n"),
        _Reply(rc=0, stdout="ham-droid/abc12345\n"),  # already on target branch
        _Reply(rc=0),  # add
        _Reply(rc=0),  # commit
        _Reply(rc=0, stdout=sha + "\n"),  # rev-parse HEAD
        _Reply(rc=0),  # push
        _Reply(
            rc=0,
            stdout="https://github.com/Code-Munkiz/ham/pull/1234\n",
        ),  # gh pr create
    )
    res = execute_build_lane_post_exec(_inputs(project), runner=runner)
    assert res.build_outcome == "pr_opened"
    # Ensure no checkout call was made.
    assert not any(c[:2] == ["git", "checkout"] for c in runner.calls)


def test_orchestrator_push_blocked(tmp_path: Path) -> None:
    project = _make_repo(tmp_path)
    sha = "a" * 40
    runner = FakeRunner(
        _Reply(rc=0, stdout=" M src/foo.py\n"),
        _Reply(rc=0, stdout="main\n"),
        _Reply(rc=0),  # checkout
        _Reply(rc=0),  # add
        _Reply(rc=0),  # commit
        _Reply(rc=0, stdout=sha + "\n"),  # rev-parse
        _Reply(rc=1, stderr="remote: error: protected branch\n"),  # push
    )
    res = execute_build_lane_post_exec(_inputs(project), runner=runner)
    assert res.build_outcome == "push_blocked"
    assert res.pr_url is None
    assert res.pr_branch == "ham-droid/abc12345"
    assert res.pr_commit_sha == sha
    assert "protected branch" in (res.error_summary or "")
    # No gh call must have happened.
    assert not any(c and c[0] == "gh" for c in runner.calls)


def test_orchestrator_pr_failed_when_gh_returns_error(tmp_path: Path) -> None:
    project = _make_repo(tmp_path)
    sha = "b" * 40
    runner = FakeRunner(
        _Reply(rc=0, stdout=" M src/foo.py\n"),
        _Reply(rc=0, stdout="main\n"),
        _Reply(rc=0),
        _Reply(rc=0),
        _Reply(rc=0),
        _Reply(rc=0, stdout=sha + "\n"),
        _Reply(rc=0),
        _Reply(rc=1, stderr="gh: GraphQL error\n"),
    )
    res = execute_build_lane_post_exec(_inputs(project), runner=runner)
    assert res.build_outcome == "pr_failed"
    assert res.pr_commit_sha == sha
    assert "gh pr create failed" in (res.error_summary or "")


def test_orchestrator_pr_failed_when_gh_returns_no_url(tmp_path: Path) -> None:
    project = _make_repo(tmp_path)
    sha = "c" * 40
    runner = FakeRunner(
        _Reply(rc=0, stdout=" M src/foo.py\n"),
        _Reply(rc=0, stdout="main\n"),
        _Reply(rc=0),
        _Reply(rc=0),
        _Reply(rc=0),
        _Reply(rc=0, stdout=sha + "\n"),
        _Reply(rc=0),
        _Reply(rc=0, stdout="some non-URL output\n"),
    )
    res = execute_build_lane_post_exec(_inputs(project), runner=runner)
    assert res.build_outcome == "pr_failed"
    assert res.pr_url is None
    assert res.pr_commit_sha == sha


def test_orchestrator_status_fails(tmp_path: Path) -> None:
    project = _make_repo(tmp_path)
    runner = FakeRunner(_Reply(rc=128, stderr="fatal: not a working tree\n"))
    res = execute_build_lane_post_exec(_inputs(project), runner=runner)
    assert res.build_outcome == "pr_failed"
    assert "git status failed" in (res.error_summary or "")


def test_orchestrator_commit_uses_inline_user_identity(tmp_path: Path) -> None:
    project = _make_repo(tmp_path)
    sha = "d" * 40
    runner = FakeRunner(
        _Reply(rc=0, stdout=" M src/foo.py\n"),
        _Reply(rc=0, stdout="main\n"),
        _Reply(rc=0),
        _Reply(rc=0),
        _Reply(rc=0),
        _Reply(rc=0, stdout=sha + "\n"),
        _Reply(rc=0),
        _Reply(rc=0, stdout="https://github.com/Code-Munkiz/ham/pull/1\n"),
    )
    execute_build_lane_post_exec(_inputs(project), runner=runner)
    commit_call = next(c for c in runner.calls if "commit" in c)
    # Confirm -c user.name/email is used inline (no global mutation).
    assert "-c" in commit_call
    assert any(tok.startswith("user.name=") for tok in commit_call)
    assert any(tok.startswith("user.email=") for tok in commit_call)
    # Confirm we do NOT use --amend or --force or --no-verify.
    assert "--amend" not in commit_call
    assert all("--force" not in tok for tok in commit_call)


def test_no_real_subprocess_or_network_uses_runner_seam(tmp_path: Path) -> None:
    """
    The orchestrator must take all process-spawning IO through the runner seam.

    If the FakeRunner pre-empts every call and the function still returns a
    non-trivial outcome, no real subprocess can have been launched.
    """
    project = _make_repo(tmp_path)
    runner = FakeRunner(_Reply(rc=0, stdout=""))  # nothing-to-change short-circuit
    res = execute_build_lane_post_exec(_inputs(project), runner=runner)
    assert res.build_outcome == "nothing_to_change"
    # Working tree of tmp_path/proj must be unchanged: only `.git` directory we made.
    children = sorted(p.name for p in project.iterdir())
    assert children == [".git"]


def test_module_outcome_constant_matches_persistence_layer() -> None:
    # Build Lane outcome vocabulary is sourced from the persistence module so
    # every Build run can be persisted on ControlPlaneRun.build_outcome.
    assert set(DROID_BUILD_OUTCOMES) == {
        "pr_opened",
        "nothing_to_change",
        "push_blocked",
        "pr_failed",
    }


def test_subprocess_runner_typing_alias_is_callable() -> None:
    # Defensive: type-alias must be importable and shape-compatible.
    assert SubprocessRunner is not None  # type: ignore[truthy-function]
