"""Custom Builder Studio — `CustomBuilderProfile` Pydantic model + helpers.

A Custom Builder is a named, reusable, coding-builder profile that a user
creates inside their HAM workspace. The profile binds a permission preset,
file scope, model source preference, and review behaviour on top of HAM's
existing ``opencode_cli`` lane. HAM remains the conductor; the builder is a
profile binding, not a new harness.

This module owns only the *data model* (validation + safe serialization).
Persistence lives in ``src.persistence.custom_builder_store``; API surfaces,
the OpenCode compiler, and the runtime are deferred to follow-up PRs.

Secret hygiene: ``model_ref`` is rejected if it looks like a raw secret
(``^[A-Za-z0-9]{32,}$``). ``public_dict`` is the seam used to scrub fields
listed in ``SECRET_PROHIBITED_FIELDS`` before serializing to operators or
non-operator clients. Today the set is empty; the helper exists so future
fields can be added without changing call sites.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.ham.coding_router.types import (
    ModelSourcePreference,
    ProviderKind,
    TaskKind,
)

PermissionPreset = Literal[
    "safe_docs",
    "app_build",
    "bug_fix",
    "refactor",
    "game_build",
    "test_write",
    "readonly_analyst",
    "custom",
]

ReviewMode = Literal["always", "on_mutation", "on_delete_only", "never"]
DeletionPolicy = Literal["deny", "require_review", "allow_with_warning"]
ExternalNetworkPolicy = Literal["deny", "ask", "allow"]

_BUILDER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_PATH_ENTRY_RE = re.compile(r"^[A-Za-z0-9._/*-]+$")
_INTENT_TAG_RE = re.compile(r"^[A-Za-z0-9._/*-]+$")
_OPERATION_ENTRY_RE = re.compile(r"^[A-Za-z0-9._/*-]+$")
_SECRET_LOOKING_RE = re.compile(r"^[A-Za-z0-9]{32,}$")

_MAX_ENTRY_LEN = 128
_MAX_TIMESTAMP_LEN = 64

SECRET_PROHIBITED_FIELDS: frozenset[str] = frozenset()


class CustomBuilderProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    builder_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$",
    )
    workspace_id: str = Field(min_length=1, max_length=128)
    owner_user_id: str = Field(min_length=1, max_length=128)

    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)
    intent_tags: list[str] = Field(default_factory=list, max_length=16)
    task_kinds: list[TaskKind] = Field(default_factory=list, max_length=16)

    preferred_harness: Literal["opencode_cli"] = "opencode_cli"
    allowed_harnesses: list[ProviderKind] = Field(
        default_factory=lambda: ["opencode_cli"],
    )

    model_source: ModelSourcePreference = "ham_default"
    model_ref: str | None = Field(default=None, max_length=256)

    permission_preset: PermissionPreset = "app_build"
    allowed_paths: list[str] = Field(default_factory=list, max_length=64)
    denied_paths: list[str] = Field(default_factory=list, max_length=64)
    denied_operations: list[str] = Field(default_factory=list, max_length=32)

    review_mode: ReviewMode = "on_mutation"
    deletion_policy: DeletionPolicy = "require_review"
    external_network_policy: ExternalNetworkPolicy = "deny"

    enabled: bool = True

    created_at: str = Field(min_length=1, max_length=_MAX_TIMESTAMP_LEN)
    updated_at: str = Field(min_length=1, max_length=_MAX_TIMESTAMP_LEN)
    updated_by: str = Field(min_length=1, max_length=128)

    @field_validator("builder_id")
    @classmethod
    def _builder_id_shape(cls, v: str) -> str:
        s = v.strip()
        if not _BUILDER_ID_RE.match(s):
            raise ValueError(
                "builder_id must start with a lowercase letter or digit and "
                "contain only lowercase letters, digits, underscore, or hyphen "
                "(max 64 chars)",
            )
        return s

    @field_validator("intent_tags")
    @classmethod
    def _intent_tags_shape(cls, v: list[str]) -> list[str]:
        for raw in v:
            if not isinstance(raw, str) or not raw:
                raise ValueError("intent_tags entries must be non-empty strings")
            if len(raw) > _MAX_ENTRY_LEN:
                raise ValueError(
                    f"intent_tag entry too long (max {_MAX_ENTRY_LEN} chars)",
                )
            if not _INTENT_TAG_RE.match(raw):
                raise ValueError(
                    "intent_tag entries may only contain letters, digits, "
                    "and the characters . _ / * -",
                )
        return v

    @field_validator("allowed_paths", "denied_paths")
    @classmethod
    def _path_entries_shape(cls, v: list[str]) -> list[str]:
        for raw in v:
            if not isinstance(raw, str) or not raw:
                raise ValueError("path entries must be non-empty strings")
            if len(raw) > _MAX_ENTRY_LEN:
                raise ValueError(
                    f"path entry too long (max {_MAX_ENTRY_LEN} chars)",
                )
            if not _PATH_ENTRY_RE.match(raw):
                raise ValueError(
                    "path entries may only contain letters, digits, and the characters . _ / * -",
                )
        return v

    @field_validator("denied_operations")
    @classmethod
    def _denied_operation_entries(cls, v: list[str]) -> list[str]:
        for raw in v:
            if not isinstance(raw, str) or not raw:
                raise ValueError("denied_operations entries must be non-empty strings")
            if len(raw) > _MAX_ENTRY_LEN:
                raise ValueError(
                    f"denied_operations entry too long (max {_MAX_ENTRY_LEN} chars)",
                )
            if not _OPERATION_ENTRY_RE.match(raw):
                raise ValueError(
                    "denied_operations entries may only contain letters, digits, "
                    "and the characters . _ / * -",
                )
        return v

    @field_validator("model_ref")
    @classmethod
    def _model_ref_not_secret(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if _SECRET_LOOKING_RE.match(v):
            raise ValueError(
                "model_ref looks like a raw secret. Use a model identifier "
                "such as 'openrouter/anthropic/claude-sonnet-4.6' or a "
                "BYOK reference like 'byok:<record-id>' instead.",
            )
        return v

    @model_validator(mode="after")
    def _cross_field_invariants(self) -> CustomBuilderProfile:
        if "opencode_cli" not in self.allowed_harnesses:
            raise ValueError(
                "allowed_harnesses must include 'opencode_cli' because "
                "preferred_harness is fixed to it in MVP",
            )
        if self.permission_preset == "custom" and not (
            self.allowed_paths or self.denied_paths or self.denied_operations
        ):
            raise ValueError(
                "custom preset requires at least one allowed_paths, "
                "denied_paths, or denied_operations entry",
            )
        return self


def validate_profile(profile: CustomBuilderProfile) -> None:
    """Re-validate an already-parsed :class:`CustomBuilderProfile`.

    Mirrors :func:`src.ham.agent_profiles.validate_agents_config` — callers
    that mutated a profile in-place (or constructed it from a dict bypassing
    Pydantic) can ask for the full invariant set without rebuilding the
    object themselves.
    """
    CustomBuilderProfile.model_validate(profile.model_dump())


def public_dict(profile: CustomBuilderProfile) -> dict[str, Any]:
    """Return a JSON-safe dict of the profile with prohibited fields stripped.

    The set of prohibited fields is currently empty; this helper exists so
    that future operator-only or secret-bearing fields can be added without
    changing call sites.
    """
    raw = profile.model_dump()
    if not SECRET_PROHIBITED_FIELDS:
        return raw
    return {k: v for k, v in raw.items() if k not in SECRET_PROHIBITED_FIELDS}


__all__ = [
    "SECRET_PROHIBITED_FIELDS",
    "CustomBuilderProfile",
    "DeletionPolicy",
    "ExternalNetworkPolicy",
    "PermissionPreset",
    "ReviewMode",
    "public_dict",
    "validate_profile",
]
