"""Tests for src/ham/builder_plan_status.py — CloudRuntimeJob status transitions.

Exhaustive 6x6 matrix: every (from_status, to_status) pair asserted as
legal or illegal per Contract 6.
"""

from __future__ import annotations

import pytest

from src.ham.builder_plan_status import validate_transition

_ALL_STATUSES = ["queued", "running", "cancelling", "cancelled", "completed", "failed"]

_LEGAL = {
    ("queued", "running"),
    ("queued", "cancelled"),
    ("queued", "failed"),
    ("running", "cancelling"),
    ("running", "completed"),
    ("running", "failed"),
    ("cancelling", "cancelled"),
}


# ── Exhaustive 6x6 matrix ─────────────────────────────────────────


class TestTransitionMatrix:
    @pytest.mark.parametrize(
        "from_s, to_s",
        sorted(_LEGAL),
        ids=[f"{f}->{t}" for f, t in sorted(_LEGAL)],
    )
    def test_legal_transitions_pass(self, from_s, to_s):
        validate_transition(from_s, to_s)

    @pytest.mark.parametrize(
        "from_s, to_s",
        sorted(
            {(f, t) for f in _ALL_STATUSES for t in _ALL_STATUSES}
            - _LEGAL
        ),
        ids=[
            f"{f}->{t}"
            for f, t in sorted(
                {(f, t) for f in _ALL_STATUSES for t in _ALL_STATUSES}
                - _LEGAL
            )
        ],
    )
    def test_illegal_transitions_raise(self, from_s, to_s):
        with pytest.raises(ValueError):
            validate_transition(from_s, to_s)


# ── Terminal states are sticky ─────────────────────────────────────


class TestTerminalStatesAreSticky:
    @pytest.mark.parametrize("terminal", ["cancelled", "completed", "failed"])
    def test_terminal_to_any_raises(self, terminal):
        for target in _ALL_STATUSES:
            with pytest.raises(ValueError, match="terminal"):
                validate_transition(terminal, target)


# ── Named edge cases ──────────────────────────────────────────────


class TestEdgeCases:
    def test_no_skip_cancelling(self):
        """running → cancelled must go through cancelling first."""
        with pytest.raises(ValueError):
            validate_transition("running", "cancelled")

    def test_queued_to_cancelled_is_legal(self):
        """Cancel-before-run: queue-side cancel is legal per Contract 6."""
        validate_transition("queued", "cancelled")

    def test_self_transition_is_illegal(self):
        """No status may transition to itself."""
        for s in _ALL_STATUSES:
            with pytest.raises(ValueError):
                validate_transition(s, s)
