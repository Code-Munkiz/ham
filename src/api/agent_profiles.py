"""Read API for HAM agent profiles (merged project config). Writes use settings preview/apply."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from src.ham.agent_profiles import agents_config_from_merged
from src.memory_heist import discover_config

router = APIRouter(tags=["agents"])


def _get_project_root(project_id: str) -> str:
    from src.api.server import get_project_store

    store = get_project_store()
    record = store.get_project(project_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PROJECT_NOT_FOUND",
                    "message": f"Unknown project_id {project_id!r}.",
                }
            },
        )
    return record.root


@router.get("/api/projects/{project_id}/agents")
async def get_project_agents(project_id: str) -> dict[str, Any]:
    """Effective HAM agent profiles from merged Ham config (see `.ham/settings.json` + chain)."""
    root = _get_project_root(project_id)
    merged = discover_config(Path(root)).merged
    cfg = agents_config_from_merged(merged)
    return {
        "kind": "ham_agent_profiles",
        "agents": cfg.model_dump(mode="json"),
    }
