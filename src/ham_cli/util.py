"""Shared helpers for ham_cli."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Prefer operator-facing name; VITE_* only as fallback for dev machines.
_ENV_API_KEYS = ("HAM_API_BASE", "VITE_HAM_API_BASE")


def get_api_base() -> str | None:
    for key in _ENV_API_KEYS:
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw.rstrip("/")
    return None


def find_repo_root(start: Path | None = None) -> Path | None:
    """Directory that looks like the HAM repo root (has desktop/ and src/api/)."""
    cur = (start or Path.cwd()).resolve()
    for _ in range(12):
        desktop_pkg = cur / "desktop" / "package.json"
        server_py = cur / "src" / "api" / "server.py"
        if desktop_pkg.is_file() and server_py.is_file():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def emit_json(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True))


def err(msg: str) -> None:
    print(msg, file=sys.stderr)
