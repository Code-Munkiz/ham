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
CITY_BUILDER_LITE_APP_TYPE = "game.city-builder-lite"
LANDING_PAGE_CORE_APP_TYPE = "site.landing-page-core"
DASHBOARD_UI_CORE_APP_TYPE = "site.dashboard-ui-core"
SAAS_DASHBOARD_CORE_APP_TYPE = "app.saas-dashboard-core"
ADMIN_DASHBOARD_CORE_APP_TYPE = "app.admin-dashboard-core"
SALES_OPS_DASHBOARD_CORE_APP_TYPE = "app.sales-ops-dashboard-core"

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

_CITY_BUILDER_LITE_CROSS_RECIPE_NEGATIVES: tuple[str, ...] = (
    r"\bcity[- ]build(ing|er)\b.{0,120}\b(grid|buildings|houses|farms|place|day|turn|production|population|goal)\b",
    r"\b(browser|local|dom|small|tiny)\b.{0,60}\bcity\b.{0,120}\b(grid|building|place|day|resource|population|happiness)\b",
    r"\bplace\b.{0,60}\b(buildings|houses|farms|wells?)\b.{0,120}\b(grid|city|small\s+grid)\b",
    r"\bbuilding\s+palette\b.{0,120}\b(grid|place|day|resource|production|goal|restart)\b",
    r"\b(5x5|6x6|5\s*x\s*5|6\s*x\s*6)\b.{0,120}\b(grid|city|building|houses|farms)\b",
    r"\b(end\s+day|advance\s+days?)\b.{0,120}\b(production|resources?|building|grid|city|population|happiness)\b",
    r"\bbuildings?\b.{0,80}\bproduce\b.{0,120}\b(resources?|food|coins?|turn|day|each\s+turn|each\s+day)\b",
    r"\bpopulation\s+(goal|growth|happiness)\b.{0,120}\b(city|grid|building|day|goal)\b",
    r"\b(new\s+city|restart)\b.{0,120}\b(grid|resources?|buildings?|day|city\s+goal)\b",
)

_GLOBAL_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(calculator|todo|to[-\s]?do|crm)\b",
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
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES + _CITY_BUILDER_LITE_CROSS_RECIPE_NEGATIVES

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
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES + _CITY_BUILDER_LITE_CROSS_RECIPE_NEGATIVES

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
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES + _CITY_BUILDER_LITE_CROSS_RECIPE_NEGATIVES

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
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES + _CITY_BUILDER_LITE_CROSS_RECIPE_NEGATIVES

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
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES + _CITY_BUILDER_LITE_CROSS_RECIPE_NEGATIVES

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
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES + _CITY_BUILDER_LITE_CROSS_RECIPE_NEGATIVES

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
) + _HANGMAN_LITE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES + _CITY_BUILDER_LITE_CROSS_RECIPE_NEGATIVES

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
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES + _CITY_BUILDER_LITE_CROSS_RECIPE_NEGATIVES

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
) + _RESOURCE_MGMT_CROSS_RECIPE_NEGATIVES + _WORD_BUILDER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES + _CITY_BUILDER_LITE_CROSS_RECIPE_NEGATIVES

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
) + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _TURN_BASED_TACTICS_LITE_CROSS_RECIPE_NEGATIVES + _CITY_BUILDER_LITE_CROSS_RECIPE_NEGATIVES

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
    r"\bcity[- ]build(ing|er)\b",
    r"\bbuilding\s+palette\b",
    r"\bplace\b.{0,60}\b(buildings|houses|farms|wells?|power)\b",
    r"\bend\s+day\b",
    r"\bpopulation\s+(goal|happiness|growth)\b",
    r"\b(new\s+city|restart)\b.{0,80}\b(city|grid|resources?|buildings?)\b",
    r"\bbuildings?\b.{0,80}\bproduce\b.{0,80}\b(resources?|food|coins?)\b",
    r"\bresource\s+counters?\b",
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

