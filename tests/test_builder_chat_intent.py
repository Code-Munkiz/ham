from __future__ import annotations

import pytest

from src.ham.builder_chat_intent import (
    classify_builder_chat_intent,
    is_builder_advice_or_question_turn,
    is_builder_edit_like_followup,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("what is HAM", "answer_question"),
        ("how does routing work", "answer_question"),
        ("could you make sense of this error", "answer_question"),
        ("how would we shard the database", "plan_only"),
        ("how would you build Tetris?", "plan_only"),
        ("build me a landing page for roofers", "build_or_create"),
        ("build me a game like Tetris", "build_or_create"),
        ("build me a game like tettris", "build_or_create"),
        ("make a tetris clone", "build_or_create"),
        ("create a browser game", "build_or_create"),
        ("turn this idea into an app", "build_or_create"),
        ("generate a website", "build_or_create"),
        ("what is Tetris?", "answer_question"),
        ("does this make sense?", "answer_question"),
        ("HAM we need to build a commission tracker", "build_or_create"),
        ("make a SaaS dashboard", "build_or_create"),
        ("", "answer_question"),
    ],
)
def test_classify_builder_chat_intent_buckets(text: str, expected: str) -> None:
    assert classify_builder_chat_intent(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("what do you suggest?", True),
        ("what files did you change?", True),
        ("why does it look bad?", True),
        ("explain the code", True),
        ("what does the AC button do?", True),
        ("what would you improve about this game?", True),
        ("how would you improve this?", True),
        ("nice make the buttons larger and purple", False),
        ("make the buttons purple", False),
        ("nice make them have a yellow border around the buttons", False),
        ("make the buttons random colors not just purple", False),
    ],
)
def test_is_builder_advice_or_question_turn(text: str, expected: bool) -> None:
    assert is_builder_advice_or_question_turn(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("nice make the buttons larger and purple", True),
        ("make the buttons purple", True),
        ("change the buttons to purple", True),
        ("add a yellow border around the buttons", True),
        ("make the buttons random colors", True),
        ("make the buttons random colors not just purple", True),
        ("make the layout wider", True),
        ("make it look more modern", True),
        ("nice make them have a yellow border around the buttons", True),
        ("what do you suggest?", False),
        ("explain the code", False),
        ("what files did you change?", False),
    ],
)
def test_is_builder_edit_like_followup(text: str, expected: bool) -> None:
    assert is_builder_edit_like_followup(text) is expected


@pytest.mark.parametrize(
    "text",
    [
        "nice make them have a yellow border around the buttons",
        "make the buttons random colors not just purple",
    ],
)
def test_live_followup_phrases_are_edit_like_not_advice(text: str) -> None:
    assert is_builder_advice_or_question_turn(text) is False
    assert is_builder_edit_like_followup(text) is True
    assert classify_builder_chat_intent(text) != "build_or_create"


@pytest.mark.parametrize(
    "text",
    [
        "what files did you change?",
        "what do you suggest?",
        "why does it look bad?",
    ],
)
def test_advice_followups_are_not_edit_like(text: str) -> None:
    assert is_builder_advice_or_question_turn(text) is True
    assert is_builder_edit_like_followup(text) is False
