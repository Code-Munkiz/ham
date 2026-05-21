"""Tests for deterministic GoHAM Social autonomy content guards."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.ham.social_autonomy.content_guards import (
    AUTONOMY_FORBIDDEN_TOPIC_MATCHED,
    AUTONOMY_PAYLOAD_EMPTY_OR_TOO_SHORT,
    AUTONOMY_SAFETY_RULE_UNENFORCED,
    AUTONOMY_SAFETY_RULE_VIOLATION,
    collect_content_guard_reasons,
    evaluate_content_guards,
    forbidden_topic_matched,
    safety_rules_checklist,
)


def test_social_autonomy_content_guards_forbidden_topics_empty_and_case_insensitive() -> None:
    assert forbidden_topic_matched("Buy Crypto now", ["crypto"]) is True
    assert forbidden_topic_matched("Buy Crypto now", ["CRYPTO"]) is True
    assert forbidden_topic_matched("Buy Crypto now", []) is False
    assert forbidden_topic_matched("Buy Crypto now", ["", "   "]) is False


@pytest.mark.parametrize(
    ("draft", "topic", "payload_summary"),
    [
        ("Alpha Leak incoming", "launch", "summary"),
        ("draft", "Alpha Leak topic", "summary"),
        ("draft", "launch", "Alpha Leak summary"),
    ],
)
def test_social_autonomy_content_guards_forbidden_topics_match_all_candidate_fields(
    draft: str,
    topic: str,
    payload_summary: str,
) -> None:
    ok, reason = evaluate_content_guards(
        draft,
        topic=topic,
        payload_summary=payload_summary,
        forbidden_topics=["alpha leak"],
    )

    assert ok is False
    assert reason == AUTONOMY_FORBIDDEN_TOPIC_MATCHED


@pytest.mark.parametrize(
    ("mention_count", "expected_ok"),
    [
        (4, True),
        (5, True),
        (6, False),
    ],
)
def test_social_autonomy_content_guards_mass_tagging_blocks_above_limit(
    mention_count: int,
    expected_ok: bool,
) -> None:
    draft = "heads up " + " ".join(f"@friend{i}" for i in range(mention_count))

    ok, reason = safety_rules_checklist(draft, ["mass_tagging"], mass_tagging_limit=5)

    assert ok is expected_ok
    assert reason == (None if expected_ok else AUTONOMY_SAFETY_RULE_VIOLATION)


def test_social_autonomy_content_guards_repeated_payload_window() -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    previous_payloads = [
        {"payload": "Same Launch Update", "recorded_at": now - timedelta(minutes=10)},
        {"payload": "Same Launch Update", "recorded_at": now - timedelta(hours=2)},
        {"payload": "Different Launch Update", "recorded_at": now - timedelta(minutes=5)},
    ]

    ok, reason = safety_rules_checklist(
        "same launch update",
        ["repeated_payload"],
        now=now,
        previous_payloads=previous_payloads,
        repeated_payload_window_seconds=60 * 60,
    )

    assert ok is False
    assert reason == AUTONOMY_SAFETY_RULE_VIOLATION

    old_or_different = previous_payloads[1:]
    assert safety_rules_checklist(
        "same launch update",
        ["repeated_payload"],
        now=now,
        previous_payloads=old_or_different,
        repeated_payload_window_seconds=60 * 60,
    ) == (True, None)


@pytest.mark.parametrize(
    "draft",
    [
        "send your password so we can help",
        "drop your private key in the chat",
        "share the seed phrase here",
    ],
)
def test_social_autonomy_content_guards_credential_request_keywords(draft: str) -> None:
    assert safety_rules_checklist(draft, ["credential_request"]) == (
        False,
        AUTONOMY_SAFETY_RULE_VIOLATION,
    )


@pytest.mark.parametrize(
    "draft",
    [
        "100% guaranteed returns for everyone",
        "guaranteed 10x from here",
        "risk-free profit is guaranteed",
    ],
)
def test_social_autonomy_content_guards_price_guarantee_keywords(draft: str) -> None:
    assert safety_rules_checklist(draft, ["price_guarantee"]) == (
        False,
        AUTONOMY_SAFETY_RULE_VIOLATION,
    )


def test_social_autonomy_content_guards_no_external_links_only_when_enabled() -> None:
    draft = "Read the announcement at https://example.com"

    assert safety_rules_checklist(draft, ["no_external_links"]) == (
        False,
        AUTONOMY_SAFETY_RULE_VIOLATION,
    )
    assert safety_rules_checklist(draft, []) == (True, None)
    assert safety_rules_checklist("No link here", ["no_external_links"]) == (True, None)


@pytest.mark.parametrize(
    ("payload", "expected_ok"),
    [
        ("", False),
        ("   \n\t", False),
        ("hi", False),
        ("hey", True),
    ],
)
def test_social_autonomy_content_guards_payload_min_length(payload: str, expected_ok: bool) -> None:
    ok, reason = safety_rules_checklist(
        payload,
        ["payload_min_length"],
        min_payload_length=3,
    )

    assert ok is expected_ok
    assert reason == (None if expected_ok else AUTONOMY_PAYLOAD_EMPTY_OR_TOO_SHORT)


def test_social_autonomy_content_guards_unknown_rule_fails_closed() -> None:
    ok, reason = safety_rules_checklist("ordinary safe payload", ["warning_about_thursday"])

    assert ok is False
    assert reason == AUTONOMY_SAFETY_RULE_UNENFORCED


def test_social_autonomy_content_guards_reasons_are_deduped_in_evaluation_order() -> None:
    reasons = collect_content_guard_reasons(
        "send your password at https://example.com",
        topic="alpha leak",
        forbidden_topics=["alpha", "ALPHA"],
        safety_rules=[
            "credential_request",
            "no_external_links",
            "payload_min_length",
            "warning_about_thursday",
        ],
        min_payload_length=100,
    )

    assert reasons == [
        AUTONOMY_FORBIDDEN_TOPIC_MATCHED,
        AUTONOMY_SAFETY_RULE_VIOLATION,
        AUTONOMY_PAYLOAD_EMPTY_OR_TOO_SHORT,
        AUTONOMY_SAFETY_RULE_UNENFORCED,
    ]


def test_social_autonomy_content_guards_no_llm_or_regex_imports() -> None:
    source = Path("src/ham/social_autonomy/content_guards.py").read_text(encoding="utf-8")

    assert "litellm" not in source
    assert "openai" not in source
    assert "anthropic" not in source
    assert "import re" not in source