_CITY_BUILDER_LITE_NEGATIVE_PATTERNS: tuple[str, ...] = (
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
    r"\bturn[- ]based\b.{0,80}\bcard\b",
    r"\bcard\s+battle\b",
    r"\b(draw\s+pile|discard\s+pile)\b",
    r"\bplay\s+(a\s+)?card\b",
    r"\bdeck[- ]building\b",
    r"\b(nonogram|picross|sudoku|minesweeper)\b",
    r"\blogic\s+grid\s+puzzle\b",
    r"\bdaily\s+puzzle\s+grid\b",
    r"\bfill\s+cells\b.{0,80}\b(clue|row|column|constraint)\b",
    r"\bturn[- ]based\b.{0,100}\btactics\b",
    r"\btactics\b.{0,100}\b(units|enemies|move|attack)\b",
    r"\bselect\b.{0,60}\b(a\s+)?unit\b",
    r"\bdefeat\s+all\s+enemies\b",
    r"\bresource\s+analytics\b",
    r"\b(dashboard|analytics)\b.{0,80}\bresource\b",
    r"\bresource\b.{0,80}\b(dashboard|analytics|spreadsheet)\b",
    r"\bresource\s+management\b.{0,120}\b(sim|simulation|game)\b(?!.{0,120}\b(place|placing|building\s+palette|houses|farms|grid)\b)",
    r"\bturn[-\s]?based\b.{0,80}\bresource\s+management\b",
    r"\bcolony\s+management\b",
    r"\bproduction\s+chain\b",
    r"\bfactory\s+automation\b",
    r"\bbelt(s)?\b.{0,80}\b(logistics|automation|factory)\b",
    r"\btower\s+defense\b",
    r"\breal[- ]time\s+strategy\b",
    r"\brts\b",
    r"\bcity\s+planning\b.{0,80}\b(spreadsheet|dashboard|tool)\b",
    r"\burban\s+planning\b.{0,80}\b(dashboard|tool|spreadsheet)\b",
    r"\breal\s+estate\b.{0,80}\b(dashboard|tool|app)\b",
    r"\bfinance\b.{0,80}\bdashboard\b",
    r"\bfinancial\b.{0,80}\bdashboard\b",
    r"\bmap\s+editor\b",
    r"\blevel\s+editor\b",
    r"\bmultiplayer\b.{0,80}\bcity\b",
    r"\bonline\b.{0,80}\bcity\b",
    r"\bphysics\b.{0,80}\b(game|sim)\b",
    r"\btech\s+tree\b",
    r"\bcampaign\b",
    r"\bdashboard\s+grid\b",
    r"\b(dashboard|data\s+table|spreadsheet)\b",
    r"\bsurvey\b",
    r"\beducation\s+website\b",
    r"\b(dashboard|landing\s*page|saas)\b",
    r"^city$",
    r"^builder$",
    r"^grid$",
    r"^resources?$",
    r"^buildings?$",
    r"^population$",
    r"^map$",
    r"^planning$",
    r"^simulation$",
    r"^dashboard$",
    r"^management$",
    r"^city\s+builder$",
    r"^build a city builder\.?$",
    r"^city app$",
    r"^grid builder$",
) + _REACTION_TIME_CHALLENGE_CROSS_RECIPE_NEGATIVES + _TYPING_SPEED_RACER_CROSS_RECIPE_NEGATIVES + _RHYTHM_TAP_LITE_CROSS_RECIPE_NEGATIVES + _DECK_BUILDER_LITE_CROSS_RECIPE_NEGATIVES + _CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES

_CITY_BUILDER_LITE_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bcity[- ]build(ing|er)\b.{0,120}\b(grid|buildings|houses|farms|place|day|turn|production|population|goal)\b",
    r"\b(browser|local|dom|small|tiny)\b.{0,60}\bcity\b.{0,120}\b(grid|building|place|day|resource|population|happiness)\b",
    r"\bplace\b.{0,60}\b(buildings|houses|farms|wells?|power)\b.{0,120}\b(grid|city|small\s+grid)\b",
    r"\bbuilding\s+palette\b.{0,120}\b(grid|place|day|resource|production|goal|restart)\b",
    r"\b(5x5|6x6|5\s*x\s*5|6\s*x\s*6)\b.{0,120}\b(grid|city|building|houses|farms)\b",
    r"\b(end\s+day|advance\s+days?)\b.{0,120}\b(production|resources?|building|grid|city|population|happiness)\b",
    r"\bbuildings?\b.{0,80}\bproduce\b.{0,120}\b(resources?|food|coins?|turn|day|each\s+turn|each\s+day)\b",
    r"\bpopulation\s+(goal|growth|happiness)\b.{0,120}\b(city|grid|building|day|goal)\b",
    r"\b(new\s+city|restart)\b.{0,120}\b(grid|resources?|buildings?|day|city\s+goal|population)\b",
    r"\bcity\s+goal\b.{0,120}\b(day|population|happiness|win|result)\b",
    r"\bresource\s+counters?\b.{0,120}\b(city|grid|building|day|place|production)\b",
    r"\bmeet\b.{0,60}\b(city|population)\s+goal\b.{0,120}\b(day|grid|building)\b",
)


def _normalized_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", str(prompt or "").strip().lower())


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _count_matches(text: str, patterns: tuple[str, ...]) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text))


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


def _matches_city_builder_lite(text: str) -> bool:
    return _matches_recipe(
        text,
        negatives=_CITY_BUILDER_LITE_NEGATIVE_PATTERNS,
        positives=_CITY_BUILDER_LITE_POSITIVE_PATTERNS,
    )


