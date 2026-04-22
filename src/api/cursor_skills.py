"""Operator skills catalog for dashboard chat control plane."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.cursor_skills_catalog import list_cursor_skills

router = APIRouter(tags=["control-plane"], dependencies=[Depends(get_ham_clerk_actor)])


@router.get("/api/cursor-skills")
async def get_cursor_skills() -> dict[str, Any]:
    """Ham `.cursor/skills` index (name + description). Subagent charters: ``GET /api/cursor-subagents``."""
    skills = list_cursor_skills()
    return {"skills": skills, "count": len(skills)}
