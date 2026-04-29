from __future__ import annotations

import os
import subprocess
from typing import Any

from src.ham.hermes_runtime_inventory import resolve_hermes_cli_binary

_VERSION_ARGV: tuple[str, ...] = ("--version",)
_TIMEOUT_S = 12.0


def fetch_hermes_cli_version_line() -> dict[str, Any]:
    """Allowlisted ``hermes --version`` only (no arbitrary subcommands)."""
    binary = resolve_hermes_cli_binary()
    if not binary:
        return {
            "status": "unavailable",
            "version_line": "",
            "warning": "Hermes CLI not found (PATH or HAM_HERMES_CLI_PATH).",
        }
    cmd = [binary, *_VERSION_ARGV]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            env=os.environ.copy(),
            shell=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {
            "status": "error",
            "version_line": "",
            "warning": str(exc)[:300],
        }
    out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    if proc.returncode != 0:
        return {
            "status": "error",
            "version_line": out[:500],
            "exit_code": proc.returncode,
        }
    return {"status": "ok", "version_line": out[:500]}
