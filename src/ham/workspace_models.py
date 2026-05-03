"""
Multi-user workspace primitives (Phase 1a — backend skeleton).

Pure data models + literal types. No I/O, no FastAPI imports, no Clerk imports.
These types are consumed by:

- ``src/persistence/workspace_store.py`` — pluggable storage backend (in-memory,
  file-backed, Firestore).
- ``src/ham/workspace_perms.py`` — role → permission table.
- ``src/ham/workspace_resolver.py`` — actor + workspace → ``WorkspaceContext``.
- ``src/api/dependencies/workspace.py`` — FastAPI deps (Phase 1b consumers).

Phase 1a is **additive only**. Nothing here is wired into existing routers,
the chat store, social policy, or any v1 endpoint. Local-dev mode (no
``HAM_CLERK_REQUIRE_AUTH``) is unaffected; these types are dormant until
Phase 1b registers the routers.

Hard contract — these documents must NEVER carry secret material:

- No ``token``, ``api_key``, ``access_token``, ``refresh_token``, or ``secret``
  field is allowed on any workspace mirror document.
- Provider credentials live in Google Secret Manager (Phase 3).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


WorkspaceRole = Literal["owner", "admin", "member", "viewer"]
"""HAM-native workspace role taxonomy.

Precedence (in :func:`workspace_resolver.resolve_workspace_context`):

1. Workspace-level membership row (``workspaces/{wid}/members/{uid}``) wins.
2. Org-level fallback maps ``org:admin`` → ``admin``, ``org:member`` →
   ``member``, ``org:guest`` → ``viewer``.
3. Personal workspaces (``org_id is None``) only allow the
   ``owner_user_id`` to access (resolves to ``owner``).
