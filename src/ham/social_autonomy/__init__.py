"""GoHAM Social autonomy profile schema and state helpers."""

from src.ham.social_autonomy.enforcement import (
    AUTONOMY_ACTION_NOT_ALLOWED,
    AUTONOMY_APPLY_REASON_CODES,
    AUTONOMY_CHANNEL_DISABLED,
    AUTONOMY_DAILY_CAP_EXCEEDED,
    AUTONOMY_EMERGENCY_STOP,
    AUTONOMY_PROFILE_NOT_RUNNING,
    AUTONOMY_QUIET_HOURS_ACTIVE,
    autonomy_reasons_for_apply,
)
from src.ham.social_autonomy.schema import (
    GoHamSocialProfile,
    QuietHours,
    SocialAutonomyAction,
    SocialAutonomyChannel,
    SocialAutonomyChannelConfig,
    SocialAutonomyStatus,
)
from src.ham.social_autonomy.state import (
    AUTONOMY_INVALID_STATE_TRANSITION,
    AutonomyTransitionResult,
    transition_status,
    transition_to_paused,
    transition_to_running,
    transition_to_stopped,
)

__all__ = [
    "AUTONOMY_ACTION_NOT_ALLOWED",
    "AUTONOMY_APPLY_REASON_CODES",
    "AUTONOMY_CHANNEL_DISABLED",
    "AUTONOMY_DAILY_CAP_EXCEEDED",
    "AUTONOMY_EMERGENCY_STOP",
    "AUTONOMY_PROFILE_NOT_RUNNING",
    "AUTONOMY_QUIET_HOURS_ACTIVE",
    "AUTONOMY_INVALID_STATE_TRANSITION",
    "AutonomyTransitionResult",
    "GoHamSocialProfile",
    "QuietHours",
    "SocialAutonomyAction",
    "SocialAutonomyChannel",
    "SocialAutonomyChannelConfig",
    "SocialAutonomyStatus",
    "autonomy_reasons_for_apply",
    "transition_status",
    "transition_to_paused",
    "transition_to_running",
    "transition_to_stopped",
]
