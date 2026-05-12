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
    assert "No fabricated execution" in base
    for negated in (
        "NO shell",
        "NO git",
        "NO build",
        "NO push",
        "NO PR",
        "NO snapshot",
        "NO cron",
        "NO filesystem tools",
    ):
        assert negated in base, f"missing negation: {negated!r}"
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
