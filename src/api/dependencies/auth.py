"""
FastAPI dependency for actor-only routes (Phase 1b).

Sibling to :mod:`src.api.dependencies.workspace`. Used by routes that don't
have a ``workspace_id`` path parameter (``/api/me``, ``GET /api/workspaces``,
``POST /api/workspaces``).

Auth semantics mirror :func:`require_workspace` exactly:

- Hosted (``HAM_CLERK_REQUIRE_AUTH=true``): a valid Clerk JWT is required.
- Local dev with ``HAM_LOCAL_DEV_WORKSPACE_BYPASS=true``: synthetic actor.
- Local dev without bypass: ``401 HAM_WORKSPACE_AUTH_REQUIRED``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.dependencies.workspace import resolve_actor_or_401
from src.ham.clerk_auth import HamActor


async def require_actor(
    actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> HamActor:
    """Return the authenticated :class:`HamActor` or raise ``401``."""
    return resolve_actor_or_401(actor)


__all__ = ["require_actor"]
