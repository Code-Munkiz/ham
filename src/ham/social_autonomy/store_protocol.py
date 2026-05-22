"""GoHAM Social durable-store Protocol aggregator.

All six Protocol classes for the GoHAM Social persistence layer are
re-exported from this module so callers can import from a single location
regardless of where the Protocol is natively defined.

Native locations:
- :class:`SocialAutonomyStoreProtocol`      → :mod:`src.ham.social_autonomy.store`
- :class:`SocialDeliveryLogStoreProtocol`   → :mod:`src.ham.social_delivery_log`
- :class:`HamgomoonLearningStoreProtocol`   → :mod:`src.ham.hamgomoon_learning.store`
- :class:`TelegramTranscriptStoreProtocol`  → :mod:`src.ham.social_telegram_transcript_store`
- :class:`TelegramOffsetStoreProtocol`      → :mod:`src.ham.social_telegram_offset_store`
- :class:`SocialSchedulerStateStoreProtocol` + :class:`SocialSchedulerState`
    → :mod:`src.ham.social_scheduler_state_store`
"""

from __future__ import annotations

from src.ham.hamgomoon_learning.store import HamgomoonLearningStoreProtocol
from src.ham.social_autonomy.store import SocialAutonomyStoreProtocol
from src.ham.social_delivery_log import SocialDeliveryLogStoreProtocol
from src.ham.social_scheduler_state_store import (
    SocialSchedulerState,
    SocialSchedulerStateStoreProtocol,
)
from src.ham.social_telegram_offset_store import TelegramOffsetStoreProtocol
from src.ham.social_telegram_transcript_store import TelegramTranscriptStoreProtocol

__all__ = [
    "SocialAutonomyStoreProtocol",
    "SocialDeliveryLogStoreProtocol",
    "HamgomoonLearningStoreProtocol",
    "TelegramTranscriptStoreProtocol",
    "TelegramOffsetStoreProtocol",
    "SocialSchedulerStateStoreProtocol",
    "SocialSchedulerState",
]
