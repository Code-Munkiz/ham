"""Tests for the HAMgomoon Hermes social critic (stub default)."""
from __future__ import annotations

from src.ham.hamgomoon_learning.hermes_critic import (
    SocialCritic,
    StubSocialCritic,
    get_default_social_critic,
)
from src.ham.hamgomoon_learning.models import HermesSocialCritique, SocialDraftRecord


def test_stub_critic_returns_full_critique() -> None:
    critic = StubSocialCritic()
    draft = SocialDraftRecord(draft_id="dx", channel="x", proposed_action="post", draft_text="hi")
    out = critic.critique(draft)
    assert isinstance(out, HermesSocialCritique)
    assert out.draft_id == "dx"
    assert 0.0 <= out.brand_fit_score <= 1.0
    assert 0.0 <= out.safety_score <= 1.0
    assert 0.0 <= out.clarity_score <= 1.0
    assert isinstance(out.risk_flags, list)
    assert out.engagement_hypothesis


def test_default_critic_is_stub() -> None:
    critic = get_default_social_critic()
    assert isinstance(critic, SocialCritic)
    assert isinstance(critic, StubSocialCritic)
