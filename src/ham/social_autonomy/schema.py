"""Pydantic schema for the GoHAM Social autonomy profile.

This module is intentionally pure schema: no HTTP wiring, persistence, provider
transport, or environment reads. The profile describes the user's autonomy
envelope; later layers decide how to persist and enforce it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

SocialAutonomyStatus = Literal["draft", "running", "paused", "stopped"]
SocialAutonomyChannel = Literal["x", "telegram", "discord"]
SocialAutonomyAction = Literal["reply", "broadcast", "activity", "message"]

NonNegativeStrictInt = Annotated[StrictInt, Field(ge=0)]
Hour = Annotated[StrictInt, Field(ge=0, le=23)]


def _datetime_is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


class SocialAutonomyChannelConfig(BaseModel):
    """Per-channel availability and enablement flags.

    ``available`` captures product capability. Discord remains unavailable in
    this mission, so :class:`GoHamSocialProfile` normalizes that slot to
    ``available=False`` and ``enabled=False`` when present.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    available: bool = True


class QuietHours(BaseModel):
    """Optional local quiet-hours window for autonomous activity."""

    model_config = ConfigDict(extra="forbid")

    start_hour: Hour
    end_hour: Hour
    timezone: str = Field(min_length=1, max_length=128)

    @field_validator("timezone")
    @classmethod
    def _strip_timezone(cls, value: str) -> str:
        timezone = value.strip()
        if not timezone:
            raise ValueError("quiet_hours.timezone must be non-empty.")
        return timezone


class SocialAutonomyTickSummary(BaseModel):
    """Persisted summary of the most recent autonomous social tick."""

    model_config = ConfigDict(extra="forbid")

    ran: bool
    dry_run: bool
    actions_considered: list[str]
    actions_taken: list[str]
    blocked_reasons: list[str]
    profile_status: SocialAutonomyStatus
    recorded_at: datetime
    next_run_summary: str | None = None

    @field_validator("recorded_at")
    @classmethod
    def _recorded_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if not _datetime_is_timezone_aware(value):
            raise ValueError("recorded_at must be timezone-aware.")
        return value

    @field_validator("blocked_reasons")
    @classmethod
    def _dedupe_blocked_reasons(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for reason in value:
            if reason in seen:
                continue
            seen.add(reason)
            out.append(reason)
        return out


class GoHamSocialProfile(BaseModel):
    """Persisted GoHAM Social autonomy envelope."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1, max_length=128)
    workspace_id: str | None = Field(default=None, min_length=1, max_length=128)
    project_id: str | None = Field(default=None, min_length=1, max_length=128)
    status: SocialAutonomyStatus
    goal: str = Field(min_length=1, max_length=2_000)
    persona_id: str = Field(min_length=1, max_length=128)
    channels: dict[SocialAutonomyChannel, SocialAutonomyChannelConfig]
    actions_allowed_per_channel: dict[SocialAutonomyChannel, list[SocialAutonomyAction]]
    daily_caps: dict[SocialAutonomyChannel, NonNegativeStrictInt]
    cadence: str = Field(min_length=1, max_length=128)
    quiet_hours: QuietHours | None = None
    forbidden_topics: list[str] = Field(max_length=64)
    safety_rules: list[str] = Field(max_length=64)
    learning_enabled: bool
    emergency_stop: bool
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    last_tick_summary: SocialAutonomyTickSummary | None = None

    @field_validator("profile_id", "workspace_id", "project_id", "goal", "persona_id", "cadence")
    @classmethod
    def _strip_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("string fields must be non-empty.")
        return text

    @field_validator("channels")
    @classmethod
    def _normalize_channel_capabilities(
        cls,
        value: dict[str, SocialAutonomyChannelConfig],
    ) -> dict[str, SocialAutonomyChannelConfig]:
        if "discord" in value:
            value = {
                **value,
                "discord": value["discord"].model_copy(
                    update={"available": False, "enabled": False},
                ),
            }
        return value

    @field_validator("actions_allowed_per_channel")
    @classmethod
    def _dedupe_actions(
        cls,
        value: dict[str, list[SocialAutonomyAction]],
    ) -> dict[str, list[SocialAutonomyAction]]:
        deduped: dict[str, list[SocialAutonomyAction]] = {}
        for channel, actions in value.items():
            seen: set[SocialAutonomyAction] = set()
            deduped[channel] = []
            for action in actions:
                if action in seen:
                    continue
                seen.add(action)
                deduped[channel].append(action)
        return deduped

    @field_validator("forbidden_topics", "safety_rules")
    @classmethod
    def _strip_and_dedupe_strings(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for raw in value:
            text = raw.strip()
            if not text:
                raise ValueError("list entries must be non-empty strings.")
            if text in seen:
                continue
            seen.add(text)
            out.append(text)
        return out

    @field_validator("last_run_at", "next_run_at")
    @classmethod
    def _tick_timestamps_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and not _datetime_is_timezone_aware(value):
            raise ValueError("last_run_at and next_run_at must be timezone-aware.")
        return value

    @model_validator(mode="after")
    def _coerce_emergency_stop_and_validate_timestamps(self) -> GoHamSocialProfile:
        if self.emergency_stop and self.status != "stopped":
            self.status = "stopped"
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be greater than or equal to created_at.")
        if self.last_run_at is not None and self.last_run_at > self.updated_at:
            raise ValueError("last_run_at must be less than or equal to updated_at.")
        return self


def profile_to_safe_dict(profile: GoHamSocialProfile) -> dict[str, Any]:
    """Return a JSON-serialisable autonomy profile snapshot."""
    return profile.model_dump(mode="json")
