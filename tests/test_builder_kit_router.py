from __future__ import annotations

import pytest

from src.ham.builder_kit_router import select_kit_for_prompt
from src.ham.builder_kits import list_kit_ids


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("build me a landing page for roofers", "landing-page"),
        ("create a marketing site", "landing-page"),
        ("build me a waitlist for my product launch", "landing-page"),
        ("build me an analytics dashboard", "dashboard"),
        ("create a kpi page", "dashboard"),
        ("make a metrics dashboard", "dashboard"),
        ("make a todo app", "todo"),
        ("build a task tracker", "todo"),
        ("build a CRUD app for notes", "todo"),
        ("build a calculator", "calculator"),
        ("make me a four-function calculator", "calculator"),
        ("build me a tetris clone", "tetris"),
        ("build a falling blocks game", "tetris"),
        ("build me a CRM", "generic"),
        ("", "generic"),
        ("   ", "generic"),
    ],
)
def test_select_kit_for_prompt(text: str, expected: str) -> None:
    assert select_kit_for_prompt(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "build me a landing page for roofers",
        "build me an analytics dashboard",
        "make a todo app",
        "build a calculator",
        "build me a tetris clone",
        "build me a CRM",
        "",
        "   ",
    ],
)
def test_select_kit_for_prompt_always_returns_registered_id(text: str) -> None:
    assert select_kit_for_prompt(text) in list_kit_ids()
