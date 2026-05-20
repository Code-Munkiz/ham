"""Read-side AutonomyProfile gates for one-shot social runners.

The run-once entry points use this module as a narrow adapter from the
file-backed profile store to the pure enforcement helper. Missing profiles are
treated as legacy/no-autonomy state so existing operator CLIs remain byte-equal
until the user explicitly configures the new autonomy envelope.
"""

from __future__ import annotations

from pathlib import Path

from src.ham.social_autonomy.enforcement import autonomy_reasons_for_apply
from src.ham.social_autonomy.schema import SocialAutonomyAction, SocialAutonomyChannel
from src.ham.social_autonomy.store import read_social_autonomy_profile, social_autonomy_path

_CHANNEL_DEFAULT_ACTIONS: dict[SocialAutonomyChannel, tuple[SocialAutonomyAction, ...]] = {
    "x": ("reply", "broadcast"),
    "telegram": ("reply", "activity", "message"),
    "discord": ("message",),
}


def autonomy_reasons_for_runner(
    *,
    channel: SocialAutonomyChannel,
    action: SocialAutonomyAction | None,
    root: Path | None = None,
) -> list[str]:
    """Return AutonomyProfile blockers for a one-shot runner.

    A missing profile document intentionally returns ``[]`` so a repo without a
    configured autonomy envelope preserves the legacy runner result exactly.
    """
    base = root or Path.cwd()
    if not social_autonomy_path(base).exists():
        return []

    profile = read_social_autonomy_profile(base)
    effective_action = action or _first_relevant_action(
        profile.actions_allowed_per_channel.get(channel, []), channel
    )
    return autonomy_reasons_for_apply(profile, channel=channel, action=effective_action)


def _first_relevant_action(
    allowed_actions: list[SocialAutonomyAction],
    channel: SocialAutonomyChannel,
) -> SocialAutonomyAction:
    allowed = set(allowed_actions)
    for candidate in _CHANNEL_DEFAULT_ACTIONS[channel]:
        if candidate in allowed:
            return candidate
    return _CHANNEL_DEFAULT_ACTIONS[channel][0]


__all__ = ["autonomy_reasons_for_runner"]
