"""Conservative prompt → Build Registry v2 app type routing (ADR-0017 Phase 2E).

Pure string matching only. No I/O, no LLM calls, no registry file loads.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

IDLE_INCREMENTAL_APP_TYPE = "game.idle-incremental"
TRIVIA_TIMER_APP_TYPE = "game.trivia-timer"
BRANCHING_NARRATIVE_APP_TYPE = "game.branching-narrative"
MEMORY_MATCH_APP_TYPE = "game.memory-match"
WORD_DAILY_APP_TYPE = "game.word-daily"
DAILY_PUZZLE_GRID_APP_TYPE = "game.daily-puzzle-grid"
RESOURCE_MANAGEMENT_SIM_APP_TYPE = "game.resource-management-sim"
HANGMAN_LITE_APP_TYPE = "game.hangman-lite"

_HANGMAN_LITE_CROSS_RECIPE_NEGATIVES: tuple[str, ...] = (
    r"\bhangman(-style)?\b",
    r"\bhangman\b.{0,80}\b(word\s+game|letter\s+guessing|wrong\s+guesses?|game)\b",
    r"\b(word\s+game|letter\s+guessing|game)\b.{0,80}\bhangman\b",
    r"\bguess\s+letters?\b.{0,100}\b(hidden\s+word|reveal)\b",
    r"\b(hidden\s+word|reveal)\b.{0,100}\bguess\s+letters?\b",
    r"\bletter\s+guessing\b.{0,80}\b(word\s+game|game|hidden\s+word)\b",
    r"\bwrong\s+guesses?\b.{0,80}\bhangman\b",
    r"\bhangman\b.{0,80}\bwrong\s+guesses?\b",
)

_RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES: tuple[str, ...] = (
    r"\bresource\s+management\b.{0,80}\b(sim|simulation|game)\b",
    r"\b(sim|simulation|game)\b.{0,80}\bresource\s+management\b",
    r"\bcolony\s+management\b.{0,80}\bgame\b",
    r"\bgame\b.{0,80}\bcolony\s+management\b",
    r"\bproduction\s+chain\b.{0,80}\b(sim|simulation|game)\b",
    r"\b(sim|simulation|game)\b.{0,80}\bproduction\s+chain\b",
    r"\bresource\s+allocation\b.{0,80}\bgame\b",
    r"\bfarm\s+management\b.{0,80}\bsim\b",
    r"\bturn[-\s]?based\b.{0,80}\bresource\s+management\b",
)

_GLOBAL_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(dashboard|landing\s*page|saas|calculator|todo|to[-\s]?do|crm)\b",
    r"\b(crypto|trading)\s+(dashboard|app|platform)\b",
    r"\b(snake|pong|asteroids|flappy)\b",
    r"\b(tetris|tetromino|platformer)\b",
)

_IDLE_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(trivia|quiz)\b",
    r"\bmemory\s+(card|match)\b",
    r"\bbranching\s+story\b",
    r"\bchoose\s+your\s+own\s+adventure\b",
    r"\b(wordle|daily\s+word|word\s+guess)\b",
    r"\b(nonogram|picross|sudoku|minesweeper)\b",
    r"\blogic\s+grid\s+puzzle\b",
    r"\bdaily\s+puzzle\s+grid\b",
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES

_TRIVIA_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(idle|incremental|clicker|tycoon)\b",
    r"\bcookie\s+clicker\b",
    r"\bpassive\s+income\b",
    r"\bmemory\s+(card|match)\b",
    r"\bbranching\s+story\b",
    r"\bchoose\s+your\s+own\s+adventure\b",
    r"\binteractive\s+fiction\b",
    r"\bsurvey\b",
    r"\bflashcard\b",
    r"\bform\b.{0,80}\bmultiple\s+choice\b",
    r"\bmultiple\s+choice\b.{0,80}\bform\b",
    r"\beducation\s+website\b",
    r"\b(wordle|daily\s+word|word\s+guess)\b",
    r"\b(nonogram|picross|sudoku|minesweeper)\b",
    r"\blogic\s+grid\s+puzzle\b",
    r"\bdaily\s+puzzle\s+grid\b",
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES

_IDLE_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\b(idle|incremental|clicker|tycoon)\b",
    r"\bcookie\s+clicker\b",
    r"\bpassive\s+income\b",
    r"\b(idle|incremental|clicker|tycoon)\s+(game|app)\b",
    r"\b(mining|factory|business)\s+(clicker|idle|tycoon)\b",
    r"\b(clicker|idle|tycoon)\s+(game|style)\b",
    r"\b(game|app)\b.{0,100}\b(earn|collect)\b.{0,60}\b(coins?|currency|gold|resources?)\b.{0,80}\b(upgrades?|buy|purchase)\b",
    r"\b(earn|collect|mine)\b.{0,60}\b(coins?|currency|gold|resources?)\b.{0,80}\b(upgrades?|buy|purchase)\b",
)

_TRIVIA_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\btrivia\b.{0,100}\b(timer|timed|countdown|seconds|game|quiz|challenge|score|question)\b",
    r"\b(timer|timed|countdown)\b.{0,100}\b(trivia|quiz)\b",
    r"\b(timed|timer|countdown)\b.{0,80}\b(quiz|trivia)\b.{0,80}\bgame\b",
    r"\bquiz\s+game\b",
    r"\btrivia\s+game\b",
    r"\bmultiple\s+choice\b.{0,80}\b(trivia|quiz)\b.{0,80}\bgame\b",
    r"\b(trivia|quiz)\b.{0,80}\bmultiple\s+choice\b",
    r"\b(trivia|quiz)\s+challenge\b",
    r"\b\d+\s+question\b.{0,80}\b(trivia|quiz)\b",
    r"\b(trivia|quiz)\b.{0,80}\b(score|questions?)\b",
    r"\btrivia\s+quiz\b",
    r"\bhistory\s+trivia\b",
)

_BRANCHING_NARRATIVE_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(idle|incremental|clicker|tycoon)\b",
    r"\bcookie\s+clicker\b",
    r"\bpassive\s+income\b",
    r"\b(trivia|quiz)\b",
    r"\bmemory\s+(card|match)\b",
    r"\b(blog|chatbot)\b",
    r"\bwriting\s+app\b",
    r"\bai\s+dungeon\b",
    r"\blive\s+generated\b.{0,80}\bstory\b",
    r"\bgeneric\s+rpg\b",
    r"\bsurvey\b",
    r"\bflashcard\b",
    r"\beducation\s+website\b",
    r"\b(wordle|daily\s+word|word\s+guess)\b",
    r"\b(nonogram|picross|sudoku|minesweeper)\b",
    r"\blogic\s+grid\s+puzzle\b",
    r"\bdaily\s+puzzle\s+grid\b",
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES

_BRANCHING_NARRATIVE_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bbranching\s+story\b.{0,80}\bgame\b",
    r"\bgame\b.{0,80}\bbranching\s+story\b",
    r"\bchoose\s+your\s+own\s+adventure\b",
    r"\binteractive\s+fiction\b",
    r"\bdialogue\s+choice\b.{0,80}\brpg\b",
    r"\bstory\s+game\b.{0,100}\b(choices?|choice|ending)\b",
    r"\b(choices?|choice)\b.{0,100}\b(story|ending|narrative)\b",
    r"\bnarrative\s+game\b.{0,100}\b(multiple\s+endings?|endings?)\b",
    r"\btext\s+adventure\b.{0,100}\b(inventory|choices?|choice)\b",
    r"\bbranching\s+narrative\b",
)

_MEMORY_MATCH_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(idle|incremental|clicker|tycoon)\b",
    r"\bcookie\s+clicker\b",
    r"\bpassive\s+income\b",
    r"\b(trivia|quiz)\b",
    r"\bbranching\s+story\b",
    r"\bchoose\s+your\s+own\s+adventure\b",
    r"\binteractive\s+fiction\b",
    r"\bcard\s+battler\b",
    r"\btrading\s+card\b",
    r"\bflashcard\b",
    r"\bgeneric\s+card\s+game\b",
    r"\bpoker\b",
    r"\bsolitaire\b",
    r"\bsurvey\b",
    r"\b(wordle|daily\s+word|word\s+guess)\b",
    r"\b(nonogram|picross|sudoku|minesweeper)\b",
    r"\blogic\s+grid\s+puzzle\b",
    r"\bdaily\s+puzzle\s+grid\b",
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES

_MEMORY_MATCH_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bmemory\s+(card|match)\b",
    r"\bemoji\s+memory\b.{0,80}\bgame\b",
    r"\bgame\b.{0,80}\bmemory\s+(card|match)\b",
    r"\bflip(ped)?\s+cards?\b.{0,100}\b(find|match|pair)\b",
    r"\b(find|match|pair)\b.{0,100}\bflip(ped)?\s+cards?\b",
    r"\bconcentration\b.{0,80}\bcard\b.{0,80}\bgame\b",
    r"\bcard\s+matching\b.{0,80}\bgame\b",
    r"\bmatching\s+pairs\b.{0,100}\bgame\b",
    r"\bmatching\s+pairs\b.{0,100}\bflip(ped)?\s+cards?\b",
    r"\b\d+x\d+\b.{0,100}\bcard\s+matching\b",
    r"\bmove\s+counter\b.{0,100}\b(memory|matching|pair|flip)\b",
)

_WORD_DAILY_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(idle|incremental|clicker|tycoon)\b",
    r"\bcookie\s+clicker\b",
    r"\bpassive\s+income\b",
    r"\b(trivia|quiz)\b",
    r"\bmemory\s+(card|match)\b",
    r"\bbranching\s+story\b",
    r"\bchoose\s+your\s+own\s+adventure\b",
    r"\binteractive\s+fiction\b",
    r"\bcrossword\b",
    r"\bword\s+search\b",
    r"\bflashcard\b",
    r"\btyping\s+(speed|test|game)\b",
    r"\bdictionary\b",
    r"\bwriting\s+app\b",
    r"\bsurvey\b",
    r"\beducation\s+website\b",
    r"\b(nonogram|picross|sudoku|minesweeper)\b",
    r"\blogic\s+grid\s+puzzle\b",
    r"\bdaily\s+puzzle\s+grid\b",
    r"\bfill\s+cells\b.{0,80}\b(clue|row|column|constraint)\b",
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES

_WORD_DAILY_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bwordle(-style)?\b",
    r"\bdaily\s+word\b.{0,100}\b(guess(ing)?|game|puzzle)\b",
    r"\b(guess(ing)?)\b.{0,100}\bdaily\s+word\b",
    r"\bword\s+guess(ing)?\b.{0,100}\b(game|puzzle|challenge)\b",
    r"\b(game|puzzle|challenge)\b.{0,100}\bword\s+guess(ing)?\b",
    r"\bhidden\s+word\b.{0,120}\b(guess|feedback|green|yellow|gray|grey)\b",
    r"\b(green|yellow|gray|grey)\b.{0,120}\b(hidden\s+word|letter\s+feedback|feedback)\b",
    r"\bletter\s+feedback\b.{0,100}\b(word|guess|attempts?|tries)\b",
    r"\b(attempts?|tries|guesses)\b.{0,100}\bletter\s+feedback\b",
    r"\b\d+-letter\b.{0,80}\bword\s+guess(ing)?\b",
    r"\bword\s+guess(ing)?\b.{0,80}\b\d+\s+(attempts?|tries|guesses)\b",
    r"\bword\s+game\b.{0,120}\b(attempts?|tries|letter\s+feedback|duplicate-letter)\b",
    r"\b(attempts?|tries|letter\s+feedback|duplicate-letter)\b.{0,120}\bword\s+game\b",
    r"\bduplicate-letter\b.{0,100}\b(word|guess|handling|feedback)\b",
    r"\bdaily\s+word\s+puzzle\b",
    r"\bkeyboard\s+input\b.{0,100}\b(word|guess|daily|puzzle)\b",
    r"\b(word|daily)\b.{0,100}\bkeyboard\s+input\b",
)

_DAILY_PUZZLE_GRID_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(idle|incremental|clicker|tycoon)\b",
    r"\bcookie\s+clicker\b",
    r"\bpassive\s+income\b",
    r"\b(trivia|quiz)\b",
    r"\bmemory\s+(card|match)\b",
    r"\bbranching\s+story\b",
    r"\bchoose\s+your\s+own\s+adventure\b",
    r"\binteractive\s+fiction\b",
    r"\b(wordle|daily\s+word|word\s+guess|wordle-style)\b",
    r"\bcrossword\b",
    r"\bword\s+search\b",
    r"\bminesweeper\b",
    r"\b(dashboard|data\s+table|spreadsheet)\b",
    r"\bdashboard\s+grid\b",
    r"\bcss\s+grid\b",
    r"\bgrid\s+layout\b",
    r"\bsurvey\b",
    r"\bflashcard\b",
    r"\beducation\s+website\b",
    r"\b(blog|chatbot)\b",
    r"\bwriting\s+app\b",
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES

_DAILY_PUZZLE_GRID_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bdaily\s+puzzle\s+grid\b",
    r"\blogic\s+grid\s+puzzle\b",
    r"\bgrid\s+logic\s+puzzle\b",
    r"\btile\s+logic\s+puzzle\b",
    r"\bdaily\s+grid\s+puzzle\b.{0,120}\b(row|column|rule|clue|constraint|cell)\b",
    r"\b(row|column|rule|clue|constraint|cell)\b.{0,120}\bdaily\s+grid\s+puzzle\b",
    r"\bsudoku(-like)?\b.{0,80}\b(grid|puzzle|game)\b",
    r"\b(grid|puzzle|game)\b.{0,80}\bsudoku(-like)?\b",
    r"\bnonogram(-style)?\b.{0,80}\b(puzzle|game)\b",
    r"\b(picross|nonogram)\b.{0,80}\b(puzzle|game|style)\b",
    r"\bfill\s+cells\b.{0,120}\b(clue|clues|constraint|rule|row|column)\b",
    r"\b(clue|clues|constraint|rule)\b.{0,120}\bfill\s+cells\b",
    r"\bgame\b.{0,80}\bfill\s+cells\b.{0,80}\b(clue|clues)\b",
    r"\bmini\s+sudoku\b",
    r"\b(row|column)\b.{0,80}\b(rule|constraint|clue)\b.{0,80}\b(grid|puzzle|cell)\b",
    r"\bgrid\s+puzzle\b.{0,100}\b(hint|completion|constraint|rule|clue|cell)\b",
    r"\b(hint|completion)\b.{0,100}\bgrid\s+puzzle\b",
)

_RESOURCE_MANAGEMENT_SIM_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(idle|incremental|clicker|tycoon)\b",
    r"\bcookie\s+clicker\b",
    r"\bpassive\s+income\b",
    r"\b(trivia|quiz)\b",
    r"\bmemory\s+(card|match)\b",
    r"\bbranching\s+story\b",
    r"\bchoose\s+your\s+own\s+adventure\b",
    r"\binteractive\s+fiction\b",
    r"\b(wordle|daily\s+word|word\s+guess)\b",
    r"\b(nonogram|picross|sudoku|minesweeper)\b",
    r"\blogic\s+grid\s+puzzle\b",
    r"\bdaily\s+puzzle\s+grid\b",
    r"\b(inventory\s+management\s+app|inventory\s+management\s+system)\b",
    r"\b(finance|financial)\s+dashboard\b",
    r"\btrading\s+app\b",
    r"\blive\s+market\b",
    r"\bmultiplayer\s+economy\b",
    r"\bresource\s+allocation\s+spreadsheet\b",
    r"\bspreadsheet\b",
    r"\b(data\s+table|erp)\b",
    r"\binventory\s+management\b(?!.{0,60}\bgame\b)",
    r"\bmanagement\s+app\b",
    r"\breal[-\s]?time\s+combat\b",
    r"\bcity\s+builder\b.{0,100}\bcombat\b",
    r"\bgeneric\s+dashboard\b",
) + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES

_HANGMAN_LITE_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(idle|incremental|clicker|tycoon)\b",
    r"\bcookie\s+clicker\b",
    r"\bpassive\s+income\b",
    r"\b(trivia|quiz)\b",
    r"\bmemory\s+(card|match)\b",
    r"\bbranching\s+story\b",
    r"\bchoose\s+your\s+own\s+adventure\b",
    r"\binteractive\s+fiction\b",
    r"\b(wordle|daily\s+word|wordle-style)\b",
    r"\bdaily\s+word\b.{0,100}\b(guess(ing)?|game|puzzle)\b",
    r"\bword\s+guess(ing)?\b.{0,100}\b(game|puzzle|challenge)\b",
    r"\b(green|yellow|gray|grey)\b.{0,120}\b(feedback|letter\s+feedback)\b",
    r"\bletter\s+feedback\b",
    r"\bduplicate-letter\b",
    r"\bcrossword\b",
    r"\bword\s+search\b",
    r"\bflashcard\b",
    r"\btyping\s+(speed|test|game)\b",
    r"\b(dashboard|landing\s*page|saas)\b",
    r"\b(nonogram|picross|sudoku|minesweeper)\b",
    r"\blogic\s+grid\s+puzzle\b",
    r"\bdaily\s+puzzle\s+grid\b",
    r"\bsurvey\b",
    r"\beducation\s+website\b",
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES

_HANGMAN_LITE_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bhangman(-style)?\b",
    r"\bhangman\b.{0,80}\b(word\s+game|game|letter)\b",
    r"\b(word\s+game|game)\b.{0,80}\bhangman\b",
    r"\bguess\s+letters?\b.{0,100}\b(hidden\s+word|reveal|word)\b",
    r"\b(hidden\s+word|word)\b.{0,100}\bguess\s+letters?\b",
    r"\bletter\s+guessing\b.{0,80}\b(word\s+game|game|hangman)\b",
    r"\bword\s+game\b.{0,80}\bletter\s+guessing\b",
    r"\bwrong\s+guesses?\b.{0,80}\bhangman\b",
    r"\bhangman\b.{0,80}\bwrong\s+guesses?\b",
    r"\bhangman\s+game\b",
    r"\bsimple\s+hangman\b",
    r"\bbuild\b.{0,40}\bhangman\b",
    r"\bmake\b.{0,40}\bhangman\b",
)

_RESOURCE_MANAGEMENT_SIM_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bresource\s+management\b.{0,80}\b(sim|simulation|game)\b",
    r"\b(sim|simulation|game)\b.{0,80}\bresource\s+management\b",
    r"\bcolony\s+management\b.{0,80}\bgame\b",
    r"\bgame\b.{0,80}\bcolony\s+management\b",
    r"\bfactory\b.{0,100}\bresource\s+allocation\b.{0,80}\bgame\b",
    r"\bresource\s+allocation\b.{0,80}\bgame\b",
    r"\bgame\b.{0,120}\b(manage|managing)\b.{0,80}\b(food|energy|workers?|wood|stone|resources?)\b",
    r"\b(manage|managing)\b.{0,80}\b(food|energy|workers?|wood|stone|resources?)\b.{0,80}\bgame\b",
    r"\bturn[-\s]?based\b.{0,80}\bresource\s+management\b",
    r"\bresource\s+management\b.{0,80}\bturn[-\s]?based\b",
    r"\bturn[-\s]?based\b.{0,80}\bresource\s+management\b.{0,80}\bgame\b",
    r"\bproduction\s+chain\b.{0,80}\b(sim|simulation|game)\b",
    r"\b(sim|simulation|game)\b.{0,80}\bproduction\s+chain\b",
    r"\bgame\b.{0,120}\b(resources?|capacity\s+limits?|upgrades?|goals?)\b",
    r"\b(resources?|capacity\s+limits?|upgrades?)\b.{0,120}\bgame\b",
    r"\bfarm\s+management\b.{0,80}\bsim\b",
    r"\btiny\s+farm\s+management\s+sim\b",
    r"\bsmall\b.{0,40}\bcolony\s+management\b.{0,80}\bgame\b",
)


def _normalized_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", str(prompt or "").strip().lower())


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _matches_recipe(text: str, *, negatives: tuple[str, ...], positives: tuple[str, ...]) -> bool:
    if _matches_any(text, negatives):
        return False
    return _matches_any(text, positives)


def _matches_trivia(text: str) -> bool:
    return _matches_recipe(text, negatives=_TRIVIA_NEGATIVE_PATTERNS, positives=_TRIVIA_POSITIVE_PATTERNS)


def _matches_idle(text: str) -> bool:
    return _matches_recipe(text, negatives=_IDLE_NEGATIVE_PATTERNS, positives=_IDLE_POSITIVE_PATTERNS)


def _matches_branching_narrative(text: str) -> bool:
    return _matches_recipe(
        text,
        negatives=_BRANCHING_NARRATIVE_NEGATIVE_PATTERNS,
        positives=_BRANCHING_NARRATIVE_POSITIVE_PATTERNS,
    )


def _matches_memory_match(text: str) -> bool:
    return _matches_recipe(
        text,
        negatives=_MEMORY_MATCH_NEGATIVE_PATTERNS,
        positives=_MEMORY_MATCH_POSITIVE_PATTERNS,
    )


def _matches_word_daily(text: str) -> bool:
    return _matches_recipe(
        text,
        negatives=_WORD_DAILY_NEGATIVE_PATTERNS,
        positives=_WORD_DAILY_POSITIVE_PATTERNS,
    )


def _matches_daily_puzzle_grid(text: str) -> bool:
    return _matches_recipe(
        text,
        negatives=_DAILY_PUZZLE_GRID_NEGATIVE_PATTERNS,
        positives=_DAILY_PUZZLE_GRID_POSITIVE_PATTERNS,
    )


def _matches_resource_management_sim(text: str) -> bool:
    return _matches_recipe(
        text,
        negatives=_RESOURCE_MANAGEMENT_SIM_NEGATIVE_PATTERNS,
        positives=_RESOURCE_MANAGEMENT_SIM_POSITIVE_PATTERNS,
    )


def _matches_hangman_lite(text: str) -> bool:
    return _matches_recipe(
        text,
        negatives=_HANGMAN_LITE_NEGATIVE_PATTERNS,
        positives=_HANGMAN_LITE_POSITIVE_PATTERNS,
    )


def select_registry_v2_app_type_for_prompt(prompt: str) -> str | None:
    """Return a Game Pack app type id for clear prompt matches, else ``None``."""
    text = _normalized_prompt(prompt)
    if not text:
        return None
    if _matches_any(text, _GLOBAL_NEGATIVE_PATTERNS):
        return None
    # Precedence: trivia → idle → branching narrative → memory match → word daily
    # → daily puzzle grid → resource management sim → hangman lite.
    if _matches_trivia(text):
        return TRIVIA_TIMER_APP_TYPE
    if _matches_idle(text):
        return IDLE_INCREMENTAL_APP_TYPE
    if _matches_branching_narrative(text):
        return BRANCHING_NARRATIVE_APP_TYPE
    if _matches_memory_match(text):
        return MEMORY_MATCH_APP_TYPE
    if _matches_word_daily(text):
        return WORD_DAILY_APP_TYPE
    if _matches_daily_puzzle_grid(text):
        return DAILY_PUZZLE_GRID_APP_TYPE
    if _matches_resource_management_sim(text):
        return RESOURCE_MANAGEMENT_SIM_APP_TYPE
    if _matches_hangman_lite(text):
        return HANGMAN_LITE_APP_TYPE
    return None


def enrich_plan_metadata_with_registry_v2(
    metadata: Mapping[str, Any],
    prompt: str,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Copy metadata and add ``registry_v2_app_type`` when flag + intent match."""
    from src.ham.build_registry.scaffold_context import build_registry_v2_enabled

    merged = dict(metadata)
    if not build_registry_v2_enabled(env):
        return merged
    app_type = select_registry_v2_app_type_for_prompt(prompt)
    if app_type:
        merged["registry_v2_app_type"] = app_type
    return merged
