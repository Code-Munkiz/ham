"""Security and collection behavior for native Hermes workspace file harvest."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from src.ham.hermes_workspace_execution import collect_workspace_files


@pytest.mark.skipif(sys.platform == "win32", reason="posix symlink test")
def test_collect_workspace_files_rejects_symlink_outside_root(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "src").mkdir()
    (workspace / ".env").write_text("SECRET=inside", encoding="utf-8")
    (workspace / "src" / "ok.ts").write_text("export {};\n", encoding="utf-8")
    try:
        os.symlink("../.env", workspace / "src" / "leak.ts")
    except OSError:
        pytest.skip("symlink not supported")
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("OUTSIDE=1", encoding="utf-8")
    try:
        os.symlink(str(outside), workspace / "src" / "escape.ts")
    except OSError:
        pytest.skip("symlink not supported")

    collected = collect_workspace_files(workspace)

    assert "src/ok.ts" in collected
    assert "src/leak.ts" not in collected
    assert "src/escape.ts" not in collected
    assert ".env" not in collected


def test_collect_workspace_files_includes_regular_files(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "index.html").write_text("<html></html>\n", encoding="utf-8")

    collected = collect_workspace_files(workspace)

    assert collected == {"index.html": "<html></html>\n"}