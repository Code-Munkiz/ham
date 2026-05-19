"""Tests for src/ham/builder_template_kinds.py — Phase 2 Subsystem 9.

Locks the strangler-pattern contract:

- ``calculator`` / ``tetris`` route to ``legacy_deterministic`` (temporary
  compatibility only).
- Everything else — including unknown kinds, whitespace variants, and
  future kinds — routes to ``llm``.
- The legacy set is **frozen** at exactly ``{calculator, tetris}``. Any
  attempt to add a new legacy kind must update the lock test
  deliberately (which acts as a review checkpoint).
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
# select_scaffold_path — legacy deterministic kinds
# ---------------------------------------------------------------------------


class TestLegacyDeterministicKinds:
    def test_calculator_returns_legacy_deterministic(self):
        assert select_scaffold_path("calculator") == "legacy_deterministic"

    def test_tetris_returns_legacy_deterministic(self):
        assert select_scaffold_path("tetris") == "legacy_deterministic"

    def test_registry_contains_calculator(self):
        assert "calculator" in _REGISTRY
        assert _REGISTRY["calculator"] == "legacy_deterministic"

    def test_registry_contains_tetris(self):
        assert "tetris" in _REGISTRY
        assert _REGISTRY["tetris"] == "legacy_deterministic"

    def test_legacy_constant_matches_literal(self):
        assert LEGACY_DETERMINISTIC == "legacy_deterministic"
        assert LLM == "llm"


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

    def test_legacy_lookalike_does_not_match(self):
        # "deterministic" must never be a magic legacy key; the legacy set
        # is exactly {calculator, tetris}.
        assert select_scaffold_path("deterministic") == "llm"
        assert select_scaffold_path("legacy_deterministic") == "llm"


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
    def test_calculator_normalizes_to_legacy(self, raw: str):
        assert select_scaffold_path(raw) == "legacy_deterministic"

    @pytest.mark.parametrize(
        "raw",
        [
            "Tetris",
            "TETRIS",
            "  tetris  ",
            "tetris\t",
        ],
    )
    def test_tetris_normalizes_to_legacy(self, raw: str):
        assert select_scaffold_path(raw) == "legacy_deterministic"

    def test_non_string_input_returns_llm(self):
        assert select_scaffold_path(None) == "llm"  # type: ignore[arg-type]
        assert select_scaffold_path(123) == "llm"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# is_legacy_deterministic_kind helper
# ---------------------------------------------------------------------------


class TestIsLegacyHelper:
    def test_helper_true_for_legacy_kinds(self):
        assert is_legacy_deterministic_kind("calculator") is True
        assert is_legacy_deterministic_kind("tetris") is True
        # Normalization still applies.
        assert is_legacy_deterministic_kind("  Tetris  ") is True

    def test_helper_false_for_llm_kinds(self):
        assert is_legacy_deterministic_kind("todo") is False
        assert is_legacy_deterministic_kind("") is False
        assert is_legacy_deterministic_kind("unknown") is False


# ---------------------------------------------------------------------------
# Frozen legacy set — lock test (REVIEW CHECKPOINT)
# ---------------------------------------------------------------------------


class TestLegacySetLock:
    """If this test fails, you are trying to add a new legacy template kind.

    Per ADR-0011 the legacy set is **frozen** at ``{calculator, tetris}`` —
    new template kinds must route through the LLM scaffold path. If you
    truly need to extend the legacy set, update both the assertion and the
    accompanying ADR explaining why the LLM path cannot serve the new kind.
    """

    def test_legacy_kinds_set_is_exactly_calculator_and_tetris(self):
        assert _LEGACY_DETERMINISTIC_KINDS == frozenset({"calculator", "tetris"})

    def test_legacy_deterministic_kinds_public_helper_returns_same_frozen_set(self):
        out = legacy_deterministic_kinds()
        assert out == frozenset({"calculator", "tetris"})
        assert isinstance(out, frozenset)

    def test_no_unexpected_registry_entries(self):
        # The registry currently equals the legacy set; if a new kind is
        # added to _REGISTRY (with any value), this assertion will fail.
        assert set(_REGISTRY.keys()) == {"calculator", "tetris"}

    def test_every_registry_value_is_a_known_path(self):
        for kind, path in _REGISTRY.items():
            assert path in {"legacy_deterministic", "llm"}, (
                f"unexpected scaffold-path value for {kind!r}: {path!r}"
            )


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
        assert result in {"legacy_deterministic", "llm"}
