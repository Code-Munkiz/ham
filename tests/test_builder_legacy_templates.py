"""Tests for src/ham/builder_legacy_templates.py (ADR-0011 strangler facade).

Locks:
- the legacy detection facade matches the registry's legacy set,
- prompt detection routes tetris and calculator to the right legacy kind,
- non-legacy prompts return ``None`` (so chat will route them through
  the LLM scaffold path),
- the facade does not import or invoke any live model / gateway / agent.
"""

from __future__ import annotations

import src.ham.builder_legacy_templates as legacy
from src.ham.builder_legacy_templates import (
    LEGACY_TEMPLATE_KINDS,
    is_legacy_calculator_prompt,
    is_legacy_tetris_prompt,
    legacy_template_kind_for_prompt,
)
from src.ham.builder_template_kinds import legacy_deterministic_kinds


def test_legacy_template_kinds_mirrors_registry():
    assert LEGACY_TEMPLATE_KINDS == legacy_deterministic_kinds()
    assert LEGACY_TEMPLATE_KINDS == frozenset({"calculator", "tetris"})


def test_is_legacy_calculator_prompt_matches_canonical_phrasing():
    assert is_legacy_calculator_prompt("build me a calculator app")
    assert is_legacy_calculator_prompt("make a calc app")
    assert not is_legacy_calculator_prompt("build a tetris clone")
    assert not is_legacy_calculator_prompt("create a todo list app")


def test_is_legacy_tetris_prompt_matches_canonical_phrasing():
    assert is_legacy_tetris_prompt("build me a tetris clone")
    assert not is_legacy_tetris_prompt("make a calculator")
    assert not is_legacy_tetris_prompt("create a dashboard")


def test_legacy_template_kind_for_prompt_resolves_tetris_first():
    # Tetris is checked before calculator (precedence preserved from
    # builder_chat_scaffold). A prompt mentioning both lands on tetris.
    assert legacy_template_kind_for_prompt("tetris with a calculator sidebar") == "tetris"
    assert legacy_template_kind_for_prompt("build me a calculator") == "calculator"


def test_legacy_template_kind_for_prompt_returns_none_for_new_kinds():
    # Anything outside the legacy set must fall through to None so the
    # chat / worker routes it through the LLM scaffold path.
    for prompt in (
        "build me a todo app",
        "create a dashboard",
        "make a landing page",
        "spin up an analytics portal",
        "scaffold a chess game",
        "",
    ):
        assert legacy_template_kind_for_prompt(prompt) is None, prompt


def test_legacy_module_does_not_import_live_runtime_dependencies():
    # Strong signal that this facade is detection-only: no LLM client,
    # no gateway, no agent runtime imports leak into module namespace.
    forbidden = (
        "complete_chat_messages_openrouter",
        "stream_chat_turn",
        "complete_chat_turn",
        "execute_droid_workflow",
        "run_cursor_agent_launch",
        "generate_scaffold",
    )
    mod_attrs = set(vars(legacy).keys())
    for name in forbidden:
        assert name not in mod_attrs, (
            f"legacy templates facade must not re-export runtime API {name!r}"
        )