_DASHBOARD_UI_CORE_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(idle|incremental|clicker|tycoon|trivia|quiz|wordle|hangman|tactics|city[- ]?builder|deck[- ]?building)\b",
    r"\b(admin|backoffice|back-office|user\s+management|permissions?|role[- ]?based|rbac|crud)\b",
    r"\b(analytics\s+workbench|ad[- ]?hoc\s+quer(y|ies)|pivot\s+tables?|drill[- ]?down)\b",
    r"\b(auth|authentication|accounts?|login|sign[- ]?in|sign[- ]?up|tenant|multi[- ]?tenant|billing|checkout|payments?)\b",
    r"\b(backend|api|database|postgres|mysql|mongodb|server|endpoint|websocket|sse)\b",
    r"\b(crm|project\s+management|kanban|tickets?|leads?)\b",
    r"\b(fintech|trading|order\s+book|candlestick|candles?|exchange|portfolio\s+tracker)\b",
    r"\b(real[- ]?time|live\s+(monitoring|updates?|data)|ops\s+dashboard|operations\s+dashboard|observability)\b",
    r"\b(map|maps|geospatial|geo\s*json|leaflet|mapbox)\b",
    r"\b(game\s+hud|hud\s+overlay|in[- ]?game\s+hud)\b",
    r"\blanding\s+page\b",
    r"\b(fake\s+dashboard\s+screenshot|dashboard\s+screenshot)\b",
    r"\b(clone|pixel[- ]?perfect|exact\s+copy)\b",
    r"^dashboard$",
    r"^app$",
    r"^admin$",
    r"^analytics$",
    r"^metrics$",
    r"^chart$",
    r"^table$",
    r"^data$",
    r"^report$",
    r"^portal$",
    r"^overview$",
    r"^build\s+me\s+a\s+dashboard$",
)

_DASHBOARD_UI_CORE_OVERVIEW_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bread[- ]?only\s+dashboard\b",
    r"\bstatic\s+dashboard\b",
    r"\bstatic\b.{0,80}\bdashboard\b",
    r"\bdashboard\s+overview\b",
    r"\bmetrics\s+overview\b",
    r"\blocal\s+sample[- ]?data\s+dashboard\b",
    r"\bno\s+backend\b.{0,80}\bdashboard\b",
    r"\bdashboard\b.{0,120}\b(no\s+backend|read[- ]?only|static|overview|local\s+sample)\b",
)

_DASHBOARD_UI_CORE_KPI_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bkpi\s+cards?\b",
    r"\bkpis?\b",
    r"\bmetric\s+cards?\b",
    r"\bstatus\s+cards?\b",
)

_DASHBOARD_UI_CORE_CHART_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\b(line\s+chart|bar\s+chart|trend\s+charts?|charts?)\b",
)

_DASHBOARD_UI_CORE_TABLE_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\b(simple\s+)?(data\s+)?table\b",
    r"\bdatagrid\b",
    r"\brecent\s+activity\s+table\b",
)

_DASHBOARD_UI_CORE_STATE_LAYOUT_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\b(empty|loading|error)\s+states?\b",
    r"\bloading/empty/error\s+states?\b",
    r"\bresponsive\s+(layout|stacking|structure)\b",
    r"\blocal[- ]only\s+filters?\b",
)

_SAAS_DASHBOARD_CORE_HOME_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bsaas\s+(?:app\s+)?dashboard\b",
    r"\bproduct\s+dashboard\b",
    r"\bworkspace\s+dashboard\b",
    r"\bapp\s+home\b",
    r"\bproduct\s+home\b",
)

_SAAS_DASHBOARD_CORE_CONTENT_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bapp\s+shell\b",
    r"\b(sidebar|topbar)\b",
    r"\b(workspace|account|project)\s+(selector|switcher|context)\b",
    r"\busage\s+(cards?|summary|kpis?|metrics?)\b",
    r"\bkpi\s+cards?\b",
    r"\bplan\s+(status|tier|card)\b",
    r"\brecent\s+activity\b",
    r"\bactivity\s+(feed|list)\b",
    r"\b(resource|project|team)\s+(list|table)\b",
    r"\bupgrade\s+(cta|prompt|card)\b",
    r"\bsettings?\s+(shortcut|shortcuts|link|links)\b",
)

_SAAS_DASHBOARD_CORE_BOUNDED_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\b(local|static)\s+(sample\s+)?data\b",
    r"\bno\s+backend\b",
    r"\bwithout\s+(?:a\s+)?backend\b",
    r"\bno\s+auth\b",
    r"\bno\s+billing\b",
    r"\bno\s+crud\b",
    r"\bno\s+live\s+data\b",
    r"\bno\s+real[- ]?time\b",
)

