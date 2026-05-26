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
TYPING_SPEED_RACER_APP_TYPE = "game.typing-speed-racer"
WORD_BUILDER_APP_TYPE = "game.word-builder"
CARD_DECK_TURN_BASED_APP_TYPE = "game.card-deck-turn-based"
REACTION_TIME_CHALLENGE_APP_TYPE = "game.reaction-time-challenge"
RHYTHM_TAP_LITE_APP_TYPE = "game.rhythm-tap-lite"
DECK_BUILDER_LITE_APP_TYPE = "game.deck-builder-lite"
TURN_BASED_TACTICS_LITE_APP_TYPE = "game.turn-based-tactics-lite"

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

_TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES: tuple[str, ...] = (
    r"\btyping\s+speed\b",
    r"\btyping\s+speed\s+racer\b",
    r"\btyping\s+speed\s+game\b",
    r"\bwpm\b.{0,80}\b(typing|accuracy|challenge|game|test)\b",
    r"\b(typing|accuracy|challenge|game|test)\b.{0,80}\bwpm\b",
    r"\bwords?\s+per\s+minute\b",
    r"\btyping\s+(challenge|test|game)\b.{0,100}\b(wpm|accuracy|mistakes?|timer|streaks?)\b",
    r"\b(wpm|accuracy|mistakes?|timer|streaks?)\b.{0,100}\btyping\s+(challenge|test|game)\b",
    r"\b\d+\s+second\b.{0,60}\btyping\b.{0,60}\b(test|game|challenge)\b",
    r"\btype\b.{0,60}\bprompts?\b.{0,100}\b(fast|quick|speed|possible)\b",
    r"\b(fast|quick|speed|possible)\b.{0,100}\btype\b.{0,60}\bprompts?\b",
    r"\bkeyboard\s+speed\b.{0,80}\b(game|challenge|test|timer)\b",
    r"\b(game|challenge|test)\b.{0,80}\bkeyboard\s+speed\b",
)

_WORD_BUILDER_CROSS_RECIPE_NEGATIVES: tuple[str, ...] = (
    r"\bword\s+build(er|ing)\b",
    r"\bword-building\b",
    r"\bspelling\s+challenge\b",
    r"\b(build|make|create)\b.{0,80}\bwords?\b.{0,80}\bfrom\b.{0,80}\b(set\s+of\s+)?letters?\b",
    r"\bwords?\b.{0,80}\bfrom\b.{0,80}\b(set\s+of\s+)?letters?\b",
    r"\bword\s+game\b.{0,100}\bletter\s+tiles?\b",
    r"\bletter\s+tiles?\b.{0,100}\bword\s+game\b",
    r"\bletter\s+pool\b.{0,80}\bword\b.{0,80}\b(puzzle|game|challenge)\b",
    r"\bword\b.{0,80}\bletter\s+pool\b",
    r"\barrange\b.{0,60}\bletters?\b.{0,80}\bword\s+slots?\b",
    r"\bword\s+slots?\b.{0,80}\barrange\b.{0,60}\bletters?\b",
    r"\bvalid\s+word\s+submissions?\b",
    r"\bword\s+game\b.{0,100}\bvalid\s+word\s+submissions?\b",
    r"\bduplicate\s+submissions?\b.{0,80}\b(score|twice|word)\b",
    r"\bword-building\b.{0,80}\b(hints?|levels?)\b",
    r"\b(hints?|levels?)\b.{0,80}\bword-building\b",
)

_CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES: tuple[str, ...] = (
    r"\bturn[- ]based\b.{0,80}\bcard\b.{0,80}\b(battle|game|duel)\b",
    r"\bcard\s+battle\b",
    r"\bcard\s+duel\b",
    r"\b(draw\s+pile|discard\s+pile)\b.{0,80}\b(hand|card)\b",
    r"\b(hand|card)\b.{0,80}\b(draw\s+pile|discard\s+pile)\b",
    r"\bplay\s+(a\s+)?card\b.{0,80}\b(turn|per\s+turn|hand|deck)\b",
    r"\bplays?\s+(a\s+)?card\b.{0,80}\b(turn|per\s+turn|hand|deck)\b",
    r"\bdraws?\s+cards?\b.{0,80}\bplay\b.{0,80}\b(turn|one\s+card)\b",
    r"\bdraws?\s+cards?\b.{0,80}\bplays?\b.{0,80}\b(one\s+card|turn)\b",
    r"\bcard\s+game\b.{0,100}\b(draw\s+pile|discard\s+pile|hand)\b",
    r"\b(draw\s+pile|discard\s+pile|hand)\b.{0,100}\bcard\s+game\b",
    r"\bsolitaire[- ]like\b.{0,80}\b(strategy\s+)?card\s+game\b",
    r"\bshuffle\b.{0,60}\bdeck\b.{0,80}\b(draw|hand|play)\b",
    r"\bcard\s+effects?\b.{0,80}\b(enemy|opponent|hp|health|damage)\b",
    r"\b(enemy|opponent)\b.{0,80}\bcard\b.{0,80}\b(battle|game|turn)\b",
    r"\bdefeat\b.{0,60}\b(enemy|opponent)\b.{0,80}\bcard\b",
)

_REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES: tuple[str, ...] = (
    r"\breaction[- ]time\b.{0,80}\b(game|test|challenge|click|tap|millisecond|ms)\b",
    r"\b(game|test|challenge)\b.{0,80}\breaction[- ]time\b",
    r"\b(false\s+start|too\s+early)\b.{0,80}\b(click|tap|reaction|reflex)\b",
    r"\bwait\s+for\s+(the\s+)?(screen\s+to\s+turn\s+green|signal|green)\b",
    r"\bpress\s+space\b.{0,80}\b(signal|when|appears)\b",
    r"\breflex\s+(challenge|test|game)\b.{0,80}\b(reaction|millisecond|ms|false\s+start)\b",
    r"\brandom\s+delay\b.{0,80}\b(click|tap|press|signal|reaction)\b",
    r"\bbest\s+reaction\s+time\b",
    r"\baverage\s+reaction\s+time\b",
)

_RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES: tuple[str, ...] = (
    r"\brhythm\s+tap\b.{0,80}\b(game|beat|timing|perfect|good|miss|combo|streak|cue)\b",
    r"\btap[- ]the[- ]beat\b.{0,80}\b(timing|window|score|streak|perfect|good|miss)\b",
    r"\b(beat|cue)s?\b.{0,80}\b(sequence|appear)\b.{0,80}\b(tap|press|click|timing)\b",
    r"\bpress\s+space\b.{0,80}\b(beat|cue|on\s+beat)\b",
    r"\btiming\s+window\b.{0,80}\b(perfect|good|miss|tap|beat)\b",
    r"\b(perfect|good|miss)\b.{0,60}\b(timing|window|score|tap|beat)\b",
    r"\bcombo\b.{0,80}\b(streak|tap|beat|timing|score)\b",
    r"\brhythm\s+(game|challenge)\b.{0,80}\b(beat|cue|tap|timing|combo|streak)\b",
)

_DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES: tuple[str, ...] = (
    r"\bdeck[- ]building\b.{0,80}\b(card|encounter|reward|battle|run)\b",
    r"\b(starter|small)\s+deck\b.{0,80}\b(reward|encounter|add\s+card)\b",
    r"\badd\s+cards?\s+to\s+(the\s+)?deck\b.{0,80}\b(reward|encounter|after|battle)\b",
    r"\broguelite\b.{0,80}\bdeck\b.{0,80}\b(card|reward|run)\b",
    r"\bcard\s+rewards?\b.{0,80}\b(after|encounter|battle|win|pick)\b",
    r"\bencounters?\b.{0,80}\b(reward|add\s+card|deck)\b",
    r"\bdeck[- ]building\b.{0,80}\bcard\s+game\b",
    r"\bdraw\b.{0,40}\bhand\b.{0,80}\b(reward|add\s+card|encounter)\b",
)

_TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES: tuple[str, ...] = (
    r"\bturn[- ]based\b.{0,100}\btactics\b.{0,100}\b(grid|units|battle)\b",
    r"\btactics\b.{0,100}\b(grid|units|enemies)\b.{0,100}\b(move|attack|turn)\b",
    r"\b(grid|tile)\b.{0,100}\b(units|enemies)\b.{0,100}\b(move|attack|turn)\b",
    r"\bselect\b.{0,60}\b(a\s+)?unit\b.{0,100}\b(move|attack)\b",
    r"\bmove\b.{0,60}\bunits?\b.{0,100}\b(attack|enemies)\b",
    r"\bplayer\s+turn\b.{0,100}\benemy\s+turn\b",
    r"\benemy\s+turn\b.{0,100}\bplayer\s+turn\b",
    r"\bmovement\s+range\b.{0,100}\b(attack\s+range|attack)\b",
    r"\battack\s+range\b.{0,100}\b(movement\s+range|move)\b",
    r"\bdefeat\s+all\s+enemies\b.{0,100}\b(grid|tactics|battle|units)\b",
    r"\btactical\s+battle\b.{0,100}\b(grid|units|turn)\b",
    r"\b(5x5|6x6|5\s*x\s*5|6\s*x\s*6)\b.{0,100}\b(grid|tactics|units|battle)\b",
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
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES

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
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES

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
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES

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
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES

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
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES

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
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES

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
) + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES

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
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES

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

_TYPING_SPEED_RACER_NEGATIVE_PATTERNS: tuple[str, ...] = (
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
    r"\bhangman(-style)?\b",
    r"\bhangman\b.{0,80}\b(game|word)\b",
    r"\bguess\s+letters?\b",
    r"\bletter\s+guessing\b",
    r"\bcrossword\b",
    r"\bword\s+search\b",
    r"\bflashcard\b",
    r"\bdictionary\b",
    r"\bwriting\s+app\b",
    r"\btext\s+editor\b",
    r"\btyping\s+tutor\b",
    r"\btyping\s+app\b(?!.{0,80}\b(speed|wpm|race|challenge|accuracy|mistakes?|timer|streaks?)\b)",
    r"\b(dashboard|landing\s*page|saas)\b",
    r"\b(nonogram|picross|sudoku|minesweeper)\b",
    r"\blogic\s+grid\s+puzzle\b",
    r"\bdaily\s+puzzle\s+grid\b",
    r"\bsurvey\b",
    r"\beducation\s+website\b",
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES

_TYPING_SPEED_RACER_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\btyping\s+speed\b.{0,80}\b(game|racer|challenge|test)\b",
    r"\b(game|racer|challenge|test)\b.{0,80}\btyping\s+speed\b",
    r"\btyping\s+speed\s+racer\b",
    r"\btyping\s+speed\s+game\b",
    r"\bwpm\b.{0,100}\b(typing|accuracy|challenge|game|test)\b",
    r"\b(typing|accuracy|challenge|game|test)\b.{0,100}\bwpm\b",
    r"\bwords?\s+per\s+minute\b",
    r"\btyping\s+(challenge|test|game)\b.{0,100}\b(wpm|accuracy|mistakes?|timer|streaks?)\b",
    r"\b(wpm|accuracy|mistakes?|timer|streaks?)\b.{0,100}\btyping\s+(challenge|test|game)\b",
    r"\btyping\s+game\b.{0,100}\b(accuracy|mistakes?)\b",
    r"\b(accuracy|mistakes?)\b.{0,100}\btyping\s+game\b",
    r"\b\d+\s+second\b.{0,60}\btyping\b.{0,60}\b(test|game|challenge)\b",
    r"\btype\b.{0,60}\bprompts?\b.{0,100}\b(fast|quick|speed|possible)\b",
    r"\b(fast|quick|speed|possible)\b.{0,100}\btype\b.{0,60}\bprompts?\b",
    r"\bkeyboard\s+speed\b.{0,80}\b(game|challenge|test|timer)\b",
    r"\b(game|challenge|test)\b.{0,80}\bkeyboard\s+speed\b",
    r"\btyping\b.{0,60}\b(race|racer)\b",
)

