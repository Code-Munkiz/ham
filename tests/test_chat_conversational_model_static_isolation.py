"""VAL-LANE-011 — static structural lock: the conversational env var name MUST NOT appear
in shared helpers / non-chat modules.

Runs `rg --fixed-strings HAM_CHAT_CONVERSATIONAL_MODEL` via subprocess against the
seven forbidden files. Exits 1 (zero matches) → passes.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_FILES = (
    "src/llm_client.py",
    "src/integrations/nous_gateway_client.py",
    "src/ham/builder_edit_worker.py",
    "src/api/goham_planner.py",
    "src/ham/builder_chat_hooks.py",
    "src/hermes_feedback.py",
    "src/swarm_agency.py",
)


def test_conversational_env_token_not_in_shared_helpers() -> None:
    """`rg --fixed-strings HAM_CHAT_CONVERSATIONAL_MODEL` returns exit 1 over forbidden files."""
    rg = shutil.which("rg")
    if rg is None:
        pytest.skip("rg (ripgrep) is required for this structural guard")

    cmd = [rg, "--fixed-strings", "HAM_CHAT_CONVERSATIONAL_MODEL", *FORBIDDEN_FILES]
    result = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, (
        f"Expected rg exit 1 (zero matches); got {result.returncode}.\n"
        f"stdout=\n{result.stdout}\nstderr=\n{result.stderr}"
    )
    assert result.stdout == "", f"Unexpected matches: {result.stdout!r}"


def test_all_forbidden_files_exist() -> None:
    """Guard the guard: each forbidden path must exist so the rg sweep is meaningful."""
    for rel in FORBIDDEN_FILES:
        assert (REPO_ROOT / rel).is_file(), f"forbidden-file path missing: {rel}"