_SAAS_DASHBOARD_CORE_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(admin|backoffice|back-office|user\s+management|permissions?|role[- ]?based|rbac)\b",
    r"\b(auth|authentication|login|log[- ]?in|sign[- ]?in|sign[- ]?up|session|tenant|multi[- ]?tenant|user\s+accounts?|account\s+management)\b",
    r"\b(backend|api|database|postgres|mysql|mongodb|server|endpoint|websocket|sse)\b",
    r"\b(billing|payment|payments|checkout|invoice|invoices|subscription|subscriptions)\b",
    r"\bcrud\b",
    r"\b(create|edit|update|delete)\b.{0,80}\b(users?|records?|items?|projects?|entries|workflows?)\b",
    r"\b(users?|records?|items?|projects?|entries|workflows?)\b.{0,80}\b(create|edit|update|delete)\b",
    r"\b(forms?|admin\s+panel)\b.{0,80}\b(create|edit|update|delete|crud)\b",
    r"\b(analytics\s+workbench|ad[- ]?hoc\s+quer(y|ies)|pivot\s+tables?|drill[- ]?down)\b",
    r"\b(crm|kanban|project\s+management|leads?|tickets?)\b",
    r"\b(real[- ]?time|live\s+(monitoring|updates?|data)|ops\s+dashboard|operations\s+dashboard|observability)\b",
    r"\b(fintech|trading|order\s+book|candlestick|candles?|exchange|portfolio\s+tracker)\b",
    r"\b(ecommerce|e-commerce|store\s+admin|order\s+management|product\s+management|shop\s+admin)\b",
    r"\b(map|maps|geospatial|geo\s*json|leaflet|mapbox)\b",
    r"\b(clone|pixel[- ]?perfect|exact\s+copy)\b",
    r"\blanding\s+page\b.{0,120}\b(dashboard\s+screenshot|screenshot)\b",
    r"\b(read[- ]?only|static)\s+dashboard\s+overview\b",
)

_ADMIN_DASHBOARD_CORE_HOME_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\badmin\s+dashboard\b",
    r"\badmin\s+control\s+panel\b",
    r"\binternal\s+operations\s+dashboard\b",
    r"\b(backoffice|back[- ]office)\s+dashboard\b",
    r"\badmin\s+console\b.{0,80}\bdashboard\b",
)

_ADMIN_DASHBOARD_CORE_CONTENT_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\b(staff|user|team)\s+(management|summary|overview)\b",
    r"\brole\s*/?\s*permission\s+summary\b",
    r"\b(role|permission)s?\s+summary\b",
    r"\breview\s+queue\b",
    r"\bmoderation\s+queue\b",
    r"\baudit\s+log\b",
    r"\bsystem\s+status\b",
    r"\b(system\s+health|health\s+panel)\b",
    r"\b(resource|user)\s+table\b",
)

_ADMIN_DASHBOARD_CORE_BOUNDED_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\b(static|demo|read[- ]only|illustrative)\b",
    r"\blocal\s+(mock|sample)\s+data\b",
    r"\bmock\s+data\s+only\b",
    r"\bno\s+backend\b",
    r"\bwithout\s+(?:a\s+)?backend\b",
    r"\bno\s+auth\b",
    r"\bno\s+rbac\b",
    r"\bno\s+crud\b",
    r"\bno\s+destructive\s+actions?\b",
    r"\bno\s+live\s+data\b",
    r"\bno\s+live\s+monitoring\b",
    r"\bno\s+real\s+audit\s+logging\b",
)

_ADMIN_DASHBOARD_CORE_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(auth|authentication|login|log[- ]?in|sign[- ]?in|sign[- ]?up|accounts?|session|jwt|oauth)\b",
    r"\b(backend|api|database|postgres|mysql|mongodb|server|endpoint|websocket|sse)\b",
    r"\b(create|edit|update|delete|invite|onboard|provision)\b.{0,100}\b(users?|accounts?|members?)\b",
    r"\b(users?|accounts?|members?)\b.{0,100}\b(create|edit|update|delete|invite|onboard|provision)\b",
    r"\b(permission|permissions|role|roles)\b.{0,100}\b(edit|update|mutat(e|ion)|assign|revoke|grant)\b",
    r"\b(edit|update|mutat(e|ion)|assign|revoke|grant)\b.{0,100}\b(permission|permissions|role|roles)\b",
    r"\brbac\b.{0,100}\b(implementation|editor|enforcement)\b",
    r"\bcrud\b.{0,100}\b(forms?|workflow|flows?)\b",
    r"\b(destructive|dangerous)\s+actions?\b.{0,80}\b(mutate|save|persist|write)\b",
    r"\b(mutate|persist|write)\b.{0,80}\b(destructive|dangerous)\s+actions?\b",
    r"\bmoderation\s+workflow\b",
    r"\bbilling|payments?|invoices?\b",
    r"\b(real[- ]?time|live)\s+(monitoring|logs?|streaming|updates?|data)\b",
    r"\breal\s+audit\s+logging\b",
    r"\b(security|compliance)\s+(implementation|console|tooling|center)\b",
    r"\b(cryptographic|crypto(?:graphy)?|encryption|kms)\b",
    r"\b(analytics\s+workbench|ad[- ]?hoc\s+quer(y|ies)|pivot\s+tables?|drill[- ]?down)\b",
    r"\b(crm|project\s+management|kanban|tickets?|leads?)\b",
    r"\b(ecommerce|e-commerce|store\s+admin|order\s+management|product\s+management|shop\s+admin)\b",
    r"\b(fintech|trading|order\s+book|candlestick|candles?|exchange|portfolio\s+tracker)\b",
    r"\b(clone|pixel[- ]?perfect|exact\s+copy)\b",
    r"\b(read[- ]?only|static)\s+dashboard\s+overview\b",
    r"\b(product|workspace)\s+dashboard\s+home\b",
)

