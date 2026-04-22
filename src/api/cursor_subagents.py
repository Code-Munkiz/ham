"""Cursor subagent rules catalog (read-only) for dashboard control plane."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.cursor_subagents_catalog import list_cursor_subagents

router = APIRouter(tags=["control-plane"], dependencies=[Depends(get_ham_clerk_actor)])


@router.get("/api/cursor-subagents")
async def get_cursor_subagents() -> dict[str, Any]:
    """Index of ``.cursor/rules/subagent-*.mdc`` (charter + metadata; not full rule bodies)."""
    subagents = list_cursor_subagents()
    return {"subagents": subagents, "count": len(subagents)}
