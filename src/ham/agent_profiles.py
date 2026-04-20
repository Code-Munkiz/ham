"""HAM agent profiles — project-scoped assistant identities (builder), distinct from Hermes runtime profiles."""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.ham.hermes_skills_catalog import list_catalog_entries

PRIMARY_AGENT_DEFAULT_ID = "ham.default"

_PROFILE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


class HamAgentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    skills: list[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("id")
    @classmethod
    def id_shape(cls, v: str) -> str:
        s = v.strip()
        if not _PROFILE_ID_RE.match(s):
            raise ValueError(
                "profile id must start with alphanumeric and contain only "
                "letters, digits, dot, underscore, hyphen (max 128 chars)",
            )
        return s

    @field_validator("skills")
    @classmethod
    def skills_items(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for raw in v:
            s = raw.strip()
            if not s:
                raise ValueError("skills entries must be non-empty strings")
            if len(s) > 512:
                raise ValueError("skill id too long (max 512)")
            if s in seen:
                raise ValueError(f"duplicate skill id in profile: {s!r}")
            seen.add(s)
            out.append(s)
        return out


class HamAgentsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profiles: list[HamAgentProfile] = Field(min_length=1)
    primary_agent_id: str = Field(min_length=1, max_length=128)


def default_agents_config() -> HamAgentsConfig:
    return HamAgentsConfig(
        profiles=[
            HamAgentProfile(
                id=PRIMARY_AGENT_DEFAULT_ID,
                name="HAM",
                description="Primary assistant",
                skills=[],
                enabled=True,
            )
        ],
        primary_agent_id=PRIMARY_AGENT_DEFAULT_ID,
    )


@lru_cache(maxsize=1)
def hermes_runtime_skill_catalog_ids() -> frozenset[str]:
    """Valid Hermes runtime catalog_ids for profile skill attachment validation."""
    return frozenset(str(e["catalog_id"]) for e in list_catalog_entries())


def validate_agents_config(
    cfg: HamAgentsConfig,
    *,
    validate_skill_catalog: bool = True,
) -> None:
    ids = [p.id for p in cfg.profiles]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate profile id in profiles list")
    if cfg.primary_agent_id not in ids:
        raise ValueError("primary_agent_id must match an existing profile id")
    if validate_skill_catalog:
        catalog = hermes_runtime_skill_catalog_ids()
        for p in cfg.profiles:
            for sid in p.skills:
                if sid not in catalog:
                    raise ValueError(f"unknown Hermes runtime skill catalog_id: {sid!r}")


def agents_config_from_merged(merged: dict[str, Any]) -> HamAgentsConfig:
    """Parse `agents` from merged Ham config; fall back to defaults if absent or invalid."""
    raw = merged.get("agents")
    if not isinstance(raw, dict):
        return default_agents_config()
    profiles_raw = raw.get("profiles")
    primary = raw.get("primary_agent_id")
    if not isinstance(profiles_raw, list) or not profiles_raw:
        return default_agents_config()
    if not isinstance(primary, str) or not primary.strip():
        return default_agents_config()
    try:
        profiles = [HamAgentProfile.model_validate(p) for p in profiles_raw]
        cfg = HamAgentsConfig(profiles=profiles, primary_agent_id=primary.strip())
        validate_agents_config(cfg, validate_skill_catalog=True)
        return cfg
    except Exception:
        return default_agents_config()
