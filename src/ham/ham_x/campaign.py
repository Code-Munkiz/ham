"""Campaign context helpers for HAM-on-X Phase 1B."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.config import HamXConfig, load_ham_x_config

CampaignRiskLevel = str

DEFAULT_CAMPAIGN_TOPICS = (
    "ham",
    "hermes",
    "base",
    "base ecosystem",
    "onchain",
    "builders",
    "autonomous agents",
)


class HamXCampaignConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    agent_id: str
    campaign_id: str
    account_id: str
    profile_id: str
    policy_profile_id: str
    brand_voice_id: str
    autonomy_mode: str
    catalog_skill_id: str
    risk_level: CampaignRiskLevel = "low"
    topics: list[str] = Field(default_factory=lambda: list(DEFAULT_CAMPAIGN_TOPICS))

    def platform_context(self) -> dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "campaign_id": self.campaign_id,
            "account_id": self.account_id,
            "profile_id": self.profile_id,
            "policy_profile_id": self.policy_profile_id,
            "brand_voice_id": self.brand_voice_id,
            "autonomy_mode": self.autonomy_mode,
            "catalog_skill_id": self.catalog_skill_id,
        }


def campaign_from_config(config: HamXConfig | None = None) -> HamXCampaignConfig:
    cfg = config or load_ham_x_config()
    return HamXCampaignConfig(
        tenant_id=cfg.tenant_id,
        agent_id=cfg.agent_id,
        campaign_id=cfg.campaign_id,
        account_id=cfg.account_id,
        profile_id=cfg.profile_id,
        policy_profile_id=cfg.policy_profile_id,
        brand_voice_id=cfg.brand_voice_id,
        autonomy_mode=cfg.autonomy_mode,
        catalog_skill_id=cfg.catalog_skill_id,
    )