_WORD_BUILDER_NEGATIVE_PATTERNS: tuple[str, ...] = (
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
    r"\bhangman(-style)?\b",
    r"\bhangman\b.{0,80}\b(game|word)\b",
    r"\bguess\s+letters?\b",
    r"\bletter\s+guessing\b",
    r"\btyping\s+speed\b",
    r"\btyping\s+speed\s+(game|racer)\b",
    r"\bwpm\b",
    r"\bwords?\s+per\s+minute\b",
    r"\btyping\s+(challenge|test|game)\b.{0,100}\b(wpm|accuracy|mistakes?|timer)\b",
    r"\bcrossword\b",
    r"\bword\s+search\b",
    r"\bflashcard\b",
    r"\bdictionary\b",
    r"\bwriting\s+app\b",
    r"\btext\s+editor\b",
    r"\b(dashboard|landing\s*page|saas)\b",
    r"\b(nonogram|picross|sudoku|minesweeper)\b",
    r"\blogic\s+grid\s+puzzle\b",
    r"\bdaily\s+puzzle\s+grid\b",
    r"\bsurvey\b",
    r"\beducation\s+website\b",
    r"\bword\s+game\b(?!.{0,120}\b(letter\s+tiles?|letter\s+pool|word\s+slots?|build\s+words?|valid\s+word|arrange\s+letters?|duplicate\s+submissions?)\b)",
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES

_WORD_BUILDER_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bword\s+build(er|ing)\b.{0,80}\b(game|challenge|puzzle)\b",
    r"\b(game|challenge|puzzle)\b.{0,80}\bword\s+build(er|ing)\b",
    r"\bword\s+build(er|ing)\b",
    r"\bword-building\b",
    r"\bspelling\s+challenge\b.{0,80}\bgame\b",
    r"\bgame\b.{0,80}\bspelling\s+challenge\b",
    r"\bspelling\s+challenge\b",
    r"\b(build|make|create)\b.{0,80}\bwords?\b.{0,80}\bfrom\b.{0,80}\b(set\s+of\s+)?letters?\b",
    r"\bwords?\b.{0,80}\bfrom\b.{0,80}\b(set\s+of\s+)?letters?\b",
    r"\bword\s+game\b.{0,100}\bletter\s+tiles?\b",
    r"\bletter\s+tiles?\b.{0,100}\bword\s+game\b",
    r"\bletter\s+pool\b.{0,80}\bword\b.{0,80}\b(puzzle|game|challenge)\b",
    r"\bword\b.{0,80}\bletter\s+pool\b",
    r"\barrange\b.{0,60}\bletters?\b.{0,80}\bword\s+slots?\b",
    r"\bword\s+slots?\b.{0,80}\barrange\b.{0,60}\bletters?\b",
    r"\bvalid\s+word\s+submissions?\b",
    r"\bword\s+game\b.{0,100}\bvalid\s+word\s+submissions?\b",
    r"\bduplicate\s+submissions?\b.{0,80}\b(score|twice|word)\b",
    r"\bword-building\b.{0,80}\b(hints?|levels?)\b",
    r"\b(hints?|levels?)\b.{0,80}\bword-building\b",
)


