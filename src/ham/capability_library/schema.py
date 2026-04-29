"""Pydantic models for ``.ham/capability-library/v1/index.json``."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "ham.capability_library.v1"

_REF_RE = re.compile(
    r"^(?P<kind>hermes|capdir):(?P<id>[a-zA-Z0-9][a-zA-Z0-9._-]{0,255})$"
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_ref(ref: str) -> tuple[Literal["hermes", "capdir"], str]:
    m = _REF_RE.match((ref or "").strip())
    if not m:
        raise ValueError(
            "ref must be like hermes:<catalog_id> or capdir:<directory_id> (alphanumeric, dot, _, -).",
        )
    return m.group("kind"), m.group("id")  # type: ignore[return-value]


class LibraryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=8, max_length=300)
    notes: str = Field(default="", max_length=4000)
    user_order: int = Field(default=0, ge=0, le=1_000_000)
    created_at: str = Field(default_factory=utc_now_iso, max_length=64)
    updated_at: str = Field(default_factory=utc_now_iso, max_length=64)

    @model_validator(mode="after")
    def _validate_ref(self) -> LibraryEntry:
        parse_ref(self.ref)
        return self


class CapabilityLibraryIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default=SCHEMA_VERSION,
        pattern=r"^ham\.capability_library\.v1$",
    )
    entries: list[LibraryEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_refs(self) -> CapabilityLibraryIndex:
        seen: set[str] = set()
        for e in self.entries:
            if e.ref in seen:
                raise ValueError(f"duplicate ref {e.ref!r}")
            seen.add(e.ref)
        return self

    @classmethod
    def from_disk(cls, data: dict[str, Any]) -> CapabilityLibraryIndex:
        if not data:
            return cls()
        return cls.model_validate(data)

    def ordered_entries(self) -> list[LibraryEntry]:
        return sorted(self.entries, key=lambda e: (e.user_order, e.ref))
