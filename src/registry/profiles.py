from __future__ import annotations

import re
from typing import Any, Protocol

from pydantic import BaseModel, Field


class IntentProfile(BaseModel):
    id: str
    version: str = "1.0.0"
    argv: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProfileRegistry:
    def __init__(self, profiles: dict[str, IntentProfile]):
        self._profiles = profiles

    def get(self, profile_id: str) -> IntentProfile:
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise KeyError(f"Unknown profile_id: {profile_id}") from exc

    def ids(self) -> list[str]:
        return sorted(self._profiles.keys())


class Selector(Protocol):
    def select(self, prompt: str) -> str: ...


class KeywordSelector:
    def select(self, prompt: str) -> str:
        tokens = set(re.findall(r"[a-z0-9_]+", prompt.lower()))
        # Precedence is deliberate: status before diff. Do not reorder without updating tests.
        if "status" in tokens:
            return "inspect.git_status"
        if "diff" in tokens:
            return "inspect.git_diff"
        return "inspect.cwd"


DEFAULT_PROFILE_REGISTRY = ProfileRegistry(
    {
        "inspect.cwd": IntentProfile(
            id="inspect.cwd",
            version="1.0.0",
            argv=["python", "-c", "import os; print(os.getcwd())"],
            metadata={},
        ),
        "inspect.git_status": IntentProfile(
            id="inspect.git_status",
            version="1.0.0",
            argv=["git", "status", "--short"],
            metadata={},
        ),
        "inspect.git_diff": IntentProfile(
            id="inspect.git_diff",
            version="1.0.0",
            argv=["git", "diff", "--name-only"],
            metadata={},
        ),
    }
)