_ADMIN_NEGATED_EXCLUSION_PATTERNS: tuple[str, ...] = (
    r"\b(?:no|without|sans|zero|free\s+of)\s+(?:a\s+|an\s+|any\s+|the\s+)?backend\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+(?:a\s+|an\s+|any\s+|the\s+)?auth(?:entication)?\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+(?:a\s+|an\s+|any\s+|the\s+)?rbac\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+(?:a\s+|an\s+|any\s+|the\s+)?crud\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+destructive\s+actions?\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+live\s+monitoring\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+live\s+data\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+real\s+audit\s+logging\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+permissions?\s+mutation\b",
)


_DASHBOARD_NEGATED_EXCLUSION_PATTERN = re.compile(
    r"\b(?:no|without|sans|zero|free\s+of)\s+"
    r"(?:a\s+|an\s+|any\s+|the\s+|live\s+|real[- ]?time\s+|admin\s+)*"
    r"(?:crud|back[- ]?ends?|servers?|apis?|auth|authentication|"
    r"accounts?|logins?|log[- ]?in|sign[- ]?ups?|sign[- ]?ins?|"
    r"databases?|db|payments?|billing|live\s+data|real[- ]?time\s+data|"
    r"admin\s+permissions?)"
    r"(?:\s*(?:,|and|or)\s*"
    r"(?:a\s+|an\s+|any\s+|the\s+|live\s+|real[- ]?time\s+|admin\s+)*"
    r"(?:crud|back[- ]?ends?|servers?|apis?|auth|authentication|"
    r"accounts?|logins?|log[- ]?in|sign[- ]?ups?|sign[- ]?ins?|"
    r"databases?|db|payments?|billing|live\s+data|real[- ]?time\s+data|"
    r"admin\s+permissions?))*"
)


def _strip_dashboard_negated_exclusions(text: str) -> str:
    """Remove explicitly-negated dashboard exclusions after strong-positive match."""
    stripped = _strip_negated_exclusions(text)
    return _DASHBOARD_NEGATED_EXCLUSION_PATTERN.sub(" ", stripped)


_SAAS_NEGATED_EXCLUSION_PATTERN = re.compile(
    r"\b(?:no|without|sans|zero|free\s+of)\s+"
    r"(?:a\s+|an\s+|any\s+|the\s+|live\s+|real[- ]?time\s+|admin\s+|user\s+)*"
    r"(?:crud|back[- ]?ends?|servers?|apis?|auth|authentication|"
    r"accounts?|logins?|log[- ]?in|sign[- ]?ups?|sign[- ]?ins?|"
    r"user\s+management|admin\s+user\s+management|permissions?|rbac|"
    r"role[- ]?based(?:\s+access\s+control)?|"
    r"databases?|db|payments?|billing|subscriptions?|invoices?|"
    r"subscription\s+management|invoice\s+management|"
    r"live\s+data|real[- ]?time\s+data|real[- ]?time\s+updates?)"
    r"(?:\s*(?:,|and|or|,\s*and|,\s*or)\s*"
    r"(?:a\s+|an\s+|any\s+|the\s+|live\s+|real[- ]?time\s+|admin\s+|user\s+)*"
    r"(?:crud|back[- ]?ends?|servers?|apis?|auth|authentication|"
    r"accounts?|logins?|log[- ]?in|sign[- ]?ups?|sign[- ]?ins?|"
    r"user\s+management|admin\s+user\s+management|permissions?|rbac|"
    r"role[- ]?based(?:\s+access\s+control)?|"
    r"databases?|db|payments?|billing|subscriptions?|invoices?|"
    r"subscription\s+management|invoice\s+management|"
    r"live\s+data|real[- ]?time\s+data|real[- ]?time\s+updates?))*"
)


def _strip_saas_negated_exclusions(text: str) -> str:
    """Remove explicitly-negated SaaS exclusions after strong-positive match."""
    stripped = _SAAS_NEGATED_EXCLUSION_PATTERN.sub(" ", text)
    return _strip_negated_exclusions(stripped)


def _strip_admin_negated_exclusions(text: str) -> str:
    """Remove explicitly-negated admin exclusions after strong-positive match."""
    stripped = _strip_saas_negated_exclusions(text)
    for pattern in _ADMIN_NEGATED_EXCLUSION_PATTERNS:
        stripped = re.sub(pattern, " ", stripped)
    return stripped


