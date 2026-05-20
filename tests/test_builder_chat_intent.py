from __future__ import annotations

import pytest

from src.ham.builder_chat_intent import (
    classify_builder_chat_intent,
    is_builder_advice_or_question_turn,
    is_builder_edit_like_followup,
    is_crud_feature_build_request,
    looks_like_explicit_no_build,
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
        ("build me a game", "build_or_create"),
        ("try building a game like asteroids again", "build_or_create"),
        ("let's build a feature", "build_or_create"),
        ("", "answer_question"),
        ("don't build yet", "plan_only"),
        ("do not build this", "plan_only"),
        ("don't create it", "plan_only"),
        ("without building it", "plan_only"),
        ("plan only -- don't build", "plan_only"),
        ("just plan, don't build", "plan_only"),
        ("help me plan, but don't build yet", "plan_only"),
        ("talk through it before building", "plan_only"),
        ("Plan a dashboard for validator performance", "plan_only"),
        ("show me the plan before building", "plan_only"),
        ("create a dashboard", "build_or_create"),
        ("make a calculator app", "build_or_create"),
    ],
)
def test_classify_builder_chat_intent_buckets(text: str, expected: str) -> None:
    assert classify_builder_chat_intent(text) == expected


def test_crud_task_tracker_maps_to_build_or_create() -> None:
    prompt = (
        "Build me a simple launch task tracker with create, edit, delete, empty state, "
        "and form validation. Use mock data only."
    )
    assert is_crud_feature_build_request(prompt) is True
    assert classify_builder_chat_intent(prompt) == "build_or_create"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("don't build yet", True),
        ("do not build this", True),
        ("don't create it", True),
        ("without building it", True),
        ("plan only", True),
        ("just plan, don't build", True),
        ("talk through it before building", True),
        ("plan only -- don't build", True),
        ("build me a landing page", False),
        ("create a dashboard", False),
        ("this builds character", False),
        ("building blocks are fun", False),
        ("", False),
        ("   ", False),
    ],
)
def test_looks_like_explicit_no_build(text: str, expected: bool) -> None:
    assert looks_like_explicit_no_build(text) is expected


@pytest.mark.parametrize(
    "text",
    [
        "this builds character",
        "building blocks are fun",
    ],
)
def test_building_inflection_avoids_false_positive_build_intent(text: str) -> None:
    assert classify_builder_chat_intent(text) != "build_or_create"


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
