"""Deterministic content guards for the GoHAM Social autonomy runner.

The helpers in this module are intentionally pure: callers inject candidate
text, configured rules, clock values, and previous payload summaries. The guard
order is stable and side-effect free:

1. forbidden topics across draft/topic/payload summary
2. safety rules in the caller-supplied order

Unsupported safety rules fail closed with ``autonomy_safety_rule_unenforced``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

AUTONOMY_FORBIDDEN_TOPIC_MATCHED = "autonomy_forbidden_topic_matched"
AUTONOMY_SAFETY_RULE_VIOLATION = "autonomy_safety_rule_violation"
AUTONOMY_SAFETY_RULE_UNENFORCED = "autonomy_safety_rule_unenforced"
AUTONOMY_PAYLOAD_EMPTY_OR_TOO_SHORT = "autonomy_payload_empty_or_too_short"

DEFAULT_MASS_TAGGING_LIMIT = 5
DEFAULT_MIN_PAYLOAD_LENGTH = 3
DEFAULT_REPEATED_PAYLOAD_WINDOW_SECONDS = 60 * 60

SAFETY_RULE_MASS_TAGGING = "mass_tagging"
SAFETY_RULE_REPEATED_PAYLOAD = "repeated_payload"
SAFETY_RULE_CREDENTIAL_REQUEST = "credential_request"
SAFETY_RULE_PRICE_GUARANTEE = "price_guarantee"
SAFETY_RULE_NO_EXTERNAL_LINKS = "no_external_links"
SAFETY_RULE_PAYLOAD_MIN_LENGTH = "payload_min_length"

_PAYLOAD_MIN_LENGTH_ALIASES = {
    SAFETY_RULE_PAYLOAD_MIN_LENGTH,
    "empty_payload",
    "too_short_payload",
    "empty_or_too_short_payload",
}

_CREDENTIAL_REQUEST_KEYWORDS = (
    "password",
    "private key",
    "seed phrase",
    "recovery phrase",
    "secret key",
    "api key",
    "mnemonic",
)

_PRICE_GUARANTEE_KEYWORDS = (
    "100% guaranteed",
    "guaranteed 10x",
    "guaranteed return",
    "guaranteed returns",
    "guaranteed profit",
    "guaranteed gains",
    "risk-free profit",
    "can't lose",
    "cannot lose",
)

_PAYLOAD_KEYS = ("payload", "draft", "text", "summary", "payload_summary")
_TIMESTAMP_KEYS = ("recorded_at", "executed_at", "created_at", "sent_at")

PreviousPayload = str | Mapping[str, Any]

__all__ = [
    "AUTONOMY_FORBIDDEN_TOPIC_MATCHED",
    "AUTONOMY_PAYLOAD_EMPTY_OR_TOO_SHORT",
    "AUTONOMY_SAFETY_RULE_UNENFORCED",
    "AUTONOMY_SAFETY_RULE_VIOLATION",
    "DEFAULT_MASS_TAGGING_LIMIT",
    "DEFAULT_MIN_PAYLOAD_LENGTH",
    "DEFAULT_REPEATED_PAYLOAD_WINDOW_SECONDS",
    "SAFETY_RULE_CREDENTIAL_REQUEST",
    "SAFETY_RULE_MASS_TAGGING",
    "SAFETY_RULE_NO_EXTERNAL_LINKS",
    "SAFETY_RULE_PAYLOAD_MIN_LENGTH",
    "SAFETY_RULE_PRICE_GUARANTEE",
    "SAFETY_RULE_REPEATED_PAYLOAD",
    "PreviousPayload",
    "collect_content_guard_reasons",
    "evaluate_content_guards",
    "forbidden_topic_matched",
    "forbidden_topics_match_candidate",
    "safety_rules_checklist",
]


def forbidden_topic_matched(text: str, topics: Sequence[str]) -> bool:
    """Return whether any non-empty topic is a case-insensitive substring."""

    haystack = text.casefold()
    for topic in topics:
        needle = topic.strip().casefold()
        if needle and needle in haystack:
            return True
    return False


def forbidden_topics_match_candidate(
    draft: str,
    topics: Sequence[str],
    *,
    topic: str | None = None,
    payload_summary: str | None = None,
) -> bool:
    """Match forbidden topics across draft, topic, and payload-summary fields."""

    return any(
        forbidden_topic_matched(field, topics)
        for field in (draft, topic or "", payload_summary or "")
    )


def evaluate_content_guards(
    draft: str,
    *,
    topic: str | None = None,
    payload_summary: str | None = None,
    forbidden_topics: Sequence[str] = (),
    safety_rules: Sequence[str] = (),
    now: datetime | None = None,
    previous_payloads: Sequence[PreviousPayload] = (),
    mass_tagging_limit: int = DEFAULT_MASS_TAGGING_LIMIT,
    repeated_payload_window_seconds: int = DEFAULT_REPEATED_PAYLOAD_WINDOW_SECONDS,
    min_payload_length: int = DEFAULT_MIN_PAYLOAD_LENGTH,
) -> tuple[bool, str | None]:
    """Return ``(ok, reason)`` for the first content-guard block.

    ``reason`` is ``None`` only when all configured checks pass.
    """

    reasons = collect_content_guard_reasons(
        draft,
        topic=topic,
        payload_summary=payload_summary,
        forbidden_topics=forbidden_topics,
        safety_rules=safety_rules,
        now=now,
        previous_payloads=previous_payloads,
        mass_tagging_limit=mass_tagging_limit,
        repeated_payload_window_seconds=repeated_payload_window_seconds,
        min_payload_length=min_payload_length,
    )
    if reasons:
        return False, reasons[0]
    return True, None


def collect_content_guard_reasons(
    draft: str,
    *,
    topic: str | None = None,
    payload_summary: str | None = None,
    forbidden_topics: Sequence[str] = (),
    safety_rules: Sequence[str] = (),
    now: datetime | None = None,
    previous_payloads: Sequence[PreviousPayload] = (),
    mass_tagging_limit: int = DEFAULT_MASS_TAGGING_LIMIT,
    repeated_payload_window_seconds: int = DEFAULT_REPEATED_PAYLOAD_WINDOW_SECONDS,
    min_payload_length: int = DEFAULT_MIN_PAYLOAD_LENGTH,
) -> list[str]:
    """Return all deterministic guard reason codes, deduped in insertion order."""

    reasons: list[str] = []
    if forbidden_topics_match_candidate(
        draft,
        forbidden_topics,
        topic=topic,
        payload_summary=payload_summary,
    ):
        reasons.append(AUTONOMY_FORBIDDEN_TOPIC_MATCHED)

    reasons.extend(
        _safety_rule_reasons(
            draft,
            safety_rules,
            now=now,
            previous_payloads=previous_payloads,
            mass_tagging_limit=mass_tagging_limit,
            repeated_payload_window_seconds=repeated_payload_window_seconds,
            min_payload_length=min_payload_length,
        )
    )
    return _dedupe_preserving_order(reasons)


def safety_rules_checklist(
    draft: str,
    rules: Sequence[str],
    *,
    now: datetime | None = None,
    previous_payloads: Sequence[PreviousPayload] = (),
    mass_tagging_limit: int = DEFAULT_MASS_TAGGING_LIMIT,
    repeated_payload_window_seconds: int = DEFAULT_REPEATED_PAYLOAD_WINDOW_SECONDS,
    min_payload_length: int = DEFAULT_MIN_PAYLOAD_LENGTH,
) -> tuple[bool, str | None]:
    """Return ``(ok, reason)`` for the first deterministic safety-rule block."""

    reasons = _safety_rule_reasons(
        draft,
        rules,
        now=now,
        previous_payloads=previous_payloads,
        mass_tagging_limit=mass_tagging_limit,
        repeated_payload_window_seconds=repeated_payload_window_seconds,
        min_payload_length=min_payload_length,
    )
    if reasons:
        return False, reasons[0]
    return True, None


def _safety_rule_reasons(
    draft: str,
    rules: Sequence[str],
    *,
    now: datetime | None,
    previous_payloads: Sequence[PreviousPayload],
    mass_tagging_limit: int,
    repeated_payload_window_seconds: int,
    min_payload_length: int,
) -> list[str]:
    reasons: list[str] = []
    for raw_rule in rules:
        rule = raw_rule.strip().casefold()
        if not rule:
            continue
        if rule == SAFETY_RULE_MASS_TAGGING:
            if _mention_count(draft) > mass_tagging_limit:
                reasons.append(AUTONOMY_SAFETY_RULE_VIOLATION)
            continue
        if rule == SAFETY_RULE_REPEATED_PAYLOAD:
            if _repeated_payload_within_window(
                draft,
                now=now,
                previous_payloads=previous_payloads,
                window_seconds=repeated_payload_window_seconds,
            ):
                reasons.append(AUTONOMY_SAFETY_RULE_VIOLATION)
            continue
        if rule == SAFETY_RULE_CREDENTIAL_REQUEST:
            if _contains_any_keyword(draft, _CREDENTIAL_REQUEST_KEYWORDS):
                reasons.append(AUTONOMY_SAFETY_RULE_VIOLATION)
            continue
        if rule == SAFETY_RULE_PRICE_GUARANTEE:
            if _contains_any_keyword(draft, _PRICE_GUARANTEE_KEYWORDS):
                reasons.append(AUTONOMY_SAFETY_RULE_VIOLATION)
            continue
        if rule == SAFETY_RULE_NO_EXTERNAL_LINKS:
            if _has_external_link(draft):
                reasons.append(AUTONOMY_SAFETY_RULE_VIOLATION)
            continue
        if rule in _PAYLOAD_MIN_LENGTH_ALIASES:
            if len(draft.strip()) < min_payload_length:
                reasons.append(AUTONOMY_PAYLOAD_EMPTY_OR_TOO_SHORT)
            continue
        reasons.append(AUTONOMY_SAFETY_RULE_UNENFORCED)
    return _dedupe_preserving_order(reasons)


def _mention_count(text: str) -> int:
    count = 0
    for index, char in enumerate(text):
        if char != "@":
            continue
        if index > 0 and not text[index - 1].isspace():
            continue
        next_index = index + 1
        if next_index >= len(text):
            continue
        next_char = text[next_index]
        if next_char.isalnum() or next_char == "_":
            count += 1
    return count


def _repeated_payload_within_window(
    draft: str,
    *,
    now: datetime | None,
    previous_payloads: Sequence[PreviousPayload],
    window_seconds: int,
) -> bool:
    if window_seconds < 0:
        raise ValueError("repeated_payload_window_seconds must be non-negative")

    normalized_draft = _normalize_payload(draft)
    if not normalized_draft:
        return False
    window = timedelta(seconds=window_seconds)

    for previous in previous_payloads:
        previous_text = _previous_payload_text(previous)
        if _normalize_payload(previous_text) != normalized_draft:
            continue

        previous_timestamp = _previous_payload_timestamp(previous)
        if now is None or previous_timestamp is None:
            return True
        age = _to_utc(now) - _to_utc(previous_timestamp)
        if timedelta(0) <= age <= window:
            return True
    return False


def _previous_payload_text(previous: PreviousPayload) -> str:
    if isinstance(previous, str):
        return previous
    for key in _PAYLOAD_KEYS:
        value = previous.get(key)
        if isinstance(value, str):
            return value
    return ""


def _previous_payload_timestamp(previous: PreviousPayload) -> datetime | None:
    if isinstance(previous, str):
        return None
    for key in _TIMESTAMP_KEYS:
        value = previous.get(key)
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            except ValueError:
                return None
    return None


def _contains_any_keyword(text: str, keywords: Sequence[str]) -> bool:
    haystack = text.casefold()
    return any(keyword in haystack for keyword in keywords)


def _has_external_link(text: str) -> bool:
    haystack = text.casefold()
    return "http://" in haystack or "https://" in haystack


def _normalize_payload(text: str) -> str:
    return " ".join(text.casefold().split())


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _dedupe_preserving_order(reasons: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        out.append(reason)
    return out
