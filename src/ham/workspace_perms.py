"""
Workspace role → permission table (Phase 1a — backend skeleton).

Pure constants and tiny helpers. No I/O, no Pydantic, no FastAPI.
Phase 1a only declares the catalogue; Phase 1b wires :func:`require_perm`
into routers.

Permission strings are namespaced (``resource:action``) so future phases can
extend additively without renaming existing strings:

- ``workspace:read``      — view workspace metadata.
- ``workspace:write``     — rename / update settings.
- ``workspace:admin``     — soft-archive, owner transfer (owner-only effect).
- ``member:read``         — list members.
- ``member:write``        — invite / remove / change role (Phase 1d).
- ``audit:read``          — read workspace audit feed (Phase 2+ surfaces it).

Future phases append more strings (e.g. ``chat:write``, ``artifact:write``,
``social_policy:write``); they must NOT remove any string declared here
without a deprecation cycle.

Org-role fallback: when the actor has no workspace-level membership row but
their Clerk ``org_id`` matches the workspace's ``org_id``, the resolver maps
the Clerk org role to a workspace role using :data:`ORG_ROLE_TO_WORKSPACE_ROLE`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:  # pragma: no cover
    from src.ham.workspace_models import WorkspaceContext, WorkspaceRole


# ---------------------------------------------------------------------------
# Permission catalogue (Phase 1a surface)
# ---------------------------------------------------------------------------

PERM_WORKSPACE_READ: Final[str] = "workspace:read"
PERM_WORKSPACE_WRITE: Final[str] = "workspace:write"
PERM_WORKSPACE_ADMIN: Final[str] = "workspace:admin"
PERM_MEMBER_READ: Final[str] = "member:read"
PERM_MEMBER_WRITE: Final[str] = "member:write"
PERM_AUDIT_READ: Final[str] = "audit:read"


# ---------------------------------------------------------------------------
# Role → permissions
# ---------------------------------------------------------------------------

# Note: declared as ``Mapping[str, frozenset[str]]`` (string-keyed) to keep this
# module free of pydantic-bound Literal at import time. The resolver always
# looks roles up via the ``WorkspaceRole`` literal type.
ROLE_PERMS: Final[Mapping[str, frozenset[str]]] = {
    "owner": frozenset(
        {
            PERM_WORKSPACE_READ,
            PERM_WORKSPACE_WRITE,
            PERM_WORKSPACE_ADMIN,
            PERM_MEMBER_READ,
            PERM_MEMBER_WRITE,
            PERM_AUDIT_READ,
        }
    ),
    "admin": frozenset(
        {
            PERM_WORKSPACE_READ,
            PERM_WORKSPACE_WRITE,
            PERM_MEMBER_READ,
            PERM_MEMBER_WRITE,
            PERM_AUDIT_READ,
        }
    ),
    "member": frozenset(
        {
            PERM_WORKSPACE_READ,
            PERM_MEMBER_READ,
        }
    ),
    "viewer": frozenset(
        {
            PERM_WORKSPACE_READ,
        }
    ),
}


# Mapping Clerk org-level role strings to HAM-native workspace roles.
# Used only when no workspace-level membership row exists and the workspace
# has a non-null ``org_id`` matching the actor's ``org_id``.
ORG_ROLE_TO_WORKSPACE_ROLE: Final[Mapping[str, WorkspaceRole]] = {
    "org:admin": "admin",
    "org:member": "member",
    "org:guest": "viewer",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def perms_for_role(role: WorkspaceRole) -> frozenset[str]:
    """Return the immutable permission set for a workspace role.

    Raises ``KeyError`` for unknown roles (defensive; should never trigger
    since callers receive a typed ``WorkspaceRole`` literal).
    """
    return ROLE_PERMS[role]


def map_org_role_to_workspace_role(org_role: str | None) -> WorkspaceRole:
    """Fallback when no workspace-level membership row exists.

    Unknown / missing org roles map to ``viewer`` (least privilege).
    """
    if not org_role:
        return "viewer"
    return ORG_ROLE_TO_WORKSPACE_ROLE.get(org_role, "viewer")


def has_perm(ctx: WorkspaceContext, perm: str) -> bool:
    """Permission predicate. Pure helper — no exception raised."""
    return perm in ctx.perms


__all__ = [
    "ORG_ROLE_TO_WORKSPACE_ROLE",
    "PERM_AUDIT_READ",
    "PERM_MEMBER_READ",
    "PERM_MEMBER_WRITE",
    "PERM_WORKSPACE_ADMIN",
    "PERM_WORKSPACE_READ",
    "PERM_WORKSPACE_WRITE",
    "ROLE_PERMS",
    "has_perm",
    "map_org_role_to_workspace_role",
    "perms_for_role",
]