def _matches_dashboard_ui_core(text: str) -> bool:
    if not _matches_any(text, _DASHBOARD_UI_CORE_OVERVIEW_POSITIVE_PATTERNS):
        return False
    has_kpi = _matches_any(text, _DASHBOARD_UI_CORE_KPI_POSITIVE_PATTERNS)
    has_chart = _matches_any(text, _DASHBOARD_UI_CORE_CHART_POSITIVE_PATTERNS)
    has_table = _matches_any(text, _DASHBOARD_UI_CORE_TABLE_POSITIVE_PATTERNS)
    has_state_layout = _matches_any(text, _DASHBOARD_UI_CORE_STATE_LAYOUT_POSITIVE_PATTERNS)
    if not (has_chart or has_table or has_state_layout):
        return False
    # Prefer explicit KPI language, but allow strong chart+table dashboard prompts.
    if not (has_kpi or (has_chart and has_table)):
        return False
    # Keep the matcher conservative: only neutralize negated exclusions for
    # prompts that already satisfy strong dashboard-positive signals.
    effective = _strip_dashboard_negated_exclusions(text)
    if _matches_any(effective, _DASHBOARD_UI_CORE_NEGATIVE_PATTERNS):
        return False
    return True


def _matches_saas_dashboard_core(text: str) -> bool:
    if not _matches_any(text, _SAAS_DASHBOARD_CORE_HOME_POSITIVE_PATTERNS):
        return False
    if _count_matches(text, _SAAS_DASHBOARD_CORE_CONTENT_POSITIVE_PATTERNS) < 2:
        return False
    if not _matches_any(text, _SAAS_DASHBOARD_CORE_BOUNDED_POSITIVE_PATTERNS):
        return False
    effective = _strip_saas_negated_exclusions(text)
    if _matches_any(effective, _SAAS_DASHBOARD_CORE_NEGATIVE_PATTERNS):
        return False
    return True


def _matches_admin_dashboard_core(text: str) -> bool:
    if not _matches_any(text, _ADMIN_DASHBOARD_CORE_HOME_POSITIVE_PATTERNS):
        return False
    if _count_matches(text, _ADMIN_DASHBOARD_CORE_CONTENT_POSITIVE_PATTERNS) < 2:
        return False
    if not _matches_any(text, _ADMIN_DASHBOARD_CORE_BOUNDED_POSITIVE_PATTERNS):
        return False
    effective = _strip_admin_negated_exclusions(text)
    if _matches_any(effective, _ADMIN_DASHBOARD_CORE_NEGATIVE_PATTERNS):
        return False
    return True


_SALES_OPS_DASHBOARD_CORE_HOME_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bsales\s+ops\s+dashboard\b",
    r"\bsales\s+operations\s+dashboard\b",
    r"\brevops\s+dashboard\b",
    r"\brevenue\s+operations\s+dashboard\b",
    r"\bcommission\s+dashboard\b",
    r"\brevenue\s+recovery\s+dashboard\b",
)

_SALES_OPS_DASHBOARD_CORE_CONTENT_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\b(agent|team)\s+performance\b",
    r"\bsales\s+activity\b",
    r"\bpipeline\s+(stage\s+)?movement\b",
    r"\bstage\s+movement\b",
    r"\bcommission\s+(earned|pending|summary)\b",
    r"\b(clawbacks?|chargebacks?)\b",
    r"\bpayout\s+status\b",
    r"\brecovered\s+dollars\b",
    r"\brecoverable\s+balance\b",
    r"\baging\s+buckets?\b",
    r"\brecovery\s+(queue|summary|exception)\b",
    r"\bexception\s+queue\b",
    r"\bprocess\s+bottlenecks?\b",
    r"\bcycle\s+time\b",
    r"\bactivity\s+(feed|audit\s+feed)\b",
    r"\b(date|team|agent|status|stage)\s+filters?\b",
)

_SALES_OPS_DASHBOARD_CORE_BOUNDED_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\b(static|local|sample|demo|illustrative|read[- ]only)\b",
    r"\blocal\s+(mock|sample)\s+data\b",
    r"\b(static|local)\s+sample\s+data\b",
    r"\bno\s+payroll\b",
    r"\bno\s+payments?\b",
    r"\bno\s+accounting\b",
    r"\bno\s+asc\s*606\b",
    r"\bno\s+crm\s+sync\b",
    r"\bno\s+backend\b",
    r"\bno\s+api\b",
    r"\bno\s+real\s+pii\b",
    r"\bno\s+legal\s+collections\s+automation\b",
)

_SALES_OPS_DASHBOARD_CORE_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(product|workspace)\s+(dashboard|home)\b",
    r"\b(admin|backoffice|control\s+panel)\b",
    r"\blanding\s+page\b",
    r"\bgeneric\s+executive\s+revenue\s+dashboard\b",
    r"\breal\s+payroll\b",
    r"\bpayment\s+processing\b",
    r"\baccounting\s+ledger\b",
    r"\basc\s*606\b.{0,80}\b(calculation|engine|compliance)\b",
    r"\blegal\s+collections\s+automation\b",
    r"\blive\s+(crm|api|database)\b",
    r"\bcrm\s+sync\b",
    r"\b(backend|api|database)\s+integrations?\b",
    r"\breal\s+(bank|account|payment)\s+identifiers?\b",
    r"\breal\s+(customer\s+)?pii\b",
    r"\bcustomer\s+database\b",
    r"\b(tax|accounting)\s+(claims?|certification)\b",
    r"\bcompliance\s+certification\b",
    r"\blive\s+dunning\b",
    r"\b(telephony|sms)\s+automation\b",
    r"\bregulated\s+financial\s+advice\b",
    r"\bpayout\s+(approval|disbursement)\b",
    r"\b(trading|order\s+book|financial\s+market|fintech)\b",
    r"\b(clone|pixel[- ]?perfect|exact\s+copy)\b",
)

