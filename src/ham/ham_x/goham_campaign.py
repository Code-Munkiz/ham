"""Campaign profile models for GoHAM Firehose control."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.campaign import DEFAULT_CAMPAIGN_TOPICS
from src.ham.ham_x.config import HamXConfig, load_ham_x_config

ActionType = Literal["post", "quote"]
RiskTolerance = Literal["low", "medium", "high"]


class GohamCampaignProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: str
    topics: list[str] = Field(default_factory=lambda: list(DEFAULT_CAMPAIGN_TOPICS))
    watch_queries: list[str] = Field(default_factory=list)
    forbidden_topics: list[str] = Field(default_factory=list)
    allowed_action_types: list[ActionType] = Field(default_factory=lambda: ["post"])
    daily_action_budget: int = 1
    max_posts_per_day: int = 1
    max_quotes_per_day: int = 0
    min_spacing_minutes: int = 120
    link_policy: bool = False
    risk_tolerance: RiskTolerance = "low"
    brand_voice_id: str
    active_hours: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)


def campaign_profile_from_config(config: HamXConfig | None = None) -> GohamCampaignProfile:
    cfg = config or load_ham_x_config()
    allowed = [
        item.strip()
        for item in (cfg.goham_allowed_actions or "post").split(",")
        if item.strip() in {"post", "quote"}
    ]
    return GohamCampaignProfile(
        campaign_id=cfg.campaign_id,
        watch_queries=[cfg.live_dry_run_query],
        allowed_action_types=allowed or ["post"],
        daily_action_budget=cfg.goham_max_total_actions_per_day,
        max_posts_per_day=cfg.goham_max_original_posts_per_day,
        max_quotes_per_day=cfg.goham_max_quotes_per_day,
        min_spacing_minutes=cfg.goham_min_spacing_minutes,
        link_policy=not cfg.goham_block_links,
        brand_voice_id=cfg.brand_voice_id,
        stop_conditions=[
            "emergency_stop",
            "daily_hard_stop",
            "provider_auth_stop",
            "consecutive_failure_stop",
        ],
    )
