"""VAL-SAFETY-012 — every test that touches the conversational env var must use
monkeypatch-based env isolation. Bare `os.environ[VAR_NAME]` assignment statements
are forbidden across the `tests/` tree for the conversational var.

Asserted via ripgrep: zero matches → exit 1 → test passes.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"


def test_no_bare_env_assignment_for_conversational_var() -> None:
    """`rg -nE 'os\\.environ\\[["\\x27]HAM_CHAT_CONVERSATIONAL_MODEL["\\x27]\\]\\s*='` returns exit 1."""
    rg = shutil.which("rg")
    if rg is None:
        pytest.skip("rg (ripgrep) is required for this test-hygiene canary")

    pattern = r'os\.environ\[["\x27]HAM_CHAT_CONVERSATIONAL_MODEL["\x27]\]\s*='
    cmd = [rg, "-n", "-e", pattern, str(TESTS_DIR)]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, (
        f"Expected rg exit 1 (zero matches); got {result.returncode}.\n"
        f"stdout=\n{result.stdout}\nstderr=\n{result.stderr}"
    )
    assert result.stdout == "", f"Unexpected bare env assignments: {result.stdout!r}"
