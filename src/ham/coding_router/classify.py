"""Deterministic, regex-driven classifier for the chat-first Coding Router.

Phase 1 keeps this dumb on purpose: a small ordered table of regex rules,
no LLM call, no network, no allocation of large state. If the recommender
later needs more nuance we can promote to a hybrid classifier; until then,
"unknown" is a perfectly good output that tells the conductor to ask the
user to pick an alternative.

Rule order matters: more specific rules come first.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from src.ham.coding_router.types import CodingTask, TaskKind

# Confidence threshold below which the conductor should treat the result as
# ``unknown`` even if the table matched a low-confidence rule. The recommender
# does not gate on this — it leaves the policy decision to the caller.
CONFIDENCE_LOW: float = 0.6

_MAX_PROMPT_LEN = 12_000


@dataclass(frozen=True)
class _Rule:
    pattern: re.Pattern[str]
    kind: TaskKind
    confidence: float
    label: str


def _r(pattern: str, kind: TaskKind, confidence: float, label: str) -> _Rule:
    return _Rule(re.compile(pattern, re.IGNORECASE), kind, confidence, label)


# Ordered, most-specific-first. Each rule's ``label`` is logged in the
# CodingTask.matched_pattern field to help debug recommender choices.
_RULES: Sequence[_Rule] = (
    # Conceptual / explanation prompts.
    _r(
        r"^\s*(explain|what does|how does|walk me through|why is|why does|tell me about)\b",
        "explain",
        0.9,
        "explain:lead-verb",
    ),
    # Read-only audits / reviews / architecture reports.
    _r(
        r"\b(security review|threat model|owasp)\b",
        "security_review",
        0.85,
        "security_review",
    ),
    _r(
        r"\b(architecture (report|review|overview)|system design review)\b",
        "architecture_report",
        0.85,
        "architecture_report",
    ),
    _r(
        r"\b(audit|read[- ]only review|code review)\b",
        "audit",
        0.8,
        "audit",
    ),
    # Low-risk edits.
    _r(
        r"\b(typos?|fix typo|spelling)\b",
        "typo_only",
        0.9,
        "typo_only",
    ),
    _r(
        r"\b(format(ting)?|prettier|black|ruff format)\b",
        "format_only",
        0.85,
        "format_only",
    ),
    _r(
        r"\b(comments?|docstrings?|jsdoc)\b.{0,40}\b(add|update|fix|improve|write)\b",
        "comments_only",
        0.8,
        "comments_only",
    ),
    _r(
        r"\b(add|update|fix|improve|write)\b.{0,40}\b(comments?|docstrings?|jsdoc)\b",
        "comments_only",
        0.8,
        "comments_only:reverse",
    ),
    _r(
        r"\b(doc|docs|documentation|readme)\b.{0,40}\b(fix|update|improve|tidy|polish)\b",
        "doc_fix",
        0.75,
        "doc_fix",
    ),
    _r(
        r"\b(fix|update|improve|tidy|polish)\b.{0,40}\b(doc|docs|documentation|readme)\b",
        "doc_fix",
        0.75,
        "doc_fix:reverse",
    ),
    # Refactors.
    _r(
        r"\b(refactor|rename|restructure|reorganize|extract (a )?(function|method|class))\b",
        "refactor",
        0.7,
        "refactor",
    ),
    # Multi-file edits / migrations.
    _r(
        r"\b(migrate|sweep|across the (codebase|repo)|all (files|callers)|repo[- ]wide)\b",
        "multi_file_edit",
        0.7,
        "multi_file_edit",
    ),
    # Features.
    _r(
        r"\b(implement|build|create|add)\b.{0,60}\b(component|endpoint|route|api|feature|page|screen)\b",
        "feature",
        0.7,
        "feature",
    ),
    # Fixes (last among edit kinds — generic enough to catch many prompts).
    _r(
        r"\b(fix|bug|broken|wrong|crash|error|fails?)\b",
        "fix",
        0.65,
        "fix",
    ),
    # Single-file edit fallback (lower confidence; recommender requires Claude readiness).
    _r(
        r"\b(this file|in this file|tweak|small change|adjust)\b",
        "single_file_edit",
        0.6,
        "single_file_edit",
    ),
)


def classify_task(user_prompt: str, *, project_id: str | None = None) -> CodingTask:
    """Classify ``user_prompt`` into a :class:`CodingTask`.

    Empty / whitespace-only / oversized prompts always land as ``unknown``
    with confidence ``0.0``. Prompts longer than ``_MAX_PROMPT_LEN`` are
    truncated before matching to keep classification cheap.
    """
    raw = user_prompt or ""
    text = raw.strip()
    if not text:
        return CodingTask(
            user_prompt=raw,
            project_id=project_id,
            kind="unknown",
            confidence=0.0,
            matched_pattern=None,
        )
    if len(text) > _MAX_PROMPT_LEN:
        text = text[:_MAX_PROMPT_LEN]

    for rule in _RULES:
        if rule.pattern.search(text):
            return CodingTask(
                user_prompt=raw,
                project_id=project_id,
                kind=rule.kind,
                confidence=rule.confidence,
                matched_pattern=rule.label,
            )
    return CodingTask(
        user_prompt=raw,
        project_id=project_id,
        kind="unknown",
        confidence=0.0,
        matched_pattern=None,
    )


__all__ = ["CONFIDENCE_LOW", "classify_task"]
