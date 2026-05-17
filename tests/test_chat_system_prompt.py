"""System prompt assembly for chat (UI actions must survive catalog size)."""

from __future__ import annotations

import pytest

from src.api.chat import (
    _DEFAULT_CHAT_SYSTEM_PROMPT,
    _MAX_SYSTEM_PROMPT_CHARS,
    _chat_system_prompt,
    _fit_system_prompt_under_cap_with_vision_tail,
)
from src.ham.chat_user_content import vision_system_suffix


def test_fit_system_prompt_preserves_vision_suffix_when_base_overflows_cap() -> None:
    """Multimodal system assembly used to slice ``combined[:cap]``, dropping the vision tail."""
    suf = vision_system_suffix()
    assert len(suf) < _MAX_SYSTEM_PROMPT_CHARS
    pad_len = _MAX_SYSTEM_PROMPT_CHARS - len(suf) + 500
    base = "p" * pad_len
    out = _fit_system_prompt_under_cap_with_vision_tail(
        base,
        vision_tail=suf,
        max_chars=_MAX_SYSTEM_PROMPT_CHARS,
    )
    assert out.endswith(suf)
    assert len(out) == _MAX_SYSTEM_PROMPT_CHARS
    assert "**Vision (workspace chat):**" in out


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
