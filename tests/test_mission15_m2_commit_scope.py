"""
Mission 15 M2 commit scope verification.

Asserts that the M2 commit touches only the expected paths and does NOT
touch ``frontend/``, ``desktop/``, ``docs/``, or ``.github/``.

Assertion covered: VAL-M15-M2-DEPLOY-COMMIT-001
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# The commit immediately before M2 work started (M2 F7 self-probe commit).
_PRE_M2_BASELINE_SHA = "0f97579ce2e5f817ad2a39c90545f03d65bbf171"

# Top-level path prefixes the M2 commit must NOT touch.
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


def test_m2_commit_only_touches_m2_paths() -> None:
    """All files changed after the pre-M2 baseline must be scoped to M2-related
    modules (src/ham/social*, src/api/social*, tests/) and must NOT touch
    ``frontend/``, ``desktop/``, ``docs/``, or ``.github/``.

    Pass condition (VAL-M15-M2-DEPLOY-COMMIT-001):
    ``git diff --name-only <pre_m2>..HEAD`` lists no files under the
    forbidden prefixes.
    """
    diff_output = _git(
        "diff",
        "--name-only",
        f"{_PRE_M2_BASELINE_SHA}..HEAD",
    )
    changed_files = [f.strip() for f in diff_output.splitlines() if f.strip()]

    assert changed_files, (
        "Expected at least one file to have changed since the pre-M2 "
        f"baseline ({_PRE_M2_BASELINE_SHA[:8]})."
    )

    forbidden_files = [
        f for f in changed_files if any(f.startswith(prefix) for prefix in _FORBIDDEN_PREFIXES)
    ]
    assert not forbidden_files, (
        "M2 commits touched forbidden path(s):\n"
        + "\n".join(f"  {f}" for f in forbidden_files)
        + f"\nAll forbidden prefixes: {_FORBIDDEN_PREFIXES}"
    )


def test_m2_head_is_on_main() -> None:
    """The current HEAD must be on the main branch (or reachable from origin/main
    once pushed).  This validates that we are not working on a side branch.

    VAL-M15-M2-DEPLOY-COMMIT-001 (branch discipline)
    """
    branch_output = _git("rev-parse", "--abbrev-ref", "HEAD").strip()
    assert branch_output == "main", f"Expected HEAD to be on 'main', but found: {branch_output!r}"
