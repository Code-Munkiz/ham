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
