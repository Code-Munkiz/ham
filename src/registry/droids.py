from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DroidRecord(BaseModel):
    id: str
    version: str = "1.0.0"
    name: str
    role: str
    description: str = ""
    model: str = "openrouter/nousresearch/hermes-3-llama-3.1-405b"
    provider: str = "openrouter"
    backend_id: str = "local.droid"
    metadata: dict[str, Any] = Field(default_factory=dict)


class DroidRegistry:
    def __init__(self, droids: dict[str, DroidRecord]) -> None:
        self._droids = droids

    def get(self, droid_id: str) -> DroidRecord:
        try:
            return self._droids[droid_id]
        except KeyError as exc:
            raise KeyError(f"Unknown droid_id: {droid_id!r}") from exc

    def ids(self) -> list[str]:
        return sorted(self._droids.keys())


DEFAULT_DROID_REGISTRY = DroidRegistry(
    {
        "droid.builder": DroidRecord(
            id="droid.builder",
            version="1.0.0",
            name="Builder",
            role="Code Implementation",
            description="Scaffolds, edits, and ships code changes. Primary execution droid for build tasks.",
            metadata={},
        ),
        "droid.reviewer": DroidRecord(
            id="droid.reviewer",
            version="1.0.0",
            name="Reviewer",
            role="Code Review",
            description="Audits diffs, flags policy violations, and validates output quality.",
            metadata={},
        ),
    }
)
