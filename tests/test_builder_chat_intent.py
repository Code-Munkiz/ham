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
        ("build me a landing page for roofers", "build_or_create"),
        ("HAM we need to build a commission tracker", "build_or_create"),
        ("make a SaaS dashboard", "build_or_create"),
        ("", "answer_question"),
    ],
)
def test_classify_builder_chat_intent_buckets(text: str, expected: str) -> None:
    assert classify_builder_chat_intent(text) == expected