_SALES_OPS_NEGATED_EXCLUSION_PATTERNS: tuple[str, ...] = (
    r"\b(?:no|without|sans|zero|free\s+of)\s+(?:a\s+|an\s+|any\s+|the\s+)?payroll\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+payments?\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+payment\s+processing\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+accounting(?:\s+ledger)?\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+asc\s*606\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+crm(?:\s+sync)?\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+(?:a\s+|an\s+|any\s+|the\s+)?backend\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+(?:a\s+|an\s+|any\s+|the\s+)?api\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+(?:a\s+|an\s+|any\s+|the\s+)?database\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+real\s+pii\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+legal\s+collections\s+automation\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+live\s+dunning\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+telephony\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+sms\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+payout\s+(approval|disbursement)\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+regulated\s+financial\s+advice\b",
)


def _strip_sales_ops_negated_exclusions(text: str) -> str:
    """Remove explicitly-negated sales-ops exclusions after strong-positive match."""
    stripped = _strip_admin_negated_exclusions(text)
    for pattern in _SALES_OPS_NEGATED_EXCLUSION_PATTERNS:
        stripped = re.sub(pattern, " ", stripped)
    return stripped


def _matches_sales_ops_dashboard_core(text: str) -> bool:
    if not _matches_any(text, _SALES_OPS_DASHBOARD_CORE_HOME_POSITIVE_PATTERNS):
        return False
    if _count_matches(text, _SALES_OPS_DASHBOARD_CORE_CONTENT_POSITIVE_PATTERNS) < 3:
        return False
    if not _matches_any(text, _SALES_OPS_DASHBOARD_CORE_BOUNDED_POSITIVE_PATTERNS):
        return False
    effective = _strip_sales_ops_negated_exclusions(text)
    if _matches_any(effective, _SALES_OPS_DASHBOARD_CORE_NEGATIVE_PATTERNS):
        return False
    return True


_LANDING_PAGE_CORE_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\b(idle|incremental|clicker|tycoon)\b",
    r"\b(trivia|quiz)\b.{0,80}\b(game|timer|challenge)\b",
    r"\bmemory\s+(card|match)\b",
    r"\bbranching\s+story\b",
    r"\bchoose\s+your\s+own\s+adventure\b",
    r"\b(wordle|daily\s+word|word\s+guess)\b",
    r"\bdaily\s+puzzle\s+grid\b",
    r"\bresource\s+management\b.{0,80}\b(sim|simulation|game)\b",
    r"\bhangman(-style)?\b",
    r"\btyping\s+speed\b",
    r"\bword\s+build(er|ing)\b",
    r"\bturn[- ]based\b.{0,80}\bcard\b",
    r"\breaction[- ]time\b.{0,80}\bgame\b",
    r"\brhythm\s+tap\b",
    r"\bdeck[- ]building\b.{0,80}\bcard\b",
    r"\bturn[- ]based\b.{0,80}\btactics\b",
    r"\bcity[- ]build(ing|er)\b",
    r"\bbuild\b.{0,40}\b(game|clicker|trivia|hangman|puzzle)\b",
    r"\bgame\b.{0,80}\b(player|score|level|turns?|grid|units?|enemies?)\b",
    r"\b(admin|analytics|data)\s+dashboard\b",
    r"\bdashboard\b",
    r"\bproject\s+management\b",
    r"\bcrm\b",
    r"\b(ecommerce|checkout|cart|payment|stripe|storefront|online\s+store|shop\s+page)\b",
    r"\b(blog|cms|documentation\s+site|docs\s+site|help\s+center)\b",
    r"\b(backend|api|authentication|auth|accounts|login|signup)\b",
    r"\bfull\s+web\s+app\b",
    r"\bweb\s+app\b.{0,80}\b(auth|authentication|login|accounts)\b",
    r"\b(clone|pixel[- ]perfect|exact\s+copy)\b",
    r"\bclone\b.{0,80}\b(stripe|apple|google)\b",
    r"^website$",
    r"^homepage$",
    r"^page$",
    r"^design$",
    r"^modern$",
    r"^saas$",
    r"^startup$",
    r"^product$",
    r"^beautiful$",
    r"^responsive$",
    r"^app$",
    r"^dashboard$",
    r"^build a website$",
    r"^make a homepage$",
    r"^build a homepage$",
    r"^make a website$",
    r"^build a page$",
    r"^make a page$",
)

