"""ham readiness — practical local checklist (no repo mutations)."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console
from rich.table import Table

from src.ham_cli.util import find_repo_root, get_api_base


def _module_ok(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _desktop_pack_scripts(repo: Path) -> tuple[bool, bool]:
    """Return (package_json_ok, has_pack_win)."""
    pkg = repo / "desktop" / "package.json"
    if not pkg.is_file():
        return False, False
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True, False
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return True, False
    return True, "pack:win" in scripts


def _git_branch_and_clean(repo: Path) -> tuple[str | None, bool | None, str | None]:
    """branch, is_clean (True/False/None unknown), error hint."""
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=8,
        )
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return None, None, "not a git work tree"
        br = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=8,
        )
        branch = br.stdout.strip() if br.returncode == 0 else None
        st = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=8,
        )
        if st.returncode != 0:
            return branch, None, None
        dirty = bool(st.stdout.strip())
        return branch, not dirty, None
    except (OSError, subprocess.TimeoutExpired):
        return None, None, "git unavailable"


def collect_readiness() -> dict[str, Any]:
    repo = find_repo_root()
    py_ok = sys.version_info >= (3, 10)
    mod_run = _module_ok("src.persistence.run_store")
    mod_api = _module_ok("src.api.server")
    imports_ok = mod_run and mod_api

    desktop_dir = repo / "desktop" if repo else None
    desktop_exists = desktop_dir.is_dir() if desktop_dir else False
    pkg_ok, has_win = _desktop_pack_scripts(repo) if repo else (False, False)
    scripts_ok = pkg_ok and has_win

    branch, clean, git_err = (None, None, None)
    if repo:
        branch, clean, git_err = _git_branch_and_clean(repo)

    api_base = get_api_base()
    api_reachable: bool | None = None
    api_error: str | None = None
    if api_base:
        try:
            r = httpx.get(f"{api_base}/api/status", timeout=10.0)
            api_reachable = r.is_success
            if not r.is_success:
                api_error = f"HTTP {r.status_code}"
        except Exception as exc:  # noqa: BLE001
            api_reachable = False
            api_error = str(exc)

    browser_runtime_router_ok = False
    hermes_cli_on_path: bool | None = None
    playwright_importable: bool | None = None
    if repo:
        browser_runtime_router_ok = (repo / "src" / "api" / "browser_runtime.py").is_file()
        hermes_cli_on_path = shutil.which("hermes") is not None
        playwright_importable = importlib.util.find_spec("playwright") is not None

    return {
        "python_ok": py_ok,
        "python": sys.version.split()[0],
        "imports_ok": imports_ok,
        "mod_run_store": mod_run,
        "mod_api_server": mod_api,
        "repo_root": str(repo) if repo else None,
        "desktop_dir_ok": desktop_exists,
        "desktop_package_json_ok": pkg_ok,
        "pack_win_script": has_win,
        "pack_scripts_ok": scripts_ok,
        "git_branch": branch,
        "git_clean": clean,
        "git_note": git_err,
        "ham_api_base": api_base,
        "api_reachable": api_reachable,
        "api_error": api_error,
        "browser_runtime_router_present": browser_runtime_router_ok,
        "hermes_cli_on_path": hermes_cli_on_path,
        "playwright_importable": playwright_importable,
    }


def run_readiness() -> None:
    data = collect_readiness()
    console = Console(highlight=False)

    table = Table(show_header=True, header_style="bold", title="HAM release readiness")
    table.add_column("Check", style="dim", no_wrap=True)
    table.add_column("Status")
    table.add_column("Detail", style="dim")

    def row(check: str, ok: bool | None, detail: str) -> None:
        if ok is True:
            st = "[green]OK[/green]"
        elif ok is False:
            st = "[red]Needs attention[/red]"
        else:
            st = "[yellow]—[/yellow]"
        table.add_row(check, st, detail)

    row(
        "Python 3.10+",
        data["python_ok"],
        data["python"],
    )
    row(
        "Required imports",
        data["imports_ok"],
        "run_store, api.server"
        if data["imports_ok"]
        else f"run_store={data['mod_run_store']}, api.server={data['mod_api_server']}",
    )
    row(
        "desktop/ directory",
        data["desktop_dir_ok"],
        "present" if data["desktop_dir_ok"] else "missing",
    )
    row(
        "Desktop pack scripts",
        data["pack_scripts_ok"],
        "pack:win in package.json"
        if data["pack_scripts_ok"]
        else (
            f"package.json ok={data['desktop_package_json_ok']}, "
            f"win={data['pack_win_script']}"
        ),
    )
    if data["repo_root"]:
        branch = data["git_branch"] or "?"
        clean = data["git_clean"]
        if data["git_note"]:
            row("Git", None, data["git_note"])
        elif clean is True:
            row("Git", True, f"branch {branch}, working tree clean")
        elif clean is False:
            row("Git", False, f"branch {branch}, working tree has local changes")
        else:
            row("Git", None, f"branch {branch}, could not determine cleanliness")
    else:
        row("Git", None, "repo root not detected from cwd")

    base = data["ham_api_base"]
    if not base:
        row("API base", None, "HAM_API_BASE unset (optional for local work)")
    elif data["api_reachable"] is True:
        row("API /api/status", True, base)
    else:
        err = data["api_error"] or "request failed"
        row("API /api/status", False, f"{base} — {err}")

    if data["repo_root"]:
        row(
            "Browser runtime module (repo)",
            data["browser_runtime_router_present"],
            "src/api/browser_runtime.py present"
            if data["browser_runtime_router_present"]
            else "expected router file missing",
        )
        hc = data["hermes_cli_on_path"]
        row(
            "Hermes CLI on PATH",
            hc,
            "hermes found" if hc else "not found (optional for inventory)",
        )
        pw = data["playwright_importable"]
        row(
            "Playwright Python package",
            pw,
            "importable (optional for API browser routes)"
            if pw
            else "not detected in this Python env",
        )
    else:
        row("Computer control readiness", None, "repo root not detected; skipped")

    row(
        "Computer Control Pack (Phase 1)",
        True,
        "directory-only; no execution; goHAM and MCP host future",
    )

    console.print(table)
    console.print(
        "\n[dim]Expert commands: ham doctor, ham status, ham api status — "
        "this view is a quick checklist only.[/dim]"
    )
