"""Layout constraints for managed workspace working trees."""

from __future__ import annotations

import os
import re
from pathlib import Path

_REL_PART = re.compile(r"^[A-Za-z0-9_.\-]{1,400}$")


def ham_managed_workspace_root() -> Path:
    raw = (os.environ.get("HAM_MANAGED_WORKSPACE_ROOT") or "/srv/ham-workspaces").strip()
    return Path(raw).expanduser().resolve(strict=False)


def managed_working_dir(workspace_id: str, project_id: str) -> Path:
    wi = workspace_id.strip()
    pi = project_id.strip()
    if not wi or not pi or not _REL_PART.match(wi) or not _REL_PART.match(pi):
        raise ValueError("invalid workspace_id or project_id for managed workspace path")
    return ham_managed_workspace_root() / "managed" / wi / pi / "working"


def sanitize_rel_file_path(rel: str) -> str | None:
    """Return posix relative path or None if traversal or invalid."""
    if not rel or "\x00" in rel:
        return None
    p = Path(rel)
    if p.is_absolute():
        return None
    parts: list[str] = []
    for part in p.parts:
        if part in {".", ""}:
            continue
        if part == "..":
            return None
        if part == ".git" or part == ".ham":
            continue
        if not _REL_PART.match(part):
            return None
        parts.append(part)
    if not parts:
        return None
    return "/".join(parts)


def posix_paths_under(root: Path) -> dict[str, Path]:
    """Map sanitized relative posix path → absolute Path for snapshot walk."""
    out: dict[str, Path] = {}
    root = root.resolve(strict=False)
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_dir():
            continue
        try:
            rp = p.resolve(strict=False).relative_to(root)
        except ValueError:
            continue
        rel = sanitize_rel_file_path(str(rp).replace("\\", "/"))
        if rel:
            out[rel] = p
    return out