_CARD_DECK_TURN_BASED_NEGATIVE_PATTERNS: tuple[str, ...] = (
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
    r"\bhangman(-style)?\b",
    r"\bhangman\b.{0,80}\b(game|word)\b",
    r"\bguess\s+letters?\b",
    r"\bletter\s+guessing\b",
    r"\btyping\s+speed\b",
    r"\btyping\s+speed\s+(game|racer)\b",
    r"\bwpm\b",
    r"\bwords?\s+per\s+minute\b",
    r"\btyping\s+(challenge|test|game)\b.{0,100}\b(wpm|accuracy|mistakes?|timer)\b",
    r"\bcrossword\b",
    r"\bword\s+search\b",
    r"\bword\s+build(er|ing)\b",
    r"\bword-building\b",
    r"\bspelling\s+challenge\b",
    r"\bletter\s+pool\b",
    r"\bletter\s+tiles?\b",
    r"\b(nonogram|picross|sudoku|minesweeper)\b",
    r"\blogic\s+grid\s+puzzle\b",
    r"\bdaily\s+puzzle\s+grid\b",
    r"\bresource\s+management\b",
    r"\b(poker|blackjack|casino|betting|wagering|gambling|roulette|slots)\b",
    r"\b(chips|odds)\b.{0,80}\b(bet|wager|casino|poker|blackjack)\b",
    r"\b(bet|wager)\b.{0,80}\b(chips|odds|casino|poker|blackjack)\b",
    r"\bnft\b",
    r"\b(trading\s+card|collectible\s+card)\s+marketplace\b",
    r"\bcard\s+marketplace\b",
    r"\bcard\s+auction\b",
    r"\b(buy|sell|trade|auction)\b.{0,80}\b(cards?|collectibles?)\b",
    r"\bflashcard\b",
    r"\bspaced\s+repetition\b",
    r"\bstudy\s+deck\b",
    r"\bpitch\s+deck\b",
    r"\bslide\s+deck\b",
    r"\binvestor\s+deck\b",
    r"\bpresentation\s+deck\b",
    r"\b(dashboard|kanban)\b.{0,80}\b(cards?|card\s+layout)\b",
    r"\b(cards?|card\s+layout)\b.{0,80}\b(dashboard|kanban)\b",
    r"\bpricing\s+cards?\b",
    r"\bprofile\s+cards?\b",
    r"\bcredit\s+card\b",
    r"\bbusiness\s+card\b",
    r"\bcard\s+deck\s+app\b",
    r"\bdeck\s+builder\b",
    r"\bbuild\s+a\s+card\s+app\b",
    r"\bdeck[- ]building\b",
    r"\badd\s+cards?\s+to\s+(the\s+)?deck\b",
    r"\bcard\s+rewards?\b.{0,80}\b(after|encounter|battle|win|pick)\b",
    r"\broguelite\b.{0,80}\bdeck\b",
    r"\bstarter\s+deck\b.{0,80}\b(reward|encounter|add\s+card)\b",
    r"\bencounters?\b.{0,80}\b(reward|add\s+card|pick)\b",
    r"\bchoose\b.{0,40}\b(reward|card)\b.{0,80}\b(add|deck)\b",
    r"\bflip\s+pairs?\b",
    r"\bmatch\s+pairs?\b.{0,80}\bcards?\b",
    r"\bconcentration\b.{0,80}\bcard\b",
    r"\bcard\s+matching\b",
    r"\bsurvey\b",
    r"\beducation\s+website\b",
    r"\b(dashboard|landing\s*page|saas)\b",
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES

_CARD_DECK_TURN_BASED_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bturn[- ]based\b.{0,80}\bcard\b.{0,80}\b(battle|game|duel)\b",
    r"\bcard\s+(battle|duel)\b.{0,80}\b(turn|turn-based|hp|health|enemy)\b",
    r"\b(draw\s+pile|discard\s+pile)\b.{0,80}\b(hand|card)\b",
    r"\b(hand|card)\b.{0,80}\b(draw\s+pile|discard\s+pile)\b",
    r"\bplay\s+(a\s+)?card\b.{0,80}\b(turn|per\s+turn|hand|deck)\b",
    r"\bplays?\s+(a\s+)?card\b.{0,80}\b(turn|per\s+turn|hand|deck)\b",
    r"\bdraws?\s+cards?\b.{0,80}\bplay\b.{0,80}\b(turn|one\s+card)\b",
    r"\bdraws?\s+cards?\b.{0,80}\bplays?\b.{0,80}\b(one\s+card|turn)\b",
    r"\bcard\s+game\b.{0,100}\b(draw\s+pile|discard\s+pile|hand)\b",
    r"\b(draw\s+pile|discard\s+pile|hand)\b.{0,100}\bcard\s+game\b",
    r"\bsolitaire[- ]like\b.{0,80}\b(strategy\s+)?card\s+game\b.{0,80}\b(deck|hand|discard|score)\b",
    r"\bshuffle\b.{0,60}\bdeck\b.{0,80}\b(draw|hand|play)\b",
    r"\bcard\s+effects?\b.{0,80}\b(enemy|opponent|hp|health|damage|heal)\b",
    r"\b(enemy|opponent)\b.{0,80}\bcard\b.{0,80}\b(battle|game|turn)\b",
    r"\bdefeat\b.{0,60}\b(enemy|opponent)\b.{0,80}\bcard\b",
    r"\bplay\s+one\s+card\s+per\s+turn\b",
    r"\btrack\s+victory\b.{0,80}\b(card|deck|hand|battle)\b",
)

_REACTION_TIME_CHALLENGE_NEGATIVE_PATTERNS: tuple[str, ...] = (
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
    r"\bhangman(-style)?\b",
    r"\bhangman\b.{0,80}\b(game|word)\b",
    r"\bguess\s+letters?\b",
    r"\bletter\s+guessing\b",
    r"\btyping\s+speed\b",
    r"\btyping\s+speed\s+(game|racer)\b",
    r"\bwpm\b",
    r"\bwords?\s+per\s+minute\b",
    r"\btyping\s+(challenge|test|game|race)\b",
    r"\bword\s+build(er|ing)\b",
    r"\bword-building\b",
    r"\bspelling\s+challenge\b",
    r"\bturn[- ]based\b.{0,80}\bcard\b",
    r"\bcard\s+battle\b",
    r"\b(draw\s+pile|discard\s+pile)\b",
    r"\bplay\s+(a\s+)?card\b",
    r"\b(nonogram|picross|sudoku|minesweeper)\b",
    r"\blogic\s+grid\s+puzzle\b",
    r"\bdaily\s+puzzle\s+grid\b",
    r"\bresource\s+management\b",
    r"\bpomodoro\b",
    r"\bstopwatch\b",
    r"\bstopwatch\s+app\b",
    r"\bproductivity\s+timer\b",
    r"\bcountdown\s+timer\s+app\b",
    r"\bfocus\s+timer\b",
    r"\b(rhythm|music)\s+tap\b",
    r"\brhythm\s+game\b",
    r"\bmusic\s+rhythm\b",
    r"\btap\s+to\s+the\s+beat\b",
    r"\bmedical\b.{0,80}\b(reflex|reaction)\b",
    r"\bclinical\b.{0,80}\b(reaction|reflex|assessment)\b",
    r"\breflex\s+test\b.{0,80}\b(medical|clinical|diagnos)\b",
    r"\baccessibility\b.{0,80}\b(reaction|assessment)\b",
    r"\bdashboard\b.{0,80}\b(response\s+time|reaction)\b",
    r"\banalytics\b.{0,80}\b(response\s+time|reaction)\b",
    r"\bresponse\s+time\b.{0,80}\b(dashboard|analytics)\b",
    r"\bphysics\b.{0,80}\b(collision|game)\b",
    r"\bcollision\b.{0,80}\b(physics|game)\b",
    r"\b(gambling|betting|wagering|casino)\b.{0,80}\b(reaction|reflex)\b",
    r"\b(reaction|reflex)\b.{0,80}\b(bet|wager|gambling)\b",
    r"\bsurvey\b",
    r"\beducation\s+website\b",
    r"\b(dashboard|landing\s*page|saas)\b",
) + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES

