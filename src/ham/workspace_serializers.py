"""
Pure JSON shape helpers for Phase 1b workspace routes.

No I/O, no FastAPI imports — just dict-shaping. Centralizes response shapes
so contract tests can pin them once.
"""

from __future__ import annotations

import re
from typing import Any

from src.ham.workspace_models import (
    NAME_MAX_LEN,
    NAME_MIN_LEN,
    SLUG_MAX_LEN,
    WorkspaceContext,
    WorkspaceMember,
    WorkspaceRecord,
    WorkspaceRole,
    is_valid_slug,
)
from src.ham.workspace_perms import perms_for_role

# ---------------------------------------------------------------------------
# Slug derivation
# ---------------------------------------------------------------------------


_SLUGIFY_REPLACE_RE = re.compile(r"[^a-z0-9]+")
_SLUGIFY_TRIM_RE = re.compile(r"(^-+|-+$)")


def slugify_name(name: str) -> str:
    """Best-effort slug from a free-form workspace name.

    Lowercase, replaces runs of non-alnum with ``-``, trims leading/trailing
    hyphens, truncates to :data:`SLUG_MAX_LEN`. Returns ``""`` if the input
    has no alnum characters.
    """
    s = (name or "").lower().strip()
    s = _SLUGIFY_REPLACE_RE.sub("-", s)
    s = _SLUGIFY_TRIM_RE.sub("", s)
    return s[:SLUG_MAX_LEN]


def derive_unique_slug(
    base: str,
    *,
    is_taken: callable,  # type: ignore[type-arg]  # narrow callable
    max_attempts: int = 50,
) -> str | None:
    """Pick a slug not in ``is_taken``. Tries ``base``, ``base-2``, ``base-3`` …

    ``base`` should already be a valid slug. ``is_taken(slug) -> bool`` is
    typically ``lambda s: store.list_workspaces_for_user(...) ...``.

    Returns ``None`` if we can't find a unique slug within ``max_attempts``;
    the caller should surface ``HAM_WORKSPACE_SLUG_CONFLICT``.
    """
    if not is_valid_slug(base):
        return None
    if not is_taken(base):
        return base
    for n in range(2, max_attempts + 1):
        suffix = f"-{n}"
        candidate = base[: SLUG_MAX_LEN - len(suffix)] + suffix
        if is_valid_slug(candidate) and not is_taken(candidate):
            return candidate
    return None


# ---------------------------------------------------------------------------
# Email masking (used by member list)
# ---------------------------------------------------------------------------


def mask_email(email: str | None) -> str | None:
    """``alice@example.com`` → ``a****@example.com``. ``None`` passes through."""
    if not email or "@" not in email:
        return None
    local, _, domain = email.partition("@")
    if not local:
        return None
    if len(local) == 1:
        return f"{local}*@{domain}"
    return f"{local[0]}{'*' * (len(local) - 1)}@{domain}"


# ---------------------------------------------------------------------------
# Workspace record → response shapes
# ---------------------------------------------------------------------------


def workspace_summary(
    rec: WorkspaceRecord,
    *,
    role: WorkspaceRole,
    perms: frozenset[str] | set[str] | None = None,
    is_default: bool = False,
) -> dict[str, Any]:
    """Per-row shape returned by ``/api/me`` and ``/api/workspaces``."""
    effective_perms = sorted(perms) if perms is not None else sorted(perms_for_role(role))
    return {
        "workspace_id": rec.workspace_id,
        "org_id": rec.org_id,
        "name": rec.name,
        "slug": rec.slug,
        "description": rec.description,
        "status": rec.status,
        "role": role,
        "perms": effective_perms,
        "is_default": bool(is_default),
        "created_at": rec.created_at.isoformat(),
        "updated_at": rec.updated_at.isoformat(),
    }


def workspace_response(
    rec: WorkspaceRecord,
    ctx: WorkspaceContext,
    *,
    is_default: bool = False,
) -> dict[str, Any]:
    """Full single-workspace response for GET / PATCH / DELETE / POST."""
    return {
        "workspace": workspace_summary(
            rec,
            role=ctx.role,
            perms=ctx.perms,
            is_default=is_default,
        ),
        "context": {
            "role": ctx.role,
            "perms": sorted(ctx.perms),
            "org_role": ctx.org_role,
        },
    }


# ---------------------------------------------------------------------------
# Member list response shape
# ---------------------------------------------------------------------------


def member_response(
    member: WorkspaceMember,
    *,
    email: str | None = None,
) -> dict[str, Any]:
    return {
        "user_id": member.user_id,
        "role": member.role,
        "added_by": member.added_by,
        "added_at": member.added_at.isoformat(),
        "email_preview": mask_email(email),
    }


# ---------------------------------------------------------------------------
# Default workspace selection
# ---------------------------------------------------------------------------


def pick_default_workspace_id(
    summaries: list[dict[str, Any]],
) -> str | None:
    """Choose default from a list of summary dicts.

    Algorithm:
    1. Most-recently-updated active workspace where caller is owner.
    2. Most-recently-updated active workspace where caller is admin.
    3. Most-recently-updated active workspace.
    4. ``None`` if no active workspaces.
    """

    def _key(s: dict[str, Any]) -> str:
        return s.get("updated_at") or ""

    active = [s for s in summaries if s.get("status") == "active"]
    if not active:
        return None
    for role in ("owner", "admin"):
        candidates = [s for s in active if s.get("role") == role]
        if candidates:
            return max(candidates, key=_key)["workspace_id"]
    return max(active, key=_key)["workspace_id"]


# ---------------------------------------------------------------------------
# Body validation helpers
# ---------------------------------------------------------------------------


def validate_workspace_name(name: str) -> str | None:
    """Return None if valid; else error message."""
    if not isinstance(name, str):
        return "name must be a string"
    s = name.strip()
    if len(s) < NAME_MIN_LEN:
        return f"name must be at least {NAME_MIN_LEN} character"
    if len(s) > NAME_MAX_LEN:
        return f"name must be at most {NAME_MAX_LEN} characters"
    return None


__all__ = [
    "derive_unique_slug",
    "mask_email",
    "member_response",
    "pick_default_workspace_id",
    "slugify_name",
    "validate_workspace_name",
    "workspace_response",
    "workspace_summary",
]
