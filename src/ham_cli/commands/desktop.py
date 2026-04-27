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
_LC_PHASE4B_CLI = "browser_real_4b"


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
            "real_browser_automation": False,
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
        "implemented": True,
        "mode": "inert_process_shell",
        "transport": "stdio_json_rpc",
        "inbound_network": False,
        "running": False,
        "start_allowed": False,
        "blocked_reason": "kill_switch_engaged",
        "health": "unavailable",
        "droid_access": "not_enabled",
        "capabilities": {
            "browser_automation": "not_implemented",
            "filesystem_access": "not_implemented",
            "shell_commands": "not_implemented",
            "app_window_control": "not_implemented",
            "mcp_adapters": "not_implemented",
        },
        "note": "CLI mirror only. Live inert sidecar lifecycle (spawn/stdio) runs in HAM Desktop main, not via this CLI.",
    }


def _cli_local_control_browser_mvp_skeleton(*, platform_status: str) -> dict[str, object]:
    supported = platform_status == "linux_first"
    return {
        "kind": "ham_cli_desktop_local_control_browser_mvp_skeleton",
        "supported": supported,
        "armed": False,
        "allow_loopback": False,
        "session_running": False,
        "gate_blocked_reason": "kill_switch_engaged" if supported else "platform_not_supported",
        "note": "Live browser session is Electron main (HAM Desktop) only; CLI cannot start BrowserWindow.",
    }


def _cli_local_control_browser_real_skeleton(*, platform_status: str) -> dict[str, object]:
    supported = platform_status == "linux_first"
    return {
        "kind": "ham_cli_desktop_local_control_browser_real_skeleton",
        "supported": supported,
        "armed": False,
        "allow_loopback": False,
        "managed_profile": True,
        "cdp_localhost_only": True,
        "uses_default_profile": False,
        "session_running": False,
        "gate_blocked_reason": "kill_switch_engaged" if supported else "platform_not_supported",
        "note": "Managed Chromium + localhost CDP runs in HAM Desktop main only; CLI cannot spawn Chrome.",
    }


def _cli_sidecar_lifecycle_stub(operation: str) -> dict[str, object]:
    return {
        "kind": "ham_cli_desktop_local_control_sidecar_lifecycle",
        "ok": False,
        "available": False,
        "reason": "electron_only",
        "operation": operation,
        "note": "Sidecar start/stop/health IPC is implemented in HAM Desktop; CLI cannot attach without Electron.",
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
        "schema_version": 6,
        "phase": _LC_PHASE4B_CLI,
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
        "browser_mvp": _cli_local_control_browser_mvp_skeleton(platform_status=platform_status),
        "browser_real": _cli_local_control_browser_real_skeleton(platform_status=platform_status),
        "capabilities": {
            "browser_automation": "available_guarded" if platform_status == "linux_first" else "not_implemented",
            "real_browser_cdp": "available_guarded" if platform_status == "linux_first" else "not_implemented",
            "filesystem_access": "not_implemented",
            "shell_commands": "not_implemented",
            "app_window_control": "not_implemented",
            "mcp_adapters": "not_implemented",
        },
        "note": "CLI mirrors Phase 4B aggregate; HAM Desktop runs 4A embedded browser + 4B managed Chromium/CDP IPC + policy v3 on disk.",
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


def run_desktop_local_control_browser_status(*, json_out: bool) -> None:
    """Static browser MVP + real-browser mirror (no Electron)."""
    plat = sys.platform
    if plat.startswith("linux"):
        platform_status = "linux_first"
    elif plat == "win32":
        platform_status = "windows_planned"
    else:
        platform_status = "unsupported"
    bundle = {
        "kind": "ham_cli_desktop_local_control_browser_status_bundle",
        "browser_mvp": _cli_local_control_browser_mvp_skeleton(platform_status=platform_status),
        "browser_real": _cli_local_control_browser_real_skeleton(platform_status=platform_status),
    }
    if json_out:
        typer.echo(json.dumps(bundle, indent=2))
        return
    typer.echo("Desktop Local Control — browser (CLI mirror, read-only)")
    typer.echo(f"  4A embedded: {bundle['browser_mvp']['supported']} · gate: {bundle['browser_mvp']['gate_blocked_reason']}")
    typer.echo(f"  4B real CDP: {bundle['browser_real']['supported']} · gate: {bundle['browser_real']['gate_blocked_reason']}")
    typer.echo(f"  {bundle['browser_mvp']['note']}")


def run_desktop_local_control_sidecar(*, json_out: bool) -> None:
    """Static Phase 3B sidecar shape mirror (no Electron child process from CLI)."""
    s = _cli_local_control_sidecar_skeleton()
    if json_out:
        typer.echo(json.dumps(s, indent=2))
        return
    typer.echo("Desktop Local Control — sidecar (CLI mirror, read-only)")
    typer.echo(f"  Mode: {s['mode']} · running: {s['running']} · transport: {s['transport']}")
    typer.echo(f"  Start allowed: {s['start_allowed']} · blocked: {s.get('blocked_reason')}")
    typer.echo(f"  Droid access: {s['droid_access']} · inbound network: {s['inbound_network']}")
    typer.echo(f"  {s['note']}")


def run_desktop_local_control_sidecar_lifecycle(*, operation: str, json_out: bool) -> None:
    """Lifecycle is desktop-only; CLI returns an explicit stub."""
    p = _cli_sidecar_lifecycle_stub(operation)
    if json_out:
        typer.echo(json.dumps(p, indent=2))
        return
    typer.echo(f"Sidecar {operation}: not available from CLI (requires HAM Desktop).")
    typer.echo(f"  {p['note']}")
