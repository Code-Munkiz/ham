"""Static checks on the `.env.example` placeholder for HAM_CHAT_CONVERSATIONAL_MODEL.

Locks VAL-ENV-001 / VAL-ENV-002 / VAL-ENV-014.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
PLACEHOLDER_KEY = "HAM_CHAT_CONVERSATIONAL_MODEL"
FORBIDDEN_PROVIDER_SLUGS = (
    "anthropic/claude-3.5-sonnet",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "google/gemini-pro",
)


def _env_example_text() -> str:
    assert ENV_EXAMPLE.exists(), f".env.example missing at {ENV_EXAMPLE}"
    return ENV_EXAMPLE.read_text(encoding="utf-8")


_COMMENTED_ASSIGNMENT = re.compile(r"^#\s*[A-Z][A-Z0-9_]+=")


def _placeholder_block(text: str) -> tuple[int, list[str], list[str]]:
    lines = text.splitlines()
    placeholder_pattern = re.compile(r"^# HAM_CHAT_CONVERSATIONAL_MODEL=\s*$")
    matches = [i for i, line in enumerate(lines) if placeholder_pattern.match(line)]
    if len(matches) != 1:
        return -1, [], []
    idx = matches[0]
    comment_lines: list[str] = []
    j = idx - 1
    while j >= 0 and lines[j].lstrip().startswith("#"):
        if _COMMENTED_ASSIGNMENT.match(lines[j].lstrip()):
            break
        comment_lines.insert(0, lines[j])
        j -= 1
    return idx, comment_lines, lines


def test_conversational_model_placeholder_present_exactly_once() -> None:
    """VAL-ENV-001 — exactly one commented-out placeholder, no active assignment."""
    text = _env_example_text()
    commented = re.findall(r"^# HAM_CHAT_CONVERSATIONAL_MODEL=\s*$", text, flags=re.MULTILINE)
    active = re.findall(r"^HAM_CHAT_CONVERSATIONAL_MODEL=", text, flags=re.MULTILINE)
    assert len(commented) == 1, f"expected exactly one commented placeholder, got {commented!r}"
    assert active == [], f"unexpected active assignment(s): {active!r}"


def test_conversational_model_placeholder_in_dashboard_chat_block() -> None:
    """VAL-ENV-001 — placeholder lives in the dashboard chat block (after HAM_CHAT_PREMIUM_MODEL)."""
    text = _env_example_text()
    idx, _, _ = _placeholder_block(text)
    assert idx > 0
    head = "\n".join(text.splitlines()[:idx])
    assert "HAM_CHAT_PREMIUM_MODEL" in head, "placeholder must follow HAM_CHAT_PREMIUM_MODEL"


def test_conversational_model_placeholder_is_opt_in() -> None:
    """VAL-ENV-002 — comment block names opt-in semantics and seeds no provider default."""
    text = _env_example_text()
    idx, comment_lines, _ = _placeholder_block(text)
    assert idx > 0
    assert comment_lines, "expected at least one comment line above the placeholder"
    comment_block = "\n".join(comment_lines).lower()
    assert (
        "opt-in" in comment_block
        or "optional" in comment_block
        or "unset" in comment_block
    ), f"comment block must mention opt-in semantics; got: {comment_block!r}"
    for slug in FORBIDDEN_PROVIDER_SLUGS:
        assert slug.lower() not in comment_block, (
            f"comment block must not seed a paid/provider-specific default; found {slug!r}"
        )


def test_conversational_model_placeholder_documents_precedence() -> None:
    """VAL-ENV-014 — comment block names body.model_id and HERMES_GATEWAY_MODEL precedence."""
    text = _env_example_text()
    idx, comment_lines, _ = _placeholder_block(text)
    assert idx > 0
    block = "\n".join(comment_lines).lower()
    assert "body.model_id" in block or "model_id" in block, (
        f"comment block must reference body.model_id / model_id; got: {block!r}"
    )
    assert "hermes_gateway_model" in block, (
        f"comment block must reference HERMES_GATEWAY_MODEL; got: {block!r}"
    )