_REACTION_TIME_CHALLENGE_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\breaction[- ]time\b.{0,100}\b(game|click|tap|test|challenge|millisecond|ms|false\s+start)\b",
    r"\b(game|click|tap|test|challenge)\b.{0,100}\breaction[- ]time\b",
    r"\bwait\b.{0,80}\b(for\s+)?(screen\s+to\s+turn\s+green|signal|go)\b.{0,100}\b(click|tap|fast|reaction)\b",
    r"\b(screen\s+to\s+turn\s+green|turn\s+green)\b.{0,100}\b(click|tap|fast|reaction)\b",
    r"\bfalse\s+start\b.{0,100}\b(too\s+early|click|tap|retry|reaction|reflex)\b",
    r"\b(too\s+early|click(ed)?\s+too\s+early)\b.{0,100}\b(false\s+start|reaction|reflex)\b",
    r"\bpress\s+space\b.{0,100}\b(signal|appears|when)\b.{0,100}\b(reaction|millisecond|ms|feedback)\b",
    r"\bpress(es)?\s+space\b.{0,100}\b(signal|appears|when)\b",
    r"\breflex\s+(challenge|test|game)\b.{0,100}\b(false\s+start|reaction|millisecond|ms|retry)\b",
    r"\breaction\s+test\b.{0,80}\bgame\b.{0,100}\b(signal|millisecond|ms|press|space)\b",
    r"\breaction[- ]speed\b.{0,80}\bgame\b.{0,100}\b(random\s+delay|play\s+again|best\s+score)\b",
    r"\brandom\s+delay\b.{0,100}\b(click|tap|press|signal|reaction)\b",
    r"\b(click|tap|press)\b.{0,100}\brandom\s+delay\b.{0,100}\b(reaction|signal|reflex)\b",
    r"\bbest\s+reaction\s+time\b",
    r"\baverage\s+reaction\s+time\b",
    r"\breaction\s+speed\b.{0,80}\b(game|challenge|test|millisecond|ms|delay)\b",
    r"\bplay\s+again\b.{0,80}\b(reaction|reflex|retry)\b",
    r"\bretry\b.{0,80}\b(reaction|reflex|false\s+start|better\s+score)\b",
    r"\bmeasure\b.{0,60}\b(reaction|response)\s+time\b.{0,60}\b(millisecond|ms)\b",
    r"\bget\s+millisecond\b.{0,80}\b(reaction|feedback)\b",
)

