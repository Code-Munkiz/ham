"""Structural locks for the chat conductor / router ownership boundary.

These tests are deliberately small and focused on **invariants the audit
established** (see commit message "refactor(chat): clarify conductor
routing boundaries"):

- ``src/ham/agent_router.py`` is a structured-signal provider; its result
  type carries no user-facing copy field.
- ``src/ham/builder_chat_intent.classify_builder_chat_intent`` returns an
  enum label only (no user-facing copy).
- ``src/api/coding_conductor`` candidates expose friendly labels and never
  leak raw provider IDs in the public dict for known providers.
- The two user-facing transcript-copy sources (operator path in
  ``src/ham/chat_operator.format_operator_assistant_message`` and builder
  happy-path acks in ``src/ham/builder_chat_hooks._builder_ack_prefix``)
  do not emit raw provider IDs or internal env / runs-store / protocol
  tokens in their canonical happy outputs.

If a future refactor adds a user-copy field to a "structured signal"
module, or pushes an internal provider id into either transcript-copy
source, the relevant assertion here will fail loudly.
"""
from __future__ import annotations

from typing import get_type_hints

from src.api.coding_conductor import _candidate_to_public_dict
from src.ham.agent_router import AgentRouteResult, route_agent_intent
from src.ham.builder_chat_hooks import _builder_ack_prefix
from src.ham.builder_chat_intent import classify_builder_chat_intent
from src.ham.chat_operator import (
    OperatorTurnResult,
    format_operator_assistant_message,
)
from src.ham.coding_router import Candidate


_FORBIDDEN_VISIBLE_TOKENS: tuple[str, ...] = (
    "opencode_cli",
    "claude_code",
    "claude_agent",
    "factory_droid_audit",
    "factory_droid_build",
    "cursor_cloud",
    "no_agent",
    "proposal_digest",
    "base_revision",
    "operator.phase",
    ".ham/runs",
    "ControlPlaneRun",
    "HERMES_GATEWAY",
    "HAM_DROID_EXEC_TOKEN",
    "HAM_RUN_LAUNCH_TOKEN",
    "HAM_CURSOR_AGENT_LAUNCH_TOKEN",
    "HAM_SETTINGS_WRITE_TOKEN",
)


# ---------------------------------------------------------------------------
# agent_router: structured-signal-only
# ---------------------------------------------------------------------------


def test_agent_router_result_carries_no_user_facing_copy_field() -> None:
    """``AgentRouteResult`` must remain a structured-signal type only."""
    hints = get_type_hints(AgentRouteResult)
    allowed = {
        "intent",
        "mode",
        "provider",
        "task",
        "repo_ref",
        "branch",
        "confidence",
        "missing",
        "reason_code",
    }
    actual = set(hints.keys())
    assert actual == allowed, (
        "AgentRouteResult fields changed; if you intend to add a structured "
        "signal field update this test, but do NOT add a user-facing copy "
        "field here — operator transcript copy belongs in "
        "src/ham/chat_operator.format_operator_assistant_message."
    )


def test_agent_router_normal_chat_returns_structured_only() -> None:
    out = route_agent_intent("what does this error mean?", default_project_id=None)
    assert out.intent == "normal_chat"
    # Pydantic dump exposes only structured fields; ensure no stray narrative.
    dumped = out.model_dump()
    for value in dumped.values():
        if isinstance(value, str):
            for tok in _FORBIDDEN_VISIBLE_TOKENS:
                assert tok not in value


# ---------------------------------------------------------------------------
# builder_chat_intent: enum-only output
# ---------------------------------------------------------------------------


def test_classify_builder_chat_intent_returns_known_label_only() -> None:
    """The Builder intent classifier must return one of the canonical labels."""
    allowed = {"answer_question", "plan_only", "build_or_create"}
    for prompt in (
        "what does the dispatcher do?",
        "how should we structure the calculator?",
        "build me a tetris clone",
        "",
    ):
        out = classify_builder_chat_intent(prompt)
        assert out in allowed, f"unknown builder intent label: {out!r}"


# ---------------------------------------------------------------------------
# coding_conductor: candidates expose friendly labels, never raw IDs
# ---------------------------------------------------------------------------


def test_coding_conductor_candidate_public_dict_uses_friendly_label() -> None:
    cursor = Candidate(
        provider="cursor_cloud",
        reason="Cursor candidate.",
        blockers=[],
        confidence=0.9,
        requires_operator=False,
        requires_confirmation=True,
        will_open_pull_request=True,
    )
    out = _candidate_to_public_dict(cursor)
    assert out["label"] == "Cursor"
    # The provider id remains as a stable machine-readable handle, but no
    # secondary string field in the dict echoes the internal id.
    string_fields = {k: v for k, v in out.items() if isinstance(v, str) and k != "provider"}
    for value in string_fields.values():
        for tok in (
            "opencode_cli",
            "claude_code",
            "factory_droid_audit",
            "factory_droid_build",
            "cursor_cloud",
            "no_agent",
        ):
            assert tok not in value, f"public candidate copy leaked raw id: {tok!r}"


def test_coding_conductor_candidate_public_dict_managed_build_uses_brand_label() -> None:
    managed_build = Candidate(
        provider="factory_droid_build",
        reason="Managed build candidate.",
        blockers=[],
        confidence=0.85,
        requires_operator=False,
        requires_confirmation=True,
        will_open_pull_request=False,
    )
    out = _candidate_to_public_dict(managed_build)
    assert out["label"] == "Factory Droid build"
    assert "factory_droid_build" not in out["reason"]
    assert "factory_droid_build" not in out["label"]


# ---------------------------------------------------------------------------
# chat_operator: transcript copy never leaks raw provider IDs
# ---------------------------------------------------------------------------


def test_format_operator_assistant_message_cursor_launch_uses_brand_label() -> None:
    op = OperatorTurnResult(
        handled=True,
        intent="cursor_agent_launch",
        ok=True,
        data={
            "repository": "https://github.com/example/repo",
            "ref": "main",
            "status": "running",
            "mission_checkpoint": "scaffold",
        },
    )
    msg = format_operator_assistant_message(op)
    assert "Cursor" in msg
    for tok in _FORBIDDEN_VISIBLE_TOKENS:
        assert tok not in msg, f"operator visible copy leaked {tok!r}"


# ---------------------------------------------------------------------------
# builder_chat_hooks: ack prefix uses product-friendly nouns only
# ---------------------------------------------------------------------------


def test_builder_ack_prefix_is_user_friendly_and_internal_token_clean() -> None:
    prefix = _builder_ack_prefix("build me a calculator app", operation="build_or_create")
    assert prefix.strip(), "builder ack prefix must not be empty for build intent"
    for tok in _FORBIDDEN_VISIBLE_TOKENS:
        assert tok not in prefix, f"builder ack prefix leaked {tok!r}"
    # Generic update operation must produce non-empty user-friendly text.
    update = _builder_ack_prefix("change the buttons to purple", operation="update_existing_project")
    assert update.strip()
    for tok in _FORBIDDEN_VISIBLE_TOKENS:
        assert tok not in update
