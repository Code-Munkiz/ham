"""HAMgomoon Hermes learning loop (Path B: advisory + honest UI).

Greenfield package: bounded, redacted JSONL store of social drafts plus
optional Hermes-style critique. Never mutates apply paths, never weakens
existing live-gate stack, never persists secrets.
"""
from __future__ import annotations

from src.ham.hamgomoon_learning.context import render_hamgomoon_learning_hints
from src.ham.hamgomoon_learning.hermes_critic import (
    SocialCritic,
    StubSocialCritic,
    get_default_social_critic,
)
from src.ham.hamgomoon_learning.models import (
    DeliveryOutcome,
    HermesSocialCritique,
    LearningRecord,
    ReviewOutcome,
    SocialDraftRecord,
)
from src.ham.hamgomoon_learning.redaction import (
    redact_external_id,
    redact_learning_record,
    redact_text,
)
from src.ham.hamgomoon_learning.store import (
    append_learning_record,
    list_recent_learning_records,
    summarize_learning_hints,
)

__all__ = [
    "SocialDraftRecord",
    "ReviewOutcome",
    "DeliveryOutcome",
    "HermesSocialCritique",
    "LearningRecord",
    "redact_text",
    "redact_external_id",
    "redact_learning_record",
    "append_learning_record",
    "list_recent_learning_records",
    "summarize_learning_hints",
    "SocialCritic",
    "StubSocialCritic",
    "get_default_social_critic",
    "render_hamgomoon_learning_hints",
]
