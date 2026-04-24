"""ham status — local + optional remote summary."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import typer

from src.ham_cli.util import emit_json, find_repo_root, get_api_base
from src.persistence.run_store import RunStore


def run_status(*, json_out: bool, api_base: str | None) -> None:
    repo = find_repo_root()
    cwd = Path.cwd().resolve()

    local: dict[str, Any] = {
        "cwd": str(cwd),
        "repo_root": str(repo) if repo else None,
    }

    runs_count = 0
    runs_dir_exists = False
    if repo:
        store = RunStore(root=repo)
        runs_dir = repo / ".ham" / "runs"
        runs_dir_exists = runs_dir.is_dir()
        if runs_dir_exists:
            runs_count = len(store.list_runs(limit=10_000))

    cp_dir_raw = (os.environ.get("HAM_CONTROL_PLANE_RUNS_DIR") or "").strip()
    if cp_dir_raw:
        cp_path = Path(cp_dir_raw).expanduser()
    else:
        cp_path = Path.home() / ".ham" / "control_plane_runs"
    local["bridge_runs_dir"] = str(repo / ".ham" / "runs") if repo else None
    local["bridge_run_json_count"] = runs_count
    local["control_plane_runs_dir"] = str(cp_path)
    local["control_plane_runs_dir_exists"] = cp_path.is_dir()

    base = (api_base or "").strip().rstrip("/") or get_api_base()
    remote: dict[str, Any] | None = None
    if base:
        try:
            r = httpx.get(f"{base}/api/status", timeout=10.0)
            remote = {
                "ham_api_base": base,
                "http_status": r.status_code,
                "ok": r.is_success,
            }
            if r.is_success:
                try:
                    remote["body"] = r.json()
                except Exception:  # noqa: BLE001
                    remote["body"] = r.text[:2000]
            else:
                remote["error_body"] = r.text[:500]
        except Exception as exc:  # noqa: BLE001
            remote = {"ham_api_base": base, "ok": False, "error": str(exc)}

    out: dict[str, Any] = {"local": local, "remote": remote}

    if json_out:
        emit_json(out)
        if remote is not None and remote.get("ok") is False:
            raise typer.Exit(code=1)
        return

    print("HAM status")
    print(f"  cwd: {cwd}")
    print(f"  repo root: {repo or '(not detected)'}")
    if repo:
        print(f"  .ham/runs JSON files: {runs_count} (dir exists: {runs_dir_exists})")
    print(f"  control-plane runs dir: {cp_path} (exists: {cp_path.is_dir()})")

    if remote:
        print(f"  API {base}/api/status: ", end="")
        if remote.get("ok"):
            print("OK")
            body = remote.get("body")
            if isinstance(body, dict):
                cap = body.get("capabilities")
                if isinstance(cap, dict):
                    print(f"    capabilities keys: {', '.join(sorted(cap.keys())[:8])}{'…' if len(cap) > 8 else ''}")
        else:
            print("FAIL")
            if remote.get("error"):
                print(f"    {remote['error']}")
            elif remote.get("http_status"):
                print(f"    HTTP {remote['http_status']}")
    else:
        print("  API: (set HAM_API_BASE for remote status)")
