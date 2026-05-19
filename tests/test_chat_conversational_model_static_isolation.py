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


_HTTP_OVERRIDE_FORBIDDEN_FILES = (
    "src/ham/builder_edit_worker.py",
    "src/api/goham_planner.py",
    "src/ham/builder_chat_hooks.py",
    "src/hermes_feedback.py",
    "src/swarm_agency.py",
    "src/llm_client.py",
)

_HTTP_OVERRIDE_FORBIDDEN_DIRS = ("frontend", "desktop")


def test_http_model_override_identifier_stays_backend_only() -> None:
    """VAL-LANE-011 — `http_model_override` may only live in chat.py/gateway client/tests."""
    rg = shutil.which("rg")
    if rg is None:
        pytest.skip("rg (ripgrep) is required for this structural guard")

    cmd = [rg, "--fixed-strings", "http_model_override", *_HTTP_OVERRIDE_FORBIDDEN_FILES]
    result = subprocess.run(
        cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, check=False
    )
    assert result.returncode == 1, (
        f"Expected rg exit 1 (zero matches); got {result.returncode}.\n"
        f"stdout=\n{result.stdout}\nstderr=\n{result.stderr}"
    )
    assert result.stdout == "", f"Unexpected matches: {result.stdout!r}"


def test_no_frontend_builder_studio_conversational_lane_references() -> None:
    """VAL-LANE-012 — frontend/desktop trees must not reference the new identifiers."""
    rg = shutil.which("rg")
    if rg is None:
        pytest.skip("rg (ripgrep) is required for this structural guard")

    for token in ("HAM_CHAT_CONVERSATIONAL_MODEL", "http_model_override"):
        for d in _HTTP_OVERRIDE_FORBIDDEN_DIRS:
            target = REPO_ROOT / d
            if not target.exists():
                continue
            cmd = [rg, "--fixed-strings", token, str(target)]
            result = subprocess.run(
                cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, check=False
            )
            assert result.returncode == 1, (
                f"Expected rg exit 1 (zero matches) for {token!r} under {d}/; "
                f"got {result.returncode}.\nstdout=\n{result.stdout}\nstderr=\n{result.stderr}"
            )