_RHYTHM_TAP_LITE_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(idle|incremental|clicker|tycoon)\b",
    r"\bcookie\s+clicker\b",
    r"\bpassive\s+income\b",
    r"\b(trivia|quiz)\b",
    r"\bmemory\s+(card|match)\b",
    r"\bbranching\s+story\b",
    r"\bchoose\s+your\s+own\s+adventure\b",
    r"\b(wordle|daily\s+word|wordle-style)\b",
    r"\bdaily\s+word\b.{0,100}\b(guess(ing)?|game|puzzle)\b",
    r"\bword\s+guess(ing)?\b.{0,100}\b(game|puzzle|challenge)\b",
    r"\bhangman(-style)?\b",
    r"\bhangman\b.{0,80}\b(game|word)\b",
    r"\bguess\s+letters?\b",
    r"\bletter\s+guessing\b",
    r"\btyping\s+speed\b",
    r"\btyping\s+speed\s+(game|racer)\b",
    r"\bwpm\b",
    r"\bwords?\s+per\s+minute\b",
    r"\btyping\s+(challenge|test|game|race)\b",
    r"\bword\s+build(er|ing)\b",
    r"\bword-building\b",
    r"\bspelling\s+challenge\b",
    r"\bturn[- ]based\b.{0,80}\bcard\b",
    r"\bcard\s+battle\b",
    r"\b(draw\s+pile|discard\s+pile)\b",
    r"\bplay\s+(a\s+)?card\b",
    r"\b(nonogram|picross|sudoku|minesweeper)\b",
    r"\blogic\s+grid\s+puzzle\b",
    r"\bdaily\s+puzzle\s+grid\b",
    r"\bresource\s+management\b",
    r"\breaction[- ]time\b",
    r"\b(false\s+start|too\s+early)\b.{0,80}\b(click|tap|reaction|reflex)\b",
    r"\bwait\s+for\s+(the\s+)?(screen\s+to\s+turn\s+green|signal|green)\b",
    r"\b(screen\s+to\s+turn\s+green|turn\s+green)\b",
    r"\breflex\s+(challenge|test|game)\b.{0,80}\b(reaction|millisecond|ms|false\s+start)\b",
    r"\brandom\s+delay\b.{0,80}\b(click|tap|reaction)\b",
    r"\bbest\s+reaction\s+time\b",
    r"\bpomodoro\b",
    r"\bstopwatch\b",
    r"\bstopwatch\s+app\b",
    r"\bproductivity\s+timer\b",
    r"\bcountdown\s+timer\s+app\b",
    r"\bfocus\s+timer\b",
    r"\bmetronome\b",
    r"\bmusic\s+player\b",
    r"\bkaraoke\b",
    r"\blyric\s+game\b",
    r"\bmedical\b.{0,80}\b(rhythm|reflex|reaction|assessment)\b",
    r"\bclinical\b.{0,80}\b(rhythm|reaction|reflex|assessment)\b",
    r"\baccessibility\b.{0,80}\b(rhythm|reaction|assessment)\b",
    r"\bdashboard\b.{0,80}\b(music|analytics|rhythm)\b",
    r"\banalytics\b.{0,80}\b(music|rhythm)\b",
    r"\bmusic\b.{0,80}\b(dashboard|analytics)\b",
    r"\bphysics\b.{0,80}\b(collision|game)\b",
    r"\bcollision\b.{0,80}\b(physics|game)\b",
    r"\b(gambling|betting|wagering|casino)\b.{0,80}\b(rhythm|music|tap)\b",
    r"\b(rhythm|music|tap)\b.{0,80}\b(bet|wager|gambling)\b",
    r"\bsurvey\b",
    r"\beducation\s+website\b",
    r"\b(dashboard|landing\s*page|saas)\b",
) + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES

_RHYTHM_TAP_LITE_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\brhythm\s+tap\b.{0,100}\b(game|beat|timing|perfect|good|miss|combo|streak|cue)\b",
    r"\btap[- ]the[- ]beat\b.{0,100}\b(timing|window|score|streak|perfect|good|miss)\b",
    r"\b(beat|cue)s?\b.{0,80}\b(sequence|appear)\b.{0,100}\b(tap|press|click|timing)\b",
    r"\bpress\s+space\b.{0,100}\b(beat|cue|on\s+beat)\b.{0,100}\b(perfect|good|miss|timing|right\s+time)\b",
    r"\bpress\s+space\b.{0,80}\b(beat|cue|on\s+beat)\b",
    r"\btiming\s+window\b.{0,100}\b(perfect|good|miss)\b",
    r"\b(perfect|good|miss)\b.{0,80}\b(timing|window|score|tap|beat)\b",
    r"\bcombo\b.{0,80}\b(streak|score)\b.{0,80}\b(tap|beat|timing|rhythm)\b",
    r"\brhythm\s+(game|challenge)\b.{0,100}\b(beat|cue|tap|timing|combo|streak|result)\b",
    r"\bdom\b.{0,40}\brhythm\b.{0,80}\b(beat|cue|tap|timing)\b",
    r"\bcircles?\s+appear\b.{0,80}\b(beat|cue)\b.{0,100}\b(press|tap|space)\b",
    r"\bbeat\s+prompts?\b.{0,80}\b(tap|timing|combo|score)\b",
    r"\bplay\s+again\b.{0,80}\b(rhythm|beat|tap|score|result)\b",
)

_DECK_BUILDER_LITE_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(idle|incremental|clicker|tycoon)\b",
    r"\bcookie\s+clicker\b",
    r"\bpassive\s+income\b",
    r"\b(trivia|quiz)\b",
    r"\bmemory\s+(card|match)\b",
    r"\bbranching\s+story\b",
    r"\bchoose\s+your\s+own\s+adventure\b",
    r"\b(wordle|daily\s+word|wordle-style)\b",
    r"\bword\s+guess(ing)?\b",
    r"\bhangman(-style)?\b",
    r"\btyping\s+speed\b",
    r"\bwpm\b",
    r"\bword\s+build(er|ing)\b",
    r"\bturn[- ]based\b.{0,80}\bcard\b.{0,80}\b(battle|game|duel|turn)\b",
    r"\bcard\s+battle\b.{0,80}\b(turn|per\s+turn)\b",
    r"\bplay\s+one\s+card\s+per\s+turn\b",
    r"\breaction[- ]time\b",
    r"\b(false\s+start|too\s+early)\b",
    r"\brhythm\s+tap\b",
    r"\btap[- ]the[- ]beat\b",
    r"\b(nonogram|picross|sudoku|minesweeper)\b",
    r"\blogic\s+grid\s+puzzle\b",
    r"\bdaily\s+puzzle\s+grid\b",
    r"\bresource\s+management\b",
    r"\b(poker|blackjack|casino|betting|wagering|gambling|roulette|slots)\b",
    r"\b(chips|odds)\b.{0,80}\b(bet|wager|casino|poker|blackjack)\b",
    r"\bnft\b",
    r"\b(trading\s+card|collectible\s+card)\s+marketplace\b",
    r"\bcard\s+marketplace\b",
    r"\bcard\s+auction\b",
    r"\b(buy|sell|trade|auction)\b.{0,80}\b(cards?|collectibles?)\b",
    r"\bflashcard\b",
    r"\bspaced\s+repetition\b",
    r"\bstudy\s+deck\b",
    r"\bpitch\s+deck\b",
    r"\bslide\s+deck\b",
    r"\binvestor\s+deck\b",
    r"\bpresentation\s+deck\b",
    r"\b(dashboard|kanban)\b.{0,80}\b(cards?|card\s+layout)\b",
    r"\b(cards?|card\s+layout)\b.{0,80}\b(dashboard|kanban)\b",
    r"\bpricing\s+cards?\b",
    r"\bprofile\s+cards?\b",
    r"\bcredit\s+card\b",
    r"\bbusiness\s+card\b",
    r"\bconstruction\s+planning\s+deck\b",
    r"\bproject\s+planning\s+deck\b",
    r"\bmusic\s+deck\b",
    r"\baudio\s+deck\b",
    r"\bflip\s+pairs?\b",
    r"\bmatch\s+pairs?\b.{0,80}\bcards?\b",
    r"\bconcentration\b.{0,80}\bcard\b",
    r"\bcard\s+matching\b",
    r"\bsurvey\b",
    r"\beducation\s+website\b",
    r"\b(dashboard|landing\s*page|saas)\b",
    r"^build a deck builder$",
    r"^build a deck$",
    r"^build a deck app$",
    r"^build a card deck$",
    r"^build a card app$",
    r"^build something with cards$",
    r"^card rewards$",
    r"^card collection$",
) + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES

