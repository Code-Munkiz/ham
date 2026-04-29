"""ham doctor — local environment checks."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import httpx
import typer

from src.ham_cli.util import emit_json, find_repo_root, get_api_base


def _check_module(name: str) -> tuple[bool, str | None]:
    spec = importlib.util.find_spec(name)
    if spec is None:
        return False, f"module {name!r} not found (PYTHONPATH / venv?)"
    return True, None


def run_doctor(*, json_out: bool) -> None:
    repo = find_repo_root()
    py_ok = sys.version_info >= (3, 10)
    mod_ham, mod_err = _check_module("src.persistence.run_store")
    mod_api, _ = _check_module("src.api.server")

    desktop_dir = repo / "desktop" if repo else None
    desktop_ok = desktop_dir.is_dir() if desktop_dir else False
    pkg_json = (desktop_dir / "package.json").is_file() if desktop_dir else False

    import shutil

    node = shutil.which("node")
    npm = shutil.which("npm")
    fe_nm = (repo / "frontend" / "node_modules").is_dir() if repo else False
    de_nm = (desktop_dir / "node_modules").is_dir() if desktop_dir else False

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

    hints: list[str] = []
    if not py_ok:
        hints.append("Use Python 3.10+.")
    if repo is None:
        hints.append("Run from inside the HAM repo (or a subdirectory) so desktop/ and src/ can be found.")
    elif not mod_ham:
        hints.append("Activate the project venv and ensure repo root is on PYTHONPATH (pytest uses pythonpath=.).")
    if desktop_ok and not node:
        hints.append("Install Node.js to use ham desktop package.")
    if desktop_ok and node and not de_nm:
        hints.append("Run: cd desktop && npm install")
    if desktop_ok and not fe_nm:
        hints.append("Run: cd frontend && npm install (needed for desktop pack).")
    if api_base and api_reachable is False:
        hints.append("Fix HAM_API_BASE or bring the API up; see docs/DEPLOY_CLOUD_RUN.md.")

    payload: dict[str, Any] = {
        "python_ok": py_ok,
        "python": sys.version.split()[0],
        "repo_root": str(repo) if repo else None,
        "imports": {
            "src.persistence.run_store": mod_ham,
            "src.api.server": mod_api,
        },
        "import_error": mod_err,
        "desktop_dir_ok": desktop_ok,
        "desktop_package_json": pkg_json,
        "node_path": node,
        "npm_path": npm,
        "frontend_node_modules": fe_nm,
        "desktop_node_modules": de_nm,
        "ham_api_base_set": bool(api_base),
        "ham_api_base": api_base,
        "api_status_reachable": api_reachable,
        "api_status_error": api_error,
        "hints": hints,
        "ok": py_ok and mod_ham and (repo is not None) and desktop_ok and pkg_json,
    }

    if json_out:
        emit_json(payload)
        if not payload["ok"]:
            raise typer.Exit(code=1)
        return

    print("HAM doctor")
    print(f"  Python: {sys.version.split()[0]} {'OK' if py_ok else 'need 3.10+'}")
    print(f"  Repo root: {repo or 'not found'}")
    print(f"  Import src.persistence.run_store: {'OK' if mod_ham else 'FAIL'}")
    if mod_err:
        print(f"    {mod_err}")
    print(f"  Import src.api.server: {'OK' if mod_api else 'FAIL'}")
    print(f"  desktop/: {'OK' if desktop_ok else 'missing'}")
    print(f"  node: {node or 'not found'}")
    print(f"  npm: {npm or 'not found'}")
    print(f"  frontend/node_modules: {'OK' if fe_nm else 'missing'}")
    print(f"  desktop/node_modules: {'OK' if de_nm else 'missing'}")
    if api_base:
        print(f"  HAM_API_BASE: {api_base}")
        if api_reachable is True:
            print("  GET /api/status: OK")
        else:
            print(f"  GET /api/status: FAIL ({api_error})")
    else:
        print("  HAM_API_BASE: (unset — optional for local packaging)")

    if hints:
        print("\nNext steps:")
        for h in hints:
            print(f"  - {h}")

    if not payload["ok"]:
        raise typer.Exit(code=1)
