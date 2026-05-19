"""Tests for src/ham/builder_template_kinds.py — Phase 2 Subsystem 9."""

from __future__ import annotations

import pytest

from src.ham.builder_template_kinds import _REGISTRY, select_scaffold_path


# ---------------------------------------------------------------------------
# select_scaffold_path — deterministic kinds
# ---------------------------------------------------------------------------


class TestDeterministicKinds:
    def test_calculator_returns_deterministic(self):
        assert select_scaffold_path("calculator") == "deterministic"

    def test_tetris_returns_deterministic(self):
        assert select_scaffold_path("tetris") == "deterministic"

    def test_registry_contains_calculator(self):
        assert "calculator" in _REGISTRY
        assert _REGISTRY["calculator"] == "deterministic"

    def test_registry_contains_tetris(self):
        assert "tetris" in _REGISTRY
        assert _REGISTRY["tetris"] == "deterministic"


# ---------------------------------------------------------------------------
# select_scaffold_path — LLM kinds (default)
# ---------------------------------------------------------------------------


class TestLLMKinds:
    def test_unknown_kind_returns_llm(self):
        assert select_scaffold_path("unknown_kind") == "llm"

    def test_todo_returns_llm(self):
        assert select_scaffold_path("todo") == "llm"

    def test_dashboard_returns_llm(self):
        assert select_scaffold_path("dashboard") == "llm"

    def test_landing_page_returns_llm(self):
        assert select_scaffold_path("landing-page") == "llm"

    def test_empty_string_returns_llm(self):
        assert select_scaffold_path("") == "llm"

    def test_whitespace_string_returns_llm(self):
        assert select_scaffold_path("  ") == "llm"

    def test_novel_kind_returns_llm(self):
        # Any future kind not yet in the registry defaults to llm.
        assert select_scaffold_path("ai-chat-assistant") == "llm"


# ---------------------------------------------------------------------------
# select_scaffold_path — case sensitivity
# ---------------------------------------------------------------------------


class TestCaseSensitivity:
    def test_calculator_is_case_sensitive(self):
        # Only exact lowercase "calculator" is in the registry.
        assert select_scaffold_path("Calculator") == "llm"
        assert select_scaffold_path("CALCULATOR") == "llm"

    def test_tetris_is_case_sensitive(self):
        assert select_scaffold_path("Tetris") == "llm"
        assert select_scaffold_path("TETRIS") == "llm"


# ---------------------------------------------------------------------------
# Return type invariant
# ---------------------------------------------------------------------------


class TestReturnType:
    @pytest.mark.parametrize(
        "kind",
        [
            "calculator",
            "tetris",
            "todo",
            "dashboard",
            "landing-page",
            "",
            "anything",
        ],
    )
    def test_return_value_is_valid_literal(self, kind: str):
        result = select_scaffold_path(kind)
        assert result in {"deterministic", "llm"}
