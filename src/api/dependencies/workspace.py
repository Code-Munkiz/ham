"""
FastAPI dependency skeleton for workspace-scoped routes (Phase 1a).

Phase 1a does **not** mount any router that uses these deps; they are
imported only by tests and Phase 1b's ``/api/me`` and ``/api/workspaces``
routers.

Two deps:

- :func:`require_workspace` — resolves the path-bound ``workspace_id`` plus
  the calling :class:`HamActor` into a frozen :class:`WorkspaceContext`.
  In local-dev mode (``HAM_CLERK_REQUIRE_AUTH`` off **and**
  ``HAM_LOCAL_DEV_WORKSPACE_BYPASS=true``) a synthetic actor is used so
  developer flows keep working without Clerk.
- :func:`require_perm` — factory that returns a dep enforcing a permission
  string against the resolved :class:`WorkspaceContext`.

Local-dev semantics
-------------------

- If Clerk is not enforced (``HAM_CLERK_REQUIRE_AUTH != true``) **and**
  ``HAM_LOCAL_DEV_WORKSPACE_BYPASS=true``, calls without a JWT receive a
  synthetic ``HamActor(user_id="local_dev_user", ...)`` so v2 endpoints can
  be smoke-tested locally.
- If Clerk is not enforced and the bypass flag is **off**, callers must
  still send a Clerk JWT (or get 401). This is the safe default; the
  bypass is opt-in.
- If Clerk **is** enforced (hosted prod), only valid Clerk JWTs are
  accepted; the bypass flag is ignored.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Path

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor, clerk_operator_require_auth_enabled
from src.ham.workspace_models import WorkspaceContext
from src.ham.workspace_resolver import (
    WorkspaceForbidden,
    WorkspaceNotFound,
    WorkspaceResolveError,
    resolve_workspace_context,
)
from src.persistence.workspace_store import WorkspaceStore, build_workspace_store

LOCAL_DEV_BYPASS_ENV = "HAM_LOCAL_DEV_WORKSPACE_BYPASS"
LOCAL_DEV_USER_ID = "local_dev_user"
LOCAL_DEV_EMAIL = "dev@localhost"
LOCAL_DEV_ORG_ROLE = "org:admin"


# ---------------------------------------------------------------------------
# Local-dev synthetic actor
# ---------------------------------------------------------------------------


def _local_dev_bypass_enabled() -> bool:
    raw = (os.environ.get(LOCAL_DEV_BYPASS_ENV) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def synthetic_local_dev_actor() -> HamActor:
    """Stable synthetic actor used when local-dev bypass is on.

    Permissions intentionally include ``ham:admin`` so dev flows that gate on
    legacy operator-permission strings continue working; workspace-level
    permissions are derived through the resolver from the synthetic
    membership the dev seeded into the store (or from owner-of-personal-ws
    semantics).
    """
    return HamActor(
        user_id=LOCAL_DEV_USER_ID,
        org_id=None,
        session_id=None,
        email=LOCAL_DEV_EMAIL,
        permissions=frozenset({"ham:admin", "ham:launch", "ham:preview", "ham:status"}),
        org_role=LOCAL_DEV_ORG_ROLE,
        raw_permission_claim="local_dev_bypass",
    )


# ---------------------------------------------------------------------------
# Store accessor (overridable in tests)
# ---------------------------------------------------------------------------


_store_factory: Callable[[], WorkspaceStore] = build_workspace_store


def get_workspace_store() -> WorkspaceStore:
    """FastAPI dep: returns the configured :class:`WorkspaceStore`.

    Tests override via ``app.dependency_overrides[get_workspace_store] = ...``
    to inject a fresh :class:`InMemoryWorkspaceStore`. Phase 1a does not
    mount any app, so unit tests call this function indirectly via the
    resolver.
    """
    return _store_factory()


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def resolve_actor_or_401(actor: HamActor | None) -> HamActor:
    """Shared auth gate for both workspace-scoped (``require_workspace``) and
    actor-only (``require_actor``) routes.

    1. If Clerk required + actor missing → ``401 CLERK_SESSION_REQUIRED``.
    2. If Clerk not required + actor missing + bypass on → synthetic actor.
    3. If Clerk not required + actor missing + bypass off → ``401 HAM_WORKSPACE_AUTH_REQUIRED``.
    4. If actor present → return as-is (Clerk JWT verification already happened upstream).
    """
    if actor is not None:
        return actor
    if clerk_operator_require_auth_enabled():
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "CLERK_SESSION_REQUIRED",
                    "message": (
                        "Authorization: Bearer <Clerk session JWT> required for "
                        "workspace-scoped endpoints."
                    ),
                },
            },
        )
    if not _local_dev_bypass_enabled():
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "HAM_WORKSPACE_AUTH_REQUIRED",
                    "message": (
                        "No Clerk session and HAM_LOCAL_DEV_WORKSPACE_BYPASS is not set; "
                        "set HAM_LOCAL_DEV_WORKSPACE_BYPASS=true for local dev or send "
                        "a Clerk JWT."
                    ),
                },
            },
        )
    return synthetic_local_dev_actor()


async def require_workspace(
    workspace_id: Annotated[str, Path(min_length=1)],
    actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)] = None,  # type: ignore[assignment]
) -> WorkspaceContext:
    """Resolve a tenant-scoped :class:`WorkspaceContext`.

    Auth gating is delegated to :func:`resolve_actor_or_401`; the resolver
    then maps ``actor + workspace_id`` to a frozen ``WorkspaceContext`` or
    raises ``404 HAM_WORKSPACE_NOT_FOUND`` / ``403 HAM_WORKSPACE_FORBIDDEN``.
    """
    effective_actor = resolve_actor_or_401(actor)
    try:
        return resolve_workspace_context(effective_actor, workspace_id, store)
    except (WorkspaceForbidden, WorkspaceNotFound) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.http_payload()) from exc
    except WorkspaceResolveError as exc:  # pragma: no cover — defensive
        raise HTTPException(status_code=exc.status_code, detail=exc.http_payload()) from exc


def require_perm(perm: str) -> Callable[..., WorkspaceContext]:
    """Dep factory: enforces ``perm`` membership against the resolved context.

    Usage (Phase 1b)::

        @router.patch("/api/workspaces/{workspace_id}", dependencies=[Depends(require_perm("workspace:write"))])
        async def patch_workspace(...): ...
    """

    async def _dep(
        ctx: Annotated[WorkspaceContext, Depends(require_workspace)],
    ) -> WorkspaceContext:
        if perm not in ctx.perms:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "HAM_PERMISSION_DENIED",
                        "message": f"This action requires the {perm!r} permission.",
                        "required_perm": perm,
                        "actor_role": ctx.role,
                        "workspace_id": ctx.workspace_id,
                    },
                },
            )
        return ctx

    _dep.__name__ = f"require_perm__{perm.replace(':', '_')}"
    return _dep


__all__ = [
    "LOCAL_DEV_BYPASS_ENV",
    "LOCAL_DEV_EMAIL",
    "LOCAL_DEV_USER_ID",
    "get_workspace_store",
    "require_perm",
    "require_workspace",
    "resolve_actor_or_401",
    "synthetic_local_dev_actor",
]