_DECK_BUILDER_LITE_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bdeck[- ]building\b.{0,100}\b(card|encounter|reward|battle|run)\b",
    r"\b(card|encounter|reward|battle|run)\b.{0,100}\bdeck[- ]building\b",
    r"\b(starter|small)\s+deck\b.{0,100}\b(reward|encounter|add\s+card|battle)\b",
    r"\badd\s+cards?\s+to\s+(the\s+)?deck\b.{0,100}\b(reward|encounter|after|battle|win)\b",
    r"\broguelite\b.{0,100}\bdeck\b.{0,100}\b(card|reward|run|battle)\b",
    r"\bdraw\b.{0,60}\bhand\b.{0,100}\b(play|discard|reward|encounter|enemy)\b",
    r"\bplay\s+cards?\b.{0,100}\b(enemy|encounter|reward|discard|deck)\b",
    r"\bencounters?\b.{0,100}\b(reward|add\s+card|deck|win)\b",
    r"\bchoose\b.{0,60}\b(reward|card)\b.{0,100}\b(add|deck|improve)\b",
    r"\bdeck[- ]mutation\b",
    r"\b(remove|upgrade)\b.{0,60}\bcards?\b.{0,80}\b(deck|encounter|between)\b",
    r"\brun\s+result\b.{0,80}\b(deck|card|encounter)\b",
    r"\bdeck[- ]building\b.{0,100}\bcard\s+game\b",
)

_TURN_BASED_TACTICS_LITE_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(idle|incremental|clicker|tycoon)\b",
    r"\bcookie\s+clicker\b",
    r"\bpassive\s+income\b",
    r"\b(trivia|quiz)\b",
    r"\bmemory\s+(card|match)\b",
    r"\bbranching\s+story\b",
    r"\bchoose\s+your\s+own\s+adventure\b",
    r"\b(wordle|daily\s+word|wordle-style)\b",
    r"\bword\s+guess(ing)?\b",
    r"\bhangman(-style)?\b",
    r"\btyping\s+speed\b",
    r"\bwpm\b",
    r"\bword\s+build(er|ing)\b",
    r"\breaction[- ]time\b",
    r"\brhythm\s+tap\b",
    r"\btap[- ]the[- ]beat\b",
    r"\b(nonogram|picross|sudoku|minesweeper)\b",
    r"\blogic\s+grid\s+puzzle\b",
    r"\bdaily\s+puzzle\s+grid\b",
    r"\bfill\s+cells\b.{0,80}\b(clue|row|column|constraint)\b",
    r"\bchess\b",
    r"\bcheckers\b",
    r"\bgo\b",
    r"\bcity\s+builder\b",
    r"\bresource\s+management\b",
    r"\bturn[-\s]?based\b.{0,80}\bresource\s+management\b",
    r"\btower\s+defense\b",
    r"\breal[- ]time\s+strategy\b",
    r"\brts\b",
    r"\brpg\s+campaign\b",
    r"\bstory\s+battle\b",
    r"\bmap\s+editor\b",
    r"\blevel\s+editor\b",
    r"\bphysics\b.{0,80}\b(combat|collision|game)\b",
    r"\bcollision\b.{0,80}\b(combat|physics|game)\b",
    r"\bmultiplayer\b.{0,80}\btactics\b",
    r"\bonline\s+pvp\b",
    r"\bturn[- ]based\b.{0,80}\bcard\b",
    r"\bcard\s+battle\b",
    r"\b(draw\s+pile|discard\s+pile)\b",
    r"\bplay\s+(a\s+)?card\b",
    r"\bdeck[- ]building\b",
    r"\bdeck\s+builder\b",
    r"\badd\s+cards?\s+to\s+(the\s+)?deck\b",
    r"\bdashboard\s+grid\b",
    r"\b(dashboard|data\s+table|spreadsheet)\b",
    r"\bsurvey\b",
    r"\beducation\s+website\b",
    r"\b(dashboard|landing\s*page|saas)\b",
    r"^tactics$",
    r"^strategy$",
    r"^grid$",
    r"^units$",
    r"^enemies$",
    r"^battle$",
    r"^turns$",
    r"^move$",
    r"^attack$",
    r"^board game$",
) + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES

