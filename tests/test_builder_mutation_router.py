from __future__ import annotations

import pytest

from src.ham.builder_mutation_router import (
    builder_edit_worker_eligible,
    classify_builder_project_action,
)
from src.ham.builder_artifact_verifier import list_calculator_scaffold_verification_checks


@pytest.mark.parametrize(
    ("text", "kind", "conf"),
    [
        ("ham change the AC button to purple", "mutate", "high"),
        ("change the equals button to orange", "mutate", "high"),
        ("add a settings panel", "mutate", "high"),
        ("delete the history section", "mutate", "high"),
        ("fix the pause button", "mutate", "high"),
        ("refactor the game board into its own component", "mutate", "high"),
        ("make the page responsive", "mutate", "high"),
        ("rename the title to Deep Space Calculator", "mutate", "high"),
    ],
)
def test_high_confidence_mutations(text: str, kind: str, conf: str) -> None:
    d = classify_builder_project_action(
        text,
        has_active_snapshot=True,
        active_template="calculator",
    )
    assert d.kind == kind
    assert d.confidence == conf


@pytest.mark.parametrize(
    "text",
    [
        "what does the AC button do?",
        "what files did you change?",
        "what do you suggest?",
        "explain the code",
    ],
)
def test_answer_only_advice(text: str) -> None:
    d = classify_builder_project_action(
        text,
        has_active_snapshot=True,
        active_template="calculator",
    )
    assert d.kind == "answer_only"


@pytest.mark.parametrize(
    "text",
    [
        "clean this up",
        "make it better",
        "remove the old stuff",
    ],
)
def test_ask_clarification_vague(text: str) -> None:
    d = classify_builder_project_action(
        text,
        has_active_snapshot=True,
        active_template="calculator",
    )
    assert d.kind == "ask_clarification"
    assert d.clarification_prompt


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("delete the history section", "mutate"),
        ("delete old stuff", "ask_clarification"),
        ("remove unused code", "ask_clarification"),
    ],
)
def test_delete_policy(text: str, kind: str) -> None:
    d = classify_builder_project_action(
        text,
        has_active_snapshot=True,
        active_template="calculator",
    )
    assert d.kind == kind


def test_worker_eligible_ac_purple_not_scaffold_checks() -> None:
    prompt = "ham change the AC button to purple"
    d = classify_builder_project_action(
        prompt,
        has_active_snapshot=True,
        active_template="calculator",
    )
    assert d.kind == "mutate"
    assert list_calculator_scaffold_verification_checks(prompt) == []
    assert builder_edit_worker_eligible(prompt, decision=d, active_template="calculator") is True


def test_worker_not_ineligible_when_scaffold_verifies() -> None:
    prompt = "make the buttons bigger and blue"
    d = classify_builder_project_action(
        prompt,
        has_active_snapshot=True,
        active_template="calculator",
    )
    assert d.kind == "mutate"
    assert "large_buttons" in list_calculator_scaffold_verification_checks(prompt)
    assert builder_edit_worker_eligible(prompt, decision=d, active_template="calculator") is False


def test_digit_purple_stays_scaffold_lane() -> None:
    prompt = "make the digit keys purple"
    d = classify_builder_project_action(prompt, has_active_snapshot=True, active_template="calculator")
    assert d.kind == "mutate"
    assert "purple_digit_keys" in list_calculator_scaffold_verification_checks(prompt)
    assert builder_edit_worker_eligible(prompt, decision=d, active_template="calculator") is False


def test_non_calculator_mutation_uses_hermes_worker() -> None:
    """Tetris (and other non-calculator) snapshots use Hermes worker when scaffold cannot prove the edit."""
    prompt = "add particle effects when lines clear"
    d = classify_builder_project_action(prompt, has_active_snapshot=True, active_template="tetris")
    assert d.kind == "mutate"
    assert builder_edit_worker_eligible(prompt, decision=d, active_template="tetris") is True


def test_advice_game_improvement_is_answer_only() -> None:
    d = classify_builder_project_action(
        "what would you improve about this game?",
        has_active_snapshot=True,
        active_template="tetris",
    )
    assert d.kind == "answer_only"
