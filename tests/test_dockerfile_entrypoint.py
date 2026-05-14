"""Drift detection for the ham-api image's PID-1 reaper (Mission 2.y).

OpenCode's ``opencode serve`` lane fans out subprocess tools (bash, MCP
servers). Cloud Run does not provide an init, so the container must
install a small reaper and put it on PID 1 to keep exited children
from becoming zombies. These assertions are pure-Python: they only
read the Dockerfile and the version-pin module — no Docker build, no
``tini`` execution.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.ham.opencode_runner import TINI_INSTALL_PATH
from src.ham.opencode_runner.version_pin import (
    TINI_INSTALL_PATH as PIN_TINI_INSTALL_PATH,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile"


def _dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def _dockerfile_lines() -> list[str]:
    return _dockerfile_text().splitlines()


def test_dockerfile_installs_tini() -> None:
    text = _dockerfile_text()
    install_lines = [
        line for line in text.splitlines() if "apt-get install" in line and "tini" in line
    ]
    assert install_lines, (
        "Dockerfile must apt-get install tini for the PID-1 reaper "
        "(Mission 2.y); no install line found."
    )
    assert any("--no-install-recommends" in line for line in install_lines), (
        "tini apt-get install must use --no-install-recommends to keep the image lean."
    )


def test_dockerfile_sets_entrypoint_to_tini() -> None:
    text = _dockerfile_text()
    entrypoint_lines = [line for line in text.splitlines() if line.startswith("ENTRYPOINT")]
    assert entrypoint_lines == ['ENTRYPOINT ["/usr/bin/tini", "--"]'], (
        "Dockerfile must declare exactly one ENTRYPOINT line of the form "
        '`ENTRYPOINT ["/usr/bin/tini", "--"]`; found '
        f"{entrypoint_lines!r}."
    )


def test_dockerfile_preserves_uvicorn_cmd() -> None:
    text = _dockerfile_text()
    cmd_lines = [line for line in text.splitlines() if line.startswith("CMD")]
    assert cmd_lines, "Dockerfile must keep a CMD line."
    assert any("uvicorn src.api.server:app" in line for line in cmd_lines), (
        "Dockerfile CMD must still launch `uvicorn src.api.server:app`; "
        f"found CMD lines: {cmd_lines!r}."
    )


def test_dockerfile_entrypoint_precedes_cmd() -> None:
    lines = _dockerfile_lines()
    entrypoint_indices = [idx for idx, line in enumerate(lines) if line.startswith("ENTRYPOINT")]
    cmd_indices = [idx for idx, line in enumerate(lines) if line.startswith("CMD")]
    assert entrypoint_indices, "Dockerfile must contain an ENTRYPOINT directive."
    assert cmd_indices, "Dockerfile must contain a CMD directive."
    assert entrypoint_indices[0] < cmd_indices[0], (
        "ENTRYPOINT must appear before CMD in the Dockerfile; "
        f"entrypoint_index={entrypoint_indices[0]}, "
        f"cmd_index={cmd_indices[0]}."
    )


def test_python_tini_pin_constant_re_exported() -> None:
    assert TINI_INSTALL_PATH == "/usr/bin/tini"
    assert PIN_TINI_INSTALL_PATH == TINI_INSTALL_PATH


def test_dockerfile_tini_install_path_matches_constant() -> None:
    text = _dockerfile_text()
    entrypoint_lines = [line for line in text.splitlines() if line.startswith("ENTRYPOINT")]
    assert entrypoint_lines, "Dockerfile must contain an ENTRYPOINT directive."
    assert all(TINI_INSTALL_PATH in line for line in entrypoint_lines), (
        f"Dockerfile ENTRYPOINT must reference TINI_INSTALL_PATH "
        f"({TINI_INSTALL_PATH!r}); found {entrypoint_lines!r}."
    )
    assert re.fullmatch(r"/[A-Za-z0-9_/.-]+", TINI_INSTALL_PATH), (
        f"TINI_INSTALL_PATH must be an absolute POSIX path, got {TINI_INSTALL_PATH!r}."
    )
