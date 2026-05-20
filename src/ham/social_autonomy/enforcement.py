"""Pure enforcement helpers for GoHAM Social autonomy profiles.

This module is intentionally side-effect free: callers pass in an already
loaded :class:`GoHamSocialProfile`, and the helper returns stable blocking
reason codes without reading environment files, touching persistence, importing
provider transports, or scheduling background work.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.ham.social_autonomy.schema import (
    GoHamSocialProfile,
    SocialAutonomyAction,
    SocialAutonomyChannel,
)

AUTONOMY_PROFILE_NOT_RUNNING: Final = "autonomy_profile_not_running"
AUTONOMY_CHANNEL_DISABLED: Final = "autonomy_channel_disabled"
AUTONOMY_ACTION_NOT_ALLOWED: Final = "autonomy_action_not_allowed"
AUTONOMY_EMERGENCY_STOP: Final = "autonomy_emergency_stop"
AUTONOMY_DAILY_CAP_EXCEEDED: Final = "autonomy_daily_cap_exceeded"
AUTONOMY_QUIET_HOURS_ACTIVE: Final = "autonomy_quiet_hours_active"

AUTONOMY_APPLY_REASON_CODES: Final[tuple[str, ...]] = (
    AUTONOMY_PROFILE_NOT_RUNNING,
    AUTONOMY_CHANNEL_DISABLED,
    AUTONOMY_ACTION_NOT_ALLOWED,
    AUTONOMY_EMERGENCY_STOP,
    AUTONOMY_DAILY_CAP_EXCEEDED,
    AUTONOMY_QUIET_HOURS_ACTIVE,
)

_REASON_ORDER: Final[tuple[str, ...]] = (
    AUTONOMY_EMERGENCY_STOP,
    AUTONOMY_PROFILE_NOT_RUNNING,
    AUTONOMY_CHANNEL_DISABLED,
    AUTONOMY_ACTION_NOT_ALLOWED,
    AUTONOMY_DAILY_CAP_EXCEEDED,
    AUTONOMY_QUIET_HOURS_ACTIVE,
)

_PREVIEW_DEFAULT_ACTIONS: Final[dict[SocialAutonomyChannel, SocialAutonomyAction]] = {
    "x": "reply",
    "telegram": "activity",
    "discord": "message",
}


def autonomy_reasons_for_apply(
    profile: GoHamSocialProfile,
    *,
    channel: SocialAutonomyChannel,
    action: SocialAutonomyAction,
) -> list[str]:
    """Return stable blocking codes for applying a social action.

    The helper is total for valid ``GoHamSocialProfile`` instances, including
    the store's default draft profile. It reports every applicable autonomy
    blocker in a fixed order, with ``autonomy_emergency_stop`` first whenever it
    applies, and never returns duplicates.
    """
    reasons: list[str] = []

    if bool(profile.emergency_stop):
        reasons.append(AUTONOMY_EMERGENCY_STOP)
    if profile.status != "running":
        reasons.append(AUTONOMY_PROFILE_NOT_RUNNING)
    if not _channel_is_enabled(profile, channel):
        reasons.append(AUTONOMY_CHANNEL_DISABLED)
    if not _action_is_allowed(profile, channel, action):
        reasons.append(AUTONOMY_ACTION_NOT_ALLOWED)
    if _daily_cap_exceeded(profile, channel):
        reasons.append(AUTONOMY_DAILY_CAP_EXCEEDED)
    if _quiet_hours_active(profile):
        reasons.append(AUTONOMY_QUIET_HOURS_ACTIVE)

    return _stable_unique_reasons(reasons)


def preview_autonomy_runner_tick(
    profile: GoHamSocialProfile,
    *,
    channel: SocialAutonomyChannel,
    action: SocialAutonomyAction | None = None,
) -> dict[str, object]:
    """Return a read-only dry-run summary for the next autonomy runner tick.

    The preview intentionally has no provider or persistence dependencies. It
    only evaluates the supplied profile against the requested channel/action and
    returns a small JSON-ready contract for API and UI callers.
    """
    effective_action = action or _PREVIEW_DEFAULT_ACTIONS[channel]
    reasons = autonomy_reasons_for_apply(profile, channel=channel, action=effective_action)
    would_run = not reasons
    return {
        "channel": channel,
        "action": effective_action,
        "would_run": would_run,
        "reasons": reasons,
        "next_run_summary": (
            f"{channel}:{effective_action} would run on the next one-shot tick."
            if would_run
            else f"{channel}:{effective_action} is blocked by the autonomy envelope."
        ),
    }


def _channel_is_enabled(profile: GoHamSocialProfile, channel: str) -> bool:
    config = profile.channels.get(channel)  # type: ignore[arg-type]
    if config is None:
        return False
    return bool(config.available and config.enabled)


def _action_is_allowed(profile: GoHamSocialProfile, channel: str, action: str) -> bool:
    return action in set(profile.actions_allowed_per_channel.get(channel, []))  # type: ignore[arg-type]


def _daily_cap_exceeded(profile: GoHamSocialProfile, channel: str) -> bool:
    cap = profile.daily_caps.get(channel)  # type: ignore[arg-type]
    return cap is not None and cap <= 0


def _quiet_hours_active(profile: GoHamSocialProfile) -> bool:
    quiet_hours = profile.quiet_hours
    if quiet_hours is None:
        return False

    now_utc = _now_utc()
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)
    try:
        local_now = now_utc.astimezone(ZoneInfo(quiet_hours.timezone))
    except (ValueError, ZoneInfoNotFoundError):
        local_now = now_utc.astimezone(UTC)

    hour = local_now.hour
    start = quiet_hours.start_hour
    end = quiet_hours.end_hour
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _stable_unique_reasons(reasons: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    emitted = set(reasons)
    for code in _REASON_ORDER:
        if code in emitted and code not in seen:
            seen.add(code)
            out.append(code)
    return out


__all__ = [
    "AUTONOMY_ACTION_NOT_ALLOWED",
    "AUTONOMY_APPLY_REASON_CODES",
    "AUTONOMY_CHANNEL_DISABLED",
    "AUTONOMY_DAILY_CAP_EXCEEDED",
    "AUTONOMY_EMERGENCY_STOP",
    "AUTONOMY_PROFILE_NOT_RUNNING",
    "AUTONOMY_QUIET_HOURS_ACTIVE",
    "autonomy_reasons_for_apply",
    "preview_autonomy_runner_tick",
]