_TURN_BASED_TACTICS_LITE_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bturn[- ]based\b.{0,100}\btactics\b.{0,100}\b(grid|units|battle)\b",
    r"\btactics\b.{0,100}\b(grid|units|enemies?)\b.{0,100}\b(mov(e|ing|ement)|attack(ing)?|turn(s)?)\b",
    r"\b(grid|tile)\b.{0,100}\b(units?|enemies?)\b.{0,100}\b(mov(e|ing|ement)|attack(ing)?|turn(s)?)\b",
    r"\bselect(ing)?\b.{0,60}\b(a\s+)?unit\b.{0,100}\b(mov(e|ing|ement)|attack(ing)?)\b",
    r"\bmove\b.{0,60}\bunits?\b.{0,100}\b(attack(ing)?|enemies?)\b",
    r"\bplayer\s+turn\b.{0,100}\benemy\s+turn\b",
    r"\benemy\s+turn\b.{0,100}\bplayer\s+turn\b",
    r"\bmovement\s+range\b.{0,100}\b(attack\s+range|attack)\b",
    r"\battack\s+range\b.{0,100}\b(movement\s+range|move)\b",
    r"\bdefeat\s+all\s+enemies\b.{0,100}\b(grid|tactics|battle|units)\b",
    r"\btactical\s+battle\b.{0,100}\b(grid|units|turn)\b",
    r"\b(5x5|6x6|5\s*x\s*5|6\s*x\s*6)\b.{0,100}\b(grid|tactics|units|battle)\b",
    r"\bhealth\s+bars?\b.{0,100}\b(units?|enemies?|grid|tactics|restart|battle)\b",
    r"\b(units?|enemies?)\b.{0,100}\b(turn(s)?|mov(e|ing)|attack(ing)?)\b.{0,100}\b(win|battle|tactics)\b",
    r"\btactics\b.{0,100}\b(battle|grid)\b.{0,100}\b(units?|enemies?|player)\b.{0,100}\b(turn(s)?|mov(e|ing)|attack(ing)?)\b",
    r"\b(player|enemy)\s+units?\b.{0,100}\btake\s+turns\b.{0,100}\bgrid\b",
    r"\brestart\s+battle\b.{0,100}\b(grid|units?|tactics|health)\b",
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


def _matches_typing_speed_racer(text: str) -> bool:
    return _matches_recipe(
        text,
        negatives=_TYPING_SPEED_RACER_NEGATIVE_PATTERNS,
        positives=_TYPING_SPEED_RACER_POSITIVE_PATTERNS,
    )


def _matches_word_builder(text: str) -> bool:
    return _matches_recipe(
        text,
        negatives=_WORD_BUILDER_NEGATIVE_PATTERNS,
        positives=_WORD_BUILDER_POSITIVE_PATTERNS,
    )


def _matches_card_deck_turn_based(text: str) -> bool:
    return _matches_recipe(
        text,
        negatives=_CARD_DECK_TURN_BASED_NEGATIVE_PATTERNS,
        positives=_CARD_DECK_TURN_BASED_POSITIVE_PATTERNS,
    )


def _matches_reaction_time_challenge(text: str) -> bool:
    return _matches_recipe(
        text,
        negatives=_REACTION_TIME_CHALLENGE_NEGATIVE_PATTERNS,
        positives=_REACTION_TIME_CHALLENGE_POSITIVE_PATTERNS,
    )


def _matches_rhythm_tap_lite(text: str) -> bool:
    return _matches_recipe(
        text,
        negatives=_RHYTHM_TAP_LITE_NEGATIVE_PATTERNS,
        positives=_RHYTHM_TAP_LITE_POSITIVE_PATTERNS,
    )


def _matches_deck_builder_lite(text: str) -> bool:
    return _matches_recipe(
        text,
        negatives=_DECK_BUILDER_LITE_NEGATIVE_PATTERNS,
        positives=_DECK_BUILDER_LITE_POSITIVE_PATTERNS,
    )


def _matches_turn_based_tactics_lite(text: str) -> bool:
    return _matches_recipe(
        text,
        negatives=_TURN_BASED_TACTICS_LITE_NEGATIVE_PATTERNS,
        positives=_TURN_BASED_TACTICS_LITE_POSITIVE_PATTERNS,
    )


def select_registry_v2_app_type_for_prompt(prompt: str) -> str | None:
    """Return a Game Pack app type id for clear prompt matches, else ``None``."""
    text = _normalized_prompt(prompt)
    if not text:
        return None
    if _matches_any(text, _GLOBAL_NEGATIVE_PATTERNS):
        return None
    # Precedence: trivia → idle → branching narrative → memory match → word daily
    # → daily puzzle grid → resource management sim → hangman lite → typing speed racer
    # → word builder → card deck turn-based → reaction time challenge → rhythm tap lite
    # → deck builder lite → turn-based tactics lite.
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
    if _matches_typing_speed_racer(text):
        return TYPING_SPEED_RACER_APP_TYPE
    if _matches_word_builder(text):
        return WORD_BUILDER_APP_TYPE
    if _matches_card_deck_turn_based(text):
        return CARD_DECK_TURN_BASED_APP_TYPE
    if _matches_reaction_time_challenge(text):
        return REACTION_TIME_CHALLENGE_APP_TYPE
    if _matches_rhythm_tap_lite(text):
        return RHYTHM_TAP_LITE_APP_TYPE
    if _matches_deck_builder_lite(text):
        return DECK_BUILDER_LITE_APP_TYPE
    if _matches_turn_based_tactics_lite(text):
        return TURN_BASED_TACTICS_LITE_APP_TYPE
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
