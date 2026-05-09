from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProjectRecord(BaseModel):
    id: str
    version: str = "1.0.0"
    name: str
    root: str
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Build Lane (Factory Droid mutating workflow) — disabled by default.
    # Stored persistently but not yet exposed through any router or UI.
    build_lane_enabled: bool = False
    github_repo: str | None = None
