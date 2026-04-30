"""Read-only loader for versioned Social Persona specs."""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_PERSONA_DIR = Path(__file__).resolve().parent / "personas"
_ID_RE = re.compile(r"^[a-z][a-z0-9._-]{0,127}$")
_SECRETISH_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|bearer\s+[a-z0-9._~+/=-]{8,}|"
    r"sk-[a-z0-9_-]{10,}|[a-z0-9_./+=-]{48,})"
)


class PersonaExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str = Field(min_length=1, max_length=500)
    output: str = Field(min_length=1, max_length=1000)


class PersonaVocabulary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred: list[str] = Field(min_length=1, max_length=40)
    avoid: list[str] = Field(min_length=1, max_length=40)


class PlatformAdaptation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=80)
    style: str = Field(min_length=1, max_length=500)
    guidance: list[str] = Field(min_length=1, max_length=20)
    max_chars: int | None = Field(default=None, ge=1, le=4096)


class SocialPersona(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persona_id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    display_name: str = Field(min_length=1, max_length=120)
    short_bio: str = Field(min_length=1, max_length=500)
    mission: str = Field(min_length=1, max_length=1000)
    values: list[str] = Field(min_length=1, max_length=40)
    tone_rules: list[str] = Field(min_length=1, max_length=40)
    vocabulary: PersonaVocabulary
    humor_rules: list[str] = Field(min_length=1, max_length=20)
    emoji_rules: dict[str, str] = Field(min_length=1, max_length=20)
    platform_adaptations: dict[str, PlatformAdaptation]
    prohibited_content: list[str] = Field(min_length=1, max_length=40)
    safety_boundaries: list[str] = Field(min_length=1, max_length=40)
    example_replies: list[PersonaExample] = Field(min_length=1, max_length=20)
    example_announcements: list[str] = Field(min_length=1, max_length=20)
    refusal_examples: list[PersonaExample] = Field(min_length=1, max_length=20)

    @field_validator("persona_id")
    @classmethod
    def _valid_persona_id(cls, value: str) -> str:
        v = value.strip()
        if not _ID_RE.match(v):
            raise ValueError("persona_id must be lowercase slug-like")
        return v

    @model_validator(mode="after")
    def _platforms_required(self) -> "SocialPersona":
        required = {"x", "telegram", "discord"}
        missing = required - set(self.platform_adaptations)
        if missing:
            raise ValueError(f"missing platform adaptations: {sorted(missing)}")
        return self

    def canonical_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def persona_digest(persona: SocialPersona) -> str:
    raw = json.dumps(persona.canonical_dict(), sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _persona_path(persona_id: str, version: int) -> Path:
    return _PERSONA_DIR / f"{persona_id}.v{version}.yaml"


def _reject_secretish_values(value: Any, *, path: str = "persona") -> None:
    if isinstance(value, str):
        if _SECRETISH_RE.search(value):
            raise ValueError(f"secret-shaped value found at {path}")
        return
    if isinstance(value, list):
        for idx, item in enumerate(value):
            _reject_secretish_values(item, path=f"{path}[{idx}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_secretish_values(item, path=f"{path}.{key}")


@lru_cache(maxsize=16)
def load_social_persona(persona_id: str = "ham-canonical", version: int = 1) -> SocialPersona:
    path = _persona_path(persona_id, version)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"Social persona not found: {persona_id} v{version}") from exc
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError("Social persona root must be a mapping")
    _reject_secretish_values(data)
    persona = SocialPersona.model_validate(data)
    if persona.persona_id != persona_id or persona.version != version:
        raise ValueError("Social persona filename and content disagree")
    return persona
