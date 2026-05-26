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
    HANGMAN_LITE_APP_TYPE,
    IDLE_INCREMENTAL_APP_TYPE,
    MEMORY_MATCH_APP_TYPE,
    RESOURCE_MANAGEMENT_SIM_APP_TYPE,
    TRIVIA_TIMER_APP_TYPE,
    TYPING_SPEED_RACER_APP_TYPE,
    WORD_BUILDER_APP_TYPE,
    WORD_DAILY_APP_TYPE,
    CARD_DECK_TURN_BASED_APP_TYPE,
    REACTION_TIME_CHALLENGE_APP_TYPE,
    RHYTHM_TAP_LITE_APP_TYPE,
    DECK_BUILDER_LITE_APP_TYPE,
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
    "Build a spelling practice app",
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

_RESOURCE_MGMT_POSITIVE_PROMPTS = (
    "Build me a resource management sim",
    "Make a small colony management game",
    "Create a factory resource allocation game",
    "Build a game where I manage food, energy, and workers",
    "Make a turn-based resource management game",
    "Create a production chain simulation",
    "Build a game with resources, capacity limits, upgrades, and goals",
    "Make a tiny farm management sim",
)

_RESOURCE_MGMT_NEGATIVE_PROMPTS = (
    "Build a SaaS dashboard",
    "Create an inventory management app",
    "Make a finance dashboard",
    "Build a trading app",
    "Create a live market simulator",
    "Build a multiplayer economy game",
    "Make a resource allocation spreadsheet",
    "Build a city builder with real-time combat",
    "Create a generic dashboard",
)

_RESOURCE_MGMT_CROSS_RECIPE_NEGATIVE_PROMPTS = (
    "Build a memory card game",
    "Build a Wordle-style game",
    "Build a trivia quiz with timer",
    "Build an idle clicker game",
    "Build a branching story game",
    "Build me a daily puzzle grid game",
)

_HANGMAN_LITE_POSITIVE_PROMPTS = (
    "Build a hangman word game",
    "Make a simple hangman game with letter guessing",
    "Create a hangman-style game with six wrong guesses",
    "Build a word game where I guess letters to reveal a hidden word",
    "Make a hangman game with wrong guess limit",
    "Create a letter guessing hangman game",
)

_HANGMAN_LITE_NEGATIVE_PROMPTS = (
    "Build a Wordle-style game",
    "Make a daily word guessing game",
    "Build a crossword puzzle",
    "Make a word search",
    "Create flashcards",
    "Build a typing speed game",
    "Build me a trivia quiz with a timer",
    "Build me a memory card matching game",
    "build me an idle clicker game",
    "Build a SaaS dashboard",
    "Build me a resource management sim",
    "Build me a daily puzzle grid game",
)

_HANGMAN_LITE_CROSS_RECIPE_NEGATIVE_PROMPTS = (
    "Build a Wordle-style game",
    "Build me a trivia quiz with a timer",
    "Build an idle clicker game",
    "Build me a memory card matching game",
    "Build a SaaS dashboard",
)

_TYPING_SPEED_RACER_POSITIVE_PROMPTS = (
    "Build me a typing speed game",
    "Make a typing speed racer",
    "Create a WPM typing challenge",
    "Build a typing game with accuracy and mistakes",
    "Make a 60 second typing test game",
    "Create a game where I type prompts as fast as possible",
    "Build a typing challenge with WPM, accuracy, and streaks",
    "Make a keyboard speed game with a timer",
)

_TYPING_SPEED_RACER_NEGATIVE_PROMPTS = (
    "Build a Wordle-style game",
    "Make a hangman game",
    "Create flashcards",
    "Build a trivia quiz with timer",
    "Make a word search",
    "Build a crossword puzzle",
    "Create a dictionary app",
    "Make a writing app",
    "Build a typing tutor dashboard",
    "Create a text editor",
    "Build an idle clicker game",
    "Build a SaaS dashboard",
)

_TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVE_PROMPTS = (
    "Build a Wordle-style game",
    "Build me a trivia quiz with a timer",
    "Build an idle clicker game",
    "Build me a memory card matching game",
    "Build a hangman word game",
    "Build me a daily puzzle grid game",
    "Build me a resource management sim",
    "Build a SaaS dashboard",
)

_WORD_BUILDER_POSITIVE_PROMPTS = (
    "Build me a word builder game",
    "Make a spelling challenge game",
    "Create a game where I build words from a set of letters",
    "Build a word game with letter tiles and valid word submissions",
    "Make a letter pool word puzzle",
    "Create a game where I arrange letters into word slots",
    "Build a word game where duplicate submissions do not score twice",
    "Make a word-building game with hints and levels",
)

_WORD_BUILDER_NEGATIVE_PROMPTS = (
    "Build a Wordle-style game",
    "Make a daily word guessing game",
    "Build a hangman game",
    "Create a typing speed game",
    "Make a crossword puzzle",
    "Build a word search",
    "Create flashcards",
    "Build a dictionary app",
    "Make a writing app",
    "Build a trivia quiz with timer",
    "Build a memory card game",
    "Build an idle clicker game",
    "Build a SaaS dashboard",
)

_WORD_BUILDER_CROSS_RECIPE_NEGATIVE_PROMPTS = (
    "Build a Wordle-style game",
    "Build me a trivia quiz with a timer",
    "Build an idle clicker game",
    "Build me a memory card matching game",
    "Build a hangman word game",
    "Build me a typing speed game",
    "Build me a daily puzzle grid game",
    "Build me a resource management sim",
    "Build a SaaS dashboard",
)

_CARD_DECK_TURN_BASED_POSITIVE_PROMPTS = (
    "Build a simple turn-based card battle game with a draw pile, hand, discard pile, and health points.",
    "Build a browser card game where the player draws cards, plays one card per turn, and tries to defeat a simple enemy.",
    "Build a solitaire-like strategy card game with a deck, hand, discard pile, and score.",
    "Make a turn-based card game with shuffle, draw, and discard mechanics.",
    "Create a card battle game where I play one card per turn from my hand.",
    "Build a card game with draw pile, hand, discard, card effects, and a simple enemy.",
    "Make a browser game with shuffle deck, draw hand, play cards, and track victory.",
)

_CARD_DECK_TURN_BASED_NEGATIVE_PROMPTS = (
    "Build a poker game",
    "Make a blackjack app",
    "Build a casino betting game with chips and odds",
    "Create an NFT trading card marketplace",
    "Build a buy and sell collectible cards app",
    "Make a flashcard study deck",
    "Build spaced repetition cards for studying",
    "Create a pitch deck generator",
    "Build an investor slide deck",
    "Make a dashboard with cards",
    "Build a kanban board with cards",
    "Create pricing cards for a SaaS landing page",
    "Build a credit card app",
    "Make a business card designer",
    "Build a deck builder",
    "Build a card deck app",
    "Build something with cards",
    "Build a deck",
    "Build a card app",
    "Build a card layout for my dashboard",
)

_CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVE_PROMPTS = (
    "Build me a trivia quiz with a timer",
    "Build an idle clicker game",
    "Build me a memory card matching game",
    "Build me a daily word guessing game",
    "Build me a daily puzzle grid game",
    "Build me a resource management sim",
    "Build a hangman word game",
    "Build me a typing speed game",
    "Build me a word builder game",
    "Build a SaaS dashboard",
)

_REACTION_TIME_CHALLENGE_POSITIVE_PROMPTS = (
    "Build a browser reaction-time game where the player waits for the screen to turn green, clicks as fast as possible, and sees their reaction time.",
    "Build a reflex challenge where clicking too early counts as a false start and players can retry for a better score.",
    "Build a local reaction-speed game with random delays, best score tracking, and a play-again button.",
    "Build a simple reaction test game where the user presses space when the signal appears and gets millisecond feedback.",
    "Make a reaction time challenge with false start detection and best reaction time tracking.",
    "Create a browser game with random delay then click as fast as you can when the signal appears.",
    "Build a reflex test game where players wait for go then tap and see average reaction time.",
)

_REACTION_TIME_CHALLENGE_NEGATIVE_PROMPTS = (
    "Build a Pomodoro timer",
    "Make a stopwatch app",
    "Build a countdown timer app",
    "Build a typing speed test",
    "Make a typing race with WPM",
    "Build a rhythm tap game",
    "Create a music rhythm game",
    "Build a dashboard for response times",
    "Make an analytics dashboard for response times",
    "Build a medical reflex test",
    "Create a clinical reaction assessment",
    "Build an accessibility reaction assessment",
    "Build a game with physics collisions",
    "Make a gambling game with reaction bets",
    "Build a betting reaction game",
    "Build a reaction app",
    "Make a speed challenge",
    "Build a timer",
    "Click fast",
    "Build a stopwatch",
    "Build a response time dashboard",
)

_REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVE_PROMPTS = (
    "Build me a trivia quiz with a timer",
    "Build an idle clicker game",
    "Build me a memory card matching game",
    "Build me a daily word guessing game",
    "Build me a daily puzzle grid game",
    "Build me a resource management sim",
    "Build a hangman word game",
    "Build me a word builder game",
    "Build a simple turn-based card battle game with a draw pile, hand, discard pile, and health points.",
    "Build a SaaS dashboard",
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
    ("Build me a resource management sim", RESOURCE_MANAGEMENT_SIM_APP_TYPE),
    ("Make a turn-based resource management game", RESOURCE_MANAGEMENT_SIM_APP_TYPE),
    ("Build a hangman word game", HANGMAN_LITE_APP_TYPE),
    ("Make a simple hangman game with letter guessing", HANGMAN_LITE_APP_TYPE),
    ("Build me a typing speed game", TYPING_SPEED_RACER_APP_TYPE),
    ("Make a typing speed racer", TYPING_SPEED_RACER_APP_TYPE),
    ("Build me a word builder game", WORD_BUILDER_APP_TYPE),
    ("Make a spelling challenge game", WORD_BUILDER_APP_TYPE),
    (
        "Build a simple turn-based card battle game with a draw pile, hand, discard pile, and health points.",
        CARD_DECK_TURN_BASED_APP_TYPE,
    ),
    (
        "Build a browser card game where the player draws cards, plays one card per turn, and tries to defeat a simple enemy.",
        CARD_DECK_TURN_BASED_APP_TYPE,
    ),
    (
        "Build a browser reaction-time game where the player waits for the screen to turn green, clicks as fast as possible, and sees their reaction time.",
        REACTION_TIME_CHALLENGE_APP_TYPE,
    ),
    (
        "Build a reflex challenge where clicking too early counts as a false start and players can retry for a better score.",
        REACTION_TIME_CHALLENGE_APP_TYPE,
    ),
    (
        "Build a browser rhythm tap game where circles appear on beats and players press space at the right time for perfect/good/miss scores.",
        RHYTHM_TAP_LITE_APP_TYPE,
    ),
    (
        "Build a simple tap-the-beat game with timing windows, streaks, misses, and a final score.",
        RHYTHM_TAP_LITE_APP_TYPE,
    ),
    (
        "Build a browser deck-building card game where the player starts with a small deck, fights simple encounters, and chooses a new card reward after each win.",
        DECK_BUILDER_LITE_APP_TYPE,
    ),
    (
        "Build a roguelite deck builder card game with encounters, reward choices, and deck mutation between battles.",
        DECK_BUILDER_LITE_APP_TYPE,
    ),
)


_RHYTHM_TAP_LITE_POSITIVE_PROMPTS = (
    "Build a browser rhythm tap game where circles appear on beats and players press space at the right time for perfect/good/miss scores.",
    "Build a simple tap-the-beat game with timing windows, streaks, misses, and a final score.",
    "Build a local rhythm challenge where cues appear in sequence and the player taps when each cue reaches the target.",
    "Build a DOM rhythm game with beat prompts, combo scoring, and a play-again results screen.",
    "Make a rhythm tap game with perfect good miss timing windows and combo streak tracking.",
    "Build a browser game where beat cues appear in sequence and players tap for perfect or good timing scores.",
    "Create a rhythm tap challenge with timing windows, combo streaks, and a results screen.",
)

_RHYTHM_TAP_LITE_NEGATIVE_PROMPTS = (
    "Build a Pomodoro timer",
    "Make a stopwatch app",
    "Build a countdown timer app",
    "Build a metronome",
    "Build a music player",
    "Build a karaoke lyric game",
    "Build a typing speed test",
    "Make a typing race with WPM",
    "Build a reaction time test",
    "Build a browser reaction-time game where the player waits for the screen to turn green, clicks as fast as possible, and sees their reaction time.",
    "Build a medical rhythm assessment",
    "Create a clinical accessibility assessment",
    "Build a dashboard for music analytics",
    "Make a gambling game with rhythm bets",
    "Build a betting wagering game",
    "Build a game with physics collisions",
    "Build a rhythm app",
    "Make a beat game",
    "Build a timer",
    "Click fast",
    "Build a music app",
    "Tap",
)

_RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVE_PROMPTS = (
    "Build me a trivia quiz with a timer",
    "Build an idle clicker game",
    "Build me a memory card matching game",
    "Build me a daily word guessing game",
    "Build me a typing speed game",
    "Build a reflex challenge where clicking too early counts as a false start and players can retry for a better score.",
    "Build a simple turn-based card battle game with a draw pile, hand, discard pile, and health points.",
    "Build a browser deck-building card game where the player starts with a small deck, fights simple encounters, and chooses a new card reward after each win.",
    "Build a SaaS dashboard",
)


