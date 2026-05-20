"""Status transition helpers for GoHAM Social autonomy profiles."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.ham.social_autonomy.schema import SocialAutonomyStatus

AUTONOMY_INVALID_STATE_TRANSITION = "autonomy_invalid_state_transition"

_ALLOWED_TRANSITIONS: frozenset[tuple[SocialAutonomyStatus, SocialAutonomyStatus]] = frozenset(
    {
        ("draft", "running"),
        ("running", "paused"),
        ("running", "stopped"),
        ("paused", "running"),
        ("paused", "stopped"),
    }
)


class AutonomyTransitionResult(BaseModel):
    """Pure state-machine result for a requested autonomy status transition."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    from_status: SocialAutonomyStatus
    requested_status: SocialAutonomyStatus
    status: SocialAutonomyStatus
    reasons: list[str] = Field(default_factory=list)


def transition_status(
    from_status: SocialAutonomyStatus,
    to_status: SocialAutonomyStatus,
    *,
    emergency_stop: bool = False,
) -> AutonomyTransitionResult:
    """Validate a status transition without mutating any profile object.

    ``emergency_stop=True`` is the safety override: it succeeds and forces the
    resulting status to ``stopped`` regardless of the requested target.
    """
    if emergency_stop:
        return AutonomyTransitionResult(
            ok=True,
            from_status=from_status,
            requested_status=to_status,
            status="stopped",
            reasons=[],
        )

    if (from_status, to_status) in _ALLOWED_TRANSITIONS:
        return AutonomyTransitionResult(
            ok=True,
            from_status=from_status,
            requested_status=to_status,
            status=to_status,
            reasons=[],
        )

    return AutonomyTransitionResult(
        ok=False,
        from_status=from_status,
        requested_status=to_status,
        status=from_status,
        reasons=[AUTONOMY_INVALID_STATE_TRANSITION],
    )


def transition_to_running(
    from_status: SocialAutonomyStatus,
    *,
    emergency_stop: bool = False,
) -> AutonomyTransitionResult:
    """Validate a transition to ``running``."""
    return transition_status(from_status, "running", emergency_stop=emergency_stop)


def transition_to_paused(
    from_status: SocialAutonomyStatus,
    *,
    emergency_stop: bool = False,
) -> AutonomyTransitionResult:
    """Validate a transition to ``paused``."""
    return transition_status(from_status, "paused", emergency_stop=emergency_stop)


def transition_to_stopped(
    from_status: SocialAutonomyStatus,
    *,
    emergency_stop: bool = False,
) -> AutonomyTransitionResult:
    """Validate a transition to ``stopped``."""
    return transition_status(from_status, "stopped", emergency_stop=emergency_stop)
