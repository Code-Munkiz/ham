"""Tests for src/ham/build_registry — unwired Game Pack registry loader/composer."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from src.ham.build_registry import (
    BuildRegistryConfigError,
    compose_build_recipe,
    load_registry_pack,
    render_playbook_context,
    validate_registry_pack,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
GAME_PACK_ROOT = REPO_ROOT / "docs/build-kit-registry-v2/game-pack"

EXPECTED_MECHANIC_ORDER = (
    "mechanic.score",
    "mechanic.economy",
    "mechanic.upgrades",
    "mechanic.save-load",
)

EXPECTED_TRIVIA_MECHANIC_ORDER = (
    "mechanic.question-set",
    "mechanic.score",
    "mechanic.timer",
    "mechanic.answer-validation",
    "mechanic.progression",
)

EXPECTED_BRANCHING_NARRATIVE_MECHANIC_ORDER = (
    "mechanic.story-node-graph",
    "mechanic.story-flags",
    "mechanic.inventory-lite",
    "mechanic.choice-resolution",
    "mechanic.ending-resolution",
)

EXPECTED_MEMORY_MATCH_MECHANIC_ORDER = (
    "mechanic.card-pair-set",
    "mechanic.card-flip-state",
    "mechanic.interaction-lock",
    "mechanic.match-detection",
    "mechanic.move-counter",
    "mechanic.victory-detection",
)

EXPECTED_WORD_DAILY_MECHANIC_ORDER = (
    "mechanic.word-target",
    "mechanic.daily-seed",
    "mechanic.guess-grid",
    "mechanic.attempt-limit",
    "mechanic.letter-feedback",
    "mechanic.win-loss-state",
    "mechanic.keyboard-input",
)

EXPECTED_DAILY_PUZZLE_GRID_MECHANIC_ORDER = (
    "mechanic.puzzle-seed",
    "mechanic.grid-state",
    "mechanic.constraint-rules",
    "mechanic.cell-interaction",
    "mechanic.mistake-tracking",
    "mechanic.hint-system-lite",
    "mechanic.completion-check",
)

EXPECTED_RESOURCE_MANAGEMENT_SIM_MECHANIC_ORDER = (
    "mechanic.resource-pool",
    "mechanic.capacity-limit",
    "mechanic.production-chain",
    "mechanic.allocation-decision",
    "mechanic.turn-or-tick-loop",
    "mechanic.upgrade-path",
    "mechanic.event-modifier",
    "mechanic.goal-and-failure-state",
)

EXPECTED_HANGMAN_LITE_MECHANIC_ORDER = (
    "mechanic.hidden-word",
    "mechanic.letter-guessing",
    "mechanic.duplicate-guess-prevention",
    "mechanic.reveal-state",
    "mechanic.wrong-guess-limit",
    "mechanic.hangman-win-loss-state",
)

EXPECTED_TYPING_SPEED_RACER_MECHANIC_ORDER = (
    "mechanic.typing-prompt-set",
    "mechanic.timer-or-race-clock",
    "mechanic.typing-input-stream",
    "mechanic.mistake-tracking-typing",
    "mechanic.accuracy-scoring",
    "mechanic.wpm-calculation",
    "mechanic.streak-combo",
    "mechanic.typing-result-state",
)

WAVE_1_APP_TYPES = (
    "game.idle-incremental",
    "game.trivia-timer",
    "game.branching-narrative",
    "game.memory-match",
    "game.word-daily",
)

WAVE_1_ADAPTIVE_POLICY_LIST_FIELDS = (
    "hard_constraints",
    "soft_defaults",
    "user_overridable",
    "clarify_if_changed",
    "out_of_scope_unless_explicit",
)

WAVE_1_CONFLICT_POLICY_KEYS = (
    "user_explicit_overrides_soft_defaults",
    "safety_constraints_override_user_request",
    "core_loop_conflicts_require_clarification",
    "out_of_scope_items_require_explicit_request",
    "fallback_to_v1_or_generic_when_recipe_no_longer_fits",
)


@pytest.fixture
def game_pack_root() -> Path:
    return GAME_PACK_ROOT


class TestHappyPath:
    def test_load_docs_game_pack(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        assert pack.pack_id == "pack.game"
        assert pack.schema_version == "0.1"
        assert len(pack.modules) == 192

    def test_validate_docs_game_pack(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)

    def test_compose_idle_incremental(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        recipe = compose_build_recipe(pack, "game.idle-incremental")
        assert recipe.app_type_id == "game.idle-incremental"
        assert recipe.stack_kit_id == "stack.dom-game-minimal"
        assert recipe.mechanic_ids == EXPECTED_MECHANIC_ORDER

    def test_render_starts_with_header(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        recipe = compose_build_recipe(pack, "game.idle-incremental")
        rendered = render_playbook_context(recipe)
        assert rendered.startswith("Build Kit Registry v2 — BuildRecipe\n")

    def test_render_includes_key_ids_and_safety(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.idle-incremental")
        rendered = render_playbook_context(recipe)
        assert "game.idle-incremental" in rendered
        assert "stack.dom-game-minimal" in rendered
        assert "validator.no-negative-currency" in rendered
        assert "no-network-egress-for-mvp" in rendered
        assert "Safety constraints:" in rendered

    def test_render_is_deterministic(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.idle-incremental")
        first = render_playbook_context(recipe)
        second = render_playbook_context(recipe)
        assert first == second

    def test_render_under_default_budget(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.idle-incremental")
        rendered = render_playbook_context(recipe)
        assert len(rendered) <= 12_000


class TestTriviaTimerRecipe:
    def test_compose_trivia_timer(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        recipe = compose_build_recipe(pack, "game.trivia-timer")
        assert recipe.app_type_id == "game.trivia-timer"
        assert recipe.stack_kit_id == "stack.dom-game-minimal"
        assert recipe.mechanic_ids == EXPECTED_TRIVIA_MECHANIC_ORDER

    def test_render_trivia_includes_key_ids(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.trivia-timer")
        rendered = render_playbook_context(recipe)
        assert "game.trivia-timer" in rendered
        assert "stack.dom-game-minimal" in rendered
        assert "validator.timer-cleanup" in rendered
        assert "validator.score-calculation" in rendered
        assert "validator.question-progression" in rendered
        assert "static-question-data-for-mvp" in rendered

    def test_render_trivia_under_default_budget(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.trivia-timer")
        rendered = render_playbook_context(recipe)
        assert len(rendered) <= 12_000
        assert rendered.startswith("Build Kit Registry v2 — BuildRecipe\n")

    def test_idle_recipe_still_compose_after_trivia_added(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        recipe = compose_build_recipe(pack, "game.idle-incremental")
        assert recipe.mechanic_ids == EXPECTED_MECHANIC_ORDER


class TestBranchingNarrativeRecipe:
    def test_compose_branching_narrative(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        recipe = compose_build_recipe(pack, "game.branching-narrative")
        assert recipe.app_type_id == "game.branching-narrative"
        assert recipe.stack_kit_id == "stack.dom-game-minimal"
        assert recipe.mechanic_ids == EXPECTED_BRANCHING_NARRATIVE_MECHANIC_ORDER

    def test_render_branching_narrative_includes_key_ids(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.branching-narrative")
        rendered = render_playbook_context(recipe)
        assert "game.branching-narrative" in rendered
        assert "stack.dom-game-minimal" in rendered
        assert "mechanic.story-node-graph" in rendered
        assert "mechanic.choice-resolution" in rendered
        assert "validator.story-graph-reachability" in rendered
        assert "validator.no-dead-end-choice" in rendered
        assert "static-story-data-for-mvp" in rendered

    def test_render_branching_narrative_under_default_budget(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.branching-narrative")
        rendered = render_playbook_context(recipe)
        assert len(rendered) <= 12_000
        assert rendered.startswith("Build Kit Registry v2 — BuildRecipe\n")

    def test_idle_and_trivia_still_compose_after_branching_added(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        idle = compose_build_recipe(pack, "game.idle-incremental")
        trivia = compose_build_recipe(pack, "game.trivia-timer")
        assert idle.mechanic_ids == EXPECTED_MECHANIC_ORDER
        assert trivia.mechanic_ids == EXPECTED_TRIVIA_MECHANIC_ORDER


class TestMemoryMatchRecipe:
    def test_compose_memory_match(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        recipe = compose_build_recipe(pack, "game.memory-match")
        assert recipe.app_type_id == "game.memory-match"
        assert recipe.stack_kit_id == "stack.dom-game-minimal"
        assert recipe.mechanic_ids == EXPECTED_MEMORY_MATCH_MECHANIC_ORDER

    def test_render_memory_match_includes_key_ids(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.memory-match")
        rendered = render_playbook_context(recipe)
        assert "game.memory-match" in rendered
        assert "stack.dom-game-minimal" in rendered
        assert "mechanic.card-pair-set" in rendered
        assert "mechanic.card-flip-state" in rendered
        assert "mechanic.match-detection" in rendered
        assert "mechanic.interaction-lock" in rendered
        assert "validator.flip-lock-prevents-third-card" in rendered
        assert "validator.match-completion" in rendered
        assert "static-card-data-for-mvp" in rendered

    def test_render_memory_match_under_default_budget(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.memory-match")
        rendered = render_playbook_context(recipe)
        assert len(rendered) <= 12_000
        assert rendered.startswith("Build Kit Registry v2 — BuildRecipe\n")

    def test_other_recipes_still_compose_after_memory_match_added(
        self, game_pack_root: Path
    ):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        idle = compose_build_recipe(pack, "game.idle-incremental")
        trivia = compose_build_recipe(pack, "game.trivia-timer")
        branching = compose_build_recipe(pack, "game.branching-narrative")
        assert idle.mechanic_ids == EXPECTED_MECHANIC_ORDER
        assert trivia.mechanic_ids == EXPECTED_TRIVIA_MECHANIC_ORDER
        assert branching.mechanic_ids == EXPECTED_BRANCHING_NARRATIVE_MECHANIC_ORDER


class TestWordDailyRecipe:
    def test_compose_word_daily(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        recipe = compose_build_recipe(pack, "game.word-daily")
        assert recipe.app_type_id == "game.word-daily"
        assert recipe.stack_kit_id == "stack.dom-game-minimal"
        assert recipe.mechanic_ids == EXPECTED_WORD_DAILY_MECHANIC_ORDER

    def test_render_word_daily_includes_key_ids(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.word-daily")
        rendered = render_playbook_context(recipe)
        assert "game.word-daily" in rendered
        assert "stack.dom-game-minimal" in rendered
        assert "mechanic.word-target" in rendered
        assert "mechanic.guess-grid" in rendered
        assert "mechanic.letter-feedback" in rendered
        assert "mechanic.daily-seed" in rendered
        assert "validator.duplicate-letter-feedback" in rendered
        assert "validator.daily-seed-stability" in rendered
        assert "static-word-list-for-mvp" in rendered

    def test_render_word_daily_under_default_budget(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.word-daily")
        rendered = render_playbook_context(recipe)
        assert len(rendered) <= 12_000
        assert rendered.startswith("Build Kit Registry v2 — BuildRecipe\n")

    def test_other_recipes_still_compose_after_word_daily_added(
        self, game_pack_root: Path
    ):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        idle = compose_build_recipe(pack, "game.idle-incremental")
        trivia = compose_build_recipe(pack, "game.trivia-timer")
        branching = compose_build_recipe(pack, "game.branching-narrative")
        memory = compose_build_recipe(pack, "game.memory-match")
        assert idle.mechanic_ids == EXPECTED_MECHANIC_ORDER
        assert trivia.mechanic_ids == EXPECTED_TRIVIA_MECHANIC_ORDER
        assert branching.mechanic_ids == EXPECTED_BRANCHING_NARRATIVE_MECHANIC_ORDER
        assert memory.mechanic_ids == EXPECTED_MEMORY_MATCH_MECHANIC_ORDER


class TestDailyPuzzleGridRecipe:
    def test_compose_daily_puzzle_grid(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        recipe = compose_build_recipe(pack, "game.daily-puzzle-grid")
        assert recipe.app_type_id == "game.daily-puzzle-grid"
        assert recipe.stack_kit_id == "stack.dom-game-minimal"
        assert recipe.mechanic_ids == EXPECTED_DAILY_PUZZLE_GRID_MECHANIC_ORDER

    def test_render_daily_puzzle_grid_includes_key_ids(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.daily-puzzle-grid")
        rendered = render_playbook_context(recipe)
        assert "game.daily-puzzle-grid" in rendered
        assert "stack.dom-game-minimal" in rendered
        assert "mechanic.grid-state" in rendered
        assert "mechanic.constraint-rules" in rendered
        assert "mechanic.puzzle-seed" in rendered
        assert "validator.grid-dimensions" in rendered
        assert "validator.constraint-consistency" in rendered
        assert "validator.completion-detection" in rendered
        assert "static-puzzle-data-for-mvp" in rendered

    def test_render_daily_puzzle_grid_under_default_budget(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.daily-puzzle-grid")
        rendered = render_playbook_context(recipe)
        assert len(rendered) <= 12_000
        assert rendered.startswith("Build Kit Registry v2 — BuildRecipe\n")

    def test_daily_puzzle_grid_adaptive_policy_fields(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        app = pack.module_data("game.daily-puzzle-grid")
        for field in WAVE_1_ADAPTIVE_POLICY_LIST_FIELDS:
            value = app.get(field)
            assert isinstance(value, list), f"game.daily-puzzle-grid: {field} must be a list"
            assert value, f"game.daily-puzzle-grid: {field} must be non-empty"

        conflict_policy = app.get("conflict_policy")
        assert isinstance(conflict_policy, dict)
        for key in WAVE_1_CONFLICT_POLICY_KEYS:
            assert key in conflict_policy
            assert conflict_policy[key] is True

    def test_wave1_recipes_still_compose_after_daily_puzzle_grid_added(
        self, game_pack_root: Path
    ):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        idle = compose_build_recipe(pack, "game.idle-incremental")
        trivia = compose_build_recipe(pack, "game.trivia-timer")
        branching = compose_build_recipe(pack, "game.branching-narrative")
        memory = compose_build_recipe(pack, "game.memory-match")
        word = compose_build_recipe(pack, "game.word-daily")
        puzzle = compose_build_recipe(pack, "game.daily-puzzle-grid")
        assert idle.mechanic_ids == EXPECTED_MECHANIC_ORDER
        assert trivia.mechanic_ids == EXPECTED_TRIVIA_MECHANIC_ORDER
        assert branching.mechanic_ids == EXPECTED_BRANCHING_NARRATIVE_MECHANIC_ORDER
        assert memory.mechanic_ids == EXPECTED_MEMORY_MATCH_MECHANIC_ORDER
        assert word.mechanic_ids == EXPECTED_WORD_DAILY_MECHANIC_ORDER
        assert puzzle.mechanic_ids == EXPECTED_DAILY_PUZZLE_GRID_MECHANIC_ORDER


class TestResourceManagementSimRecipe:
    def test_compose_resource_management_sim(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        recipe = compose_build_recipe(pack, "game.resource-management-sim")
        assert recipe.app_type_id == "game.resource-management-sim"
        assert recipe.stack_kit_id == "stack.dom-game-minimal"
        assert recipe.mechanic_ids == EXPECTED_RESOURCE_MANAGEMENT_SIM_MECHANIC_ORDER

    def test_render_resource_management_sim_includes_key_ids(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.resource-management-sim")
        rendered = render_playbook_context(recipe)
        assert "game.resource-management-sim" in rendered
        assert "stack.dom-game-minimal" in rendered
        assert "mechanic.resource-pool" in rendered
        assert "mechanic.production-chain" in rendered
        assert "mechanic.allocation-decision" in rendered
        assert "mechanic.capacity-limit" in rendered
        assert "mechanic.turn-or-tick-loop" in rendered
        assert "validator.no-negative-resources" in rendered
        assert "validator.production-chain-consistency" in rendered
        assert "validator.allocation-bounds" in rendered
        assert "validator.goal-state-detection" in rendered
        assert "static-sim-data-for-mvp" in rendered

    def test_render_resource_management_sim_under_default_budget(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.resource-management-sim")
        rendered = render_playbook_context(recipe)
        assert len(rendered) <= 12_000
        assert rendered.startswith("Build Kit Registry v2 — BuildRecipe\n")

    def test_resource_management_sim_adaptive_policy_fields(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        app = pack.module_data("game.resource-management-sim")
        for field in WAVE_1_ADAPTIVE_POLICY_LIST_FIELDS:
            value = app.get(field)
            assert isinstance(value, list), (
                f"game.resource-management-sim: {field} must be a list"
            )
            assert value, f"game.resource-management-sim: {field} must be non-empty"

        conflict_policy = app.get("conflict_policy")
        assert isinstance(conflict_policy, dict)
        for key in WAVE_1_CONFLICT_POLICY_KEYS:
            assert key in conflict_policy
            assert conflict_policy[key] is True

    def test_existing_six_recipes_still_compose_after_resource_management_sim_added(
        self, game_pack_root: Path
    ):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        idle = compose_build_recipe(pack, "game.idle-incremental")
        trivia = compose_build_recipe(pack, "game.trivia-timer")
        branching = compose_build_recipe(pack, "game.branching-narrative")
        memory = compose_build_recipe(pack, "game.memory-match")
        word = compose_build_recipe(pack, "game.word-daily")
        puzzle = compose_build_recipe(pack, "game.daily-puzzle-grid")
        assert idle.mechanic_ids == EXPECTED_MECHANIC_ORDER
        assert trivia.mechanic_ids == EXPECTED_TRIVIA_MECHANIC_ORDER
        assert branching.mechanic_ids == EXPECTED_BRANCHING_NARRATIVE_MECHANIC_ORDER
        assert memory.mechanic_ids == EXPECTED_MEMORY_MATCH_MECHANIC_ORDER
        assert word.mechanic_ids == EXPECTED_WORD_DAILY_MECHANIC_ORDER
        assert puzzle.mechanic_ids == EXPECTED_DAILY_PUZZLE_GRID_MECHANIC_ORDER


class TestHangmanLiteRecipe:
    def test_compose_hangman_lite(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        recipe = compose_build_recipe(pack, "game.hangman-lite")
        assert recipe.app_type_id == "game.hangman-lite"
        assert recipe.stack_kit_id == "stack.dom-game-minimal"
        assert recipe.mechanic_ids == EXPECTED_HANGMAN_LITE_MECHANIC_ORDER

    def test_render_hangman_lite_includes_key_ids(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.hangman-lite")
        rendered = render_playbook_context(recipe)
        assert "game.hangman-lite" in rendered
        assert "stack.dom-game-minimal" in rendered
        assert "mechanic.hidden-word" in rendered
        assert "mechanic.letter-guessing" in rendered
        assert "mechanic.reveal-state" in rendered
        assert "mechanic.wrong-guess-limit" in rendered
        assert "validator.letter-reveal-correctness" in rendered
        assert "validator.duplicate-guess-blocking" in rendered
        assert "validator.hangman-win-loss-detection" in rendered
        assert "static-word-list-for-mvp" in rendered

    def test_render_hangman_lite_under_default_budget(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.hangman-lite")
        rendered = render_playbook_context(recipe)
        assert len(rendered) <= 12_000
        assert rendered.startswith("Build Kit Registry v2 — BuildRecipe\n")

    def test_hangman_lite_adaptive_policy_fields(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        app = pack.module_data("game.hangman-lite")
        for field in WAVE_1_ADAPTIVE_POLICY_LIST_FIELDS:
            value = app.get(field)
            assert isinstance(value, list), f"game.hangman-lite: {field} must be a list"
            assert value, f"game.hangman-lite: {field} must be non-empty"

        conflict_policy = app.get("conflict_policy")
        assert isinstance(conflict_policy, dict)
        for key in WAVE_1_CONFLICT_POLICY_KEYS:
            assert key in conflict_policy
            assert conflict_policy[key] is True

    def test_existing_seven_recipes_still_compose_after_hangman_lite_added(
        self, game_pack_root: Path
    ):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        idle = compose_build_recipe(pack, "game.idle-incremental")
        trivia = compose_build_recipe(pack, "game.trivia-timer")
        branching = compose_build_recipe(pack, "game.branching-narrative")
        memory = compose_build_recipe(pack, "game.memory-match")
        word = compose_build_recipe(pack, "game.word-daily")
        puzzle = compose_build_recipe(pack, "game.daily-puzzle-grid")
        sim = compose_build_recipe(pack, "game.resource-management-sim")
        assert idle.mechanic_ids == EXPECTED_MECHANIC_ORDER
        assert trivia.mechanic_ids == EXPECTED_TRIVIA_MECHANIC_ORDER
        assert branching.mechanic_ids == EXPECTED_BRANCHING_NARRATIVE_MECHANIC_ORDER
        assert memory.mechanic_ids == EXPECTED_MEMORY_MATCH_MECHANIC_ORDER
        assert word.mechanic_ids == EXPECTED_WORD_DAILY_MECHANIC_ORDER
        assert puzzle.mechanic_ids == EXPECTED_DAILY_PUZZLE_GRID_MECHANIC_ORDER
        assert sim.mechanic_ids == EXPECTED_RESOURCE_MANAGEMENT_SIM_MECHANIC_ORDER


class TestTypingSpeedRacerRecipe:
    def test_compose_typing_speed_racer(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        recipe = compose_build_recipe(pack, "game.typing-speed-racer")
        assert recipe.app_type_id == "game.typing-speed-racer"
        assert recipe.stack_kit_id == "stack.dom-game-minimal"
        assert recipe.mechanic_ids == EXPECTED_TYPING_SPEED_RACER_MECHANIC_ORDER

    def test_render_typing_speed_racer_includes_key_ids(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.typing-speed-racer")
        rendered = render_playbook_context(recipe)
        assert "game.typing-speed-racer" in rendered
        assert "stack.dom-game-minimal" in rendered
        assert "mechanic.typing-prompt-set" in rendered
        assert "mechanic.typing-input-stream" in rendered
        assert "mechanic.wpm-calculation" in rendered
        assert "mechanic.accuracy-scoring" in rendered
        assert "validator.wpm-calculation-consistency" in rendered
        assert "validator.accuracy-score-bounds" in rendered
        assert "validator.input-lock-after-finish" in rendered
        assert "static-prompt-list-for-mvp" in rendered

    def test_render_typing_speed_racer_under_default_budget(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.typing-speed-racer")
        rendered = render_playbook_context(recipe)
        assert len(rendered) <= 12_000
        assert rendered.startswith("Build Kit Registry v2 — BuildRecipe\n")

    def test_typing_speed_racer_adaptive_policy_fields(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        app = pack.module_data("game.typing-speed-racer")
        for field in WAVE_1_ADAPTIVE_POLICY_LIST_FIELDS:
            value = app.get(field)
            assert isinstance(value, list), f"game.typing-speed-racer: {field} must be a list"
            assert value, f"game.typing-speed-racer: {field} must be non-empty"

        conflict_policy = app.get("conflict_policy")
        assert isinstance(conflict_policy, dict)
        for key in WAVE_1_CONFLICT_POLICY_KEYS:
            assert key in conflict_policy
            assert conflict_policy[key] is True

    def test_existing_eight_recipes_still_compose_after_typing_speed_racer_added(
        self, game_pack_root: Path
    ):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        idle = compose_build_recipe(pack, "game.idle-incremental")
        trivia = compose_build_recipe(pack, "game.trivia-timer")
        branching = compose_build_recipe(pack, "game.branching-narrative")
        memory = compose_build_recipe(pack, "game.memory-match")
        word = compose_build_recipe(pack, "game.word-daily")
        puzzle = compose_build_recipe(pack, "game.daily-puzzle-grid")
        sim = compose_build_recipe(pack, "game.resource-management-sim")
        hangman = compose_build_recipe(pack, "game.hangman-lite")
        assert idle.mechanic_ids == EXPECTED_MECHANIC_ORDER
        assert trivia.mechanic_ids == EXPECTED_TRIVIA_MECHANIC_ORDER
        assert branching.mechanic_ids == EXPECTED_BRANCHING_NARRATIVE_MECHANIC_ORDER
        assert memory.mechanic_ids == EXPECTED_MEMORY_MATCH_MECHANIC_ORDER
        assert word.mechanic_ids == EXPECTED_WORD_DAILY_MECHANIC_ORDER
        assert puzzle.mechanic_ids == EXPECTED_DAILY_PUZZLE_GRID_MECHANIC_ORDER
        assert sim.mechanic_ids == EXPECTED_RESOURCE_MANAGEMENT_SIM_MECHANIC_ORDER
        assert hangman.mechanic_ids == EXPECTED_HANGMAN_LITE_MECHANIC_ORDER


class TestWave1AdaptivePolicyFields:
    @pytest.mark.parametrize("app_type_id", WAVE_1_APP_TYPES)
    def test_wave1_app_types_include_adaptive_policy_fields(
        self, game_pack_root: Path, app_type_id: str
    ):
        pack = load_registry_pack(game_pack_root)
        app = pack.module_data(app_type_id)
        for field in WAVE_1_ADAPTIVE_POLICY_LIST_FIELDS:
            value = app.get(field)
            assert isinstance(value, list), f"{app_type_id}: {field} must be a list"
            assert value, f"{app_type_id}: {field} must be non-empty"

        conflict_policy = app.get("conflict_policy")
        assert isinstance(conflict_policy, dict), (
            f"{app_type_id}: conflict_policy must be a mapping"
        )
        for key in WAVE_1_CONFLICT_POLICY_KEYS:
            assert key in conflict_policy, f"{app_type_id}: missing conflict_policy.{key}"
            assert conflict_policy[key] is True, (
                f"{app_type_id}: conflict_policy.{key} must be true"
            )


class TestBrokenFixtures:
    def test_broken_reference_raises(self, tmp_path: Path, game_pack_root: Path):
        shutil.copytree(game_pack_root, tmp_path / "pack")
        pack_root = tmp_path / "pack"
        economy_path = pack_root / "mechanics/economy.yaml"
        data = yaml.safe_load(economy_path.read_text(encoding="utf-8"))
        data["depends_on"] = ["mechanic.nonexistent"]
        economy_path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")

        pack = load_registry_pack(pack_root)
        with pytest.raises(BuildRegistryConfigError, match="mechanic.nonexistent"):
            validate_registry_pack(pack)

    def test_dependency_cycle_raises(self, tmp_path: Path, game_pack_root: Path):
        shutil.copytree(game_pack_root, tmp_path / "pack")
        pack_root = tmp_path / "pack"
        score_path = pack_root / "mechanics/score.yaml"
        data = yaml.safe_load(score_path.read_text(encoding="utf-8"))
        data["depends_on"] = ["mechanic.economy"]
        score_path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")

        pack = load_registry_pack(pack_root)
        with pytest.raises(BuildRegistryConfigError, match="cycle"):
            validate_registry_pack(pack)


class TestNoRuntimeWiring:
    def test_builder_llm_scaffold_lazy_imports_build_registry(self):
        import src.ham.builder_llm_scaffold as scaffold

        source = Path(scaffold.__file__).read_text(encoding="utf-8")
        assert "resolve_scaffold_context" in source
        assert "from src.ham.build_registry.scaffold_context import" in source
        module_lines = source.splitlines()
        for line in module_lines:
            stripped = line.strip()
            if stripped.startswith("from src.ham.build_registry") or stripped.startswith(
                "import src.ham.build_registry"
            ):
                assert stripped.startswith("from src.ham.build_registry.scaffold_context import")
                assert "resolve_scaffold_context" in stripped

    def test_builder_kits_does_not_import_build_registry(self):
        import src.ham.builder_kits as kits

        source = Path(kits.__file__).read_text(encoding="utf-8")
        assert "build_registry" not in source
