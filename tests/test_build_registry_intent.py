"""Tests for Build Registry v2 prompt intent routing (ADR-0017 Phase 2E)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.ham.builder_chat_scaffold import _maybe_llm_scaffold_replace
from src.ham.builder_llm_scaffold import ScaffoldResult, _build_scaffold_messages
from src.ham.builder_plan import Plan, Step
from src.ham.build_registry.intent import (
    BRANCHING_NARRATIVE_APP_TYPE,
    DAILY_PUZZLE_GRID_APP_TYPE,
    IDLE_INCREMENTAL_APP_TYPE,
    MEMORY_MATCH_APP_TYPE,
    TRIVIA_TIMER_APP_TYPE,
    WORD_DAILY_APP_TYPE,
    enrich_plan_metadata_with_registry_v2,
    select_registry_v2_app_type_for_prompt,
)
from src.ham.clerk_auth import HamActor

_IDLE_POSITIVE_PROMPTS = (
    "build me an idle clicker game",
    "make a cookie clicker style game",
    "create an incremental tycoon game",
    "build a game where I earn coins and buy upgrades",
    "make a mining clicker with passive income",
)

_IDLE_NEGATIVE_PROMPTS = (
    "build me a SaaS dashboard",
    "make a landing page",
    "build Tetris",
    "make a platformer",
    "make a crypto trading dashboard",
    "build a game",
    "make an arcade game",
    "build an idle clicker game with trivia rounds",
)

_TRIVIA_POSITIVE_PROMPTS = (
    "Build me a trivia quiz with a timer",
    "Make a timed multiple choice quiz game",
    "Create a 10 question trivia game with score",
    "Build a quiz game with a countdown timer",
    "Make a history trivia game where each question has 15 seconds",
    "Create a multiple choice trivia challenge",
    "create a trivia game",
)

_TRIVIA_NEGATIVE_PROMPTS = (
    "Build me a survey form",
    "Make a flashcard app",
    "Create an education website",
    "Build a SaaS dashboard",
    "Make a generic quiz app",
    "Build a form with multiple choice questions",
    "Make a trading dashboard",
)

_BRANCHING_POSITIVE_PROMPTS = (
    "Build me a branching story game",
    "Make a choose your own adventure game",
    "Create an interactive fiction game",
    "Build a dialogue choice RPG",
    "Make a story game where choices change the ending",
    "Create a narrative game with multiple endings",
    "Build a text adventure with inventory and choices",
)

_BRANCHING_NEGATIVE_PROMPTS = (
    "Build me a blog",
    "Make a chatbot",
    "Create a writing app",
    "Build an AI dungeon with live generated story text",
    "Build a SaaS dashboard",
    "Make a generic RPG",
    "Create a landing page for my book",
)

_MEMORY_POSITIVE_PROMPTS = (
    "Build me a memory card matching game",
    "Make an emoji memory match game",
    "Create a game where I flip cards to find pairs",
    "Build a concentration card game",
    "Make a 4x4 card matching game with move counter",
    "Create a matching pairs game with flipped cards",
)

_MEMORY_NEGATIVE_PROMPTS = (
    "Build a card battler",
    "Make a trading card collection",
    "Create flashcards",
    "Build a SaaS dashboard",
    "Build a generic card game",
    "Create a poker game",
    "Build a solitaire game",
)

_WORD_DAILY_POSITIVE_PROMPTS = (
    "Build me a daily word guessing game",
    "Make a Wordle-style game",
    "Create a 5-letter word guessing game",
    "Build a word game with six attempts and letter feedback",
    "Make a daily word puzzle with keyboard input",
    "Create a game where I guess a hidden word and get green/yellow/gray feedback",
    "Build a word guessing challenge with duplicate-letter handling",
)

_WORD_DAILY_NEGATIVE_PROMPTS = (
    "Build a crossword puzzle",
    "Make a word search",
    "Create flashcards",
    "Build a typing speed game",
    "Create a dictionary app",
    "Make a writing app",
    "Build a SaaS dashboard",
    "Build a word game",
)

_DAILY_PUZZLE_GRID_POSITIVE_PROMPTS = (
    "Build me a daily puzzle grid game",
    "Make a logic grid puzzle",
    "Create a daily grid puzzle with row and column rules",
    "Build a mini sudoku-like grid puzzle",
    "Make a nonogram-style puzzle game",
    "Create a game where I fill cells based on clues",
    "Build a tile logic puzzle with hints and completion checking",
)

_DAILY_PUZZLE_GRID_NEGATIVE_PROMPTS = (
    "Build a dashboard grid",
    "Make a data table",
    "Create a CSS grid layout",
    "Build a crossword puzzle",
    "Make a word search",
    "Build Tetris",
    "Make Minesweeper",
    "Build a puzzle game",
    "Build a grid game",
    "Make a daily game",
)

_DAILY_PUZZLE_GRID_CROSS_RECIPE_NEGATIVE_PROMPTS = (
    "Build a memory card game",
    "Build a Wordle-style game",
    "Build a trivia quiz with timer",
    "Build an idle clicker game",
    "Build a branching story game",
)

_CROSS_EXCLUSION_PROMPTS = (
    ("build me an idle clicker game", IDLE_INCREMENTAL_APP_TYPE),
    ("Build me a trivia quiz with a timer", TRIVIA_TIMER_APP_TYPE),
    ("Build me a branching story game", BRANCHING_NARRATIVE_APP_TYPE),
    ("Build me a memory card matching game", MEMORY_MATCH_APP_TYPE),
    ("Build me a daily word guessing game", WORD_DAILY_APP_TYPE),
    ("make a cookie clicker style game", IDLE_INCREMENTAL_APP_TYPE),
    ("Make a timed multiple choice quiz game", TRIVIA_TIMER_APP_TYPE),
    ("Make a choose your own adventure game", BRANCHING_NARRATIVE_APP_TYPE),
    ("Make an emoji memory match game", MEMORY_MATCH_APP_TYPE),
    ("Make a Wordle-style game", WORD_DAILY_APP_TYPE),
    ("Build me a daily puzzle grid game", DAILY_PUZZLE_GRID_APP_TYPE),
    ("Make a logic grid puzzle", DAILY_PUZZLE_GRID_APP_TYPE),
)


class TestSelectRegistryV2AppTypeForPrompt:
    @pytest.mark.parametrize("prompt", _IDLE_POSITIVE_PROMPTS)
    def test_matches_idle_incremental_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == IDLE_INCREMENTAL_APP_TYPE

    @pytest.mark.parametrize("prompt", _IDLE_NEGATIVE_PROMPTS)
    def test_rejects_non_idle_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) is None

    @pytest.mark.parametrize("prompt", _TRIVIA_POSITIVE_PROMPTS)
    def test_matches_trivia_timer_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == TRIVIA_TIMER_APP_TYPE

    @pytest.mark.parametrize("prompt", _TRIVIA_NEGATIVE_PROMPTS)
    def test_rejects_non_trivia_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) is None

    @pytest.mark.parametrize("prompt", _BRANCHING_POSITIVE_PROMPTS)
    def test_matches_branching_narrative_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == BRANCHING_NARRATIVE_APP_TYPE

    @pytest.mark.parametrize("prompt", _BRANCHING_NEGATIVE_PROMPTS)
    def test_rejects_non_branching_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) is None

    @pytest.mark.parametrize("prompt", _MEMORY_POSITIVE_PROMPTS)
    def test_matches_memory_match_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == MEMORY_MATCH_APP_TYPE

    @pytest.mark.parametrize("prompt", _MEMORY_NEGATIVE_PROMPTS)
    def test_rejects_non_memory_match_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) is None

    @pytest.mark.parametrize("prompt", _WORD_DAILY_POSITIVE_PROMPTS)
    def test_matches_word_daily_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == WORD_DAILY_APP_TYPE

    @pytest.mark.parametrize("prompt", _WORD_DAILY_NEGATIVE_PROMPTS)
    def test_rejects_non_word_daily_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) is None

    @pytest.mark.parametrize("prompt", _DAILY_PUZZLE_GRID_POSITIVE_PROMPTS)
    def test_matches_daily_puzzle_grid_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == DAILY_PUZZLE_GRID_APP_TYPE

    @pytest.mark.parametrize("prompt", _DAILY_PUZZLE_GRID_NEGATIVE_PROMPTS)
    def test_rejects_non_daily_puzzle_grid_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) is None

    @pytest.mark.parametrize("prompt", _DAILY_PUZZLE_GRID_CROSS_RECIPE_NEGATIVE_PROMPTS)
    def test_other_recipe_prompts_do_not_route_to_daily_puzzle_grid_param(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) != DAILY_PUZZLE_GRID_APP_TYPE

    @pytest.mark.parametrize("prompt,expected", _CROSS_EXCLUSION_PROMPTS)
    def test_recipes_do_not_steal_each_other(self, prompt: str, expected: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == expected

    def test_idle_prompt_does_not_route_to_trivia(self):
        assert (
            select_registry_v2_app_type_for_prompt("Build an idle clicker game")
            == IDLE_INCREMENTAL_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build an idle clicker game")
            != TRIVIA_TIMER_APP_TYPE
        )

    def test_branching_prompt_does_not_route_to_idle_or_trivia(self):
        prompt = "Build me a branching story game"
        assert select_registry_v2_app_type_for_prompt(prompt) == BRANCHING_NARRATIVE_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != IDLE_INCREMENTAL_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != TRIVIA_TIMER_APP_TYPE

    def test_trivia_and_idle_prompts_do_not_route_to_branching(self):
        assert (
            select_registry_v2_app_type_for_prompt("Build me a trivia quiz with a timer")
            == TRIVIA_TIMER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("build me an idle clicker game")
            == IDLE_INCREMENTAL_APP_TYPE
        )

    def test_memory_prompt_does_not_route_to_other_recipes(self):
        prompt = "Build me a memory card matching game"
        assert select_registry_v2_app_type_for_prompt(prompt) == MEMORY_MATCH_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != IDLE_INCREMENTAL_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != TRIVIA_TIMER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != BRANCHING_NARRATIVE_APP_TYPE

    def test_other_recipe_prompts_do_not_route_to_memory(self):
        assert (
            select_registry_v2_app_type_for_prompt("Build me a trivia quiz with a timer")
            != MEMORY_MATCH_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("build me an idle clicker game")
            != MEMORY_MATCH_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a branching story game")
            != MEMORY_MATCH_APP_TYPE
        )

    def test_word_daily_prompt_does_not_route_to_other_recipes(self):
        prompt = "Build me a daily word guessing game"
        assert select_registry_v2_app_type_for_prompt(prompt) == WORD_DAILY_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != IDLE_INCREMENTAL_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != TRIVIA_TIMER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != BRANCHING_NARRATIVE_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != MEMORY_MATCH_APP_TYPE

    def test_other_recipe_prompts_do_not_route_to_word_daily(self):
        assert (
            select_registry_v2_app_type_for_prompt("Build me a trivia quiz with a timer")
            != WORD_DAILY_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("build me an idle clicker game")
            != WORD_DAILY_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a branching story game")
            != WORD_DAILY_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a memory card matching game")
            != WORD_DAILY_APP_TYPE
        )

    def test_daily_puzzle_grid_prompt_does_not_route_to_other_recipes(self):
        prompt = "Build me a daily puzzle grid game"
        assert select_registry_v2_app_type_for_prompt(prompt) == DAILY_PUZZLE_GRID_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != IDLE_INCREMENTAL_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != TRIVIA_TIMER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != BRANCHING_NARRATIVE_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != MEMORY_MATCH_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != WORD_DAILY_APP_TYPE

    def test_other_recipe_prompts_do_not_route_to_daily_puzzle_grid(self):
        assert (
            select_registry_v2_app_type_for_prompt("Build me a trivia quiz with a timer")
            != DAILY_PUZZLE_GRID_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("build me an idle clicker game")
            != DAILY_PUZZLE_GRID_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a branching story game")
            != DAILY_PUZZLE_GRID_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a memory card matching game")
            != DAILY_PUZZLE_GRID_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a daily word guessing game")
            != DAILY_PUZZLE_GRID_APP_TYPE
        )


class TestEnrichPlanMetadataWithRegistryV2:
    def test_flag_disabled_does_not_add_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "build me an idle clicker game",
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_disabled_trivia_prompt_does_not_add_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a trivia quiz with a timer",
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_disabled_branching_prompt_does_not_add_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a branching story game",
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_disabled_memory_prompt_does_not_add_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a memory card matching game",
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_disabled_word_daily_prompt_does_not_add_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a daily word guessing game",
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_disabled_daily_puzzle_grid_prompt_does_not_add_registry_metadata(
        self, monkeypatch
    ):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a daily puzzle grid game",
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_enabled_idle_prompt_adds_registry_metadata(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic", "originated_from": "builder_chat_scaffold"},
            "build me an idle clicker game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        assert metadata["registry_v2_app_type"] == IDLE_INCREMENTAL_APP_TYPE
        assert metadata["template_kind"] == "generic"
        assert metadata["originated_from"] == "builder_chat_scaffold"

    def test_flag_enabled_trivia_prompt_adds_registry_metadata(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic", "originated_from": "builder_chat_scaffold"},
            "Build me a trivia quiz with a timer",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        assert metadata["registry_v2_app_type"] == TRIVIA_TIMER_APP_TYPE
        assert metadata["template_kind"] == "generic"
        assert metadata["originated_from"] == "builder_chat_scaffold"

    def test_flag_enabled_branching_prompt_adds_registry_metadata(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic", "originated_from": "builder_chat_scaffold"},
            "Build me a branching story game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        assert metadata["registry_v2_app_type"] == BRANCHING_NARRATIVE_APP_TYPE
        assert metadata["template_kind"] == "generic"
        assert metadata["originated_from"] == "builder_chat_scaffold"

    def test_flag_enabled_memory_prompt_adds_registry_metadata(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic", "originated_from": "builder_chat_scaffold"},
            "Build me a memory card matching game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        assert metadata["registry_v2_app_type"] == MEMORY_MATCH_APP_TYPE
        assert metadata["template_kind"] == "generic"
        assert metadata["originated_from"] == "builder_chat_scaffold"

    def test_flag_enabled_word_daily_prompt_adds_registry_metadata(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic", "originated_from": "builder_chat_scaffold"},
            "Build me a daily word guessing game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        assert metadata["registry_v2_app_type"] == WORD_DAILY_APP_TYPE
        assert metadata["template_kind"] == "generic"
        assert metadata["originated_from"] == "builder_chat_scaffold"

    def test_flag_enabled_daily_puzzle_grid_prompt_adds_registry_metadata(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic", "originated_from": "builder_chat_scaffold"},
            "Build me a daily puzzle grid game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        assert metadata["registry_v2_app_type"] == DAILY_PUZZLE_GRID_APP_TYPE
        assert metadata["template_kind"] == "generic"
        assert metadata["originated_from"] == "builder_chat_scaffold"

    def test_flag_enabled_non_idle_prompt_leaves_registry_metadata_absent(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "landing-page"},
            "build me a landing page",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "landing-page"

    def test_flag_enabled_non_trivia_prompt_leaves_registry_metadata_absent(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Make a flashcard app",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_enabled_non_branching_prompt_leaves_registry_metadata_absent(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Make a chatbot",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_enabled_non_memory_prompt_leaves_registry_metadata_absent(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build a solitaire game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_enabled_non_word_daily_prompt_leaves_registry_metadata_absent(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build a crossword puzzle",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_enabled_non_daily_puzzle_grid_prompt_leaves_registry_metadata_absent(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build a dashboard grid",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"


def _byo_actor() -> HamActor:
    return HamActor(
        user_id="user_registry_intent",
        org_id=None,
        session_id=None,
        email="user_registry_intent@example.com",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _synthetic_plan_metadata(user_message: str) -> dict:
    captured: dict = {}

    def _fake_generate_scaffold(plan, **_kw):
        captured["metadata"] = dict(plan.metadata or {})
        return ScaffoldResult(
            file_changes=[("src/App.tsx", "export default function App(){return null;}")],
            assertions=[],
        )

    with (
        patch(
            "src.llm_client.resolve_openrouter_api_key_for_actor",
            return_value="sk-or-v1-test_registry_intent",
        ),
        patch(
            "src.ham.builder_llm_scaffold._get_scaffold_model",
            return_value="openrouter/anthropic/claude-3.5-haiku",
        ),
        patch(
            "src.ham.builder_llm_scaffold.generate_scaffold",
            side_effect=_fake_generate_scaffold,
        ),
    ):
        _maybe_llm_scaffold_replace(
            user_message=user_message,
            workspace_id="ws_registry",
            project_id="proj_registry",
            files={"src/App.tsx": "// placeholder"},
            scaffold_meta={},
            ham_actor=_byo_actor(),
        )
    return captured["metadata"]


class TestChatScaffoldSyntheticPlanMetadata:
    def test_flag_disabled_idle_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = _synthetic_plan_metadata("build me an idle clicker game")
        assert metadata.get("template_kind") == "generic"
        assert "registry_v2_app_type" not in metadata

    def test_flag_disabled_trivia_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = _synthetic_plan_metadata("Build me a trivia quiz with a timer")
        assert metadata.get("template_kind") == "generic"
        assert "registry_v2_app_type" not in metadata

    def test_flag_disabled_branching_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = _synthetic_plan_metadata("Build me a branching story game")
        assert metadata.get("template_kind") == "generic"
        assert "registry_v2_app_type" not in metadata

    def test_flag_disabled_memory_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = _synthetic_plan_metadata("Build me a memory card matching game")
        assert metadata.get("template_kind") == "generic"
        assert "registry_v2_app_type" not in metadata

    def test_flag_disabled_word_daily_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = _synthetic_plan_metadata("Build me a daily word guessing game")
        assert metadata.get("template_kind") == "generic"
        assert "registry_v2_app_type" not in metadata

    def test_flag_disabled_daily_puzzle_grid_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = _synthetic_plan_metadata("Build me a daily puzzle grid game")
        assert metadata.get("template_kind") == "generic"
        assert "registry_v2_app_type" not in metadata

    def test_flag_enabled_idle_prompt_adds_registry_metadata(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata("build me an idle clicker game")
        assert metadata.get("template_kind") == "generic"
        assert metadata.get("registry_v2_app_type") == IDLE_INCREMENTAL_APP_TYPE

    def test_flag_enabled_trivia_prompt_adds_registry_metadata(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata("Build me a trivia quiz with a timer")
        assert metadata.get("template_kind") == "generic"
        assert metadata.get("registry_v2_app_type") == TRIVIA_TIMER_APP_TYPE

    def test_flag_enabled_branching_prompt_adds_registry_metadata(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata("Build me a branching story game")
        assert metadata.get("template_kind") == "generic"
        assert metadata.get("registry_v2_app_type") == BRANCHING_NARRATIVE_APP_TYPE

    def test_flag_enabled_memory_prompt_adds_registry_metadata(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata("Build me a memory card matching game")
        assert metadata.get("template_kind") == "generic"
        assert metadata.get("registry_v2_app_type") == MEMORY_MATCH_APP_TYPE

    def test_flag_enabled_word_daily_prompt_adds_registry_metadata(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata("Build me a daily word guessing game")
        assert metadata.get("template_kind") == "generic"
        assert metadata.get("registry_v2_app_type") == WORD_DAILY_APP_TYPE

    def test_flag_enabled_daily_puzzle_grid_prompt_adds_registry_metadata(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata("Build me a daily puzzle grid game")
        assert metadata.get("template_kind") == "generic"
        assert metadata.get("registry_v2_app_type") == DAILY_PUZZLE_GRID_APP_TYPE

    def test_flag_enabled_non_idle_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata("build me a landing page for roofers")
        assert metadata.get("template_kind") == "landing-page"
        assert "registry_v2_app_type" not in metadata


class TestEndToEndScaffoldMessages:
    def test_flag_enabled_idle_prompt_produces_v2_context(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "build me an idle clicker game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        plan = Plan(
            plan_id="pln_registry_intent_e2e",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="build me an idle clicker game",
            steps=[Step(title="Scaffold game", description="Create idle clicker files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )[1]["content"]
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.idle-incremental" in content
        assert "Builder Kit context:" not in content

    def test_flag_enabled_trivia_prompt_produces_v2_context(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a trivia quiz with a timer",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        plan = Plan(
            plan_id="pln_registry_intent_trivia_e2e",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a trivia quiz with a timer",
            steps=[Step(title="Scaffold game", description="Create trivia quiz files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )[1]["content"]
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.trivia-timer" in content
        assert "stack.dom-game-minimal" in content
        assert "validator.timer-cleanup" in content
        assert "Builder Kit context:" not in content
        assert content.count("Builder Kit:") == 0

    def test_flag_enabled_branching_prompt_produces_v2_context(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a branching story game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        plan = Plan(
            plan_id="pln_registry_intent_branching_e2e",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a branching story game",
            steps=[Step(title="Scaffold game", description="Create branching story files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )[1]["content"]
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.branching-narrative" in content
        assert "stack.dom-game-minimal" in content
        assert "validator.story-graph-reachability" in content
        assert "validator.no-dead-end-choice" in content
        assert "Builder Kit context:" not in content
        assert content.count("Builder Kit:") == 0

    def test_flag_enabled_memory_prompt_produces_v2_context(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a memory card matching game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        plan = Plan(
            plan_id="pln_registry_intent_memory_e2e",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a memory card matching game",
            steps=[Step(title="Scaffold game", description="Create memory match files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )[1]["content"]
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.memory-match" in content
        assert "stack.dom-game-minimal" in content
        assert "validator.flip-lock-prevents-third-card" in content
        assert "validator.match-completion" in content
        assert "Builder Kit context:" not in content
        assert content.count("Builder Kit:") == 0

    def test_flag_enabled_word_daily_prompt_produces_v2_context(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a daily word guessing game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        plan = Plan(
            plan_id="pln_registry_intent_word_daily_e2e",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a daily word guessing game",
            steps=[Step(title="Scaffold game", description="Create word daily files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )[1]["content"]
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.word-daily" in content
        assert "stack.dom-game-minimal" in content
        assert "validator.duplicate-letter-feedback" in content
        assert "validator.daily-seed-stability" in content
        assert "Builder Kit context:" not in content
        assert content.count("Builder Kit:") == 0

    def test_flag_enabled_daily_puzzle_grid_prompt_produces_v2_context(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a daily puzzle grid game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        plan = Plan(
            plan_id="pln_registry_intent_daily_puzzle_grid_e2e",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a daily puzzle grid game",
            steps=[Step(title="Scaffold game", description="Create daily puzzle grid files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )[1]["content"]
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.daily-puzzle-grid" in content
        assert "stack.dom-game-minimal" in content
        assert "validator.grid-dimensions" in content
        assert "validator.constraint-consistency" in content
        assert "validator.completion-detection" in content
        assert "Builder Kit context:" not in content
        assert content.count("Builder Kit:") == 0

    def test_flag_disabled_idle_prompt_produces_v1_context_only(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "build me an idle clicker game",
        )
        plan = Plan(
            plan_id="pln_registry_intent_v1",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="build me an idle clicker game",
            steps=[Step(title="Scaffold game", description="Create idle clicker files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(plan)[1]["content"]
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content

    def test_flag_disabled_trivia_prompt_produces_v1_context_only(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a trivia quiz with a timer",
        )
        plan = Plan(
            plan_id="pln_registry_intent_trivia_v1",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a trivia quiz with a timer",
            steps=[Step(title="Scaffold game", description="Create trivia quiz files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(plan)[1]["content"]
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content

    def test_flag_disabled_branching_prompt_produces_v1_context_only(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a branching story game",
        )
        plan = Plan(
            plan_id="pln_registry_intent_branching_v1",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a branching story game",
            steps=[Step(title="Scaffold game", description="Create branching story files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(plan)[1]["content"]
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content

    def test_flag_disabled_memory_prompt_produces_v1_context_only(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a memory card matching game",
        )
        plan = Plan(
            plan_id="pln_registry_intent_memory_v1",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a memory card matching game",
            steps=[Step(title="Scaffold game", description="Create memory match files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(plan)[1]["content"]
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content

    def test_flag_disabled_word_daily_prompt_produces_v1_context_only(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a daily word guessing game",
        )
        plan = Plan(
            plan_id="pln_registry_intent_word_daily_v1",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a daily word guessing game",
            steps=[Step(title="Scaffold game", description="Create word daily files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(plan)[1]["content"]
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content

    def test_flag_disabled_daily_puzzle_grid_prompt_produces_v1_context_only(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a daily puzzle grid game",
        )
        plan = Plan(
            plan_id="pln_registry_intent_daily_puzzle_grid_v1",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a daily puzzle grid game",
            steps=[Step(title="Scaffold game", description="Create daily puzzle grid files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(plan)[1]["content"]
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content