_DECK_BUILDER_LITE_POSITIVE_PROMPTS = (
    "Build a browser deck-building card game where the player starts with a small deck, fights simple encounters, and chooses a new card reward after each win.",
    "Build a local deck-builder where players draw a hand, play cards against a simple enemy, discard played cards, and add one reward card to their deck.",
    "Build a roguelite deck builder card game with encounters, reward choices, and deck mutation between battles.",
    "Make a deck-building card game where you upgrade or remove cards between encounters and pick rewards after each win.",
    "Build a small deck-building run with starter deck, draw hand, play cards, discard, choose rewards, and deck mutation.",
    "Create a deck-building card game with encounter rounds, card reward offers, and add cards to deck after battles.",
    "Build a browser game where players draw a hand, play cards in encounters, discard, and choose card rewards to improve their deck.",
)

_DECK_BUILDER_LITE_NEGATIVE_PROMPTS = (
    "Build a deck builder",
    "Build a deck",
    "Build a deck app",
    "Build a card deck",
    "Build a card app",
    "Build something with cards",
    "Card rewards",
    "Card collection",
    "Create a pitch deck generator",
    "Build an investor slide deck",
    "Make a presentation deck",
    "Make a flashcard study deck",
    "Build spaced repetition cards for studying",
    "Create an NFT trading card marketplace",
    "Build a buy and sell collectible cards app",
    "Build a card auction app",
    "Build a poker game",
    "Make a blackjack app",
    "Build a casino betting game with chips and odds",
    "Make a dashboard with cards",
    "Build a kanban board with cards",
    "Create pricing cards for a SaaS landing page",
    "Build profile cards for a team page",
    "Build a construction planning deck",
    "Build a project planning deck",
    "Build a music deck app",
    "Build an audio deck app",
)

_DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVE_PROMPTS = (
    "Build me a trivia quiz with a timer",
    "Build an idle clicker game",
    "Build me a memory card matching game",
    "Build me a daily word guessing game",
    "Build me a typing speed game",
    "Build a reflex challenge where clicking too early counts as a false start and players can retry for a better score.",
    "Build a browser rhythm tap game where circles appear on beats and players press space at the right time for perfect/good/miss scores.",
    "Build a simple turn-based card battle game with a draw pile, hand, discard pile, and health points.",
    "Build a SaaS dashboard",
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

    @pytest.mark.parametrize("prompt", _RESOURCE_MGMT_POSITIVE_PROMPTS)
    def test_matches_resource_management_sim_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == RESOURCE_MANAGEMENT_SIM_APP_TYPE

    @pytest.mark.parametrize("prompt", _RESOURCE_MGMT_NEGATIVE_PROMPTS)
    def test_rejects_non_resource_management_sim_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) != RESOURCE_MANAGEMENT_SIM_APP_TYPE

    @pytest.mark.parametrize("prompt", _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVE_PROMPTS)
    def test_other_recipe_prompts_do_not_route_to_resource_management_sim_param(
        self, prompt: str
    ):
        assert select_registry_v2_app_type_for_prompt(prompt) != RESOURCE_MANAGEMENT_SIM_APP_TYPE

    @pytest.mark.parametrize("prompt", _HANGMAN_LITE_POSITIVE_PROMPTS)
    def test_matches_hangman_lite_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == HANGMAN_LITE_APP_TYPE

    @pytest.mark.parametrize("prompt", _HANGMAN_LITE_NEGATIVE_PROMPTS)
    def test_rejects_non_hangman_lite_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) != HANGMAN_LITE_APP_TYPE

    @pytest.mark.parametrize("prompt", _HANGMAN_LITE_CROSS_RECIPE_NEGATIVE_PROMPTS)
    def test_other_recipe_prompts_do_not_route_to_hangman_lite_param(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) != HANGMAN_LITE_APP_TYPE

    @pytest.mark.parametrize("prompt", _TYPING_SPEED_RACER_POSITIVE_PROMPTS)
    def test_matches_typing_speed_racer_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == TYPING_SPEED_RACER_APP_TYPE

    @pytest.mark.parametrize("prompt", _TYPING_SPEED_RACER_NEGATIVE_PROMPTS)
    def test_rejects_non_typing_speed_racer_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) != TYPING_SPEED_RACER_APP_TYPE

    @pytest.mark.parametrize("prompt", _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVE_PROMPTS)
    def test_other_recipe_prompts_do_not_route_to_typing_speed_racer_param(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) != TYPING_SPEED_RACER_APP_TYPE

    @pytest.mark.parametrize("prompt", _WORD_BUILDER_POSITIVE_PROMPTS)
    def test_matches_word_builder_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == WORD_BUILDER_APP_TYPE

    @pytest.mark.parametrize("prompt", _WORD_BUILDER_NEGATIVE_PROMPTS)
    def test_rejects_non_word_builder_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) != WORD_BUILDER_APP_TYPE

    @pytest.mark.parametrize("prompt", _WORD_BUILDER_CROSS_RECIPE_NEGATIVE_PROMPTS)
    def test_other_recipe_prompts_do_not_route_to_word_builder_param(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) != WORD_BUILDER_APP_TYPE

    @pytest.mark.parametrize("prompt", _CARD_DECK_TURN_BASED_POSITIVE_PROMPTS)
    def test_matches_card_deck_turn_based_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == CARD_DECK_TURN_BASED_APP_TYPE

    @pytest.mark.parametrize("prompt", _CARD_DECK_TURN_BASED_NEGATIVE_PROMPTS)
    def test_rejects_non_card_deck_turn_based_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) != CARD_DECK_TURN_BASED_APP_TYPE

    @pytest.mark.parametrize("prompt", _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVE_PROMPTS)
    def test_other_recipe_prompts_do_not_route_to_card_deck_turn_based_param(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) != CARD_DECK_TURN_BASED_APP_TYPE

    @pytest.mark.parametrize("prompt", _REACTION_TIME_CHALLENGE_POSITIVE_PROMPTS)
    def test_matches_reaction_time_challenge_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == REACTION_TIME_CHALLENGE_APP_TYPE

    @pytest.mark.parametrize("prompt", _REACTION_TIME_CHALLENGE_NEGATIVE_PROMPTS)
    def test_rejects_non_reaction_time_challenge_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) != REACTION_TIME_CHALLENGE_APP_TYPE

    @pytest.mark.parametrize("prompt", _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVE_PROMPTS)
    def test_other_recipe_prompts_do_not_route_to_reaction_time_challenge_param(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) != REACTION_TIME_CHALLENGE_APP_TYPE

    @pytest.mark.parametrize("prompt", _RHYTHM_TAP_LITE_POSITIVE_PROMPTS)
    def test_matches_rhythm_tap_lite_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == RHYTHM_TAP_LITE_APP_TYPE

    @pytest.mark.parametrize("prompt", _RHYTHM_TAP_LITE_NEGATIVE_PROMPTS)
    def test_rejects_non_rhythm_tap_lite_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) != RHYTHM_TAP_LITE_APP_TYPE

    @pytest.mark.parametrize("prompt", _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVE_PROMPTS)
    def test_other_recipe_prompts_do_not_route_to_rhythm_tap_lite_param(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) != RHYTHM_TAP_LITE_APP_TYPE

    @pytest.mark.parametrize("prompt", _DECK_BUILDER_LITE_POSITIVE_PROMPTS)
    def test_matches_deck_builder_lite_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == DECK_BUILDER_LITE_APP_TYPE

    @pytest.mark.parametrize("prompt", _DECK_BUILDER_LITE_NEGATIVE_PROMPTS)
    def test_rejects_non_deck_builder_lite_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) != DECK_BUILDER_LITE_APP_TYPE

    @pytest.mark.parametrize("prompt", _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVE_PROMPTS)
    def test_other_recipe_prompts_do_not_route_to_deck_builder_lite_param(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) != DECK_BUILDER_LITE_APP_TYPE

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

    def test_resource_management_sim_prompt_does_not_route_to_other_recipes(self):
        prompt = "Build me a resource management sim"
        assert select_registry_v2_app_type_for_prompt(prompt) == RESOURCE_MANAGEMENT_SIM_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != IDLE_INCREMENTAL_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != TRIVIA_TIMER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != BRANCHING_NARRATIVE_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != MEMORY_MATCH_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != WORD_DAILY_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != DAILY_PUZZLE_GRID_APP_TYPE

    def test_other_recipe_prompts_do_not_route_to_resource_management_sim(self):
        assert (
            select_registry_v2_app_type_for_prompt("Build me a trivia quiz with a timer")
            != RESOURCE_MANAGEMENT_SIM_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("build me an idle clicker game")
            != RESOURCE_MANAGEMENT_SIM_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a branching story game")
            != RESOURCE_MANAGEMENT_SIM_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a memory card matching game")
            != RESOURCE_MANAGEMENT_SIM_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a daily word guessing game")
            != RESOURCE_MANAGEMENT_SIM_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a daily puzzle grid game")
            != RESOURCE_MANAGEMENT_SIM_APP_TYPE
        )

    def test_hangman_lite_prompt_does_not_route_to_other_recipes(self):
        prompt = "Build a hangman word game"
        assert select_registry_v2_app_type_for_prompt(prompt) == HANGMAN_LITE_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != IDLE_INCREMENTAL_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != TRIVIA_TIMER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != BRANCHING_NARRATIVE_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != MEMORY_MATCH_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != WORD_DAILY_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != DAILY_PUZZLE_GRID_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != RESOURCE_MANAGEMENT_SIM_APP_TYPE

    def test_other_recipe_prompts_do_not_route_to_hangman_lite(self):
        assert (
            select_registry_v2_app_type_for_prompt("Build me a trivia quiz with a timer")
            != HANGMAN_LITE_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("build me an idle clicker game")
            != HANGMAN_LITE_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a branching story game")
            != HANGMAN_LITE_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a memory card matching game")
            != HANGMAN_LITE_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Make a Wordle-style game")
            != HANGMAN_LITE_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a daily word guessing game")
            != HANGMAN_LITE_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a daily puzzle grid game")
            != HANGMAN_LITE_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a resource management sim")
            != HANGMAN_LITE_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build a crossword puzzle")
            != HANGMAN_LITE_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Make a word search")
            != HANGMAN_LITE_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Create flashcards")
            != HANGMAN_LITE_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build a typing speed game")
            != HANGMAN_LITE_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build a SaaS dashboard")
            != HANGMAN_LITE_APP_TYPE
        )

    def test_typing_speed_racer_prompt_does_not_route_to_other_recipes(self):
        prompt = "Build me a typing speed game"
        assert select_registry_v2_app_type_for_prompt(prompt) == TYPING_SPEED_RACER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != IDLE_INCREMENTAL_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != TRIVIA_TIMER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != BRANCHING_NARRATIVE_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != MEMORY_MATCH_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != WORD_DAILY_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != DAILY_PUZZLE_GRID_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != RESOURCE_MANAGEMENT_SIM_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != HANGMAN_LITE_APP_TYPE

    def test_other_recipe_prompts_do_not_route_to_typing_speed_racer(self):
        assert (
            select_registry_v2_app_type_for_prompt("Build me a trivia quiz with a timer")
            != TYPING_SPEED_RACER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("build me an idle clicker game")
            != TYPING_SPEED_RACER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a branching story game")
            != TYPING_SPEED_RACER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a memory card matching game")
            != TYPING_SPEED_RACER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Make a Wordle-style game")
            != TYPING_SPEED_RACER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a daily word guessing game")
            != TYPING_SPEED_RACER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a daily puzzle grid game")
            != TYPING_SPEED_RACER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a resource management sim")
            != TYPING_SPEED_RACER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build a hangman word game")
            != TYPING_SPEED_RACER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build a crossword puzzle")
            != TYPING_SPEED_RACER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Make a word search")
            != TYPING_SPEED_RACER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Create flashcards")
            != TYPING_SPEED_RACER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build a typing tutor dashboard")
            != TYPING_SPEED_RACER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build a SaaS dashboard")
            != TYPING_SPEED_RACER_APP_TYPE
        )

    def test_typing_speed_prompt_routes_to_typing_speed_racer_not_hangman(self):
        prompt = "Build a typing speed game"
        assert select_registry_v2_app_type_for_prompt(prompt) == TYPING_SPEED_RACER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != HANGMAN_LITE_APP_TYPE

    def test_word_builder_prompt_does_not_route_to_other_recipes(self):
        prompt = "Build me a word builder game"
        assert select_registry_v2_app_type_for_prompt(prompt) == WORD_BUILDER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != IDLE_INCREMENTAL_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != TRIVIA_TIMER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != BRANCHING_NARRATIVE_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != MEMORY_MATCH_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != WORD_DAILY_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != DAILY_PUZZLE_GRID_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != RESOURCE_MANAGEMENT_SIM_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != HANGMAN_LITE_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != TYPING_SPEED_RACER_APP_TYPE

    def test_other_recipe_prompts_do_not_route_to_word_builder(self):
        assert (
            select_registry_v2_app_type_for_prompt("Build me a trivia quiz with a timer")
            != WORD_BUILDER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("build me an idle clicker game")
            != WORD_BUILDER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a branching story game")
            != WORD_BUILDER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a memory card matching game")
            != WORD_BUILDER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Make a Wordle-style game")
            != WORD_BUILDER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a daily word guessing game")
            != WORD_BUILDER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a daily puzzle grid game")
            != WORD_BUILDER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a resource management sim")
            != WORD_BUILDER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build a hangman word game")
            != WORD_BUILDER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a typing speed game")
            != WORD_BUILDER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build a crossword puzzle")
            != WORD_BUILDER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Make a word search")
            != WORD_BUILDER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Create flashcards")
            != WORD_BUILDER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build a SaaS dashboard")
            != WORD_BUILDER_APP_TYPE
        )

    def test_word_builder_prompt_routes_to_word_builder_not_word_daily(self):
        prompt = "Build a word game with letter tiles and valid word submissions"
        assert select_registry_v2_app_type_for_prompt(prompt) == WORD_BUILDER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != WORD_DAILY_APP_TYPE

    def test_card_deck_prompt_does_not_route_to_other_recipes(self):
        prompt = (
            "Build a simple turn-based card battle game with a draw pile, hand, "
            "discard pile, and health points."
        )
        assert select_registry_v2_app_type_for_prompt(prompt) == CARD_DECK_TURN_BASED_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != IDLE_INCREMENTAL_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != TRIVIA_TIMER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != BRANCHING_NARRATIVE_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != MEMORY_MATCH_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != WORD_DAILY_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != DAILY_PUZZLE_GRID_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != RESOURCE_MANAGEMENT_SIM_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != HANGMAN_LITE_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != TYPING_SPEED_RACER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != WORD_BUILDER_APP_TYPE

    def test_memory_match_prompt_still_routes_to_memory_not_card_deck(self):
        prompt = "Build me a memory card matching game"
        assert select_registry_v2_app_type_for_prompt(prompt) == MEMORY_MATCH_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != CARD_DECK_TURN_BASED_APP_TYPE

    def test_other_recipe_prompts_do_not_route_to_card_deck_turn_based(self):
        assert (
            select_registry_v2_app_type_for_prompt("Build me a trivia quiz with a timer")
            != CARD_DECK_TURN_BASED_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("build me an idle clicker game")
            != CARD_DECK_TURN_BASED_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a branching story game")
            != CARD_DECK_TURN_BASED_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a memory card matching game")
            != CARD_DECK_TURN_BASED_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Make a Wordle-style game")
            != CARD_DECK_TURN_BASED_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a daily puzzle grid game")
            != CARD_DECK_TURN_BASED_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a resource management sim")
            != CARD_DECK_TURN_BASED_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build a hangman word game")
            != CARD_DECK_TURN_BASED_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a typing speed game")
            != CARD_DECK_TURN_BASED_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a word builder game")
            != CARD_DECK_TURN_BASED_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build a SaaS dashboard")
            != CARD_DECK_TURN_BASED_APP_TYPE
        )

    def test_typing_speed_prompt_still_routes_to_typing_not_reaction_time(self):
        prompt = "Build me a typing speed game"
        assert select_registry_v2_app_type_for_prompt(prompt) == TYPING_SPEED_RACER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != REACTION_TIME_CHALLENGE_APP_TYPE

    def test_reaction_time_prompt_does_not_route_to_other_recipes(self):
        prompt = (
            "Build a browser reaction-time game where the player waits for the screen "
            "to turn green, clicks as fast as possible, and sees their reaction time."
        )
        assert select_registry_v2_app_type_for_prompt(prompt) == REACTION_TIME_CHALLENGE_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != TYPING_SPEED_RACER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != TRIVIA_TIMER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != MEMORY_MATCH_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != CARD_DECK_TURN_BASED_APP_TYPE

    def test_other_recipe_prompts_do_not_route_to_reaction_time_challenge(self):
        assert (
            select_registry_v2_app_type_for_prompt("Build me a trivia quiz with a timer")
            != REACTION_TIME_CHALLENGE_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a typing speed game")
            == TYPING_SPEED_RACER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a memory card matching game")
            == MEMORY_MATCH_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build a Pomodoro timer")
            not in {REACTION_TIME_CHALLENGE_APP_TYPE, TRIVIA_TIMER_APP_TYPE}
        )

    def test_typing_speed_prompt_still_routes_to_typing_not_rhythm(self):
        prompt = "Build me a typing speed game"
        assert select_registry_v2_app_type_for_prompt(prompt) == TYPING_SPEED_RACER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != RHYTHM_TAP_LITE_APP_TYPE

    def test_reaction_time_prompt_still_routes_to_reaction_not_rhythm(self):
        prompt = (
            "Build a browser reaction-time game where the player waits for the screen "
            "to turn green, clicks as fast as possible, and sees their reaction time."
        )
        assert select_registry_v2_app_type_for_prompt(prompt) == REACTION_TIME_CHALLENGE_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != RHYTHM_TAP_LITE_APP_TYPE

    def test_rhythm_prompt_does_not_route_to_other_recipes(self):
        prompt = (
            "Build a browser rhythm tap game where circles appear on beats and players "
            "press space at the right time for perfect/good/miss scores."
        )
        assert select_registry_v2_app_type_for_prompt(prompt) == RHYTHM_TAP_LITE_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != REACTION_TIME_CHALLENGE_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != TYPING_SPEED_RACER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != TRIVIA_TIMER_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != MEMORY_MATCH_APP_TYPE

    def test_other_recipe_prompts_do_not_route_to_rhythm_tap_lite(self):
        assert (
            select_registry_v2_app_type_for_prompt("Build me a trivia quiz with a timer")
            != RHYTHM_TAP_LITE_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build me a typing speed game")
            == TYPING_SPEED_RACER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt(
                "Build a browser reaction-time game where the player waits for the screen "
                "to turn green, clicks as fast as possible, and sees their reaction time."
            )
            == REACTION_TIME_CHALLENGE_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build a Pomodoro timer")
            not in {RHYTHM_TAP_LITE_APP_TYPE, TRIVIA_TIMER_APP_TYPE}
        )

    def test_turn_based_card_battle_still_routes_to_card_deck_not_deck_builder(self):
        prompt = (
            "Build a simple turn-based card battle game with a draw pile, hand, "
            "discard pile, and health points."
        )
        assert select_registry_v2_app_type_for_prompt(prompt) == CARD_DECK_TURN_BASED_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != DECK_BUILDER_LITE_APP_TYPE

    def test_deck_builder_prompt_does_not_route_to_other_recipes(self):
        prompt = (
            "Build a browser deck-building card game where the player starts with a small deck, "
            "fights simple encounters, and chooses a new card reward after each win."
        )
        assert select_registry_v2_app_type_for_prompt(prompt) == DECK_BUILDER_LITE_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != CARD_DECK_TURN_BASED_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != MEMORY_MATCH_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != RHYTHM_TAP_LITE_APP_TYPE

    def test_other_recipe_prompts_do_not_route_to_deck_builder_lite(self):
        assert (
            select_registry_v2_app_type_for_prompt("Build me a memory card matching game")
            == MEMORY_MATCH_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt(
                "Build a simple turn-based card battle game with a draw pile, hand, "
                "discard pile, and health points."
            )
            == CARD_DECK_TURN_BASED_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build a deck builder")
            not in {DECK_BUILDER_LITE_APP_TYPE, CARD_DECK_TURN_BASED_APP_TYPE}
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

    def test_flag_disabled_resource_management_sim_prompt_does_not_add_registry_metadata(
        self, monkeypatch
    ):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a resource management sim",
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_disabled_hangman_lite_prompt_does_not_add_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build a hangman word game",
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_disabled_typing_speed_racer_prompt_does_not_add_registry_metadata(
        self, monkeypatch
    ):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a typing speed game",
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_disabled_word_builder_prompt_does_not_add_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a word builder game",
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_disabled_card_deck_prompt_does_not_add_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            (
                "Build a simple turn-based card battle game with a draw pile, hand, "
                "discard pile, and health points."
            ),
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_disabled_reaction_time_prompt_does_not_add_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            (
                "Build a browser reaction-time game where the player waits for the screen "
                "to turn green, clicks as fast as possible, and sees their reaction time."
            ),
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_disabled_rhythm_prompt_does_not_add_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            (
                "Build a browser rhythm tap game where circles appear on beats and players "
                "press space at the right time for perfect/good/miss scores."
            ),
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_disabled_deck_builder_prompt_does_not_add_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            (
                "Build a browser deck-building card game where the player starts with a small deck, "
                "fights simple encounters, and chooses a new card reward after each win."
            ),
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

    def test_flag_enabled_resource_management_sim_prompt_adds_registry_metadata(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic", "originated_from": "builder_chat_scaffold"},
            "Build me a resource management sim",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        assert metadata["registry_v2_app_type"] == RESOURCE_MANAGEMENT_SIM_APP_TYPE
        assert metadata["template_kind"] == "generic"
        assert metadata["originated_from"] == "builder_chat_scaffold"

    def test_flag_enabled_hangman_lite_prompt_adds_registry_metadata(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic", "originated_from": "builder_chat_scaffold"},
            "Build a hangman word game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        assert metadata["registry_v2_app_type"] == HANGMAN_LITE_APP_TYPE
        assert metadata["template_kind"] == "generic"
        assert metadata["originated_from"] == "builder_chat_scaffold"

    def test_flag_enabled_typing_speed_racer_prompt_adds_registry_metadata(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic", "originated_from": "builder_chat_scaffold"},
            "Build me a typing speed game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        assert metadata["registry_v2_app_type"] == TYPING_SPEED_RACER_APP_TYPE
        assert metadata["template_kind"] == "generic"
        assert metadata["originated_from"] == "builder_chat_scaffold"

    def test_flag_enabled_word_builder_prompt_adds_registry_metadata(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic", "originated_from": "builder_chat_scaffold"},
            "Build me a word builder game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        assert metadata["registry_v2_app_type"] == WORD_BUILDER_APP_TYPE
        assert metadata["template_kind"] == "generic"
        assert metadata["originated_from"] == "builder_chat_scaffold"

    def test_flag_enabled_card_deck_turn_based_prompt_adds_registry_metadata(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic", "originated_from": "builder_chat_scaffold"},
            (
                "Build a simple turn-based card battle game with a draw pile, hand, "
                "discard pile, and health points."
            ),
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        assert metadata["registry_v2_app_type"] == CARD_DECK_TURN_BASED_APP_TYPE
        assert metadata["template_kind"] == "generic"
        assert metadata["originated_from"] == "builder_chat_scaffold"

    def test_flag_enabled_reaction_time_prompt_adds_registry_metadata(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic", "originated_from": "builder_chat_scaffold"},
            (
                "Build a browser reaction-time game where the player waits for the screen "
                "to turn green, clicks as fast as possible, and sees their reaction time."
            ),
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        assert metadata["registry_v2_app_type"] == REACTION_TIME_CHALLENGE_APP_TYPE
        assert metadata["template_kind"] == "generic"
        assert metadata["originated_from"] == "builder_chat_scaffold"

    def test_flag_enabled_rhythm_prompt_adds_registry_metadata(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic", "originated_from": "builder_chat_scaffold"},
            (
                "Build a browser rhythm tap game where circles appear on beats and players "
                "press space at the right time for perfect/good/miss scores."
            ),
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        assert metadata["registry_v2_app_type"] == RHYTHM_TAP_LITE_APP_TYPE
        assert metadata["template_kind"] == "generic"
        assert metadata["originated_from"] == "builder_chat_scaffold"

    def test_flag_enabled_deck_builder_prompt_adds_registry_metadata(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic", "originated_from": "builder_chat_scaffold"},
            (
                "Build a browser deck-building card game where the player starts with a small deck, "
                "fights simple encounters, and chooses a new card reward after each win."
            ),
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        assert metadata["registry_v2_app_type"] == DECK_BUILDER_LITE_APP_TYPE
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

    def test_flag_enabled_non_resource_management_sim_prompt_leaves_registry_metadata_absent(
        self,
    ):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Create an inventory management app",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_enabled_wordle_prompt_routes_to_word_daily_not_hangman(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Make a Wordle-style game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
        )
        assert metadata["registry_v2_app_type"] == WORD_DAILY_APP_TYPE
        assert metadata["registry_v2_app_type"] != HANGMAN_LITE_APP_TYPE

    def test_flag_enabled_non_typing_speed_racer_prompt_leaves_registry_metadata_absent(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build a typing tutor dashboard",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_enabled_non_word_builder_prompt_leaves_registry_metadata_absent(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build a Wordle-style game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
        )
        assert metadata.get("registry_v2_app_type") == WORD_DAILY_APP_TYPE
        assert metadata.get("registry_v2_app_type") != WORD_BUILDER_APP_TYPE

    def test_flag_enabled_non_card_deck_turn_based_prompt_leaves_registry_metadata_absent(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build a poker game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_enabled_non_reaction_time_prompt_leaves_registry_metadata_absent(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build a Pomodoro timer",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_enabled_non_rhythm_prompt_leaves_registry_metadata_absent(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build a metronome",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_enabled_non_deck_builder_prompt_leaves_registry_metadata_absent(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build a deck builder",
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

    def test_flag_disabled_resource_management_sim_prompt_has_no_registry_metadata(
        self, monkeypatch
    ):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = _synthetic_plan_metadata("Build me a resource management sim")
        assert metadata.get("template_kind") == "generic"
        assert "registry_v2_app_type" not in metadata

    def test_flag_disabled_hangman_lite_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = _synthetic_plan_metadata("Build a hangman word game")
        assert metadata.get("template_kind") == "generic"
        assert "registry_v2_app_type" not in metadata

    def test_flag_disabled_typing_speed_racer_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = _synthetic_plan_metadata("Build me a typing speed game")
        assert metadata.get("template_kind") == "generic"
        assert "registry_v2_app_type" not in metadata

    def test_flag_disabled_word_builder_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = _synthetic_plan_metadata("Build me a word builder game")
        assert metadata.get("template_kind") == "generic"
        assert "registry_v2_app_type" not in metadata

    def test_flag_disabled_card_deck_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = _synthetic_plan_metadata(
            "Build a simple turn-based card battle game with a draw pile, hand, "
            "discard pile, and health points."
        )
        assert metadata.get("template_kind") == "generic"
        assert "registry_v2_app_type" not in metadata

    def test_flag_disabled_reaction_time_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = _synthetic_plan_metadata(
            "Build a browser reaction-time game where the player waits for the screen "
            "to turn green, clicks as fast as possible, and sees their reaction time."
        )
        assert metadata.get("template_kind") == "generic"
        assert "registry_v2_app_type" not in metadata

    def test_flag_disabled_rhythm_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = _synthetic_plan_metadata(
            "Build a browser rhythm tap game where circles appear on beats and players "
            "press space at the right time for perfect/good/miss scores."
        )
        assert metadata.get("template_kind") == "generic"
        assert "registry_v2_app_type" not in metadata

    def test_flag_disabled_deck_builder_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = _synthetic_plan_metadata(
            "Build a browser deck-building card game where the player starts with a small deck, "
            "fights simple encounters, and chooses a new card reward after each win."
        )
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

    def test_flag_enabled_resource_management_sim_prompt_adds_registry_metadata(
        self, monkeypatch
    ):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata("Build me a resource management sim")
        assert metadata.get("template_kind") == "generic"
        assert metadata.get("registry_v2_app_type") == RESOURCE_MANAGEMENT_SIM_APP_TYPE

    def test_flag_enabled_hangman_lite_prompt_adds_registry_metadata(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata("Build a hangman word game")
        assert metadata.get("template_kind") == "generic"
        assert metadata.get("registry_v2_app_type") == HANGMAN_LITE_APP_TYPE

    def test_flag_enabled_typing_speed_racer_prompt_adds_registry_metadata(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata("Build me a typing speed game")
        assert metadata.get("template_kind") == "generic"
        assert metadata.get("registry_v2_app_type") == TYPING_SPEED_RACER_APP_TYPE

    def test_flag_enabled_word_builder_prompt_adds_registry_metadata(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata("Build me a word builder game")
        assert metadata.get("template_kind") == "generic"
        assert metadata.get("registry_v2_app_type") == WORD_BUILDER_APP_TYPE

    def test_flag_enabled_card_deck_turn_based_prompt_adds_registry_metadata_synthetic(
        self, monkeypatch
    ):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata(
            "Build a simple turn-based card battle game with a draw pile, hand, "
            "discard pile, and health points."
        )
        assert metadata.get("template_kind") == "generic"
        assert metadata.get("registry_v2_app_type") == CARD_DECK_TURN_BASED_APP_TYPE

    def test_flag_enabled_reaction_time_prompt_adds_registry_metadata_synthetic(
        self, monkeypatch
    ):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata(
            "Build a browser reaction-time game where the player waits for the screen "
            "to turn green, clicks as fast as possible, and sees their reaction time."
        )
        assert metadata.get("template_kind") == "generic"
        assert metadata.get("registry_v2_app_type") == REACTION_TIME_CHALLENGE_APP_TYPE

    def test_flag_enabled_rhythm_prompt_adds_registry_metadata_synthetic(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata(
            "Build a browser rhythm tap game where circles appear on beats and players "
            "press space at the right time for perfect/good/miss scores."
        )
        assert metadata.get("template_kind") == "generic"
        assert metadata.get("registry_v2_app_type") == RHYTHM_TAP_LITE_APP_TYPE

    def test_flag_enabled_deck_builder_prompt_adds_registry_metadata_synthetic(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata(
            "Build a browser deck-building card game where the player starts with a small deck, "
            "fights simple encounters, and chooses a new card reward after each win."
        )
        assert metadata.get("template_kind") == "generic"
        assert metadata.get("registry_v2_app_type") == DECK_BUILDER_LITE_APP_TYPE

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

    def test_flag_enabled_resource_management_sim_prompt_produces_v2_context(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a resource management sim",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        plan = Plan(
            plan_id="pln_registry_intent_resource_mgmt_e2e",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a resource management sim",
            steps=[
                Step(title="Scaffold game", description="Create resource management sim files")
            ],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )[1]["content"]
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.resource-management-sim" in content
        assert "stack.dom-game-minimal" in content
        assert "validator.no-negative-resources" in content
        assert "validator.production-chain-consistency" in content
        assert "validator.goal-state-detection" in content
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

    def test_flag_disabled_resource_management_sim_prompt_produces_v1_context_only(
        self, monkeypatch
    ):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a resource management sim",
        )
        plan = Plan(
            plan_id="pln_registry_intent_resource_mgmt_v1",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a resource management sim",
            steps=[
                Step(title="Scaffold game", description="Create resource management sim files")
            ],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(plan)[1]["content"]
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content

    def test_flag_enabled_hangman_lite_prompt_produces_v2_context(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build a hangman word game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        plan = Plan(
            plan_id="pln_registry_intent_hangman_lite_e2e",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build a hangman word game",
            steps=[Step(title="Scaffold game", description="Create hangman game files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )[1]["content"]
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.hangman-lite" in content
        assert "stack.dom-game-minimal" in content
        assert "validator.letter-reveal-correctness" in content
        assert "validator.duplicate-guess-blocking" in content
        assert "validator.hangman-win-loss-detection" in content
        assert "Builder Kit context:" not in content
        assert content.count("Builder Kit:") == 0

    def test_flag_disabled_hangman_lite_prompt_produces_v1_context_only(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build a hangman word game",
        )
        plan = Plan(
            plan_id="pln_registry_intent_hangman_lite_v1",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build a hangman word game",
            steps=[Step(title="Scaffold game", description="Create hangman game files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(plan)[1]["content"]
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content

    def test_flag_enabled_typing_speed_racer_prompt_produces_v2_context(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a typing speed game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        plan = Plan(
            plan_id="pln_registry_intent_typing_speed_racer_e2e",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a typing speed game",
            steps=[Step(title="Scaffold game", description="Create typing speed game files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )[1]["content"]
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.typing-speed-racer" in content
        assert "stack.dom-game-minimal" in content
        assert "validator.wpm-calculation-consistency" in content
        assert "validator.accuracy-score-bounds" in content
        assert "validator.input-lock-after-finish" in content
        assert "Builder Kit context:" not in content
        assert content.count("Builder Kit:") == 0

    def test_flag_disabled_typing_speed_racer_prompt_produces_v1_context_only(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a typing speed game",
        )
        plan = Plan(
            plan_id="pln_registry_intent_typing_speed_racer_v1",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a typing speed game",
            steps=[Step(title="Scaffold game", description="Create typing speed game files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(plan)[1]["content"]
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content

    def test_flag_enabled_word_builder_prompt_produces_v2_context(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a word builder game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        plan = Plan(
            plan_id="pln_registry_intent_word_builder_e2e",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a word builder game",
            steps=[Step(title="Scaffold game", description="Create word builder game files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )[1]["content"]
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.word-builder" in content
        assert "stack.dom-game-minimal" in content
        assert "validator.letter-pool-integrity" in content
        assert "validator.word-validation-rules" in content
        assert "validator.duplicate-submission-blocking" in content
        assert "validator.word-builder-completion" in content
        assert "Builder Kit context:" not in content
        assert content.count("Builder Kit:") == 0

    def test_flag_disabled_word_builder_prompt_produces_v1_context_only(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a word builder game",
        )
        plan = Plan(
            plan_id="pln_registry_intent_word_builder_v1",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a word builder game",
            steps=[Step(title="Scaffold game", description="Create word builder game files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(plan)[1]["content"]
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content

    def test_flag_enabled_card_deck_turn_based_prompt_produces_v2_context(self):
        prompt = (
            "Build a simple turn-based card battle game with a draw pile, hand, "
            "discard pile, and health points."
        )
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            prompt,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        plan = Plan(
            plan_id="pln_registry_intent_card_deck_e2e",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message=prompt,
            steps=[Step(title="Scaffold game", description="Create card battle game files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )[1]["content"]
        assert metadata["registry_v2_app_type"] == CARD_DECK_TURN_BASED_APP_TYPE
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.card-deck-turn-based" in content
        assert "mechanic.deck-draw-pile" in content
        assert "mechanic.hand-state" in content
        assert "mechanic.discard-pile" in content
        assert "validator.deck-zone-integrity" in content
        assert "Builder Kit context:" not in content
        assert content.count("Builder Kit:") == 0

    def test_flag_disabled_card_deck_turn_based_prompt_produces_v1_context_only(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        prompt = (
            "Build a simple turn-based card battle game with a draw pile, hand, "
            "discard pile, and health points."
        )
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            prompt,
        )
        plan = Plan(
            plan_id="pln_registry_intent_card_deck_v1",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message=prompt,
            steps=[Step(title="Scaffold game", description="Create card battle game files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(plan)[1]["content"]
        assert "registry_v2_app_type" not in metadata
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content

    def test_flag_enabled_reaction_time_prompt_produces_v2_context(self):
        prompt = (
            "Build a browser reaction-time game where the player waits for the screen "
            "to turn green, clicks as fast as possible, and sees their reaction time."
        )
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            prompt,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        plan = Plan(
            plan_id="pln_registry_intent_reaction_time_e2e",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message=prompt,
            steps=[Step(title="Scaffold game", description="Create reaction time game files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )[1]["content"]
        assert metadata["registry_v2_app_type"] == REACTION_TIME_CHALLENGE_APP_TYPE
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.reaction-time-challenge" in content
        assert "mechanic.reaction-state-machine" in content
        assert "mechanic.random-signal-delay" in content
        assert "mechanic.false-start-handling" in content
        assert "mechanic.reaction-timer" in content
        assert "mechanic.reaction-input-response" in content
        assert "mechanic.reaction-result-state" in content
        assert "validator.false-start-enforcement" in content
        assert "Builder Kit context:" not in content
        assert content.count("Builder Kit:") == 0

    def test_flag_disabled_reaction_time_prompt_produces_v1_context_only(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        prompt = (
            "Build a browser reaction-time game where the player waits for the screen "
            "to turn green, clicks as fast as possible, and sees their reaction time."
        )
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            prompt,
        )
        plan = Plan(
            plan_id="pln_registry_intent_reaction_time_v1",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message=prompt,
            steps=[Step(title="Scaffold game", description="Create reaction time game files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(plan)[1]["content"]
        assert "registry_v2_app_type" not in metadata
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content

    def test_flag_enabled_rhythm_prompt_produces_v2_context(self):
        prompt = (
            "Build a browser rhythm tap game where circles appear on beats and players "
            "press space at the right time for perfect/good/miss scores."
        )
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            prompt,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        plan = Plan(
            plan_id="pln_registry_intent_rhythm_e2e",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message=prompt,
            steps=[Step(title="Scaffold game", description="Create rhythm tap game files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )[1]["content"]
        assert metadata["registry_v2_app_type"] == RHYTHM_TAP_LITE_APP_TYPE
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.rhythm-tap-lite" in content
        assert "mechanic.rhythm-round-state-machine" in content
        assert "mechanic.rhythm-beat-sequence" in content
        assert "mechanic.rhythm-timing-window" in content
        assert "mechanic.rhythm-tap-input" in content
        assert "mechanic.rhythm-accuracy-scoring" in content
        assert "mechanic.rhythm-streak-combo" in content
        assert "mechanic.rhythm-result-state" in content
        assert "validator.rhythm-timing-window-bounds" in content
        assert "Builder Kit context:" not in content
        assert content.count("Builder Kit:") == 0

    def test_flag_disabled_rhythm_prompt_produces_v1_context_only(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        prompt = (
            "Build a browser rhythm tap game where circles appear on beats and players "
            "press space at the right time for perfect/good/miss scores."
        )
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            prompt,
        )
        plan = Plan(
            plan_id="pln_registry_intent_rhythm_v1",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message=prompt,
            steps=[Step(title="Scaffold game", description="Create rhythm tap game files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(plan)[1]["content"]
        assert "registry_v2_app_type" not in metadata
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content

    def test_flag_enabled_deck_builder_prompt_produces_v2_context(self):
        prompt = (
            "Build a browser deck-building card game where the player starts with a small deck, "
            "fights simple encounters, and chooses a new card reward after each win."
        )
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            prompt,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        plan = Plan(
            plan_id="pln_registry_intent_deck_builder_e2e",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message=prompt,
            steps=[Step(title="Scaffold game", description="Create deck builder game files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )[1]["content"]
        assert metadata["registry_v2_app_type"] == DECK_BUILDER_LITE_APP_TYPE
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.deck-builder-lite" in content
        assert "mechanic.deck-builder-run-state-machine" in content
        assert "mechanic.starter-deck-seed" in content
        assert "mechanic.encounter-round-loop" in content
        assert "mechanic.reward-offer-choice" in content
        assert "mechanic.deck-mutation" in content
        assert "mechanic.deck-builder-result-state" in content
        assert "Builder Kit context:" not in content
        assert content.count("Builder Kit:") == 0

    def test_flag_disabled_deck_builder_prompt_produces_v1_context_only(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        prompt = (
            "Build a browser deck-building card game where the player starts with a small deck, "
            "fights simple encounters, and chooses a new card reward after each win."
        )
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            prompt,
        )
        plan = Plan(
            plan_id="pln_registry_intent_deck_builder_v1",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message=prompt,
            steps=[Step(title="Scaffold game", description="Create deck builder game files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(plan)[1]["content"]
        assert "registry_v2_app_type" not in metadata
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content
