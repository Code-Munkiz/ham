from __future__ import annotations

import pytest

from src.ham.builder_chat_intent import classify_builder_chat_intent


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
