"""Deny-by-default permission broker for ``opencode serve``.

Pure logic; no I/O. Tests exercise :func:`decide_permission` directly.

Policy summary:

- ``read``, ``glob``, ``grep``, ``list``, ``lsp``, ``todowrite`` → allow.
- ``edit``, ``skill`` → allow when the target path is inside the
  project root; deny otherwise.
- ``bash``, ``external_directory``, ``task`` → deny by default.
- ``webfetch``, ``websearch`` → deny (shorthand-only).
- Bash denylist patterns short-circuit to deny even when a future config
  loosens the default.
- HAM-side timeout (default 30s) yields ``deny`` from
  :func:`apply_timeout`.
"""

from __future__ import annotations

import fnmatch
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

PermissionDecision = Literal["allow", "deny", "ask"]

DEFAULT_ALLOW_CATEGORIES: frozenset[str] = frozenset(
    {"read", "glob", "grep", "list", "lsp", "todowrite"}
)
DEFAULT_DENY_CATEGORIES: frozenset[str] = frozenset(
    {"bash", "external_directory", "task", "webfetch", "websearch", "question", "doom_loop"}
)
REQUIRES_PROJECT_ROOT_SCOPING: frozenset[str] = frozenset({"edit", "skill"})

DEFAULT_BASH_DENYLIST: tuple[str, ...] = (
    "rm *",
    "rm -rf *",
    "rm -rf /",
    "find * -delete",
    "git push *",
    "git push --force*",
    "gcloud *",
    "kubectl *",
    "aws *",
    "ssh *",
    "scp *",
    "curl *",
    "wget *",
)

DEFAULT_PERMISSION_TIMEOUT_S: float = 30.0


@dataclass(frozen=True)
class PermissionContext:
    """Inputs the broker considers when deciding a permission request."""

    category: str
    project_root: Path
    target_path: str | None = None
    bash_command: str | None = None
    requested_at: float = 0.0


def _is_inside(root: Path, candidate: str) -> bool:
    try:
        target = Path(candidate)
        if not target.is_absolute():
            target = (root / target).resolve()
        else:
            target = target.resolve()
        root_resolved = root.resolve()
        return str(target).startswith(str(root_resolved) + "/") or target == root_resolved
    except (OSError, ValueError):
        return False


def _matches_bash_denylist(command: str, patterns: tuple[str, ...]) -> bool:
    cmd = (command or "").strip()
    if not cmd:
        return True
    for pat in patterns:
        if fnmatch.fnmatchcase(cmd, pat):
            return True
    return False


def decide_permission(
    ctx: PermissionContext,
    *,
    bash_denylist: tuple[str, ...] = DEFAULT_BASH_DENYLIST,
) -> tuple[PermissionDecision, str]:
    """Pure deny-by-default decision over one permission request."""
    category = (ctx.category or "").strip().lower()

    if category in DEFAULT_ALLOW_CATEGORIES:
        return "allow", "default_allow"

    if category in DEFAULT_DENY_CATEGORIES:
        if category == "bash":
            if not ctx.bash_command:
                return "deny", "bash_missing_command"
            if _matches_bash_denylist(ctx.bash_command, bash_denylist):
                return "deny", "bash_denylist_match"
            return "deny", "bash_default_deny"
        return "deny", f"{category}_default_deny"

    if category in REQUIRES_PROJECT_ROOT_SCOPING:
        if not ctx.target_path:
            return "deny", f"{category}_missing_path"
        if not _is_inside(ctx.project_root, ctx.target_path):
            return "deny", f"{category}_outside_project_root"
        return "allow", f"{category}_inside_project_root"

    return "deny", "unknown_category"


def apply_timeout(
    *,
    requested_at: float,
    now: float | None = None,
    timeout_s: float = DEFAULT_PERMISSION_TIMEOUT_S,
) -> tuple[PermissionDecision, str] | None:
    """If the request has been outstanding past ``timeout_s``, auto-deny.

    Returns ``None`` while the request is still within deadline.
    """
    current = now if now is not None else time.monotonic()
    if requested_at <= 0:
        return None
    if (current - requested_at) >= timeout_s:
        return "deny", "permission_timeout"
    return None


__all__ = [
    "DEFAULT_ALLOW_CATEGORIES",
    "DEFAULT_BASH_DENYLIST",
    "DEFAULT_DENY_CATEGORIES",
    "DEFAULT_PERMISSION_TIMEOUT_S",
    "PermissionContext",
    "PermissionDecision",
    "REQUIRES_PROJECT_ROOT_SCOPING",
    "apply_timeout",
    "decide_permission",
]
