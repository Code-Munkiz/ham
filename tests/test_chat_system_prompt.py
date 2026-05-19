"""System prompt assembly for chat (UI actions must survive catalog size)."""

from __future__ import annotations

import pytest

from src.api.chat import (
    _BUILDER_TURN_SYSTEM_INJECTION,
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
    # Preferred approval copy for workspace-scoped planner/build flows (neutral wording — no jargon).
    assert "approve before Builder work starts" in base
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
    """VAL-PROMPT-001 + VAL-BRAND-006: default prompt stays under the concise cap.

    Cap bumped from 1800 → 2900 → ~3300 to fit canon + Builder Studio grounding + stronger
    fabrication/outcome wording while `_MAX_SYSTEM_PROMPT_CHARS`` (12_000) still bounds full
    assembly with huge skill/subagent catalogs.
    """
    assert len(_DEFAULT_CHAT_SYSTEM_PROMPT) <= 3350


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
    for word in ("done", "ready", "built", "generated", "shipped", "committed", "pushed"):
        assert word in base, f"missing completion word: {word!r}"
    for artifact in ("ham_run_id", "snapshot_id", "pr_url", "control_plane_run_id"):
        assert artifact in base, f"missing artifact token: {artifact!r}"


def test_val_prompt_005_approval_before_mutation_guardrail() -> None:
    """VAL-PROMPT-005: approval-before-mutation surfaces the approval card flow."""
    base = _DEFAULT_CHAT_SYSTEM_PROMPT
    assert "Managed workspace build approval panel" in base
    assert "approve before Builder work starts" in base


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


def test_default_prompt_grounds_builder_studio_plainly() -> None:
    """VAL-BETA-BS — Builder Studio framing matches product onboarding copy."""
    base = _DEFAULT_CHAT_SYSTEM_PROMPT
    assert "**Builder Studio.**" in base
    low = base.lower()
    assert "builder studio configures" in low or "inside builder studio" in low


def test_default_prompt_avoids_managed_mission_operator_jargon() -> None:
    """VAL-JARGON-MM — planner-style chat avoids operator mission-registry language."""
    assert "managed mission" not in _DEFAULT_CHAT_SYSTEM_PROMPT.lower()
    assert "managed mission" not in _BUILDER_TURN_SYSTEM_INJECTION.lower()


def test_default_prompt_contains_ham_brand_canon() -> None:
    """VAL-BRAND-001 — default prompt embeds the HAM first-code-monkey-in-space origin canon."""
    base = _DEFAULT_CHAT_SYSTEM_PROMPT
    low = base.lower()
    assert "first code monkey launched into space" in low
    assert "ham" in low and "origin" in low


def test_default_prompt_tells_ham_not_to_deny_space_monkey_lore() -> None:
    """VAL-BRAND-002 — prompt instructs Ham not to deny the code-monkey/space lore."""
    base = _DEFAULT_CHAT_SYSTEM_PROMPT
    low = base.lower()
    assert "never deny" in low
    assert "never call it a myth" in low
    assert "embrace" in low


def test_default_prompt_uses_lore_only_when_relevant() -> None:
    """VAL-BRAND-003 — prompt requires tasteful, relevance-bounded lore use."""
    base = _DEFAULT_CHAT_SYSTEM_PROMPT
    low = base.lower()
    assert "lightly" in low
    assert "only when relevant" in low
    assert "do not force the lore" in low
    for relevant_ctx in ("identity", "origin", "mascot", "onboarding", "casual check-ins"):
        assert relevant_ctx in low, f"missing relevance hint: {relevant_ctx!r}"


def test_default_prompt_guides_warm_concise_ham_self_description() -> None:
    """VAL-BRAND-009 — casual self-description tone is warm, playful, concise, HAM-branded."""
    base = _DEFAULT_CHAT_SYSTEM_PROMPT
    low = base.lower()
    assert "casual voice" in low
    for hint in ("warm", "playful", "concis"):
        assert hint in low, f"missing casual tone hint: {hint!r}"
    for casual_q in ("who are you", "tell me about yourself", "what is ham", "what have you been up to"):
        assert casual_q in low, f"missing casual prompt cue: {casual_q!r}"
    assert "do not list internal tools" in low
    assert "inventory dump" in low


def test_default_prompt_excludes_forbidden_internal_tokens() -> None:
    """VAL-SAFETY-001 / VAL-BRAND-007 — brand canon must not leak raw internal vocabulary."""
    base = _DEFAULT_CHAT_SYSTEM_PROMPT
    forbidden = (
        "HERMES_GATEWAY",
        "HAM_DROID_EXEC_TOKEN",
        "HAM_CURSOR_AGENT_LAUNCH_TOKEN",
        "opencode_cli",
        "claude_code",
        "factory_droid_audit",
        "factory_droid_build",
        "cursor_cloud",
        "proposal_digest",
        "base_revision",
        ".ham/runs",
        "operator.phase",
    )
    for tok in forbidden:
        assert tok not in base, f"forbidden token leaked into default prompt: {tok!r}"


def test_chat_system_prompt_preserves_brand_canon_when_catalog_is_huge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-BRAND-006 — oversize catalog blocks must not crowd out base brand canon under the assembly cap."""
    monkeypatch.setattr(
        "src.api.chat.render_skills_for_system_prompt",
        lambda _: "x" * 25_000,
    )
    monkeypatch.setattr(
        "src.api.chat.render_subagents_for_system_prompt",
        lambda _: "y" * 25_000,
    )
    out = _chat_system_prompt(
        include_operator_skills=True,
        include_operator_subagents=True,
        enable_ui_actions=True,
    )
    assert "first code monkey launched into space" in out.lower()
    assert "Casual voice" in out
    assert "HAM_UI_ACTIONS_JSON:" in out
    assert len(out) <= _MAX_SYSTEM_PROMPT_CHARS


def test_chat_system_prompt_requires_completion_claim_artifacts() -> None:
    """VAL-BRAND-008 — completion-claim guardrail remains intact after brand canon edits."""
    base = _DEFAULT_CHAT_SYSTEM_PROMPT
    assert "Completion-claim rule" in base
    for tok in ("ham_run_id", "snapshot_id", "pr_url", "control_plane_run_id"):
        assert tok in base, f"missing completion-claim artifact token: {tok!r}"


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
