"""
Read-only ``GET /api/coding/readiness``.

Phase 1 of the chat-first Coding Router: surfaces per-provider readiness +
project flags for the future conductor preview card. There is **no** launch
endpoint here; provider launches stay with their existing routes (Cursor
missions, ``/api/droid/preview`` + ``/launch``, ``/api/droid/build/preview``
+ ``/launch``).

Operator awareness:

- Non-operators receive ``available`` + normie-safe ``blockers`` only.
- Operators additionally receive ``operator_signals`` (e.g. ``runner_kind``,
  ``token_configured``, ``auth_kind``). Operator signals are still strictly
  boolean / coarse-label values — never secret values, runner URLs, env-name
  strings, or internal workflow ids.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor
from src.ham.clerk_operator import actor_is_workspace_operator
from src.ham.coding_router import collate_readiness

router = APIRouter(
    prefix="/api/coding",
    tags=["coding-router"],
    dependencies=[Depends(get_ham_clerk_actor)],
)


@router.get("/readiness")
async def get_coding_readiness(
    ham_actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    project_id: str | None = None,
) -> dict[str, Any]:
    """Return per-provider readiness + project flags. No secrets, no launch."""
    is_op = actor_is_workspace_operator(ham_actor)
    snapshot = collate_readiness(
        actor=ham_actor,
        project_id=project_id,
        include_operator_details=is_op,
    )
    return {
        "kind": "coding_readiness",
        **snapshot.public_dict(),
    }


__all__ = ["router"]
