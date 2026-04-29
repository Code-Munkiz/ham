"""Read-only API for HAM :class:`ManagedMission` (managed Cloud Agent mission history)."""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor
from src.persistence.managed_mission import ManagedMission, ManagedMissionStore

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)

_store = ManagedMissionStore()

router = APIRouter(
    prefix="/api/cursor/managed",
    tags=["cursor-managed-missions"],
)


def _public_mission(m: ManagedMission) -> dict[str, Any]:
    d = m.model_dump(mode="json", exclude_none=False)
    d["kind"] = "managed_mission"
    d["latest_checkpoint"] = m.mission_checkpoint_latest
    d["latest_checkpoint_at"] = m.mission_checkpoint_updated_at
    d["latest_checkpoint_reason"] = m.mission_checkpoint_reason_last
    d["checkpoint_events"] = [
        e.model_dump(mode="json", exclude_none=False) for e in m.mission_checkpoint_events
    ]
    return d


@router.get("/missions")
async def list_managed_missions(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    limit: int = Query(50, ge=1, le=500, description="Max missions (newest by file mtime first)"),
    cursor_agent_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=512,
        description="When set, return at most one row for this Cursor agent if present",
    ),
) -> dict[str, Any]:
    if cursor_agent_id and str(cursor_agent_id).strip():
        ca = str(cursor_agent_id).strip()
        m = _store.find_by_cursor_agent_id(ca)
        rows = [m] if m else []
    else:
        rows = _store.list_newest_first(limit=limit)
    return {
        "kind": "managed_mission_list",
        "limit": limit,
        "missions": [_public_mission(x) for x in rows],
    }


@router.get("/missions/{mission_registry_id}")
async def get_managed_mission(
    mission_registry_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    mid = mission_registry_id.strip()
    if not _UUID_RE.match(mid):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Mission not found."}},
        )
    m = _store.get(mid)
    if m is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Mission not found."}},
        )
    return _public_mission(m)
