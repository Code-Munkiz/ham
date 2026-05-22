"""
Mission 15 M2 lint and format baseline verification.

Asserts that the ruff lint finding count and the ruff format-check
file count do not exceed the M1 baselines established at mission start.

Assertions covered:
  - VAL-M15-M2-LINT-RUFF-CHECK-001  (ruff check ≤ 732 lines)
  - VAL-M15-M2-LINT-RUFF-FORMAT-001 (ruff format-check ≤ 433 files)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent

# Baselines measured after M2 commit (ruff check ≤ 731 findings; format ≤ 425 files).
# These are LOWER than the mission-start baselines of 732/433 because M2 also
# fixed several pre-existing lint/format issues introduced by M1.
_RUFF_CHECK_BASELINE_MAX: int = 731
_RUFF_FORMAT_BASELINE_MAX: int = 425


def test_ruff_check_at_or_below_baseline() -> None:
    """ruff lint finding count must not exceed the M2 baseline of 732 lines.

    Pass condition (VAL-M15-M2-LINT-RUFF-CHECK-001):
    ``.venv/bin/ruff check . --exclude browser-harness
    --output-format=concise | wc -l`` returns ≤ 732.
    """
    ruff_bin = _REPO_ROOT / ".venv" / "bin" / "ruff"
    result = subprocess.run(
        [
            str(ruff_bin),
            "check",
            ".",
            "--exclude",
            "browser-harness",
            "--output-format=concise",
        ],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        # ruff check exits non-zero when findings exist; that is expected.
    )
    # Count lines in stdout the same way ``wc -l`` does.
    line_count = len(result.stdout.splitlines())
    assert line_count <= _RUFF_CHECK_BASELINE_MAX, (
        f"ruff check finding count {line_count} exceeds baseline "
        f"{_RUFF_CHECK_BASELINE_MAX}.  "
        "New lint findings were introduced; please fix or update baseline."
    )


def test_ruff_format_at_or_below_baseline() -> None:
    """ruff format-check file count must not exceed the M2 baseline of 433 files.

    Pass condition (VAL-M15-M2-LINT-RUFF-FORMAT-001):
    ``.venv/bin/ruff format --check . --exclude browser-harness
    | grep -c 'Would reformat'`` returns ≤ 433.
    """
    ruff_bin = _REPO_ROOT / ".venv" / "bin" / "ruff"
    result = subprocess.run(
        [
            str(ruff_bin),
            "format",
            "--check",
            ".",
            "--exclude",
            "browser-harness",
        ],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        # ruff format --check exits non-zero when files would be reformatted.
    )
    # ruff format --check writes "Would reformat: <path>" to stdout.
    output = result.stdout + result.stderr
    would_reformat_count = sum(1 for line in output.splitlines() if "Would reformat" in line)
    assert would_reformat_count <= _RUFF_FORMAT_BASELINE_MAX, (
        f"ruff format-check count {would_reformat_count} exceeds baseline "
        f"{_RUFF_FORMAT_BASELINE_MAX}.  "
        "New unformatted files were introduced; please run ruff format or "
        "update the baseline."
    )
