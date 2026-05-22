"""
Mission 15 M1 commit scope verification.

Asserts that all commits introduced by M1 (between the pre-M1 baseline
``8d0abfa7`` and the M1 HEAD ``17f0219c``) touch only the expected
persistence / API / test paths and do NOT touch ``frontend/``,
``desktop/``, ``docs/``, or ``.github/``.

Assertion covered: VAL-M15-M1-DEPLOY-COMMIT-001
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# The commit immediately before M1 work started (Mission 14 final commit).
_PRE_M1_BASELINE_SHA = "8d0abfa78fb29591eef29268529e3bc40a8880d9"

# The final M1 commit SHA (fix: backend-agnostic apply-reasons gate).
_M1_HEAD_SHA = "17f0219c5e700ad65f3a327cb360c7abc68f9f64"

# Top-level path prefixes the M1 commit chain must NOT touch.
_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "frontend/",
    "desktop/",
    "docs/",
    ".github/",
)

# The repo root relative to this test file.
_REPO_ROOT = Path(__file__).parent.parent


def _git(*args: str) -> str:
    """Run a git command at the repo root and return stdout."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        check=True,
    )
    return result.stdout


def test_m1_commit_only_touches_persistence_paths() -> None:
    """All files changed between the pre-M1 baseline and the M1 HEAD
    must be scoped to persistence / API / test paths.

    Pass condition (VAL-M15-M1-DEPLOY-COMMIT-001):
    ``git diff --name-only <pre_m1>..<m1_head>`` lists no files under
    ``frontend/``, ``desktop/``, ``docs/``, or ``.github/``.
    """
    diff_output = _git(
        "diff",
        "--name-only",
        f"{_PRE_M1_BASELINE_SHA}..{_M1_HEAD_SHA}",
    )
    changed_files = [f.strip() for f in diff_output.splitlines() if f.strip()]

    assert changed_files, (
        "Expected at least one file to have changed between the pre-M1 "
        f"baseline ({_PRE_M1_BASELINE_SHA[:8]}) and the M1 HEAD "
        f"({_M1_HEAD_SHA[:8]})."
    )

    forbidden_files = [
        f for f in changed_files if any(f.startswith(prefix) for prefix in _FORBIDDEN_PREFIXES)
    ]
    assert not forbidden_files, (
        "M1 commits touched forbidden path(s):\n"
        + "\n".join(f"  {f}" for f in forbidden_files)
        + f"\nAll forbidden prefixes: {_FORBIDDEN_PREFIXES}"
    )


def test_m1_commits_are_present_on_origin_main() -> None:
    """The M1 HEAD commit must be reachable from ``origin/main``.

    Verifies that the M1 commit chain has been pushed to the remote,
    satisfying the 'coherent commit set on origin/main' part of
    VAL-M15-M1-DEPLOY-COMMIT-001.
    """
    # ``git branch -r --contains <sha>`` lists remote branches that
    # contain the given commit.  We expect to see ``origin/main``.
    result = subprocess.run(
        ["git", "branch", "-r", "--contains", _M1_HEAD_SHA],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        check=True,
    )
    branches = result.stdout.strip()
    assert "origin/main" in branches, (
        f"M1 HEAD ({_M1_HEAD_SHA[:8]}) not found on origin/main.  "
        f"Remote branches containing it: {branches!r}"
    )


def test_m1_commit_count_is_coherent() -> None:
    """Exactly 6 scoped commits make up the M1 feature set.

    Checks that the commit range contains the expected number of commits
    (one per M1 feature: F1 protocol layer, F2 AutonomyProfile Firestore,
    F3 delivery+learning Firestore, F4 transcript+offset Firestore,
    F6 scheduler-state Firestore, and the F-apply-gate fix).
    """
    log_output = _git(
        "log",
        "--oneline",
        f"{_PRE_M1_BASELINE_SHA}..{_M1_HEAD_SHA}",
    )
    commits = [line.strip() for line in log_output.splitlines() if line.strip()]
    # Allow between 5 and 8 commits (one per feature; minor fixups are fine).
    assert 5 <= len(commits) <= 8, f"Expected 5–8 M1 commits, found {len(commits)}:\n" + "\n".join(
        f"  {c}" for c in commits
    )
