"""Stub adapter shape for future xAI/Grok-backed drafting."""
from __future__ import annotations

from src.ham.ham_x.action_envelope import SocialActionEnvelope
from src.ham.ham_x.audit import append_audit_event
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.safety_policy import check_social_action


def draft_social_action(
    *,
    target_summary: str,
    commentary_goal: str,
    input_ref: str | None = None,
    target_url: str | None = None,
    target_post_id: str | None = None,
    config: HamXConfig | None = None,
) -> SocialActionEnvelope:
    """Return a deterministic placeholder draft; no network calls in Phase 1A."""
    cfg = config or load_ham_x_config()
    text = (
        "Draft placeholder: add concise, relevant commentary after human review. "
        f"Target: {target_summary[:180]}. Goal: {commentary_goal[:180]}."
    )
    policy = check_social_action(text, action_type="draft")
    envelope = SocialActionEnvelope(
        action_type="draft",
        tenant_id=cfg.tenant_id,
        agent_id=cfg.agent_id,
        campaign_id=cfg.campaign_id,
        account_id=cfg.account_id,
        profile_id=cfg.profile_id,
        autonomy_mode=cfg.autonomy_mode,  # type: ignore[arg-type]
        policy_profile_id=cfg.policy_profile_id,
        brand_voice_id=cfg.brand_voice_id,
        catalog_skill_id=cfg.catalog_skill_id,
        dry_run=cfg.dry_run,
        autonomy_enabled=cfg.autonomy_enabled,
        input_ref=input_ref,
        target_url=target_url,
        target_post_id=target_post_id,
        text=text,
        model=cfg.model,
        policy_result=policy.model_dump(mode="json"),
        status="proposed" if policy.allowed else "rejected",
        reason="phase_1a_deterministic_placeholder",
        metadata={"network_calls": 0},
    )
    append_audit_event("draft_attempt", envelope.redacted_dump(), config=cfg)
    return envelope
