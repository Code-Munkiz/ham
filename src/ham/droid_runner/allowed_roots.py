"""HAM_DROID_RUNNER_ALLOWED_ROOTS enforcement (comma-separated absolute paths)."""

from __future__ import annotations

import os
from pathlib import Path


def load_allowed_roots_from_env() -> list[Path]:
    """
    Parse ``HAM_DROID_RUNNER_ALLOWED_ROOTS``: comma-separated paths.

    Only **absolute** paths (after expanduser) are kept; relative entries are ignored.
    Each root is ``resolve()``'d. Empty / unset env → empty list (no restriction).
    """
    raw = (os.environ.get("HAM_DROID_RUNNER_ALLOWED_ROOTS") or "").strip()
    if not raw:
        return []
    roots: list[Path] = []
    for part in raw.split(","):
        s = part.strip()
        if not s:
            continue
        p = Path(s).expanduser()
        if not p.is_absolute():
            continue
        try:
            roots.append(p.resolve())
        except OSError:
            continue
    return roots


def cwd_allowed_under_roots(resolved_cwd: Path, allowed_roots: list[Path]) -> bool:
    """True if ``resolved_cwd`` is exactly one root or a subdirectory (after resolve)."""
    if not allowed_roots:
        return True
    for root in allowed_roots:
        try:
            resolved_cwd.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def cwd_allowlist_violation_message(resolved_cwd: Path, allowed_roots: list[Path]) -> str | None:
    """Return a human reason if cwd is not under any allowed root; None if OK or no allowlist."""
    if not allowed_roots:
        return None
    if cwd_allowed_under_roots(resolved_cwd, allowed_roots):
        return None
    roots_txt = ", ".join(str(r) for r in allowed_roots[:8])
    if len(allowed_roots) > 8:
        roots_txt += ", …"
    return (
        f"cwd {resolved_cwd} is not contained under any allowed root "
        f"(HAM_DROID_RUNNER_ALLOWED_ROOTS). Allowed: {roots_txt}"
    )
