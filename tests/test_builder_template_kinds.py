"""Tests for src/ham/builder_template_kinds.py — Phase 2 Subsystem 9.

The legacy_deterministic runtime path was retired. Every kind — including
``calculator`` and ``tetris`` — now routes to the LLM scaffold path. The
registry is empty and ``legacy_deterministic_kinds()`` returns the empty
set. Normalization (strip + lower) still works.
"""

from __future__ import annotations

import pytest

from src.ham.builder_template_kinds import (
    LEGACY_DETERMINISTIC,
    LLM,
    _LEGACY_DETERMINISTIC_KINDS,
    _REGISTRY,
    is_legacy_deterministic_kind,
    legacy_deterministic_kinds,
    select_scaffold_path,
)


# ---------------------------------------------------------------------------
# select_scaffold_path — every kind routes to LLM
# ---------------------------------------------------------------------------


class TestAllKindsRouteToLLM:
    def test_calculator_returns_llm(self):
        assert select_scaffold_path("calculator") == "llm"

    def test_tetris_returns_llm(self):
        assert select_scaffold_path("tetris") == "llm"

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
        assert select_scaffold_path("ai-chat-assistant") == "llm"

    def test_legacy_lookalike_routes_to_llm(self):
        assert select_scaffold_path("deterministic") == "llm"
        assert select_scaffold_path("legacy_deterministic") == "llm"

    def test_legacy_constants_match_literals(self):
        assert LEGACY_DETERMINISTIC == "legacy_deterministic"
        assert LLM == "llm"


# ---------------------------------------------------------------------------
# Normalization — strip + lower
# ---------------------------------------------------------------------------


class TestNormalization:
    @pytest.mark.parametrize(
        "raw",
        [
            "Calculator",
            "CALCULATOR",
            "  calculator  ",
            " Calculator\n",
            "calculator",
        ],
    )
    def test_calculator_variants_normalize_to_llm(self, raw: str):
        assert select_scaffold_path(raw) == "llm"

    @pytest.mark.parametrize(
        "raw",
        [
            "Tetris",
            "TETRIS",
            "  tetris  ",
            "tetris\t",
        ],
    )
    def test_tetris_variants_normalize_to_llm(self, raw: str):
        assert select_scaffold_path(raw) == "llm"

    def test_non_string_input_returns_llm(self):
        assert select_scaffold_path(None) == "llm"  # type: ignore[arg-type]
        assert select_scaffold_path(123) == "llm"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# is_legacy_deterministic_kind helper — always False after retirement
# ---------------------------------------------------------------------------


class TestIsLegacyHelper:
    def test_helper_false_for_calculator(self):
        assert is_legacy_deterministic_kind("calculator") is False

    def test_helper_false_for_tetris(self):
        assert is_legacy_deterministic_kind("tetris") is False

    def test_helper_false_for_other_kinds(self):
        assert is_legacy_deterministic_kind("todo") is False
        assert is_legacy_deterministic_kind("") is False
        assert is_legacy_deterministic_kind("unknown") is False


# ---------------------------------------------------------------------------
# Empty registry — retirement lock
# ---------------------------------------------------------------------------


class TestRegistryEmpty:
    def test_registry_is_empty(self):
        assert _REGISTRY == {}

    def test_legacy_deterministic_kinds_is_empty(self):
        assert _LEGACY_DETERMINISTIC_KINDS == frozenset()

    def test_legacy_deterministic_kinds_helper_returns_empty(self):
        out = legacy_deterministic_kinds()
        assert out == frozenset()
        assert isinstance(out, frozenset)


# ---------------------------------------------------------------------------
# Return type invariant — always "llm"
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
    def test_return_value_is_always_llm(self, kind: str):
        assert select_scaffold_path(kind) == "llm"
