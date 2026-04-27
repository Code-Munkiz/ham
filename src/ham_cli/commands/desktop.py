"""ham desktop package — subprocess wrappers."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

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


def run_desktop_local_control_status(*, json_out: bool) -> None:
    """Read-only doctor: spec on disk + OS tier. Does not start Electron or read userData."""
    repo = find_repo_root()
    spec_rel = Path("docs/desktop/local_control_v1.md")
    spec_present = bool(repo is not None and (repo / spec_rel).is_file())
    plat = sys.platform
    if plat.startswith("linux"):
        platform_status, supported = "linux_first", True
    elif plat == "win32":
        platform_status, supported = "windows_planned", True
    else:
        platform_status, supported = "unsupported", False

    payload = {
        "kind": "ham_cli_desktop_local_control_status",
        "schema_version": 1,
        "phase": "doctor_status_only",
        "enabled": False,
        "spec_present": spec_present,
        "spec_relative_path": str(spec_rel).replace("\\", "/"),
        "platform": plat,
        "supported_platform": supported,
        "platform_status": platform_status,
        "note": "CLI checks repo spec + OS only. HAM Desktop → Settings → HAM + Hermes setup shows live IPC status.",
    }
    if json_out:
        typer.echo(json.dumps(payload, indent=2))
        return

    typer.echo("Desktop Local Control — CLI doctor (read-only)")
    typer.echo(f"  Phase: {payload['phase']} · enabled: {payload['enabled']} (default)")
    typer.echo(f"  Spec {spec_rel}: {'present' if spec_present else 'missing'}")
    typer.echo(f"  Platform: {plat} · tier: {platform_status} · supported: {supported}")
    typer.echo(f"  {payload['note']}")
