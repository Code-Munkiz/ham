"""Operator skills catalog for dashboard chat control plane."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.ham.cursor_skills_catalog import list_cursor_skills

router = APIRouter(tags=["control-plane"])


@router.get("/api/cursor-skills")
async def get_cursor_skills() -> dict[str, Any]:
    """Ham `.cursor/skills` index (name + description); subagent rules are not listed."""
    skills = list_cursor_skills()
    return {"skills": skills, "count": len(skills)}
