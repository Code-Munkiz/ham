"""Normalized HAM-on-X social action envelope."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.ham.ham_x.config import (
    DEFAULT_ACCOUNT_ID,
    DEFAULT_AGENT_ID,
    DEFAULT_AUTONOMY_MODE,
    DEFAULT_BRAND_VOICE_ID,
    DEFAULT_CAMPAIGN_ID,
    DEFAULT_POLICY_PROFILE_ID,
    DEFAULT_PROFILE_ID,
    DEFAULT_TENANT_ID,
)
from src.ham.ham_x.redaction import redact

ActionType = Literal["search", "draft", "quote", "post", "like", "reject", "queue"]
ActionStatus = Literal["proposed", "rejected", "queued", "approved", "executed", "failed"]
AutonomyMode = Literal["draft", "approval", "guarded", "goham"]

PLATFORM_CONTEXT_DEFAULTS: dict[str, str] = {
    "tenant_id": DEFAULT_TENANT_ID,
    "agent_id": DEFAULT_AGENT_ID,
    "campaign_id": DEFAULT_CAMPAIGN_ID,
    "account_id": DEFAULT_ACCOUNT_ID,
    "profile_id": DEFAULT_PROFILE_ID,
    "autonomy_mode": DEFAULT_AUTONOMY_MODE,
    "policy_profile_id": DEFAULT_POLICY_PROFILE_ID,
    "brand_voice_id": DEFAULT_BRAND_VOICE_ID,
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class SocialActionEnvelope(BaseModel):
    """Bounded, serializable description of a proposed X action."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action_type: ActionType
    created_at: str = Field(default_factory=utc_now_iso)
    tenant_id: str = DEFAULT_TENANT_ID
    agent_id: str = DEFAULT_AGENT_ID
    campaign_id: str = DEFAULT_CAMPAIGN_ID
    account_id: str = DEFAULT_ACCOUNT_ID
    profile_id: str = DEFAULT_PROFILE_ID
    autonomy_mode: AutonomyMode = DEFAULT_AUTONOMY_MODE
    policy_profile_id: str = DEFAULT_POLICY_PROFILE_ID
    brand_voice_id: str = DEFAULT_BRAND_VOICE_ID
    dry_run: bool = True
    autonomy_enabled: bool = False
    input_ref: str | None = None
    target_url: str | None = None
    target_post_id: str | None = None
    text: str | None = None
    model: str | None = None
    score: float | None = None
    reason: str | None = None
    policy_result: dict[str, Any] | None = None
    budget_result: dict[str, Any] | None = None
    rate_limit_result: dict[str, Any] | None = None
    status: ActionStatus = "proposed"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("score")
    @classmethod
    def _v_score(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return max(0.0, min(1.0, float(value)))

    def redacted_dump(self) -> dict[str, Any]:
        """Return a JSON-ready record with secrets masked."""
        return redact(self.model_dump(mode="json"))


def platform_context_from_config(config: Any | None = None) -> dict[str, str]:
    """Return platform context defaults, optionally populated from HamXConfig."""
    if config is None:
        return dict(PLATFORM_CONTEXT_DEFAULTS)
    return {
        "tenant_id": str(getattr(config, "tenant_id", DEFAULT_TENANT_ID) or DEFAULT_TENANT_ID),
        "agent_id": str(getattr(config, "agent_id", DEFAULT_AGENT_ID) or DEFAULT_AGENT_ID),
        "campaign_id": str(getattr(config, "campaign_id", DEFAULT_CAMPAIGN_ID) or DEFAULT_CAMPAIGN_ID),
        "account_id": str(getattr(config, "account_id", DEFAULT_ACCOUNT_ID) or DEFAULT_ACCOUNT_ID),
        "profile_id": str(getattr(config, "profile_id", DEFAULT_PROFILE_ID) or DEFAULT_PROFILE_ID),
        "autonomy_mode": str(
            getattr(config, "autonomy_mode", DEFAULT_AUTONOMY_MODE) or DEFAULT_AUTONOMY_MODE
        ),
        "policy_profile_id": str(
            getattr(config, "policy_profile_id", DEFAULT_POLICY_PROFILE_ID)
            or DEFAULT_POLICY_PROFILE_ID
        ),
        "brand_voice_id": str(
            getattr(config, "brand_voice_id", DEFAULT_BRAND_VOICE_ID) or DEFAULT_BRAND_VOICE_ID
        ),
    }


def apply_platform_context(record: dict[str, Any], config: Any | None = None) -> dict[str, Any]:
    """Ensure review/audit records carry tenant and agent context."""
    out = dict(record)
    for key, value in platform_context_from_config(config).items():
        out.setdefault(key, value)
    return out
