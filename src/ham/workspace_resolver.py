"""
Resolve a Clerk :class:`HamActor` + workspace_id into a :class:`WorkspaceContext`
(Phase 1a — backend skeleton).

Pure logic — no FastAPI imports. Phase 1b wraps this in a FastAPI dep
(`require_workspace`).

Decision order
--------------

1. Workspace must exist and be ``status="active"`` → else :class:`WorkspaceNotFound`.
2. Workspace-level membership row (``workspaces/{wid}/members/{uid}``) wins.
3. Org-level fallback when ``workspace.org_id == actor.org_id`` and no
   membership row exists; map via :data:`workspace_perms.ORG_ROLE_TO_WORKSPACE_ROLE`.
4. Personal workspaces (``workspace.org_id is None``) only allow the
   ``owner_user_id``.
5. Otherwise :class:`WorkspaceForbidden`.

Permissions
-----------

Effective permissions = ``ROLE_PERMS[role]`` ∪ ``perms_from_clerk_workspaces_claim``.
The Clerk JWT custom claim can only **add** permissions; it cannot grant
access to a workspace the user has no membership row for (Firestore is the
source of truth — claim spoofing would still be blocked at step 4).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from src.ham.clerk_auth import HamActor
from src.ham.workspace_models import (
    WorkspaceContext,
    WorkspaceRecord,
    WorkspaceRole,
)
from src.ham.workspace_perms import (
    map_org_role_to_workspace_role,
    perms_for_role,
)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class WorkspaceResolveError(Exception):
    """Base error for resolver failures (carries an HTTP-shaped payload)."""

    code: str = "HAM_WORKSPACE_ERROR"
    status_code: int = 400

    def __init__(self, message: str, *, workspace_id: str | None = None) -> None:
        super().__init__(message)
        self.workspace_id = workspace_id

    def http_payload(self) -> dict[str, object]:
        return {
            "error": {
                "code": self.code,
                "message": str(self),
                **({"workspace_id": self.workspace_id} if self.workspace_id else {}),
            },
        }


class WorkspaceNotFound(WorkspaceResolveError):  # noqa: N818  # HTTP-404-shaped name
    code = "HAM_WORKSPACE_NOT_FOUND"
    status_code = 404


class WorkspaceForbidden(WorkspaceResolveError):  # noqa: N818  # HTTP-403-shaped name
    code = "HAM_WORKSPACE_FORBIDDEN"
    status_code = 403


# ---------------------------------------------------------------------------
# Narrow store interface (subset of WorkspaceStore the resolver needs)
# ---------------------------------------------------------------------------


class _ResolverStore(Protocol):
    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None: ...
    def get_member(self, workspace_id: str, user_id: str): ...  # WorkspaceMember | None


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def perms_from_clerk_workspaces_claim(
    actor: HamActor,
    workspace_id: str,
) -> frozenset[str]:
    """Read optional ``workspaces`` JWT claim of shape ``{wid: role|[perms]}``.

    Phase 1a treats values as advisory: if the claim is a string role, we map
    it via :func:`map_org_role_to_workspace_role`-like logic; if it is a list
    of permission strings, we accept it verbatim. Either way the claim cannot
    override the Firestore-backed access decision (steps 1–4 above) — it can
    only **expand** the perm set for an actor who already has access.
    """
    claim = getattr(actor, "workspaces_claim", None)
    if not isinstance(claim, Mapping):
        return frozenset()
    raw = claim.get(workspace_id)
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        # Treat as a role string; reuse the org-role mapping table for known
        # values (so ``"admin"`` / ``"member"`` / ``"viewer"`` work directly).
        if raw in {"owner", "admin", "member", "viewer"}:
            return perms_for_role(raw)  # type: ignore[arg-type]
        return frozenset()
    if isinstance(raw, (list, tuple, set, frozenset)):
        return frozenset(str(p) for p in raw if isinstance(p, str) and p)
    return frozenset()


def _decide_role(
    actor: HamActor,
    workspace: WorkspaceRecord,
    member,  # WorkspaceMember | None
) -> WorkspaceRole:
    if member is not None:
        return member.role
    if workspace.org_id is None:
        if actor.user_id == workspace.owner_user_id:
            return "owner"
        raise WorkspaceForbidden(
            "Personal workspaces are accessible only to their owner.",
            workspace_id=workspace.workspace_id,
        )
    if actor.org_id == workspace.org_id:
        return map_org_role_to_workspace_role(actor.org_role)
    raise WorkspaceForbidden(
        "Actor is not a member of this workspace's organization.",
        workspace_id=workspace.workspace_id,
    )


def resolve_workspace_context(
    actor: HamActor,
    workspace_id: str,
    store: _ResolverStore,
) -> WorkspaceContext:
    """Build a frozen :class:`WorkspaceContext` for a request.

    Raises :class:`WorkspaceNotFound` (404) or :class:`WorkspaceForbidden`
    (403). The caller (FastAPI dep in Phase 1b) translates those to
    :class:`fastapi.HTTPException`.
    """
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise WorkspaceForbidden("workspace_id is required.")
    workspace = store.get_workspace(workspace_id)
    if workspace is None or workspace.status != "active":
        raise WorkspaceNotFound(
            "Workspace not found or archived.",
            workspace_id=workspace_id,
        )
    member = store.get_member(workspace_id, actor.user_id)
    role = _decide_role(actor, workspace, member)
    base_perms = perms_for_role(role)
    extra_perms = perms_from_clerk_workspaces_claim(actor, workspace_id)
    perms = base_perms | extra_perms
    return WorkspaceContext(
        workspace_id=workspace_id,
        org_id=workspace.org_id,
        actor_user_id=actor.user_id,
        actor_email=actor.email,
        role=role,
        perms=perms,
        org_role=actor.org_role,
        raw={
            "membership_source": "workspace_member" if member else "org_fallback",
            "claim_source": actor.raw_permission_claim,
        },
    )


__all__ = [
    "WorkspaceForbidden",
    "WorkspaceNotFound",
    "WorkspaceResolveError",
    "perms_from_clerk_workspaces_claim",
    "resolve_workspace_context",
]