"""


WorkspaceStatus = Literal["active", "archived"]
"""Soft-delete is the only deletion mode in Phase 1a."""


# ---------------------------------------------------------------------------
# Validators / helpers
# ---------------------------------------------------------------------------


_SLUG_RE = re.compile(r"^[a-z0-9](?:-?[a-z0-9])*$")
SLUG_MIN_LEN = 1
SLUG_MAX_LEN = 48
NAME_MIN_LEN = 1
NAME_MAX_LEN = 80
DESCRIPTION_MAX_LEN = 2048
WORKSPACE_ID_PREFIX = "ws_"


def normalize_email(value: str | None) -> str | None:
    """Lower-case + trim; empty → ``None``. Matches :class:`HamActor` policy."""
    if value is None:
        return None
    s = str(value).strip().lower()
    return s or None


def is_valid_slug(value: str) -> bool:
    if not isinstance(value, str):
        return False
    if not (SLUG_MIN_LEN <= len(value) <= SLUG_MAX_LEN):
        return False
    return bool(_SLUG_RE.match(value))


def is_valid_workspace_id(value: str) -> bool:
    if not isinstance(value, str) or not value.startswith(WORKSPACE_ID_PREFIX):
        return False
    suffix = value[len(WORKSPACE_ID_PREFIX) :]
    return 8 <= len(suffix) <= 32 and suffix.isalnum() and suffix.islower()


# ---------------------------------------------------------------------------
# Records (mirror Firestore documents)
# ---------------------------------------------------------------------------


class _BaseRecord(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=False, frozen=False)


class UserRecord(_BaseRecord):
    """Mirror of a Clerk user. ``user_id`` is the Clerk ``sub`` claim."""

    user_id: str = Field(min_length=1, max_length=128)
    email: str | None = None
    display_name: str | None = Field(default=None, max_length=128)
    photo_url: str | None = Field(default=None, max_length=2048)
    primary_org_id: str | None = Field(default=None, max_length=128)
    created_at: datetime
    last_seen_at: datetime
    schema_version: int = 1

    @field_validator("email")
    @classmethod
    def _norm_email(cls, v: str | None) -> str | None:
        return normalize_email(v)


class OrgRecord(_BaseRecord):
    """Mirror of a Clerk organization. ``org_id`` is Clerk ``org_id`` claim."""

    org_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=NAME_MIN_LEN, max_length=NAME_MAX_LEN)
    clerk_slug: str = Field(min_length=1, max_length=128)
    created_at: datetime
    schema_version: int = 1


class MembershipRecord(_BaseRecord):
    """Org-level membership mirror (one per (user, org)).

    Distinct from :class:`WorkspaceMember` which is workspace-level.
    """

    user_id: str = Field(min_length=1, max_length=128)
    org_id: str = Field(min_length=1, max_length=128)
    org_role: str = Field(min_length=1, max_length=64)  # "org:admin" / "org:member" / "org:guest"
    joined_at: datetime
    schema_version: int = 1


class WorkspaceRecord(_BaseRecord):
    """A HAM workspace — the tenant boundary for all Phase 2+ stores.

    ``org_id is None`` denotes a *personal* workspace owned by ``owner_user_id``.
    Slug uniqueness is enforced at the store level on ``(org_id, slug)`` (or
    ``(owner_user_id, slug)`` for personal workspaces).
    """

    workspace_id: str
    org_id: str | None = Field(default=None, max_length=128)
    owner_user_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=NAME_MIN_LEN, max_length=NAME_MAX_LEN)
    slug: str
    description: str = Field(default="", max_length=DESCRIPTION_MAX_LEN)
    status: WorkspaceStatus = "active"
    created_by: str = Field(min_length=1, max_length=128)
    created_at: datetime
    updated_at: datetime
    schema_version: int = 1

    @field_validator("workspace_id")
    @classmethod
    def _check_workspace_id(cls, v: str) -> str:
        if not is_valid_workspace_id(v):
            msg = (
                f"workspace_id must start with {WORKSPACE_ID_PREFIX!r} and be 8–32 "
                "lowercase alphanumeric chars after the prefix."
            )
            raise ValueError(msg)
        return v

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, v: str) -> str:
        if not is_valid_slug(v):
            msg = (
                f"slug must match ^[a-z0-9](-?[a-z0-9])*$ and be {SLUG_MIN_LEN}–"
                f"{SLUG_MAX_LEN} chars."
            )
            raise ValueError(msg)
        return v


class WorkspaceMember(_BaseRecord):
    """Workspace-level role override (``workspaces/{wid}/members/{uid}``).

    When present, takes precedence over org-level role mapping in the resolver.
    """

    user_id: str = Field(min_length=1, max_length=128)
    workspace_id: str
    role: WorkspaceRole
    added_by: str = Field(min_length=1, max_length=128)
    added_at: datetime
    schema_version: int = 1

    @field_validator("workspace_id")
    @classmethod
    def _check_workspace_id(cls, v: str) -> str:
        if not is_valid_workspace_id(v):
            raise ValueError("workspace_id has invalid shape")
        return v


# ---------------------------------------------------------------------------
# Request / runtime context
# ---------------------------------------------------------------------------


class WorkspaceContext(BaseModel):
    """Per-request resolved tenant context.

    Built once by :func:`workspace_resolver.resolve_workspace_context` and
    threaded to handlers + stores via :func:`require_workspace`.
    Frozen so handlers cannot mutate the role/perm set after resolution.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    workspace_id: str
    org_id: str | None
    actor_user_id: str
    actor_email: str | None
    role: WorkspaceRole
    perms: frozenset[str]
    org_role: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    def has_perm(self, perm: str) -> bool:
        return perm in self.perms

    def attribution(self) -> dict[str, Any]:
        """Audit-row-friendly subset (no PII beyond email already used elsewhere)."""
        return {
            "workspace_id": self.workspace_id,
            "org_id": self.org_id,
            "user_id": self.actor_user_id,
            "email": self.actor_email,
            "role": self.role,
            "org_role": self.org_role,
            "perms": sorted(self.perms),
        }


__all__ = [
    "DESCRIPTION_MAX_LEN",
    "MembershipRecord",
    "NAME_MAX_LEN",
    "NAME_MIN_LEN",
    "OrgRecord",
    "SLUG_MAX_LEN",
    "SLUG_MIN_LEN",
    "UserRecord",
    "WORKSPACE_ID_PREFIX",
    "WorkspaceContext",
    "WorkspaceMember",
    "WorkspaceRecord",
    "WorkspaceRole",
    "WorkspaceStatus",
    "is_valid_slug",
    "is_valid_workspace_id",
    "normalize_email",
]
