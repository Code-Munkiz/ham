"""Pure helpers and runner entry points for GoHAM Social autonomy ticks.

This module intentionally does not start timers, background workers, or live
transports. ``plan_social_autonomy_tick`` is pure and takes all dynamic
dependencies as arguments. ``run_social_autonomy_tick`` is the bounded side
effect wrapper: it reads a local profile, invokes dry-run adapters when
available, persists tick state, and optionally appends deterministic learning.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Final, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, field_validator

from src.ham.social_autonomy.schema import (
    GoHamSocialProfile,
    QuietHours,
    SocialAutonomyStatus,
    SocialAutonomyTickSummary,
)
from src.ham.social_autonomy.store import (
    SocialAutonomyStoreError,
    read_social_autonomy_profile,
    save_profile,
    social_autonomy_path,
)

AUTONOMY_PROFILE_MISSING: Final = "autonomy_profile_missing"
AUTONOMY_PROFILE_NOT_RUNNING: Final = "autonomy_profile_not_running"
AUTONOMY_EMERGENCY_STOP: Final = "autonomy_emergency_stop"
AUTONOMY_CHANNEL_DISABLED: Final = "autonomy_channel_disabled"
AUTONOMY_CHANNEL_UNAVAILABLE: Final = "autonomy_channel_unavailable"
AUTONOMY_ACTION_NOT_ALLOWED: Final = "autonomy_action_not_allowed"
AUTONOMY_QUIET_HOURS_ACTIVE: Final = "autonomy_quiet_hours_active"
AUTONOMY_CADENCE_NOT_DUE: Final = "autonomy_cadence_not_due"
AUTONOMY_CAP_EXCEEDED: Final = "autonomy_cap_exceeded"
AUTONOMY_CAP_ZERO: Final = "autonomy_cap_zero"
AUTONOMY_CAP_TRACKING_UNAVAILABLE: Final = "autonomy_cap_tracking_unavailable"
AUTONOMY_FORBIDDEN_TOPIC_MATCHED: Final = "autonomy_forbidden_topic_matched"
AUTONOMY_SAFETY_RULE_VIOLATION: Final = "autonomy_safety_rule_violation"
AUTONOMY_SAFETY_RULE_UNENFORCED: Final = "autonomy_safety_rule_unenforced"
AUTONOMY_PAYLOAD_EMPTY_OR_TOO_SHORT: Final = "autonomy_payload_empty_or_too_short"

BLOCKED_REASON_CODES: Final[tuple[str, ...]] = (
    AUTONOMY_PROFILE_MISSING,
    AUTONOMY_PROFILE_NOT_RUNNING,
    AUTONOMY_EMERGENCY_STOP,
    AUTONOMY_CHANNEL_DISABLED,
    AUTONOMY_CHANNEL_UNAVAILABLE,
    AUTONOMY_ACTION_NOT_ALLOWED,
    AUTONOMY_QUIET_HOURS_ACTIVE,
    AUTONOMY_CADENCE_NOT_DUE,
    AUTONOMY_CAP_ZERO,
    AUTONOMY_CAP_EXCEEDED,
    AUTONOMY_CAP_TRACKING_UNAVAILABLE,
    AUTONOMY_FORBIDDEN_TOPIC_MATCHED,
    AUTONOMY_SAFETY_RULE_VIOLATION,
    AUTONOMY_SAFETY_RULE_UNENFORCED,
    AUTONOMY_PAYLOAD_EMPTY_OR_TOO_SHORT,
)

_CADENCE_MANUAL = "manual"
_CADENCE_HOURLY = "hourly"
_CADENCE_DAILY = "daily"
_DEFAULT_ACTIONS: Final[dict[str, tuple[str, ...]]] = {
    "x": ("reply", "broadcast"),
    "telegram": ("message", "activity"),
    "discord": ("message",),
}

UsageCounter = Callable[[str, str, datetime], int]
ContentGuard = Callable[..., Sequence[str] | tuple[bool, str | None] | str | None]


class _TelegramAdapter(Protocol):
    def dispatch(self, action: Mapping[str, Any], *, dry_run: bool = True) -> Any:
        """Dispatch an action through the Telegram adapter."""


class _XCaller(Protocol):
    def dry_run(self, action: Mapping[str, Any]) -> Any:
        """Run an X action through the dry-run caller."""


class SocialAutonomyTickResult(BaseModel):
    """Normalized result shape returned by the autonomy tick service."""

    model_config = ConfigDict(extra="forbid")

    ran: bool
    dry_run: bool
    actions_considered: list[str]
    actions_taken: list[str]
    blocked_reasons: list[str]
    next_run_summary: str | None
    profile_status: SocialAutonomyStatus

    @field_validator("blocked_reasons")
    @classmethod
    def _dedupe_blocked_reasons(cls, value: list[str]) -> list[str]:
        return _dedupe_preserving_order(value)


@dataclass(frozen=True, slots=True)
class CadenceDecision:
    """Decision returned by the cadence gate.

    ``next_run_at`` is the timestamp a caller can persist on the profile so a
    future caller/UI can show when the next automatic tick should be tried.
    Manual and unknown cadences have no automatic next-due timestamp.
    """

    due: bool
    next_run_at: datetime | None


@dataclass(frozen=True, slots=True)
class _CandidateAction:
    channel: str
    action: str
    payload: str

    @property
    def action_id(self) -> str:
        return f"{self.channel}:{self.action}"

    def as_dispatch_payload(self) -> dict[str, str]:
        return {
            "channel": self.channel,
            "action": self.action,
            "payload": self.payload,
            "summary": self.payload,
        }


@dataclass(frozen=True, slots=True)
class _ActionEvaluation:
    actions_considered: list[str]
    actions_taken: list[str]
    blocked_reasons: list[str]


@dataclass(frozen=True, slots=True)
class _DispatchEvaluation:
    actions_taken: list[str]
    blocked_reasons: list[str]


def plan_social_autonomy_tick(
    profile: GoHamSocialProfile | None,
    *,
    now: datetime,
    usage_counter: UsageCounter | None,
    content_guard: ContentGuard | None,
    usage_source: UsageCounter | None = None,
    dry_run: bool = True,
    run_once: bool = False,
) -> SocialAutonomyTickResult:
    """Purely plan one autonomy tick against an already-loaded profile.

    The function performs no file I/O and imports no live transports. Usage
    counting and content checks are injected so tests and callers can supply
    deterministic sources. ``usage_source`` is accepted as an alias for older
    contract wording; ``usage_counter`` takes precedence.
    """

    _require_aware_datetime(now, field_name="now")
    active_usage_counter = usage_counter or usage_source
    if active_usage_counter is None:
        raise TypeError("usage_counter must be injected")
    if content_guard is None:
        raise TypeError("content_guard must be injected")

    if profile is None:
        return _result(
            ran=False,
            dry_run=dry_run,
            actions_considered=[],
            actions_taken=[],
            blocked_reasons=[AUTONOMY_PROFILE_MISSING],
            next_run_summary=None,
            profile_status="stopped",
        )

    cadence_state = _cadence_state_for_profile(profile, now, run_once=run_once)
    next_run_summary = _next_run_summary(profile, cadence_state.next_run_at)

    if profile.emergency_stop:
        return _blocked_profile_result(
            profile,
            dry_run=dry_run,
            reason=AUTONOMY_EMERGENCY_STOP,
            next_run_summary=next_run_summary,
        )

    if profile.status != "running":
        return _blocked_profile_result(
            profile,
            dry_run=dry_run,
            reason=AUTONOMY_PROFILE_NOT_RUNNING,
            next_run_summary=next_run_summary,
        )

    if is_quiet_hours_active(profile.quiet_hours, now):
        return _blocked_profile_result(
            profile,
            dry_run=dry_run,
            reason=AUTONOMY_QUIET_HOURS_ACTIVE,
            next_run_summary=next_run_summary,
        )

    if not cadence_state.due:
        return _blocked_profile_result(
            profile,
            dry_run=dry_run,
            reason=AUTONOMY_CADENCE_NOT_DUE,
            next_run_summary=next_run_summary,
        )

    evaluation = _evaluate_actions(
        profile,
        now,
        usage_counter=active_usage_counter,
        content_guard=content_guard,
    )
    return _result(
        ran=bool(evaluation.actions_taken),
        dry_run=dry_run,
        actions_considered=evaluation.actions_considered,
        actions_taken=evaluation.actions_taken,
        blocked_reasons=_dedupe_preserving_order(evaluation.blocked_reasons),
        next_run_summary=next_run_summary,
        profile_status=profile.status,
    )


def run_social_autonomy_tick(
    *,
    store_path: Path | str,
    now: datetime,
    dry_run: bool = True,
    usage_counter: UsageCounter | None = None,
    content_guard: ContentGuard | None = None,
    telegram_adapter: _TelegramAdapter | None = None,
    x_caller: _XCaller | None = None,
    learning_store: Any = None,
    run_once: bool = False,
    critic: Any = None,
    actor: str = "social-autonomy-tick",
) -> SocialAutonomyTickResult:
    """Run one bounded autonomy tick from the file-backed profile store."""

    _require_aware_datetime(now, field_name="now")
    root = Path(store_path)
    if not social_autonomy_path(root).is_file():
        return _result(
            ran=False,
            dry_run=dry_run,
            actions_considered=[],
            actions_taken=[],
            blocked_reasons=[AUTONOMY_PROFILE_MISSING],
            next_run_summary=None,
            profile_status="stopped",
        )

    try:
        profile = read_social_autonomy_profile(root)
    except SocialAutonomyStoreError as exc:
        if isinstance(exc.__cause__, json.JSONDecodeError):
            raise exc.__cause__ from exc
        raise

    result = plan_social_autonomy_tick(
        profile,
        now=now,
        usage_counter=usage_counter or _default_usage_counter,
        content_guard=content_guard or _default_content_guard,
        dry_run=dry_run,
        run_once=run_once,
    )

    if dry_run and result.actions_taken:
        dispatched = _dispatch_dry_run_actions(
            profile,
            result.actions_taken,
            telegram_adapter=telegram_adapter,
            x_caller=x_caller,
        )
        result = result.model_copy(
            update={
                "actions_taken": dispatched.actions_taken,
                "ran": bool(dispatched.actions_taken),
                "blocked_reasons": _dedupe_preserving_order(
                    [*result.blocked_reasons, *dispatched.blocked_reasons]
                ),
            }
        )

    next_run_at = _next_run_at_after_tick(profile, result, now, run_once=run_once)
    summary = SocialAutonomyTickSummary(
        ran=result.ran,
        dry_run=result.dry_run,
        actions_considered=result.actions_considered,
        actions_taken=result.actions_taken,
        blocked_reasons=result.blocked_reasons,
        profile_status=result.profile_status,
        recorded_at=now,
        next_run_summary=result.next_run_summary,
    )
    updated = profile.model_copy(
        update={
            "updated_at": now,
            "last_run_at": now if result.ran else profile.last_run_at,
            "next_run_at": next_run_at,
            "last_tick_summary": summary,
        }
    )
    save_profile(root, updated, actor=actor)

    if updated.learning_enabled:
        from src.ham.social_autonomy.learning_hook import append_tick_learning

        append_tick_learning(
            updated,
            result.model_dump(mode="json"),
            critic=critic,
            learning_store=learning_store,
        )

    return result


def _result(
    *,
    ran: bool,
    dry_run: bool,
    actions_considered: Sequence[str],
    actions_taken: Sequence[str],
    blocked_reasons: Sequence[str],
    next_run_summary: str | None,
    profile_status: SocialAutonomyStatus,
) -> SocialAutonomyTickResult:
    return SocialAutonomyTickResult(
        ran=ran,
        dry_run=dry_run,
        actions_considered=list(actions_considered),
        actions_taken=list(actions_taken),
        blocked_reasons=list(blocked_reasons),
        next_run_summary=next_run_summary,
        profile_status=profile_status,
    )


def _dedupe_preserving_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _evaluate_actions(
    profile: GoHamSocialProfile,
    now: datetime,
    *,
    usage_counter: UsageCounter,
    content_guard: ContentGuard,
) -> _ActionEvaluation:
    actions_considered: list[str] = []
    actions_taken: list[str] = []
    blocked_reasons: list[str] = []

    for channel, config in profile.channels.items():
        channel_name = str(channel)
        actions_considered.extend(_candidate_ids_for_channel(channel_name))
        if channel_name == "discord" or not bool(config.available):
            blocked_reasons.append(AUTONOMY_CHANNEL_UNAVAILABLE)
            continue
        if not bool(config.enabled):
            blocked_reasons.append(AUTONOMY_CHANNEL_DISABLED)
            continue

        allowed_actions = {
            str(action) for action in profile.actions_allowed_per_channel.get(channel, [])
        }
        channel_result = _evaluate_channel_actions(
            profile,
            channel_name,
            now,
            allowed_actions=allowed_actions,
            usage_counter=usage_counter,
            content_guard=content_guard,
        )
        actions_taken.extend(channel_result.actions_taken)
        blocked_reasons.extend(channel_result.blocked_reasons)

    return _ActionEvaluation(
        actions_considered=actions_considered,
        actions_taken=actions_taken,
        blocked_reasons=blocked_reasons,
    )


def _evaluate_channel_actions(
    profile: GoHamSocialProfile,
    channel: str,
    now: datetime,
    *,
    allowed_actions: set[str],
    usage_counter: UsageCounter,
    content_guard: ContentGuard,
) -> _ActionEvaluation:
    actions_taken: list[str] = []
    blocked_reasons: list[str] = []

    for action in _DEFAULT_ACTIONS.get(channel, ()):
        candidate = _candidate_for(profile, channel, action)
        block_reason = _candidate_block_reason(
            profile,
            candidate,
            now,
            allowed_actions=allowed_actions,
            usage_counter=usage_counter,
            content_guard=content_guard,
        )
        if block_reason is not None:
            blocked_reasons.extend(block_reason)
            continue
        actions_taken.append(candidate.action_id)

    return _ActionEvaluation(
        actions_considered=_candidate_ids_for_channel(channel),
        actions_taken=actions_taken,
        blocked_reasons=blocked_reasons,
    )


def _candidate_block_reason(
    profile: GoHamSocialProfile,
    candidate: _CandidateAction,
    now: datetime,
    *,
    allowed_actions: set[str],
    usage_counter: UsageCounter,
    content_guard: ContentGuard,
) -> list[str] | None:
    if candidate.action not in allowed_actions:
        return [AUTONOMY_ACTION_NOT_ALLOWED]

    cap = profile.daily_caps.get(candidate.channel)  # type: ignore[arg-type]
    if cap is None:
        return [AUTONOMY_CAP_TRACKING_UNAVAILABLE]
    if int(cap) == 0:
        return [AUTONOMY_CAP_ZERO]

    used = _usage_count_or_block(usage_counter, candidate, now)
    if used is None:
        return [AUTONOMY_CAP_TRACKING_UNAVAILABLE]
    if used >= int(cap):
        return [AUTONOMY_CAP_EXCEEDED]

    guard_reasons = _content_guard_reasons(
        content_guard,
        profile,
        candidate,
        now=now,
    )
    return guard_reasons or None


def _usage_count_or_block(
    usage_counter: UsageCounter,
    candidate: _CandidateAction,
    now: datetime,
) -> int | None:
    try:
        return usage_counter(candidate.channel, candidate.action, now)
    except Exception as exc:  # noqa: BLE001 - fail closed across injected sources.
        if _is_usage_source_unavailable(exc):
            return None
        raise


def _blocked_profile_result(
    profile: GoHamSocialProfile,
    *,
    dry_run: bool,
    reason: str,
    next_run_summary: str | None,
) -> SocialAutonomyTickResult:
    return _result(
        ran=False,
        dry_run=dry_run,
        actions_considered=[],
        actions_taken=[],
        blocked_reasons=[reason],
        next_run_summary=next_run_summary,
        profile_status=profile.status,
    )


def _cadence_state_for_profile(
    profile: GoHamSocialProfile,
    now: datetime,
    *,
    run_once: bool,
) -> CadenceDecision:
    return cadence_due_state(
        profile.cadence,
        profile.last_run_at,
        now,
        run_once=run_once,
        profile_timezone=_profile_timezone(profile),
    )


def _profile_timezone(profile: GoHamSocialProfile) -> str:
    if profile.quiet_hours is not None:
        return profile.quiet_hours.timezone
    return "UTC"


def _next_run_summary(profile: GoHamSocialProfile, next_run_at: datetime | None) -> str | None:
    if next_run_at is None:
        return None
    return f"Next {profile.cadence.strip().lower()} tick after {next_run_at.isoformat()}"


def _candidate_ids_for_channel(channel: str) -> list[str]:
    return [f"{channel}:{action}" for action in _DEFAULT_ACTIONS.get(channel, ())]


def _candidate_for(profile: GoHamSocialProfile, channel: str, action: str) -> _CandidateAction:
    return _CandidateAction(
        channel=channel,
        action=action,
        payload=profile.goal,
    )


def _default_usage_counter(channel: str, action: str, now: datetime) -> int:
    from src.ham.social_autonomy.usage import count_actions_in_window

    return count_actions_in_window(channel, action, now)


def _default_content_guard(
    profile: GoHamSocialProfile,
    *,
    channel: str,
    action: str,
    payload: str,
    now: datetime,
) -> list[str]:
    from src.ham.social_autonomy.content_guards import collect_content_guard_reasons

    return collect_content_guard_reasons(
        payload,
        topic=f"{channel}:{action}",
        payload_summary=payload,
        forbidden_topics=profile.forbidden_topics,
        safety_rules=profile.safety_rules,
        now=now,
    )


def _is_usage_source_unavailable(exc: Exception) -> bool:
    return exc.__class__.__name__ == "UsageSourceUnavailable"


def _content_guard_reasons(
    content_guard: ContentGuard,
    profile: GoHamSocialProfile,
    candidate: _CandidateAction,
    *,
    now: datetime,
) -> list[str]:
    try:
        raw = content_guard(
            profile,
            channel=candidate.channel,
            action=candidate.action,
            payload=candidate.payload,
            now=now,
        )
    except TypeError:
        raw = content_guard(candidate.payload)
    return _normalize_guard_result(raw)


def _normalize_guard_result(
    raw: Sequence[str] | tuple[bool, str | None] | str | None,
) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw] if raw else []
    if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[0], bool):
        ok, reason = raw
        return [] if ok or reason is None else [reason]
    return [str(reason) for reason in raw if str(reason)]


def _dispatch_dry_run_actions(
    profile: GoHamSocialProfile,
    action_ids: Sequence[str],
    *,
    telegram_adapter: _TelegramAdapter | None,
    x_caller: _XCaller | None,
) -> _DispatchEvaluation:
    dispatched: list[str] = []
    blocked_reasons: list[str] = []
    for action_id in action_ids:
        channel, action = action_id.split(":", 1)
        candidate = _candidate_for(profile, channel, action)
        dispatch_payload = candidate.as_dispatch_payload()
        if channel == "telegram":
            try:
                response = _dispatch_telegram(
                    dispatch_payload,
                    telegram_adapter=telegram_adapter,
                )
            except Exception as exc:  # noqa: BLE001 - adapter unavailability fails closed.
                if exc.__class__.__name__ != "AdapterUnavailable":
                    raise
                blocked_reasons.append(AUTONOMY_CHANNEL_UNAVAILABLE)
                continue
            normalized = _normalize_dispatch_response(response, action_id)
            dispatched.extend(normalized.actions_taken)
            blocked_reasons.extend(normalized.blocked_reasons)
            continue
        if channel == "x":
            response = _dispatch_x(dispatch_payload, x_caller=x_caller)
            normalized = _normalize_dispatch_response(response, action_id)
            dispatched.extend(normalized.actions_taken)
            blocked_reasons.extend(normalized.blocked_reasons)
            continue
        dispatched.append(action_id)
    return _DispatchEvaluation(
        actions_taken=_dedupe_preserving_order(dispatched),
        blocked_reasons=_dedupe_preserving_order(blocked_reasons),
    )


def _dispatch_telegram(
    action: Mapping[str, Any],
    *,
    telegram_adapter: _TelegramAdapter | None,
) -> Any:
    if telegram_adapter is None:
        try:
            from src.ham.social_autonomy.telegram_adapter import SocialAutonomyTelegramAdapter
        except ModuleNotFoundError:
            return action
        telegram_adapter = SocialAutonomyTelegramAdapter()
    return telegram_adapter.dispatch(action, dry_run=True)


def _dispatch_x(action: Mapping[str, Any], *, x_caller: _XCaller | None) -> Any:
    if x_caller is None:
        try:
            from src.ham.social_autonomy import x_caller as default_x_caller
        except (ImportError, ModuleNotFoundError):
            return action
        x_caller = default_x_caller
    return x_caller.dry_run(action)


def _normalize_dispatch_response(response: Any, fallback: str) -> _DispatchEvaluation:
    if isinstance(response, str):
        return _DispatchEvaluation(actions_taken=[response], blocked_reasons=[])
    if isinstance(response, Mapping):
        actions_taken = _string_list_from_mapping(response, "actions_taken")
        blocked_reasons = _string_list_from_mapping(response, "blocked_reasons")
        if (
            actions_taken
            or blocked_reasons
            or "actions_taken" in response
            or "blocked_reasons" in response
        ):
            return _DispatchEvaluation(
                actions_taken=actions_taken,
                blocked_reasons=blocked_reasons,
            )
        channel = response.get("channel")
        action = response.get("action")
        if isinstance(channel, str) and isinstance(action, str):
            return _DispatchEvaluation(
                actions_taken=[f"{channel}:{action}"],
                blocked_reasons=[],
            )
    return _DispatchEvaluation(actions_taken=[fallback], blocked_reasons=[])


def _string_list_from_mapping(response: Mapping[str, Any], key: str) -> list[str]:
    raw = response.get(key)
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item)]


def _next_run_at_after_tick(
    profile: GoHamSocialProfile,
    result: SocialAutonomyTickResult,
    now: datetime,
    *,
    run_once: bool,
) -> datetime | None:
    effective_last_run_at = now if result.ran else profile.last_run_at
    return cadence_due_state(
        profile.cadence,
        effective_last_run_at,
        now,
        run_once=run_once,
        profile_timezone=_profile_timezone(profile),
    ).next_run_at


def is_cadence_due(
    cadence: str,
    last_run_at: datetime | None,
    now: datetime,
    *,
    run_once: bool = False,
    profile_timezone: str = "UTC",
) -> bool:
    """Return whether a tick should pass the cadence gate.

    Unknown cadence strings fail closed by returning ``False``.
    """

    return cadence_due_state(
        cadence,
        last_run_at,
        now,
        run_once=run_once,
        profile_timezone=profile_timezone,
    ).due


def cadence_due_state(
    cadence: str,
    last_run_at: datetime | None,
    now: datetime,
    *,
    run_once: bool = False,
    profile_timezone: str = "UTC",
) -> CadenceDecision:
    """Evaluate the cadence gate and include the next automatic run time."""

    normalized = _normalize_cadence(cadence)
    _require_aware_datetime(now, field_name="now")
    if last_run_at is not None:
        _require_aware_datetime(last_run_at, field_name="last_run_at")

    if normalized == _CADENCE_MANUAL:
        return CadenceDecision(due=run_once, next_run_at=None)

    next_run_at = next_run_at_for(
        normalized,
        now,
        last_run_at=last_run_at,
        profile_timezone=profile_timezone,
    )

    if normalized == _CADENCE_HOURLY:
        if last_run_at is None:
            return CadenceDecision(due=True, next_run_at=next_run_at)
        return CadenceDecision(
            due=now - last_run_at >= timedelta(hours=1),
            next_run_at=next_run_at,
        )

    if normalized == _CADENCE_DAILY:
        if last_run_at is None:
            return CadenceDecision(due=True, next_run_at=next_run_at)
        timezone = _load_timezone(profile_timezone)
        return CadenceDecision(
            due=now.astimezone(timezone).date() > last_run_at.astimezone(timezone).date(),
            next_run_at=next_run_at,
        )

    return CadenceDecision(due=False, next_run_at=None)


def next_run_at_for(
    cadence: str,
    now: datetime,
    *,
    last_run_at: datetime | None = None,
    profile_timezone: str = "UTC",
) -> datetime | None:
    """Return the next automatic due timestamp for a cadence.

    ``hourly`` returns the next hourly boundary relative to ``last_run_at``
    when that boundary is still in the future, otherwise relative to ``now``.
    ``daily`` returns the next local midnight in ``profile_timezone``.
    ``manual`` and unknown cadences return ``None`` because no automatic run is
    scheduled.
    """

    normalized = _normalize_cadence(cadence)
    _require_aware_datetime(now, field_name="now")
    if last_run_at is not None:
        _require_aware_datetime(last_run_at, field_name="last_run_at")

    if normalized == _CADENCE_HOURLY:
        if last_run_at is not None:
            candidate = last_run_at + timedelta(hours=1)
            if candidate > now:
                return candidate
        return now + timedelta(hours=1)

    if normalized == _CADENCE_DAILY:
        timezone = _load_timezone(profile_timezone)
        local_now = now.astimezone(timezone)
        next_local_date = local_now.date() + timedelta(days=1)
        return datetime.combine(next_local_date, time.min, tzinfo=timezone)

    return None


def is_quiet_hours_active(
    quiet_hours_config: QuietHours | Mapping[str, object] | None,
    now: datetime,
) -> bool:
    """Return whether ``now`` falls inside the configured quiet-hours window.

    The quiet-hours interval is half-open: ``[start_hour, end_hour)``. Windows
    where ``start_hour > end_hour`` wrap across midnight.
    """

    if quiet_hours_config is None:
        return False

    _require_aware_datetime(now, field_name="now")
    quiet_hours = _coerce_quiet_hours(quiet_hours_config)
    if quiet_hours.start_hour == quiet_hours.end_hour:
        return False

    timezone = _load_timezone(quiet_hours.timezone)
    local_hour = now.astimezone(timezone).hour
    start_hour = quiet_hours.start_hour
    end_hour = quiet_hours.end_hour

    if start_hour < end_hour:
        return start_hour <= local_hour < end_hour
    return local_hour >= start_hour or local_hour < end_hour


def _normalize_cadence(cadence: str) -> str:
    return cadence.strip().lower()


def _coerce_quiet_hours(quiet_hours_config: QuietHours | Mapping[str, object]) -> QuietHours:
    if isinstance(quiet_hours_config, QuietHours):
        return quiet_hours_config
    return QuietHours.model_validate(quiet_hours_config)


def _load_timezone(profile_timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(profile_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown timezone: {profile_timezone!r}") from exc


def _require_aware_datetime(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
