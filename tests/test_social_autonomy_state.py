"""State-machine tests for GoHAM Social autonomy status transitions."""

from __future__ import annotations

import pytest

from src.ham.social_autonomy.state import (
    AUTONOMY_INVALID_STATE_TRANSITION,
    transition_status,
    transition_to_paused,
    transition_to_running,
    transition_to_stopped,
)


def test_draft_to_running_transition_succeeds() -> None:
    result = transition_to_running("draft")

    assert result.ok is True
    assert result.status == "running"
    assert result.reasons == []


def test_running_to_paused_transition_succeeds() -> None:
    result = transition_to_paused("running")

    assert result.ok is True
    assert result.status == "paused"
    assert result.reasons == []


def test_running_to_stopped_transition_succeeds() -> None:
    result = transition_to_stopped("running")

    assert result.ok is True
    assert result.status == "stopped"
    assert result.reasons == []


def test_paused_to_running_transition_succeeds() -> None:
    result = transition_to_running("paused")

    assert result.ok is True
    assert result.status == "running"
    assert result.reasons == []


def test_paused_to_stopped_transition_succeeds() -> None:
    result = transition_to_stopped("paused")

    assert result.ok is True
    assert result.status == "stopped"
    assert result.reasons == []


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        ("stopped", "running"),
        ("stopped", "paused"),
        ("draft", "paused"),
        ("draft", "stopped"),
    ],
)
def test_invalid_transitions_are_rejected_without_mutating_source_status(
    from_status: str,
    to_status: str,
) -> None:
    result = transition_status(from_status, to_status)

    assert result.ok is False
    assert result.status == from_status
    assert result.reasons == [AUTONOMY_INVALID_STATE_TRANSITION]


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        ("draft", "running"),
        ("running", "paused"),
        ("paused", "running"),
    ],
)
def test_emergency_stop_overrides_requested_transition_to_stopped(
    from_status: str,
    to_status: str,
) -> None:
    result = transition_status(from_status, to_status, emergency_stop=True)

    assert result.ok is True
    assert result.status == "stopped"
    assert result.reasons == []
