"""System prompt assembly for chat (UI actions must survive catalog size)."""

from __future__ import annotations

import pytest

from src.api.chat import (
    _DEFAULT_CHAT_SYSTEM_PROMPT,
    _MAX_SYSTEM_PROMPT_CHARS,
    _chat_system_prompt,
)


def test_chat_system_prompt_preserves_ui_actions_when_skills_catalog_is_huge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: skills/subagent blocks used to push HAM_UI_ACTIONS_JSON past the 12k cut."""
    monkeypatch.setattr(
        "src.api.chat.render_skills_for_system_prompt",
        lambda _: "x" * 25_000,
    )
    out = _chat_system_prompt(
        include_operator_skills=True,
        include_operator_subagents=False,
        enable_ui_actions=True,
    )
    assert "HAM_UI_ACTIONS_JSON:" in out
    assert "toggle_control_panel" in out
    assert len(out) <= _MAX_SYSTEM_PROMPT_CHARS


def test_chat_system_prompt_includes_no_fabricated_execution_guard() -> None:
    """The default prompt must carry an explicit guard against fabricated execution claims.

    This locks the language a previous chat turn violated when it claimed to have
    edited ``/home/user/hermes-workspace``, created commit ``e5391b5``, and
    scheduled a cron job — none of which happened. The chat route has no shell /
    git / build / PR tooling; the model must refuse to narrate execution and
    must redirect coding intents to the real Coding Plan flow.
    """
    base = _DEFAULT_CHAT_SYSTEM_PROMPT
    # Capabilities lock: every banned tool surface is explicitly negated.
    # Managed-workspace snapshots are intentionally NOT in the banned list:
    # they are created when the user approves the Managed workspace build
    # approval panel (a real API call), so denying them in the system
    # prompt while the panel is rendered would contradict the actual flow.
    assert "No fabricated execution" in base
    for negated in (
        "NO shell",
        "NO git",
        "NO build",
        "NO push",
        "NO PR",
        "NO cron",
        "NO filesystem tools",
    ):
        assert negated in base, f"missing negation: {negated!r}"
    # The prompt must not blanket-deny snapshots while the approval panel
    # is the legitimate chat-side path for creating them.
    assert "NO snapshot" not in base
    assert "capture managed-workspace snapshots" not in base
    # Routing lock: coding intents must point to the real flow.
    assert "Plan with coding agents" in base
    assert "Coding Plan card" in base
    assert "Managed workspace build approval panel" in base
    # Completion-claim lock: outcomes require server-issued ids.
    assert "Completion-claim rule" in base
    for token in ("ham_run_id", "snapshot_id", "pr_url", "control_plane_run_id"):
        assert token in base, f"missing artifact token: {token!r}"


def test_chat_system_prompt_assembly_carries_no_fabricated_execution_guard() -> None:
    """The assembled prompt (with skills/subagents/UI actions) preserves the guard."""
    out = _chat_system_prompt(
        include_operator_skills=False,
        include_operator_subagents=False,
        enable_ui_actions=False,
    )
    assert "No fabricated execution" in out
    assert "Plan with coding agents" in out
    assert "Completion-claim rule" in out


def test_chat_system_prompt_forbids_delegate_task_for_coding_execution() -> None:
    """Locks the conversational-conductor copy guard.

    Live chat fabricated a ``delegate_task`` suggestion for a managed-workspace
    smoke prompt. The Coding Plan card is the canonical surface for coding
    execution; the prompt must explicitly forbid suggesting ``delegate_task`` /
    Hermes skills / other vendored catalog adapters for that flow, and must
    prefer the managed-workspace build approval copy.
    """
    base = _DEFAULT_CHAT_SYSTEM_PROMPT
    # Anti-delegate-task lock.
    assert "delegate_task" in base, (
        "system prompt must explicitly forbid delegate_task as a coding-execution route"
    )
    assert "Do NOT suggest `delegate_task`" in base or "Do NOT suggest" in base
    # Preferred copy for the managed-workspace build flow.
    assert "managed workspace build" in base
    assert "Review the plan below and approve when ready" in base


F_PROVIDER_IDS = (
    "opencode_cli",
    "claude_code",
    "factory_droid_audit",
    "factory_droid_build",
    "cursor_cloud",
)

F_ENV_NAMES = (
    "HERMES_GATEWAY_API_KEY",
    "HERMES_GATEWAY_BASE_URL",
    "HERMES_GATEWAY_MODEL",
    "HERMES_GATEWAY_MODE",
    "HAM_DROID_EXEC_TOKEN",
    "HAM_CURSOR_AGENT_LAUNCH_TOKEN",
    "HAM_SETTINGS_WRITE_TOKEN",
    "HAM_RUN_LAUNCH_TOKEN",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "HAM_CHAT_CONVERSATIONAL_MODEL",
)

F_OPERATOR_VOCAB = (
    "proposal_digest",
    "base_revision",
    ".ham/runs",
    "operator.phase",
)


def test_val_prompt_001_length_cap() -> None:
    """VAL-PROMPT-001: default prompt is ≤ 1800 chars."""
    assert len(_DEFAULT_CHAT_SYSTEM_PROMPT) <= 1800


def test_val_prompt_002_ham_identity() -> None:
    """VAL-PROMPT-002: Ham identity present (case-sensitive)."""
    assert "Ham" in _DEFAULT_CHAT_SYSTEM_PROMPT
    assert "You are **Ham**" in _DEFAULT_CHAT_SYSTEM_PROMPT


def test_val_prompt_003_no_fabricated_execution_guardrail() -> None:
    """VAL-PROMPT-003: no-fabricated-execution guardrail preserved."""
    base = _DEFAULT_CHAT_SYSTEM_PROMPT
    assert "No fabricated execution" in base
    assert "fabricat" in base
    assert "invent" in base
    for negated in ("NO shell", "NO git", "NO build", "NO push", "NO PR", "NO filesystem"):
        assert negated in base, f"missing negation: {negated!r}"


def test_val_prompt_004_completion_claim_guardrail() -> None:
    """VAL-PROMPT-004: completion-claim guardrail preserved."""
    base = _DEFAULT_CHAT_SYSTEM_PROMPT
    assert "Completion-claim rule" in base
    for word in ("done", "built", "shipped", "committed", "pushed"):
        assert word in base, f"missing completion word: {word!r}"
    for artifact in ("ham_run_id", "snapshot_id", "pr_url", "control_plane_run_id"):
        assert artifact in base, f"missing artifact token: {artifact!r}"


def test_val_prompt_005_approval_before_mutation_guardrail() -> None:
    """VAL-PROMPT-005: approval-before-mutation surfaces the approval card flow."""
    base = _DEFAULT_CHAT_SYSTEM_PROMPT
    assert "Managed workspace build approval panel" in base
    assert "Review the plan below and approve when ready" in base


def test_val_prompt_006_route_coding_execution_guardrail() -> None:
    """VAL-PROMPT-006: route coding execution through the real plan/approval flow."""
    base = _DEFAULT_CHAT_SYSTEM_PROMPT
    assert "Coding Plan card" in base
    assert "Plan with coding agents" in base


@pytest.mark.parametrize("token", F_PROVIDER_IDS)
def test_val_prompt_007_no_provider_ids(token: str) -> None:
    """VAL-PROMPT-007: no raw provider IDs leaked in the default prompt."""
    assert token not in _DEFAULT_CHAT_SYSTEM_PROMPT


@pytest.mark.parametrize("token", F_ENV_NAMES)
def test_val_prompt_008_no_env_names(token: str) -> None:
    """VAL-PROMPT-008: no env var names leaked in the default prompt."""
    assert token not in _DEFAULT_CHAT_SYSTEM_PROMPT


@pytest.mark.parametrize("token", F_OPERATOR_VOCAB)
def test_val_prompt_009_no_operator_vocab(token: str) -> None:
    """VAL-PROMPT-009: no operator internal vocab leaked in the default prompt."""
    assert token not in _DEFAULT_CHAT_SYSTEM_PROMPT


def test_val_prompt_010_hermes_not_product_brand() -> None:
    """VAL-PROMPT-010: 'hermes' appears at most once and never as a product brand."""
    base = _DEFAULT_CHAT_SYSTEM_PROMPT
    assert base.lower().count("hermes") <= 1
    for brand in ("Hermes Workspace", "Hermes Agent", "Hermes Hub"):
        assert brand not in base, f"Hermes used as product brand: {brand!r}"


def test_chat_system_prompt_default_returns_string_starting_with_persona() -> None:
    """``_chat_system_prompt`` with default include_* flags returns a string starting with the new persona."""
    out = _chat_system_prompt(
        include_operator_skills=False,
        include_operator_subagents=False,
        enable_ui_actions=False,
    )
    assert isinstance(out, str)
    assert out.startswith("You are **Ham**")


def test_val_prompt_008_excludes_conversational_lane_env_name() -> None:
    """VAL-SAFETY-001 — the conversational-lane env var name never appears in default-chat copy."""
    assert "HAM_CHAT_CONVERSATIONAL_MODEL" not in _DEFAULT_CHAT_SYSTEM_PROMPT
    assembled = _chat_system_prompt(
        include_operator_skills=False,
        include_operator_subagents=False,
        enable_ui_actions=False,
    )
    assert "HAM_CHAT_CONVERSATIONAL_MODEL" not in assembled
    assembled_with_ui = _chat_system_prompt(
        include_operator_skills=False,
        include_operator_subagents=False,
        enable_ui_actions=True,
    )
    assert "HAM_CHAT_CONVERSATIONAL_MODEL" not in assembled_with_ui
