"""Pluggable Hermes-style social critic.

The default implementation is a deterministic stub. A future implementation
could route through :class:`src.hermes_feedback.HermesReviewer.evaluate(...)`
with a social-critic prompt variant (currently the reviewer prompt is
code-review oriented); leave that wiring for a follow-up — the contract here
is intentionally LLM-free so tests can inject a mock critic without touching
network.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.ham.hamgomoon_learning.models import HermesSocialCritique, SocialDraftRecord


@runtime_checkable
class SocialCritic(Protocol):
    def critique(self, draft: SocialDraftRecord) -> HermesSocialCritique:  # pragma: no cover - protocol
        ...


class StubSocialCritic:
    """Deterministic, offline-safe critic. Returns conservative high scores."""

    def critique(self, draft: SocialDraftRecord) -> HermesSocialCritique:
        return HermesSocialCritique(
            draft_id=draft.draft_id,
            brand_fit_score=0.9,
            safety_score=0.95,
            clarity_score=0.85,
            engagement_hypothesis="Stub critic: no live model used.",
            risk_flags=[],
            suggested_improvement=None,
            reusable_lesson="Keep drafts brief and persona-consistent.",
            policy_suggestion=None,
            should_update_strategy=False,
        )


def get_default_social_critic() -> SocialCritic:
    """Return the default critic. Tests monkeypatch this to inject mocks."""
    return StubSocialCritic()


__all__ = ["SocialCritic", "StubSocialCritic", "get_default_social_critic"]