_LANDING_PAGE_CORE_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\blanding\s+page\b.{0,180}\b(hero|features|testimonial|cta|faq|value\s+proposition)\b",
    r"\b(hero|features|testimonial|cta|faq|value\s+proposition)\b.{0,180}\blanding\s+page\b",
    r"\bproduct\s+landing\s+page\b.{0,120}\b(value\s+proposition|features|social\s+proof|cta)\b",
    r"\bmarketing\s+(landing\s+)?page\b.{0,120}\b(hero|features|cta|sections?)\b",
    r"\bstartup\s+launch\s+page\b.{0,120}\b(hero|benefits|trust|cta|waitlist|faq)\b",
    r"\bresponsive\s+marketing\s+landing\s+page\b.{0,120}\b(feature\s+cards?|cta|credibility)\b",
    r"\b(one[- ]page|single[- ]page)\b.{0,80}\b(marketing|landing|product)\b.{0,120}\b(hero|features|cta)\b",
    r"\bsaas\b.{0,80}\blanding\s+page\b.{0,120}\b(hero|value\s+proposition|features|cta|faq)\b",
    r"\bbuild\b.{0,40}\b(product\s+)?landing\s+page\b.{0,120}\b(hero|features|social\s+proof|final\s+cta)\b",
    r"\bcreate\b.{0,40}\b(product\s+)?landing\s+page\b.{0,120}\b(value\s+proposition|feature\s+sections?|trust)\b",
    r"\bbuild\b.{0,40}\blaunch\s+page\b.{0,120}\b(hero|benefits|trust|waitlist\s+cta|faq)\b",
    r"\bmarketing\s+landing\s+page\b.{0,120}\b(hero|feature\s+cards?|credibility|strong\s+cta)\b",
)


# Explicitly-negated exclusion phrases. When a strong landing positive is present,
# these are neutralized before negative matching so a static marketing page that
# *disclaims* a backend/form/payment/CMS ("no backend", "without a backend",
# "no payments", "no CMS") still routes — while genuine feature *requests*
# ("build a backend", "with a backend", "connect to an API", "payment checkout")
# keep their feature word and continue to block. Conservative: applied only when
# a strong landing positive already matched.
_LANDING_NEGATED_EXCLUSION_PATTERN = re.compile(
    r"\b(?:no|without|sans|zero|free\s+of)\s+"
    r"(?:a\s+|an\s+|any\s+|the\s+|live\s+|real\s+|server[- ]?side\s+|user\s+)*"
    r"(?:back[- ]?ends?|servers?|apis?|auth|authentication|"
    r"accounts?|logins?|log[- ]?in|sign[- ]?ups?|sign[- ]?ins?|"
    r"forms?|form\s+submissions?|form\s+handling|live\s+forms?|"
    r"payments?|checkouts?|carts?|cms|content\s+management(?:\s+system)?|"
    r"databases?|db)"
    r"(?:\s+(?:handling|submissions?|management|integrations?|systems?))?"
)


def _strip_negated_exclusions(text: str) -> str:
    """Remove explicitly-negated backend/form/payment/CMS constraint phrases."""
    return _LANDING_NEGATED_EXCLUSION_PATTERN.sub(" ", text)


def _matches_landing_page_core(text: str) -> bool:
    if not _matches_any(text, _LANDING_PAGE_CORE_POSITIVE_PATTERNS):
        return False
    effective = _strip_negated_exclusions(text)
    if _matches_any(effective, _LANDING_PAGE_CORE_NEGATIVE_PATTERNS):
        return False
    return True


def select_registry_v2_app_type_for_prompt(prompt: str) -> str | None:
    """Return a registry v2 app type id for clear prompt matches, else ``None``."""
    text = _normalized_prompt(prompt)
    if not text:
        return None
    # Keep global negatives conservative, but allow explicitly bounded Sales Ops
    # prompts that may include negated "no CRM sync" language.
    if _matches_any(text, _GLOBAL_NEGATIVE_PATTERNS) and not _matches_sales_ops_dashboard_core(text):
        return None
    # Precedence: trivia → idle → branching narrative → memory match → word daily
    # → daily puzzle grid → resource management sim → hangman lite → typing speed racer
    # → word builder → card deck turn-based → reaction time challenge → rhythm tap lite
    # → deck builder lite → turn-based tactics lite → city builder lite → landing page core
    # → dashboard ui core → saas dashboard core → admin dashboard core
    # → sales ops dashboard core.
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
    if _matches_city_builder_lite(text):
        return CITY_BUILDER_LITE_APP_TYPE
    if _matches_landing_page_core(text):
        return LANDING_PAGE_CORE_APP_TYPE
    if _matches_dashboard_ui_core(text):
        return DASHBOARD_UI_CORE_APP_TYPE
    if _matches_saas_dashboard_core(text):
        return SAAS_DASHBOARD_CORE_APP_TYPE
    if _matches_admin_dashboard_core(text):
        return ADMIN_DASHBOARD_CORE_APP_TYPE
    if _matches_sales_ops_dashboard_core(text):
        return SALES_OPS_DASHBOARD_CORE_APP_TYPE
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
