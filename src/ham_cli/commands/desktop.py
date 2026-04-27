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

_LC_PHASE2 = "policy_audit_kill_switch_only"


def _cli_local_control_policy_skeleton() -> dict[str, object]:
    return {
        "kind": "ham_cli_desktop_local_control_policy_skeleton",
        "schema_version": 1,
        "enabled": False,
        "phase": _LC_PHASE2,
        "default_deny": True,
        "allowlist_counts": {
            "browser_origins": 0,
            "filesystem_roots": 0,
            "shell_commands": 0,
            "mcp_servers": 0,
        },
        "permissions": {
            "browser_automation": False,
            "filesystem_access": False,
            "shell_commands": False,
            "app_window_control": False,
            "mcp_adapters": False,
        },
        "kill_switch": {"engaged": True, "reason": "default_disabled"},
        "note": "Live policy.json is under Electron userData; use HAM Desktop for persisted status.",
    }


def _cli_local_control_audit_skeleton() -> dict[str, object]:
    return {
        "kind": "ham_cli_desktop_local_control_audit_skeleton",
        "schema_version": 1,
        "phase": _LC_PHASE2,
        "note": "Redacted JSONL audit is appended only by HAM Desktop (main process).",
        "redacted": True,
    }


def _cli_local_control_sidecar_skeleton() -> dict[str, object]:
    return {
        "kind": "ham_cli_desktop_local_control_sidecar_skeleton",
        "expected": True,
        "implemented": False,
        "mode": "mock_status_only",
        "transport": "stdio_json_rpc_planned",
        "inbound_network": False,
        "running": False,
        "droid_access": "not_enabled",
        "capabilities": {
            "browser_automation": "not_implemented",
            "filesystem_access": "not_implemented",
            "shell_commands": "not_implemented",
            "app_window_control": "not_implemented",
            "mcp_adapters": "not_implemented",
        },
        "note": "Live sidecar is not started from CLI; HAM Desktop reports mock status only in Phase 3A.",
    }


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
        "schema_version": 3,
        "phase": _LC_PHASE2,
        "enabled": False,
        "spec_present": spec_present,
        "spec_relative_path": str(spec_rel).replace("\\", "/"),
        "platform": plat,
        "supported_platform": supported,
        "platform_status": platform_status,
        "policy": _cli_local_control_policy_skeleton(),
        "audit": _cli_local_control_audit_skeleton(),
        "kill_switch": {"engaged": True, "reason": "default_disabled"},
        "sidecar": _cli_local_control_sidecar_skeleton(),
        "note": "CLI checks repo spec + OS + static skeletons (incl. Phase 3A sidecar mock). HAM Desktop shows live IPC.",
    }
    if json_out:
        typer.echo(json.dumps(payload, indent=2))
        return

    typer.echo("Desktop Local Control — CLI doctor (read-only)")
    typer.echo(f"  Phase: {payload['phase']} · enabled: {payload['enabled']} (default)")
    typer.echo(f"  Spec {spec_rel}: {'present' if spec_present else 'missing'}")
    typer.echo(f"  Platform: {plat} · tier: {platform_status} · supported: {supported}")
    typer.echo("  Kill switch (CLI mirror): engaged · reason default_disabled")
    typer.echo(f"  {payload['note']}")


def run_desktop_local_control_policy(*, json_out: bool) -> None:
    """Static Phase 2 policy skeleton (no Electron userData access from CLI)."""
    p = _cli_local_control_policy_skeleton()
    if json_out:
        typer.echo(json.dumps(p, indent=2))
        return
    typer.echo("Desktop Local Control — policy skeleton (CLI mirror, read-only)")
    typer.echo(f"  Phase: {p['phase']} · enabled: {p['enabled']} · default_deny: {p['default_deny']}")
    typer.echo(f"  {p['note']}")


def run_desktop_local_control_audit(*, json_out: bool) -> None:
    """Static audit placeholder (live JSONL is desktop-only)."""
    a = _cli_local_control_audit_skeleton()
    if json_out:
        typer.echo(json.dumps(a, indent=2))
        return
    typer.echo("Desktop Local Control — audit (CLI placeholder)")
    typer.echo(f"  {a['note']}")


def run_desktop_local_control_kill_switch_engage() -> None:
    """Engage is desktop-only; CLI cannot persist Electron policy."""
    typer.echo(
        "Kill switch engage is not available from the CLI. "
        "Open HAM Desktop → Settings → HAM + Hermes setup → Engage kill switch.",
    )


def run_desktop_local_control_sidecar(*, json_out: bool) -> None:
    """Static Phase 3A sidecar mock (no Electron child process from CLI)."""
    s = _cli_local_control_sidecar_skeleton()
    if json_out:
        typer.echo(json.dumps(s, indent=2))
        return
    typer.echo("Desktop Local Control — sidecar (CLI mock, read-only)")
    typer.echo(f"  Mode: {s['mode']} · running: {s['running']} · transport: {s['transport']}")
    typer.echo(f"  Droid access: {s['droid_access']} · inbound network: {s['inbound_network']}")
    typer.echo(f"  {s['note']}")
