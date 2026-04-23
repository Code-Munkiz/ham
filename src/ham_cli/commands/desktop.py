"""ham desktop package — subprocess wrappers."""

from __future__ import annotations

import shutil
import subprocess

import typer

from src.ham_cli.util import err, find_repo_root

_PACK_LINUX = ["npm", "run", "pack:linux"]
_PACK_WIN = ["npm", "run", "pack:win"]


def _run_pack(script: str, npm_args: list[str]) -> None:
    repo = find_repo_root()
    if repo is None:
        err("Could not find HAM repo root (need desktop/package.json and src/api/server.py).")
        raise typer.Exit(code=1)

    desktop = repo / "desktop"
    if not (desktop / "package.json").is_file():
        err(f"Missing {desktop / 'package.json'}")
        raise typer.Exit(code=1)

    if shutil.which("npm") is None:
        err("npm not found on PATH. Install Node.js.")
        raise typer.Exit(code=1)

    typer.echo(f"Running in {desktop}: {' '.join(npm_args)}", err=False)
    proc = subprocess.run(npm_args, cwd=str(desktop), check=False)
    if proc.returncode != 0:
        err(f"npm exited with code {proc.returncode}.")
        if script == "win":
            err("Windows portable from Linux may need electron-builder; see desktop/README.md (NSIS needs Wine).")
        raise typer.Exit(code=proc.returncode)


def run_package_linux() -> None:
    """Build Linux AppImage/deb via electron-builder (same as npm run pack:linux)."""
    _run_pack("linux", _PACK_LINUX)


def run_package_win() -> None:
    """Build Windows portable via electron-builder (npm run pack:win)."""
    _run_pack("win", _PACK_WIN)
