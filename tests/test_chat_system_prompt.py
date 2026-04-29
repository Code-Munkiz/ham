"""System prompt assembly for chat (UI actions must survive catalog size)."""

from __future__ import annotations

import pytest

from src.api.chat import _MAX_SYSTEM_PROMPT_CHARS, _chat_system_prompt


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
