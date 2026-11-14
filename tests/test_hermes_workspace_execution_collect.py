"""Hermes native workspace file collection guardrails."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.ham.hermes_workspace_execution import collect_workspace_files


def test_collect_workspace_files_skips_symlinks_to_host_paths() -> None:
    with tempfile.TemporaryDirectory() as td:
        workspace = Path(td) / "workspace"
        workspace.mkdir()
        secret = Path(td) / "secret.txt"
        secret.write_text("TOPSECRET", encoding="utf-8")
        (workspace / "src").mkdir()
        (workspace / "src" / "App.tsx").write_text(
            "export default function App() { return null; }\n",
            encoding="utf-8",
        )
        (workspace / "src" / "leak.txt").symlink_to(secret)
        files = collect_workspace_files(workspace)
        assert "src/leak.txt" not in files
        assert "TOPSECRET" not in "".join(files.values())