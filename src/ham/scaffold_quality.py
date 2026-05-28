"""Lightweight static inspection and one-pass repair for LLM scaffold playability."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from src.ham.builder_plan import Plan

_LOG = logging.getLogger(__name__)

# Primary gameplay dispatch types that must not be no-ops when declared.
_PRIMARY_GAMEPLAY_ACTIONS = frozenset(
    {
        "PLAY_CARD",
        "DRAW_CARD",
        "END_TURN",
        "ALLOCATE",
        "SUBMIT_WORD",
        "START_TIMER",
        "TICK",
        "FLIP_CARD",
        "DRAW",
        "PLAY",
        "MATCH",
        "END_GAME",
        "NEXT_DAY",
        "END_TURN",
        "USE_HINT",
    }
)

_STUB_PLACEHOLDER = re.compile(
    r"//\s*(?:Logic to|TODO|FIXME|Implement(?:ation)?|placeholder|future[-\s]work|not implemented)",
    re.IGNORECASE,
)

_CASE_BLOCK = re.compile(
    r"case\s+['\"]([^'\"]+)['\"]\s*:\s*(.*?)(?=\bcase\s+['\"]|\bdefault\s*:)",
    re.DOTALL,
)

_NOOP_RETURN = re.compile(
    r"return\s+(?:state|\{\s*\.\.\.state\s*\})\s*;?\s*$",
    re.MULTILINE,
)

_DISPATCH_TYPE = re.compile(
    r"dispatch\s*\(\s*\{\s*type:\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)

_SWITCH_ON_ACTION = re.compile(r"switch\s*\(\s*action\.type\s*\)")

_LOG_ONLY_HANDLER = re.compile(
    r"(?:const|function)\s+(?:handle\w+|on\w+|play\w+|draw\w+|submit\w+|endTurn)\w*\s*=\s*"
    r"(?:\([^)]*\)\s*)?=>\s*\{\s*console\.log",
    re.IGNORECASE,
)

_EMPTY_HANDLER = re.compile(
    r"(?:onClick|onChange|onSubmit)=\{\s*(?:\(\)\s*)?=>\s*\{\s*\}\s*\}",
    re.IGNORECASE,
)

_STALE_HP_WIN_CHECK = re.compile(
    r"set(?:Enemy|Player)?Hp\s*\("
    r"(?:(?!;).){0,400}?"
    r"if\s*\(\s*(?:enemyHp|playerHp|health)\s*<=",
    re.IGNORECASE | re.DOTALL,
)

_STALE_NAMED_WIN_FN = re.compile(
    r"(?:function|const)\s+(?:checkWin\w*|check\w*Condition)\s*=\s*"
    r"(?:\([^)]*\)\s*)=>\s*\{[^}]*if\s*\(\s*(?:enemyHp|playerHp|health)\s*<=",
    re.IGNORECASE | re.DOTALL,
)

_NAMED_IMPORT = re.compile(
    r"import\s+\{\s*(\w+)\s*\}\s+from\s+['\"](\.[^'\"]+)['\"]"
)
_DEFAULT_EXPORT = re.compile(r"export\s+default\s+(\w+)")

_PROMPT_60_SECONDS = re.compile(
    r"60[\s-]?second|60s\b|after\s+60\b",
    re.IGNORECASE,
)

_EXPLICIT_60_DURATION = re.compile(
    r"useState\s*\(\s*60\s*\)"
    r"|\b(?:ROUND|GAME|TIMER|COUNTDOWN|DURATION|TIME_LIMIT|MAX_TIME|initial(?:Time|Seconds)|secondsLeft|timeLeft)\w*\s*=\s*60\b"
    r"|\b60000\b"
    r"|60\s*\*\s*1000"
    r"|(?:elapsedSeconds|elapsedTime|secondsLeft|timeLeft|timer|countdown)\w*\s*(?:<|<=|>|>=|===|==)\s*60\b",
    re.IGNORECASE,
)

_PROMPT_RESULT_REQUIRED = re.compile(
    r"\bwins?\b|\bvict(?:ory|orious)\b|\bsurvive\b|health to zero|reducing.*health|"
    r"final score|win state|game over|running out of|short run|complete a run|run result",
    re.IGNORECASE,
)

_RESULT_STATE_MARKERS = re.compile(
    r"\b(?:gameWon|gameLost|isFinished|gameOver|hasWon|hasLost|showResult|resultScreen|showResults|finalScore)\b"
    r"|set(?:Result|GameOver|Win|Victory|Status|FinalScore)\s*\("
    r"|(?:phase|gamePhase|gameState|status)\s*===?\s*['\"](?:result|complete|finished|runComplete|runResult)['\"]"
    r"|['\"](?:win|won|lose|lost|victory|result|complete|runComplete|runResult)['\"]"
    r"|type:\s*['\"](?:WIN|LOSE|VICTORY|GAME_OVER|RESULT|RUN_COMPLETE|NEW_RUN)['\"]"
    r"|enemyHp\s*<=\s*0|enemyHp\s*===?\s*0"
    r"|VictoryScreen|ResultsPanel|GameOver|GoalStatus|RunResult|DeckBuilderResults"
    r"|Play Again|Try Again|playAgain|restartGame|newRun|startNewRun|restartRun",
    re.IGNORECASE,
)

_PROMPT_RHYTHM_TIMING = re.compile(
    r"rhythm\s+tap|tap the beat|beat cue|timing accuracy|perfect.*good.*miss",
    re.IGNORECASE,
)

_PROMPT_RHYTHM_MISS_SCORING = re.compile(
    r"miss|perfect.*good.*miss|timing accuracy",
    re.IGNORECASE,
)

_RHYTHM_STREAK_RESET = re.compile(
    r"setStreak\s*\(\s*(?:0|prev\s*=>\s*0)\s*\)",
    re.IGNORECASE,
)

_RHYTHM_MISS_FEEDBACK_MARKERS = re.compile(
    r"\bmiss(?:Count|es)?\b"
    r"|MissPanel|missFeedback|timingFeedback|RhythmMiss"
    r"|lastJudgment.*miss|judgment.*['\"]miss['\"]"
    r"|['\"]miss['\"]"
    r"|setScore\s*\([^)]*-\s*\d"
    r"|score.*(?:miss|penalty)",
    re.IGNORECASE,
)

_STALE_RHYTHM_FINAL_SCORE = re.compile(
    r"setFinalScore\s*\(\s*(?:score|totalScore)\s*\)",
    re.IGNORECASE,
)

_PROMPT_CARD_DECK = re.compile(
    r"\bcards?\b|\bdecks?\b|\bhand\b|\bdraw\b|\bdiscard\b|shuffled deck|card battle",
    re.IGNORECASE,
)

_PROMPT_DECK_BUILDER = re.compile(
    r"deck[- ]building|deck builder|starter deck|card reward|add.*to.*deck|"
    r"short run|complete a run|deck mutation|roguelite.*deck|reward choice",
    re.IGNORECASE,
)

_PROMPT_DECK_BUILDER_REWARDS = re.compile(
    r"card reward|choose.*reward|reward choice|add.*to.*deck|pick.*reward|reward card",
    re.IGNORECASE,
)

_PROMPT_DECK_BUILDER_DISCARD = re.compile(
    r"\bdiscard(?:s|ed|ing)?\b|\bdiscard pile\b",
    re.IGNORECASE,
)

_PROMPT_DECK_BUILDER_RUN = re.compile(
    r"short run|complete a run|run result|new run|restart|play again|run progression|encounters?",
    re.IGNORECASE,
)

_PROMPT_TACTICS_GAME = re.compile(
    r"turn[- ]based\s+tactics|tactics\s+game|tactical\s+battle|"
    r"\b(?:player|enemy)\s+units?\b|"
    r"\bgrid\b.{0,160}\b(?:select|move|attack).{0,160}\bunit",
    re.IGNORECASE,
)

_PROMPT_TACTICS_MOVEMENT_RANGE = re.compile(
    r"within range|movement range|move them within|move range|movement options",
    re.IGNORECASE,
)

_PROMPT_TACTICS_ATTACK_RANGE = re.compile(
    r"attack range|attacks enemy|attack enemy|attack enemies",
    re.IGNORECASE,
)

_PROMPT_TACTICS_ENEMY_TURN = re.compile(
    r"enemy turn|enemy units|resolves a simple enemy|enemy phase",
    re.IGNORECASE,
)

_PROMPT_TACTICS_WIN = re.compile(
    r"defeating all enemies|defeat all enemies|wins by defeating",
    re.IGNORECASE,
)

_PROMPT_TACTICS_LOSS = re.compile(
    r"all player units are defeated|player units are defeated|all player units",
    re.IGNORECASE,
)

_PROMPT_TACTICS_RESTART = re.compile(
    r"restart the battle|restart|new battle|play again",
    re.IGNORECASE,
)

_PROMPT_CITY_BUILDER_GAME = re.compile(
    r"city[- ]building|city building|building game|"
    r"place(?:s|d)?\s+(?:houses?|farms?|wells?|power\s+buildings?)|"
    r"\b(?:houses?|farms?|wells?|power)\s+buildings?\b|"
    r"building palette|grow(?:s|ing)?\s+population|"
    r"advances?\s+days?\s+to\s+produce",
    re.IGNORECASE,
)

_PROMPT_CITY_BUILDING_TYPES = re.compile(
    r"\b(?:houses?|farms?|wells?|power\s+buildings?|power)\b",
    re.IGNORECASE,
)

_PROMPT_CITY_POPULATION_GOAL = re.compile(
    r"population\s+goal|reaching\s+a\s+population|reach(?:ing)?\s+population",
    re.IGNORECASE,
)

_PROMPT_CITY_FOOD_LOSS = re.compile(
    r"food\s+runs?\s+out|loses?\s+if\s+food|running\s+out\s+of\s+food",
    re.IGNORECASE,
)

_PROMPT_CITY_POPULATION_HAPPINESS = re.compile(
    r"population\s+and\s+happiness|grows?\s+population|happiness",
    re.IGNORECASE,
)

_PROMPT_CITY_RESTART = re.compile(
    r"restart\s+the\s+city|new\s+city|restart",
    re.IGNORECASE,
)

_PROMPT_DASHBOARD_CORE = re.compile(
    r"read[- ]only\s+dashboard|dashboard\s+overview|static\s+dashboard|"
    r"dashboard.{0,120}(?:kpi|metric).{0,120}(?:chart|line|bar).{0,120}(?:table|data\s+table|recent\s+builds)",
    re.IGNORECASE,
)

_PROMPT_DASHBOARD_KPI = re.compile(
    r"\bkpi\b|kpi\s+cards?|metric\s+cards?|status\s+cards?",
    re.IGNORECASE,
)

_PROMPT_DASHBOARD_CHART = re.compile(
    r"\bchart\b|line\s+chart|bar\s+chart|trend",
    re.IGNORECASE,
)

_PROMPT_DASHBOARD_TABLE = re.compile(
    r"\btable\b|data\s+table|recent\s+builds|datagrid",
    re.IGNORECASE,
)

_PROMPT_DASHBOARD_FILTER_REQUEST = re.compile(
    r"\bfilter(?:s|ing)?\b|filter\s+bar|\bsearch\b",
    re.IGNORECASE,
)

_PROMPT_DASHBOARD_STATE_REQUEST = re.compile(
    r"empty\/loading\/error|empty,\s*loading,\s*and\s*error|empty.*loading.*error",
    re.IGNORECASE,
)

_PROMPT_DASHBOARD_LINE_BAR_REQUEST = re.compile(
    r"line\s+chart.*bar\s+chart|bar\s+chart.*line\s+chart",
    re.IGNORECASE,
)

_PROMPT_DASHBOARD_EXCLUDED = re.compile(
    r"landing\s+page.*dashboard\s+screenshot|fake\s+dashboard\s+screenshot|"
    r"admin\s+dashboard|analytics\s+workbench|game\s+hud",
    re.IGNORECASE,
)

_DASHBOARD_FILTER_CONTROL = re.compile(
    r"<input\b|<select\b|filter\s*bar|filterbar|search",
    re.IGNORECASE,
)

_DASHBOARD_FILTER_DISABLED = re.compile(
    r"<(?:input|select)[^>]*\bdisabled\b|disabled\s*=\s*\{\s*true\s*\}|readOnly\s*=\s*\{\s*true\s*\}",
    re.IGNORECASE,
)

_DASHBOARD_FILTER_STATE = re.compile(
    r"useState\s*\([^)]*(?:filter|query|search)|set\w*(?:Filter|Query|Search)|"
    r"(?:selected|active)(?:Filter|Query|Search)",
    re.IGNORECASE,
)

_DASHBOARD_FILTER_HANDLER = re.compile(
    r"onChange|onInput|handle\w*(?:Filter|Search|Query)|dispatch\s*\(\s*\{[^}]*FILTER",
    re.IGNORECASE,
)

_DASHBOARD_FILTER_EFFECT = re.compile(
    r"\.filter\s*\(|filtered(?:Rows|Data|Table|Kpis?|Charts?)|"
    r"(?:table|chart|kpi)[^;\n]{0,80}(?:filter|query|search)",
    re.IGNORECASE,
)

_DASHBOARD_EMPTY_STATE = re.compile(
    r"\bempty\b|no\s+data|no\s+builds|nothing\s+to\s+show",
    re.IGNORECASE,
)

_DASHBOARD_LOADING_STATE = re.compile(
    r"\bloading\b|skeleton|isLoading|loadingState",
    re.IGNORECASE,
)

_DASHBOARD_ERROR_STATE = re.compile(
    r"\berror\b|failed|unable\s+to\s+load|errorState",
    re.IGNORECASE,
)

_DASHBOARD_MAIN = re.compile(r"<main\b|role\s*=\s*['\"]main['\"]")

_DASHBOARD_HEADER = re.compile(r"<header\b|role\s*=\s*['\"]banner['\"]")

_DASHBOARD_NAV = re.compile(r"<nav\b|role\s*=\s*['\"]navigation['\"]")

_DASHBOARD_H1 = re.compile(r"<h1\b")

_DASHBOARD_TABLE = re.compile(r"<table\b")

_DASHBOARD_LINE_CHART = re.compile(
    r"line\s+chart|<Line\b|chartType\s*:\s*['\"]line['\"]|build\s+quality\s+over\s+time",
    re.IGNORECASE,
)

_DASHBOARD_BAR_CHART = re.compile(
    r"bar\s+chart|<Bar\b|chartType\s*:\s*['\"]bar['\"]|issues?\s+by\s+category",
    re.IGNORECASE,
)

_BUILDING_PALETTE_MARKERS = re.compile(
    r"BuildingPalette|building-palette|buildingPalette|"
    r"selectedBuilding|selectedBuildingType|activeBuilding|currentBuilding|"
    r"setSelectedBuilding|buildingTypes\s*=|BUILDING_TYPES|buildingCatalog|"
    r"buildingOptions|paletteBuildings",
    re.IGNORECASE,
)

_HARDCODED_HOUSE_PLACEMENT = re.compile(
    r"building:\s*['\"]house['\"]|payload:\s*\{[^}]*building:\s*['\"]house['\"]",
    re.IGNORECASE,
)

_OCCUPIED_CELL_GUARD = re.compile(
    r"!(?:state\.)?grid|(?:state\.)?grid\[[^\]]+\]\s*!==?\s*null|"
    r"(?:state\.)?grid\[[^\]]+\]\s*===?\s*null|cell\s*!==?\s*null|"
    r"occupied|already\s+built|isEmpty|empty\s+cell|cannot\s+place|"
    r"invalid\s+placement|if\s*\(\s*!(?:state\.)?grid",
    re.IGNORECASE,
)

_POPULATION_GOAL_WIN = re.compile(
    r"(?:new)?[Pp]opulation\s*>=\s*(?:POPULATION_GOAL|goal|target|\d+)|"
    r"populationGoal|POPULATION_GOAL|goalPopulation|"
    r"(?:win|wins|victory)\s+(?:when|if)[^;{]{0,120}population|"
    r"reached\s+(?:the\s+)?population\s+goal|population\s+goal\s+reached|"
    r"setGameResult\s*\(\s*['\"]You win",
    re.IGNORECASE,
)

_FOOD_FAIL_CONDITION = re.compile(
    r"food\s*<=?\s*0|food\s*===?\s*0|outOfFood|foodDepleted|food\s+runs?\s+out",
    re.IGNORECASE,
)

_BUILDING_PRODUCTION_CATALOG = re.compile(
    r"(?:const|let|var)\s+(BUILDING_(?:PRODUCTION|EFFECTS|STATS)|buildingProduction|"
    r"BUILDING_CATALOG|buildingCatalog)\s*=",
    re.IGNORECASE,
)

_GRID_BUILDING_COUNT = re.compile(
    r"grid|flat\s*\(|\.filter\s*\(|cells|placedBuildings|countBuildings|"
    r"buildingType|['\"](?:farm|house|well|power|Farm|House|Well|Power)['\"]",
    re.IGNORECASE,
)

_POPULATION_ONLY_FOOD_FORMULA = re.compile(
    r"(?:resources\.)?food\s*[-=][^;]{0,120}population|"
    r"Math\.floor\s*\(\s*population\s*/|population\s*/\s*\d",
    re.IGNORECASE,
)

_HARDCODED_HAPPINESS_DELTA = re.compile(
    r"happinessChange\s*=\s*\d+\b"
    r"|setHappiness\s*\(\s*happiness\s*\+\s*\d+\s*\)"
    r"|setHappiness\s*\(\s*Math\.min\s*\(\s*\d+\s*,\s*happiness\s*\+\s*\d+\s*\)"
    r"|happiness\s*:\s*state\.happiness\s*\+\s*\d+\b",
    re.IGNORECASE,
)

_HAPPINESS_DERIVED_FROM_CITY = re.compile(
    r"happiness(?:Change|Delta)?\s*=\s*[^;{]+(?:grid|flat\s*\(|well|power|farm|house|building|food|resources|population|coins)"
    r"|happiness\s*:\s*[^;{]+(?:well|power|farm|house|grid|flat\s*\(|food|resources|population|coins)"
    r"|setHappiness\s*\([^)]*(?:grid|flat\s*\(|well|power|farm|house|food|resources|population|coins|happinessDelta|happinessChange)"
    r"|newHappiness\s*=\s*[^;{]+(?:grid|flat\s*\(|well|power|farm|house|food|resources|population|coins)",
    re.IGNORECASE,
)

_CITY_DAY_TICK_FUNCTION = re.compile(
    r"(?:const|function)\s+(?:endDay|nextDay|advanceDay|handleEndDay)\w*\s*="
    r"(?:\s*(?:async\s*)?\([^)]*\)\s*)?(?:=>)?\s*\{",
    re.IGNORECASE,
)

_CITY_DAY_ACTIONS = frozenset({"END_DAY", "NEXT_DAY", "ADVANCE_DAY"})
_CITY_PLACE_ACTIONS = frozenset({"PLACE_BUILDING", "PLACE", "BUILD", "BUILD_ON_CELL"})
_CITY_RESTART_ACTIONS = frozenset(
    {"RESTART", "NEW_CITY", "RESET", "RESTART_GAME", "NEW_GAME", "INIT", "INIT_GAME"}
)

_PLAYER_UNIT_MARKER = re.compile(
    r"isPlayer:\s*true|team:\s*['\"]player['\"]|owner:\s*['\"]player['\"]|"
    r"type:\s*['\"]player['\"]|"
    r"playerUnits|side:\s*['\"]player['\"]|role:\s*['\"]player['\"]|"
    r"id\.startsWith\s*\(\s*['\"]p|unit\.id\.startsWith\s*\(\s*['\"]p|"
    r"units\.find\s*\(\s*u\s*=>\s*u\.id\.startsWith\s*\(\s*['\"]p|"
    r"unit\.type\s*===?\s*['\"]player['\"]|u\.type\s*===?\s*['\"]player['\"]",
    re.IGNORECASE,
)

_ENEMY_UNIT_MARKER = re.compile(
    r"isPlayer:\s*false|team:\s*['\"]enemy['\"]|owner:\s*['\"]enemy['\"]|"
    r"type:\s*['\"]enemy['\"]|"
    r"enemyUnits|isEnemy:\s*true|side:\s*['\"]enemy['\"]|role:\s*['\"]enemy['\"]|"
    r"id\.startsWith\s*\(\s*['\"]e|unit\.id\.startsWith\s*\(\s*['\"]e|"
    r"units\.find\s*\(\s*u\s*=>\s*u\.id\.startsWith\s*\(\s*['\"]e|"
    r"unit\.id\.startsWith\s*\(\s*['\"]e|"
    r"unit\.type\s*===?\s*['\"]enemy['\"]|u\.type\s*===?\s*['\"]enemy['\"]",
    re.IGNORECASE,
)

_MOVEMENT_RANGE_MARKERS = re.compile(
    r"move(?:ment)?Range|moveRange|maxMove|movement\s+range|moveDistance|"
    r"manhattan|distance\s*[<=>]|adjacent|validMoves|legalMoves|withinRange|"
    r"Math\.abs\s*\([^)]+\)\s*[<=>]",
    re.IGNORECASE,
)

_ATTACK_RANGE_MARKERS = re.compile(
    r"attackRange|attack\s+range|maxAttack|inAttackRange|canAttack|attackDistance|"
    r"withinAttackRange|Math\.abs\s*\(\s*dx\s*\)\s*<=|Math\.abs\s*\(\s*dy\s*\)\s*<=",
    re.IGNORECASE,
)

_INPLACE_HP_MUTATION = re.compile(
    r"(?:target|unit|enemy|attacker|defender|playerUnit|player)\.hp\s*[-=]|\.hp\s*[-+]?=",
    re.IGNORECASE,
)

_IMMUTABLE_UNITS_RETURN = re.compile(
    r"return\s*\{[^}]*units\s*:\s*(?:state\.units\.map|state\.units\.filter|newUnits|nextUnits|updatedUnits|\[\s*\.\.\.)",
    re.IGNORECASE | re.DOTALL,
)

_TACTICS_MOVE_ACTIONS = frozenset({"MOVE_UNIT", "MOVE"})
_TACTICS_ATTACK_ACTIONS = frozenset({"ATTACK_UNIT", "ATTACK"})
_TACTICS_SELECT_ACTIONS = frozenset({"SELECT_UNIT", "SELECT"})
_TACTICS_INIT_ACTIONS = frozenset({"INIT", "INIT_GAME", "START_GAME", "NEW_GAME", "RESET"})

_TACTICS_UI_ACTIONS = frozenset(
    {"SELECT_UNIT", "SELECT", "MOVE_UNIT", "MOVE", "ATTACK_UNIT", "ATTACK", "END_TURN"}
)

_EMPTY_REWARD_POOL = re.compile(
    r"(?:const|let|var)\s+(?:rewards|rewardPool|availableRewards|rewardCards|rewardOptions)\s*=\s*\[\s*\]"
    r"|(?:rewards|rewardPool|availableRewards|rewardCards|rewardOptions)\s*:\s*\[\s*\]",
    re.IGNORECASE,
)

_POPULATED_REWARD_POOL = re.compile(
    r"(?:rewards|rewardPool|availableRewards|rewardCards|rewardOptions)\s*[=:]\s*\[\s*\{"
    r"|(?:REWARD_CARDS|rewardCards|defaultRewards)\s*=\s*\[\s*\{",
    re.IGNORECASE,
)

_DISCARD_APPEND = re.compile(
    r"discard(?:Pile)?\s*:\s*\[\.\.\.(?:state\.)?(?:discard|discardPile)"
    r"|(?:discard|discardPile)\s*:\s*\[\.\.\.(?:state\.)?(?:discard|discardPile)"
    r"|(?:discard|discardPile)\.push\s*\("
    r"|\.concat\s*\(\s*(?:state\.)?(?:discard|discardPile)",
    re.IGNORECASE,
)

_RESTART_MARKERS = re.compile(
    r"Play Again|Try Again|playAgain|restartGame|newRun|startNewRun|restartRun|NEW_RUN|RESET_RUN|"
    r"RESTART_GAME|RESTART\b|Restart",
    re.IGNORECASE,
)

_EMPTY_DECK_FACTORY = re.compile(
    r"(?:function\s+|const\s+)?(?:shuffledDeck|drawInitialHand|createDeck|buildDeck|makeDeck)\w*"
    r"(?:\s*=\s*)?(?:\([^)]*\)\s*)?(?:=>)?\s*\{[^}]*return\s*\[\s*\]",
    re.IGNORECASE | re.DOTALL,
)

_EMPTY_DECK_ARROW = re.compile(
    r"(?:const|function)\s+(?:shuffledDeck|drawInitialHand|createDeck|buildDeck)\w*\s*="
    r"\s*(?:\([^)]*\)\s*)?=>\s*\[\s*\]",
    re.IGNORECASE,
)

_STUB_DECK_IMPL = re.compile(
    r"/\*\s*implementation\s*\*/\s*return\s*\[\s*\]",
    re.IGNORECASE,
)

_POPULATED_CARD_DEF = re.compile(
    r"\[\s*\{[^}]*(?:name|damage|power|effect|id)\s*:",
    re.IGNORECASE,
)

_MEANINGFUL_REDUCER_MUTATION = re.compile(
    r"return\s*\{[^}]*\.\.\.[^}]*(?:deck|hand|discard|enemyHp|playerHp|food|wood|count|score|mistakes|wpm)\s*:",
    re.IGNORECASE | re.DOTALL,
)

_PROMPT_CARD_VICTORY = re.compile(
    r"enemy health|reducing.*health.*zero|health to zero|card battle|wins by",
    re.IGNORECASE,
)

_VICTORY_TRANSITION = re.compile(
    r"dispatch\s*\(\s*\{\s*type:\s*['\"](?:END_GAME|WIN|GAME_OVER|SET_GAME_OVER)['\"]"
    r"|setGameOver\s*\("
    r"|setResult\s*\("
    r"|if\s*\([^)]*enemyHp\s*<=\s*0[^)]*\)\s*\{[^}]*(?:setGameOver|setResult|gameEnded|gameOver|dispatch)"
    r"|(?:nextHp|newEnemyHp|updatedHp|enemyHealth)\s*<=\s*0[^;{]*(?:gameEnded|gameOver|You win)"
    r"|case\s*['\"]PLAY_CARD['\"][^}]*gameEnded:\s*true",
    re.IGNORECASE | re.DOTALL,
)

_SEED_GAME_ACTIONS = frozenset(
    {"NEW_GAME", "RESET_GAME", "START_GAME", "RESET", "INIT_GAME", "START", "INITIALIZE"}
)

_TACTICS_SEED_ACTIONS = frozenset(_SEED_GAME_ACTIONS | {"RESTART_GAME", "RESTART"})

_DISPATCH_SEED_WITH_DATA = re.compile(
    r"dispatch\s*\(\s*\{[^}]*type:\s*['\"](?:NEW_GAME|RESET_GAME|START_GAME|RESET|INIT_GAME|START|INITIALIZE)['\"]"
    r"[^}]*(?:payload|deck|hand|cards)\s*:",
    re.IGNORECASE | re.DOTALL,
)

_JS_SOURCE_SUFFIXES = (".tsx", ".ts", ".jsx", ".js")


@dataclass(frozen=True)
class ScaffoldQualityIssue:
    """One playability problem detected in generated scaffold source."""

    code: str
    message: str
    path: str | None = None
    detail: str | None = None


def _file_map(file_changes: list[tuple[str, str]]) -> dict[str, str]:
    return {path: content for path, content in file_changes}


def _resolve_import_path(from_path: str, import_rel: str) -> str:
    """Resolve a relative import to a repo-style path (best effort)."""
    base = from_path.rsplit("/", 1)[0] if "/" in from_path else ""
    parts: list[str] = []
    if base:
        parts.extend(base.split("/"))
    for segment in import_rel.replace("\\", "/").split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if parts:
                parts.pop()
            continue
        parts.append(segment)
    return "/".join(parts)


def _inspect_reducer_noops(path: str, content: str) -> list[ScaffoldQualityIssue]:
    issues: list[ScaffoldQualityIssue] = []
    if "reducer" not in content.lower() and "usereducer" not in content.lower():
        return issues
    for match in _CASE_BLOCK.finditer(content):
        action = match.group(1).strip()
        body = match.group(2)
        if action == "default":
            continue
        has_stub = bool(_STUB_PLACEHOLDER.search(body))
        if has_stub or _is_noop_case_body(body, action):
            issues.append(
                ScaffoldQualityIssue(
                    code="noop_reducer_action",
                    message=f"Reducer action '{action}' is a stub or no-op",
                    path=path,
                    detail=body.strip()[:240],
                )
            )
    return issues


def _inspect_stub_comments(path: str, content: str) -> list[ScaffoldQualityIssue]:
    issues: list[ScaffoldQualityIssue] = []
    if not _STUB_PLACEHOLDER.search(content):
        return issues
    if "reducer" in content.lower() or "dispatch" in content.lower():
        for match in _STUB_PLACEHOLDER.finditer(content):
            issues.append(
                ScaffoldQualityIssue(
                    code="stub_placeholder",
                    message="Core gameplay path contains TODO/stub placeholder comment",
                    path=path,
                    detail=match.group(0),
                )
            )
            break
    return issues


def _collect_reducer_actions(file_changes: list[tuple[str, str]]) -> dict[str, str]:
    """Map reducer action type -> case body across all files."""
    actions: dict[str, str] = {}
    for _path, content in file_changes:
        if not _SWITCH_ON_ACTION.search(content):
            continue
        for match in _CASE_BLOCK.finditer(content):
            action = match.group(1).strip()
            if action != "default":
                actions[action] = match.group(2)
    return actions


def _collect_dispatch_types(file_changes: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Return (action_type, path) for each dispatch call."""
    found: list[tuple[str, str]] = []
    for path, content in file_changes:
        for match in _DISPATCH_TYPE.finditer(content):
            found.append((match.group(1).strip(), path))
    return found


def _is_noop_case_body(body: str, action: str) -> bool:
    if _STUB_PLACEHOLDER.search(body):
        return True
    if _MEANINGFUL_REDUCER_MUTATION.search(body):
        return False
    if re.search(
        r"return\s*\{[^}]*(?:deck|hand|discardPile|discard)\s*:",
        body,
        re.IGNORECASE | re.DOTALL,
    ):
        return False
    stripped = body.strip()
    for line in stripped.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("return") and not _NOOP_RETURN.match(line):
            return False
    return bool(_NOOP_RETURN.search(stripped))


def _inspect_dispatch_reducer_mismatch(
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    reducer_actions = _collect_reducer_actions(file_changes)
    if not reducer_actions:
        return []
    issues: list[ScaffoldQualityIssue] = []
    for action, path in _collect_dispatch_types(file_changes):
        action_upper = action.upper()
        if action_upper not in _PRIMARY_GAMEPLAY_ACTIONS:
            continue
        body = reducer_actions.get(action)
        if body is None:
            issues.append(
                ScaffoldQualityIssue(
                    code="dispatch_reducer_mismatch",
                    message=f"dispatch type '{action}' has no matching reducer case",
                    path=path,
                )
            )
        elif _is_noop_case_body(body, action):
            issues.append(
                ScaffoldQualityIssue(
                    code="dispatch_reducer_mismatch",
                    message=f"dispatch type '{action}' maps to a no-op reducer case",
                    path=path,
                )
            )
    return issues


def _inspect_empty_or_log_handlers(path: str, content: str) -> list[ScaffoldQualityIssue]:
    issues: list[ScaffoldQualityIssue] = []
    if _LOG_ONLY_HANDLER.search(content):
        issues.append(
            ScaffoldQualityIssue(
                code="empty_primary_handler",
                message="Primary handler only logs and does not mutate game state",
                path=path,
            )
        )
    if _EMPTY_HANDLER.search(content):
        issues.append(
            ScaffoldQualityIssue(
                code="empty_primary_handler",
                message="Primary UI handler is empty",
                path=path,
            )
        )
    return issues


def _inspect_stale_state_win_checks(path: str, content: str) -> list[ScaffoldQualityIssue]:
    issues: list[ScaffoldQualityIssue] = []
    if _STALE_HP_WIN_CHECK.search(content):
        issues.append(
            ScaffoldQualityIssue(
                code="stale_state_win_check",
                message=(
                    "Win/loss may read stale HP state immediately after setState; "
                    "compute next state before checking result"
                ),
                path=path,
            )
        )
    elif _STALE_NAMED_WIN_FN.search(content):
        issues.append(
            ScaffoldQualityIssue(
                code="stale_state_win_check",
                message=(
                    "checkWin/checkCondition reads HP from closure; "
                    "use computed next HP or functional update result"
                ),
                path=path,
            )
        )
    return issues


def _js_sources(file_changes: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(path, content) for path, content in file_changes if path.endswith(_JS_SOURCE_SUFFIXES)]


def _combined_js_source(file_changes: list[tuple[str, str]]) -> str:
    return "\n".join(content for _path, content in _js_sources(file_changes))


def _first_path_matching(content_iter: list[tuple[str, str]], pattern: str) -> str | None:
    rx = re.compile(pattern, re.IGNORECASE)
    for path, content in content_iter:
        if rx.search(content):
            return path
    return None


def _has_explicit_timer_duration(content: str) -> bool:
    return bool(_EXPLICIT_60_DURATION.search(content))


def _prompt_requests_60_seconds(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_60_SECONDS.search(prompt))


def _prompt_requires_result_state(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_RESULT_REQUIRED.search(prompt))


def _prompt_is_rhythm_timing_game(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_RHYTHM_TIMING.search(prompt))


def _inspect_rhythm_miss_feedback_weak(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_rhythm_timing_game(plan.user_message):
        return []
    if not _PROMPT_RHYTHM_MISS_SCORING.search(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    if not _RHYTHM_STREAK_RESET.search(combined):
        return []
    if not re.search(r"perfect|good|timingWindow|offset", combined, re.I):
        return []
    if _RHYTHM_MISS_FEEDBACK_MARKERS.search(combined):
        return []
    path = _first_path_matching(
        _js_sources(file_changes),
        r"Rhythm|Game|tap|beat|score|streak|handleTap",
    )
    return [
        ScaffoldQualityIssue(
            code="rhythm_miss_feedback_weak",
            message=(
                "Rhythm miss handling only resets streak without visible miss feedback "
                "or score/result counter updates"
            ),
            path=path,
        )
    ]


def _inspect_rhythm_result_state_weak(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_rhythm_timing_game(plan.user_message):
        return []
    if not _prompt_requires_result_state(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    if not _STALE_RHYTHM_FINAL_SCORE.search(combined):
        return []
    path = _first_path_matching(
        _js_sources(file_changes),
        r"finalScore|Rhythm|Game|result",
    )
    return [
        ScaffoldQualityIssue(
            code="rhythm_result_state_weak",
            message=(
                "Final score may capture stale closure state; derive from current tally "
                "at round end via functional update or computed next score"
            ),
            path=path,
        )
    ]


def _inspect_timer_duration(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_requests_60_seconds(plan.user_message):
        return []
    sources = _js_sources(file_changes)
    combined = _combined_js_source(file_changes)
    if not re.search(r"timer|countdown|seconds|elapsed|timeLeft|secondsLeft", combined, re.I):
        return []
    if _has_explicit_timer_duration(combined):
        return []
    path = _first_path_matching(sources, r"timer|countdown|seconds|elapsed|timeLeft|secondsLeft")
    return [
        ScaffoldQualityIssue(
            code="timer_duration_mismatch",
            message=(
                "Prompt requests a 60-second round but code lacks explicit "
                "60/60000 duration constant or countdown init"
            ),
            path=path,
        )
    ]


def _inspect_missing_result_state(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_requires_result_state(plan.user_message):
        return []
    if _prompt_is_tactics_game(plan.user_message):
        return []
    if _prompt_is_city_builder_game(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    if _RESULT_STATE_MARKERS.search(combined):
        return []
    path = _first_path_matching(
        _js_sources(file_changes),
        r"App\.|Game\.|enemyHp|playerHp|health",
    )
    if path is None:
        js_sources = _js_sources(file_changes)
        path = js_sources[0][0] if js_sources else None
    return [
        ScaffoldQualityIssue(
            code="missing_result_state",
            message=(
                "Prompt requires win/loss/final result but code lacks visible "
                "result or completion state handling"
            ),
            path=path,
        )
    ]


def _prompt_is_card_deck_game(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_CARD_DECK.search(prompt))


def _prompt_is_deck_builder_game(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_DECK_BUILDER.search(prompt))


def _prompt_requests_deck_builder_rewards(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_DECK_BUILDER_REWARDS.search(prompt))


def _prompt_requests_discard_pile(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_DECK_BUILDER_DISCARD.search(prompt))


def _prompt_requires_deck_builder_run(prompt: str | None) -> bool:
    if not prompt:
        return False
    if _prompt_is_tactics_game(prompt):
        return False
    if _prompt_is_city_builder_game(prompt):
        return False
    return bool(_PROMPT_DECK_BUILDER_RUN.search(prompt))


def _prompt_is_tactics_game(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_TACTICS_GAME.search(prompt))


def _prompt_is_city_builder_game(prompt: str | None) -> bool:
    if not prompt:
        return False
    if _prompt_is_tactics_game(prompt):
        return False
    return bool(_PROMPT_CITY_BUILDER_GAME.search(prompt))


def _prompt_is_dashboard_ui_core(prompt: str | None) -> bool:
    if not prompt:
        return False
    if _PROMPT_DASHBOARD_EXCLUDED.search(prompt):
        return False
    if not _PROMPT_DASHBOARD_CORE.search(prompt):
        return False
    has_kpi = bool(_PROMPT_DASHBOARD_KPI.search(prompt))
    has_chart = bool(_PROMPT_DASHBOARD_CHART.search(prompt))
    has_table = bool(_PROMPT_DASHBOARD_TABLE.search(prompt))
    # Keep this narrow: require chart + table and at least one KPI/dashboard-overview cue.
    return has_chart and has_table and has_kpi


def _prompt_requests_dashboard_filters(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_DASHBOARD_FILTER_REQUEST.search(prompt))


def _prompt_requests_dashboard_state_examples(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_DASHBOARD_STATE_REQUEST.search(prompt))


def _prompt_requests_line_and_bar(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_DASHBOARD_LINE_BAR_REQUEST.search(prompt))


def _inspect_dashboard_missing_requested_filter(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if (
        plan is None
        or not _prompt_is_dashboard_ui_core(plan.user_message)
        or not _prompt_requests_dashboard_filters(plan.user_message)
    ):
        return []
    combined = _combined_js_source(file_changes)
    if _DASHBOARD_FILTER_CONTROL.search(combined):
        return []
    path = _first_path_matching(
        _js_sources(file_changes),
        r"Dashboard|App|Table|Chart|KPI",
    )
    return [
        ScaffoldQualityIssue(
            code="dashboard_missing_requested_filter",
            message=(
                "Dashboard prompt requests a local filter/search bar, but generated output "
                "contains no visible filter/search control"
            ),
            path=path,
        )
    ]


def _inspect_dashboard_dead_filter_control(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if (
        plan is None
        or not _prompt_is_dashboard_ui_core(plan.user_message)
        or not _prompt_requests_dashboard_filters(plan.user_message)
    ):
        return []
    combined = _combined_js_source(file_changes)
    if not _DASHBOARD_FILTER_CONTROL.search(combined):
        return []
    if _DASHBOARD_FILTER_DISABLED.search(combined):
        # Explicitly disabled illustrative controls are non-deceptive.
        return []
    has_state = bool(_DASHBOARD_FILTER_STATE.search(combined)) or bool(
        re.search(r"useState\s*\(", combined, re.IGNORECASE)
        and re.search(r"value\s*=\s*\{[^}]+\}", combined, re.IGNORECASE)
    )
    has_handler = bool(_DASHBOARD_FILTER_HANDLER.search(combined))
    has_effect = bool(_DASHBOARD_FILTER_EFFECT.search(combined))
    if has_state and has_handler and has_effect:
        return []
    path = _first_path_matching(
        _js_sources(file_changes),
        r"Filter|Search|Dashboard|Table|Chart|KPI|App",
    )
    return [
        ScaffoldQualityIssue(
            code="dashboard_dead_filter_control",
            message=(
                "Dashboard filter/search control appears interactive but has no clear "
                "state+handler+visible mapping to KPI/chart/table data"
            ),
            path=path,
        )
    ]


def _inspect_dashboard_missing_loading_error_states(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if (
        plan is None
        or not _prompt_is_dashboard_ui_core(plan.user_message)
        or not _prompt_requests_dashboard_state_examples(plan.user_message)
    ):
        return []
    combined = _combined_js_source(file_changes)
    has_empty = bool(_DASHBOARD_EMPTY_STATE.search(combined))
    has_loading = bool(_DASHBOARD_LOADING_STATE.search(combined))
    has_error = bool(_DASHBOARD_ERROR_STATE.search(combined))
    if has_empty and has_loading and has_error:
        return []
    missing_parts: list[str] = []
    if not has_empty:
        missing_parts.append("empty")
    if not has_loading:
        missing_parts.append("loading")
    if not has_error:
        missing_parts.append("error")
    path = _first_path_matching(
        _js_sources(file_changes),
        r"Dashboard|App|Table|Chart|State|Status",
    )
    return [
        ScaffoldQualityIssue(
            code="dashboard_missing_loading_error_states",
            message=(
                "Dashboard prompt requests empty/loading/error state examples, but missing: "
                + ", ".join(missing_parts)
            ),
            path=path,
        )
    ]


def _inspect_dashboard_missing_semantic_landmarks(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_dashboard_ui_core(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    has_main = bool(_DASHBOARD_MAIN.search(combined))
    has_header = bool(_DASHBOARD_HEADER.search(combined))
    has_nav = bool(_DASHBOARD_NAV.search(combined))
    has_h1 = bool(_DASHBOARD_H1.search(combined))
    has_table = bool(_DASHBOARD_TABLE.search(combined))
    if has_main and has_header and has_nav and has_h1 and has_table:
        return []
    missing_parts: list[str] = []
    if not has_main:
        missing_parts.append("main")
    if not has_header:
        missing_parts.append("header")
    if not has_nav:
        missing_parts.append("nav")
    if not has_h1:
        missing_parts.append("h1")
    if not has_table:
        missing_parts.append("table")
    path = _first_path_matching(
        _js_sources(file_changes),
        r"Dashboard|App|Layout|Shell|Table|Nav|Header",
    )
    return [
        ScaffoldQualityIssue(
            code="dashboard_missing_semantic_landmarks",
            message=(
                "Dashboard semantic shell is incomplete; missing: "
                + ", ".join(missing_parts)
            ),
            path=path,
        )
    ]


def _inspect_dashboard_missing_requested_chart_type(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if (
        plan is None
        or not _prompt_is_dashboard_ui_core(plan.user_message)
        or not _prompt_requests_line_and_bar(plan.user_message)
    ):
        return []
    combined = _combined_js_source(file_changes)
    has_line = bool(_DASHBOARD_LINE_CHART.search(combined))
    has_bar = bool(_DASHBOARD_BAR_CHART.search(combined))
    if has_line and has_bar:
        return []
    missing = "line chart" if not has_line else "bar chart"
    path = _first_path_matching(
        _js_sources(file_changes),
        r"Chart|Dashboard|App",
    )
    return [
        ScaffoldQualityIssue(
            code="dashboard_missing_requested_chart_type",
            message=(
                f"Dashboard prompt requests both line and bar charts, but output is missing: {missing}"
            ),
            path=path,
        )
    ]


def _inspect_dashboard_quality(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    issues: list[ScaffoldQualityIssue] = []
    issues.extend(_inspect_dashboard_missing_requested_filter(plan, file_changes))
    issues.extend(_inspect_dashboard_dead_filter_control(plan, file_changes))
    issues.extend(_inspect_dashboard_missing_loading_error_states(plan, file_changes))
    issues.extend(_inspect_dashboard_missing_semantic_landmarks(plan, file_changes))
    issues.extend(_inspect_dashboard_missing_requested_chart_type(plan, file_changes))
    return issues


def _has_playable_card_seed(combined: str) -> bool:
    if not _POPULATED_CARD_DEF.search(combined):
        return False
    if re.search(r"(?:deck|drawPile|draw\s*pile):\s*\[\s*\{", combined, re.I):
        return True
    if re.search(r"hand:\s*\[\s*\{", combined, re.I):
        return True
    if re.search(r"(?:initialDeck|starterDeck|cards|cardDeck|CARD_DECK)\s*=\s*\[\s*\{", combined, re.I):
        return True
    if re.search(
        r"(?:initialDeck|starterDeck|drawHand)\w*\s*=\s*(?:\([^)]*\)\s*)?=>\s*\[\s*\{",
        combined,
        re.I,
    ):
        return True
    if re.search(
        r"(?:shuffledDeck|createDeck|buildDeck|makeDeck|initialDeck|starterDeck)\w*\([^)]*\)\s*\{[^}]*return\s*\[\s*\{",
        combined,
        re.I | re.DOTALL,
    ):
        return True
    if re.search(
        r"case\s*['\"]INITIALIZE['\"][^}]*(?:deck|hand)\s*:",
        combined,
        re.I | re.DOTALL,
    ):
        return True
    return bool(re.search(r"return\s*\[[^\]]*\{[^}]*(?:name|damage|power|effect|id)\s*:", combined, re.I))


def _has_mounted_deck_initialization(combined: str) -> bool:
    if not re.search(r"useEffect\s*\(", combined):
        return False
    if not re.search(
        r"dispatch\s*\(\s*\{\s*type:\s*['\"](?:INITIALIZE|NEW_GAME|RESET|START_GAME|START|INIT_GAME)['\"]",
        combined,
        re.I,
    ):
        return False
    return _has_playable_card_seed(combined) or bool(
        re.search(r"case\s*['\"]INITIALIZE['\"]", combined, re.I)
    )


def _has_populated_reward_pool(combined: str) -> bool:
    return bool(_POPULATED_REWARD_POOL.search(combined))


def _has_discard_wiring(combined: str) -> bool:
    return bool(_DISCARD_APPEND.search(combined))


def _inspect_empty_deck_seed(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_card_deck_game(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    if not re.search(r"deck|hand|draw|discard|card", combined, re.I):
        return []
    if _has_mounted_deck_initialization(combined):
        return []
    empty_factory = bool(
        _EMPTY_DECK_FACTORY.search(combined)
        or _EMPTY_DECK_ARROW.search(combined)
        or _STUB_DECK_IMPL.search(combined)
    )
    if _has_playable_card_seed(combined) and not empty_factory:
        return []
    if empty_factory or (
        not _has_playable_card_seed(combined)
        and re.search(r"(?:deck|hand):\s*\[\s*\]", combined, re.I)
    ):
        path = _first_path_matching(
            _js_sources(file_changes),
            r"shuffledDeck|drawInitialHand|createDeck|deck|hand|Game",
        )
        return [
            ScaffoldQualityIssue(
                code="empty_deck_seed",
                message=(
                    "Card/deck prompt expects playable cards but deck/hand seed "
                    "functions or initial arrays are empty"
                ),
                path=path,
            )
        ]
    return []


def _inspect_empty_reward_pool(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_requests_deck_builder_rewards(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    if _has_populated_reward_pool(combined):
        return []
    has_reward_ui = bool(
        re.search(
            r"RewardChoice|reward phase|phase\s*===?\s*['\"]reward['\"]|SELECT_REWARD|CHOOSE_REWARD",
            combined,
            re.I,
        )
    )
    if not has_reward_ui and not _EMPTY_REWARD_POOL.search(combined):
        return []
    path = _first_path_matching(
        _js_sources(file_changes),
        r"reward|Reward|Game|reducer",
    )
    return [
        ScaffoldQualityIssue(
            code="empty_reward_pool",
            message=(
                "Deck-builder prompt expects card reward choices but reward pool "
                "array is empty or never populated"
            ),
            path=path,
        )
    ]


def _inspect_reward_choice_not_wired(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_requests_deck_builder_rewards(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    reducer_actions = _collect_reducer_actions(file_changes)
    reward_actions = {
        action: body
        for action, body in reducer_actions.items()
        if action.upper() in {"SELECT_REWARD", "CHOOSE_REWARD", "ADD_REWARD", "PICK_REWARD"}
    }
    if not reward_actions:
        return []
    issues: list[ScaffoldQualityIssue] = []
    for action_type, body in reward_actions.items():
        if re.search(r"deck\s*:\s*\[\.\.\.(?:state\.)?deck", body, re.I):
            continue
        if re.search(r"(?:state\.)?deck\.push\s*\(", body, re.I):
            continue
        if re.search(r"deck\s*:\s*\[\.\.\.(?:state\.)?deck[^\]]*,", body, re.I | re.DOTALL):
            continue
        path = _first_path_matching(_js_sources(file_changes), rf"{action_type}|reducer|deck")
        issues.append(
            ScaffoldQualityIssue(
                code="reward_choice_not_wired",
                message=(
                    f"Reducer action '{action_type}' does not append chosen reward card to deck"
                ),
                path=path,
            )
        )
    return issues


def _inspect_discard_not_wired(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_requests_discard_pile(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    if not re.search(r"discard(?:Pile)?", combined, re.I):
        return []
    if _has_discard_wiring(combined):
        return []
    plays_cards = bool(re.search(r"case\s*['\"](?:PLAY_CARD|PLAY)['\"]", combined, re.I))
    removes_from_hand = bool(
        re.search(r"hand\s*:\s*[^;]*\.filter|hand\s*:\s*[^;]*\.slice|newHand", combined, re.I)
    )
    if not (plays_cards and removes_from_hand):
        return []
    path = _first_path_matching(_js_sources(file_changes), r"PLAY_CARD|PLAY|discard|Game|reducer")
    return [
        ScaffoldQualityIssue(
            code="discard_not_wired",
            message=(
                "Played cards are removed from hand but never appended to discard pile"
            ),
            path=path,
        )
    ]


def _inspect_deck_builder_run_result_missing(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_requires_deck_builder_run(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    issues: list[ScaffoldQualityIssue] = []
    if not _RESTART_MARKERS.search(combined):
        path = _first_path_matching(_js_sources(file_changes), r"Game|App|Control|Button")
        issues.append(
            ScaffoldQualityIssue(
                code="missing_restart_action",
                message=(
                    "Deck-builder prompt requires restart/new run but no play-again "
                    "or new-run action exists"
                ),
                path=path,
            )
        )
    return issues


def _inspect_missing_victory_wiring(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _PROMPT_CARD_VICTORY.search(plan.user_message or ""):
        return []
    combined = _combined_js_source(file_changes)
    if not re.search(r"enemyHp|enemy.*health", combined, re.I):
        return []
    if not re.search(r"enemyHp\s*[-=]|enemyHp:.*-", combined, re.I):
        return []
    if _VICTORY_TRANSITION.search(combined):
        return []
    gated_result = bool(re.search(r"gameEnded|gameOver", combined, re.I))
    has_result_ui = bool(re.search(r"ResultsPanel|VictoryScreen|result", combined, re.I))
    has_end_game_case = "END_GAME" in combined
    if gated_result and has_result_ui and has_end_game_case:
        path = _first_path_matching(_js_sources(file_changes), r"Game|enemyHp|ResultsPanel")
        return [
            ScaffoldQualityIssue(
                code="missing_victory_wiring",
                message=(
                    "Enemy HP is reduced and END_GAME/result UI exist, but no win "
                    "transition fires when enemy HP reaches zero"
                ),
                path=path,
            )
        ]
    if has_result_ui and not _RESULT_STATE_MARKERS.search(combined):
        return []
    if gated_result and has_result_ui:
        path = _first_path_matching(_js_sources(file_changes), r"Game|enemyHp|ResultsPanel")
        return [
            ScaffoldQualityIssue(
                code="missing_victory_wiring",
                message=(
                    "Enemy HP is reduced but gated result UI never receives a win/game-over transition"
                ),
                path=path,
            )
        ]
    return []


def _case_reads_seed_payload(body: str) -> bool:
    return bool(
        re.search(
            r"action\.(?:payload(?:\.(?:deck|hand|cards))?|deck|hand|cards|card\b)",
            body,
            re.IGNORECASE,
        )
    )


def _case_returns_static_empty_seed(body: str) -> bool:
    if re.search(r"return\s+initialState\b", body):
        return True
    if re.search(r"return\s*\{[^}]*\.\.\.initialState\b", body, re.IGNORECASE):
        return True
    if re.search(
        r"return\s*\{[^}]*deck:\s*\[\s*\][^}]*hand:\s*\[\s*\]",
        body,
        re.IGNORECASE | re.DOTALL,
    ):
        return True
    return bool(
        re.search(
            r"return\s*\{[^}]*\.\.\.state[^}]*deck:\s*\[\s*\]",
            body,
            re.IGNORECASE | re.DOTALL,
        )
        and not _case_reads_seed_payload(body)
    )


def _dispatch_passes_seed_data(combined: str, action_type: str) -> bool:
    pattern = re.compile(
        rf"dispatch\s*\(\s*{{[^}}]*type:\s*['\"]{re.escape(action_type)}['\"]"
        rf"[^}}]*(?:payload|deck|hand|cards)\s*:",
        re.IGNORECASE | re.DOTALL,
    )
    return bool(pattern.search(combined))


def _inspect_ignored_seed_payload(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_card_deck_game(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    if not re.search(r"deck|hand|draw|discard|card|reducer", combined, re.I):
        return []
    reducer_actions = _collect_reducer_actions(file_changes)
    if not reducer_actions:
        return []
    has_populated_seed = bool(_POPULATED_CARD_DEF.search(combined) or _has_playable_card_seed(combined))
    issues: list[ScaffoldQualityIssue] = []
    for action_type, body in reducer_actions.items():
        action_upper = action_type.upper()
        if action_upper not in _SEED_GAME_ACTIONS:
            continue
        dispatch_passes_data = _dispatch_passes_seed_data(combined, action_type)
        if not dispatch_passes_data and not has_populated_seed:
            continue
        if _case_reads_seed_payload(body):
            continue
        if not _case_returns_static_empty_seed(body) and not dispatch_passes_data:
            continue
        if dispatch_passes_data or (has_populated_seed and _case_returns_static_empty_seed(body)):
            path = _first_path_matching(
                _js_sources(file_changes),
                rf"{action_type}|reducer|deck|Game|App",
            )
            issues.append(
                ScaffoldQualityIssue(
                    code="ignored_seed_payload",
                    message=(
                        f"Reducer case '{action_type}' ignores seeded deck/hand payload "
                        "and returns empty/default state"
                    ),
                    path=path,
                )
            )
    return issues


def _has_dispatch_for_action(combined: str, action_type: str) -> bool:
    return bool(
        re.search(
            rf"dispatch\s*\(\s*{{[^}}]*type:\s*['\"]{re.escape(action_type)}['\"]",
            combined,
            re.IGNORECASE,
        )
    )


def _canonical_units_empty(combined: str) -> bool:
    if re.search(r"units:\s*\[\s*\]", combined, re.IGNORECASE):
        return True
    return bool(
        re.search(r"useReducer\s*\([^,]+,\s*\{\s*units:\s*\[\s*\]", combined, re.IGNORECASE)
    )


def _has_mounted_game_init(combined: str) -> bool:
    if not re.search(r"useEffect\s*\(", combined):
        return False
    return bool(
        re.search(
            r"dispatch\s*\(\s*\{\s*type:\s*['\"](?:INIT_GAME|START_GAME|NEW_GAME|RESET|START|INITIALIZE)['\"]",
            combined,
            re.IGNORECASE,
        )
    )


def _seed_case_includes_both_sides(reducer_actions: dict[str, str]) -> bool:
    for action_type, body in reducer_actions.items():
        if action_type.upper() not in _SEED_GAME_ACTIONS:
            continue
        if _PLAYER_UNIT_MARKER.search(body) and _ENEMY_UNIT_MARKER.search(body):
            return True
    return False


def _init_applied_to_state(combined: str, reducer_actions: dict[str, str]) -> bool:
    if _seed_case_includes_both_sides(reducer_actions) and (
        not _canonical_units_empty(combined) or _has_mounted_game_init(combined)
    ):
        return True
    if (
        _PLAYER_UNIT_MARKER.search(combined)
        and _ENEMY_UNIT_MARKER.search(combined)
        and not _canonical_units_empty(combined)
    ):
        return True
    return False


def _grid_source_present(combined: str) -> bool:
    return bool(
        re.search(
            r"grid-cols|GridBoard|TacticsGrid|\.map\s*\(\s*\(?\s*row|tile|cell",
            combined,
            re.IGNORECASE,
        )
    )


def _grid_has_click_handlers(combined: str) -> bool:
    return bool(
        re.search(
            r"onClick|onCellClick|handleCellClick|handleGridClick|onTileClick",
            combined,
            re.IGNORECASE,
        )
    )


def _grid_has_select_click_handlers(combined: str) -> bool:
    if re.search(
        r"onClick[^;{]{0,320}dispatch\s*\(\s*\{[^}]*type:\s*['\"](?:SELECT_UNIT|SELECT)['\"]",
        combined,
        re.IGNORECASE | re.DOTALL,
    ):
        return True
    return bool(
        re.search(
            r"onUnitClick|handleSelectUnit|selectUnit\s*\(|onSelectUnit",
            combined,
            re.IGNORECASE,
        )
    )


def _has_attack_ui_dispatch(combined: str) -> bool:
    if _has_dispatch_for_action(combined, "ATTACK_UNIT") or _has_dispatch_for_action(
        combined, "ATTACK"
    ):
        return True
    return bool(
        re.search(
            r"onClick[^;{]{0,360}dispatch\s*\(\s*\{[^}]*type:\s*['\"](?:ATTACK_UNIT|ATTACK)['\"]",
            combined,
            re.IGNORECASE | re.DOTALL,
        )
    )


def _attack_case_mutates_hp(body: str) -> bool:
    return bool(re.search(r"hp|damage|attack", body, re.IGNORECASE))


def _attack_case_has_range_check(body: str) -> bool:
    if _ATTACK_RANGE_MARKERS.search(body):
        return True
    return bool(
        re.search(
            r"isValidAttack|validAttack|legalAttack|canAttack|inAttackRange|withinAttackRange|"
            r"attackAllowed|attackRange|manhattanDistance|manhattan|Math\.abs\s*\(",
            body,
            re.IGNORECASE,
        )
    )


def _case_mutates_enemy_hp(body: str) -> bool:
    if not re.search(r"hp\s*[-=]|\.hp\s*-=", body, re.IGNORECASE):
        return False
    return bool(
        re.search(
            r"enemyUnit|enemyUnits|type\s*===?\s*['\"]enemy['\"]|targetCell\.type\s*===?\s*['\"]enemy['\"]|"
            r"!u\.isPlayer|isPlayer:\s*false",
            body,
            re.IGNORECASE,
        )
    )


def _reducer_has_player_attack_with_range(reducer_actions: dict[str, str]) -> bool:
    if _player_attack_has_range_check(reducer_actions):
        return True
    for action, body in reducer_actions.items():
        if action == "default" or _is_noop_case_body(body, action):
            continue
        if not (_attack_case_mutates_hp(body) or _case_mutates_enemy_hp(body)):
            continue
        if _attack_case_has_range_check(body):
            return True
    return False


def _player_attack_has_range_check(reducer_actions: dict[str, str]) -> bool:
    for action in sorted(_TACTICS_ATTACK_ACTIONS):
        body = reducer_actions.get(action, "")
        if not body or _is_noop_case_body(body, action):
            continue
        if _attack_case_mutates_hp(body) and _attack_case_has_range_check(body):
            return True
    return False


def _implemented_tactics_actions(
    reducer_actions: dict[str, str],
    action_names: frozenset[str],
) -> set[str]:
    return {
        action
        for action in reducer_actions
        if action.upper() in action_names
        and not _is_noop_case_body(reducer_actions[action], action)
    }


def _move_case_changes_position(body: str) -> bool:
    return bool(
        re.search(
            r"position|newGrid|grid\s*:|payload\s*\[|payload\.(?:to|x|y)|\.map\s*\(",
            body,
            re.IGNORECASE,
        )
    )


def _move_case_has_range_check(body: str) -> bool:
    if _MOVEMENT_RANGE_MARKERS.search(body):
        return True
    return bool(
        re.search(
            r"isValidMove|validMove|legalMove|canMove|withinMoveRange|moveAllowed",
            body,
            re.IGNORECASE,
        )
    )


def _attack_case_has_inplace_hp_mutation(body: str) -> bool:
    if not _INPLACE_HP_MUTATION.search(body):
        return False
    if re.search(
        r"const\s+(?:newUnits|nextUnits|updatedUnits)\s*=\s*state\.units\.map",
        body,
        re.IGNORECASE,
    ) and not re.search(
        r"(?:target|unit|enemy|playerUnit|player)\.hp\s*[-=]",
        body,
        re.IGNORECASE,
    ):
        return False
    if re.search(
        r"(?:target|unit|enemy|playerUnit|player)\.hp\s*[-=]|\.hp\s*[-+]?=",
        body,
        re.IGNORECASE,
    ):
        if _IMMUTABLE_UNITS_RETURN.search(body) and not re.search(
            r"return\s+state\s*;|return\s*\{\s*\.\.\.state\s*\}\s*;",
            body,
            re.IGNORECASE,
        ):
            return False
        return True
    return False


def _init_case_reseeds_battle(body: str, combined: str) -> bool:
    if _is_noop_case_body(body, "INIT"):
        return False
    if _PLAYER_UNIT_MARKER.search(body) and _ENEMY_UNIT_MARKER.search(body):
        return True
    if re.search(r"return\s+initial(?:Game)?State\b", body, re.IGNORECASE):
        return not _canonical_units_empty(combined)
    return bool(
        re.search(r"units\s*:\s*\[\s*\{", body, re.IGNORECASE)
        and _PLAYER_UNIT_MARKER.search(body)
        and _ENEMY_UNIT_MARKER.search(body)
    )


def _has_enemy_turn_mutation(combined: str, reducer_actions: dict[str, str]) -> bool:
    for action_type in ("ENEMY_TURN", "END_TURN", "RESOLVE_ENEMY", "ENEMY_ACTION", "RUN_ENEMY"):
        body = reducer_actions.get(action_type, "")
        if not body:
            continue
        if re.search(r"isPlayer:\s*false|enemy|!.*isPlayer", body, re.IGNORECASE) and re.search(
            r"hp|position|damage|attack|move",
            body,
            re.IGNORECASE,
        ):
            return True
    if re.search(
        r"(?:enemyTurn|runEnemyTurn|executeEnemyTurn|handleEnemyTurn|processEnemyTurn)\s*\(",
        combined,
        re.IGNORECASE,
    ) and re.search(r"hp|position|dispatch|units|damage", combined, re.IGNORECASE):
        return True
    return False


def _has_tactics_battle_result(combined: str, prompt: str) -> bool:
    needs_win = bool(_PROMPT_TACTICS_WIN.search(prompt))
    needs_loss = bool(_PROMPT_TACTICS_LOSS.search(prompt))
    has_win = not needs_win or bool(
        re.search(
            r"all enemies|every enemy|enemies\.every|enemies\.filter|enemies\.length\s*===?\s*0|"
            r"!.*enemies\.(?:some|find)|defeat.*enem|win|victory|You Won|Battle Won|"
            r"gameState\s*===?\s*['\"]win['\"]",
            combined,
            re.IGNORECASE,
        )
    )
    has_loss = not needs_loss or bool(
        re.search(
            r"all player|playerUnits.*every|player.*defeat|player.*hp\s*<=\s*0|"
            r"lose|loss|You Lose|Battle Lost|all player units|"
            r"gameState\s*===?\s*['\"]lose['\"]",
            combined,
            re.IGNORECASE,
        )
    )
    has_result_ui = bool(
        re.search(r"result|gameOver|battleResult|ResultsPanel|TacticsResults", combined, re.IGNORECASE)
    )
    return has_win and has_loss and has_result_ui


def _restart_reseeds_tactics(combined: str, reducer_actions: dict[str, str]) -> bool:
    for action_type, body in reducer_actions.items():
        if action_type.upper() not in {"RESTART", "RESTART_GAME", "NEW_GAME", "RESET"}:
            continue
        if _init_case_reseeds_battle(body, combined):
            return True
        if re.search(
            rf"return\s+reducer\s*\(\s*state\s*,\s*\{{\s*type:\s*['\"](?:{'|'.join(_TACTICS_INIT_ACTIONS)})['\"]",
            body,
            re.IGNORECASE,
        ):
            for init_action in _TACTICS_INIT_ACTIONS:
                init_body = reducer_actions.get(init_action, "")
                if init_body and _init_case_reseeds_battle(init_body, combined):
                    return True
        if re.search(r"return\s+initial(?:Game)?State\b", body, re.IGNORECASE) and not _canonical_units_empty(
            combined
        ):
            return True
        if re.search(
            rf"dispatch\s*\(\s*\{{\s*type:\s*['\"](?:{'|'.join(_TACTICS_INIT_ACTIONS)})['\"]",
            body,
            re.IGNORECASE,
        ):
            for init_action in _TACTICS_INIT_ACTIONS:
                init_body = reducer_actions.get(init_action, "")
                if init_body and _init_case_reseeds_battle(init_body, combined):
                    return True
    init_targets = "|".join(_TACTICS_INIT_ACTIONS)
    if re.search(
        rf"RESTART(?:_GAME)?[^;{{]{{0,160}}dispatch\s*\(\s*\{{\s*type:\s*['\"](?:{init_targets})['\"]",
        combined,
        re.IGNORECASE | re.DOTALL,
    ):
        for init_action in _TACTICS_INIT_ACTIONS:
            init_body = reducer_actions.get(init_action, "")
            if init_body and _init_case_reseeds_battle(init_body, combined):
                return True
        return False
    if re.search(
        r"onClick[^;{]{0,120}Restart[^;{]{0,160}dispatch\s*\(\s*\{\s*type:\s*['\"](?:INIT|INIT_GAME)",
        combined,
        re.IGNORECASE | re.DOTALL,
    ):
        for init_action in _TACTICS_INIT_ACTIONS:
            init_body = reducer_actions.get(init_action, "")
            if init_body and _init_case_reseeds_battle(init_body, combined):
                return True
        return False
    return False


def _inspect_tactics_unit_seeding(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_tactics_game(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    if not re.search(r"unit|grid|tactics", combined, re.IGNORECASE):
        return []
    reducer_actions = _collect_reducer_actions(file_changes)
    path = _first_path_matching(_js_sources(file_changes), r"reducer|Game|units|App")
    issues: list[ScaffoldQualityIssue] = []
    has_player = bool(_PLAYER_UNIT_MARKER.search(combined))
    has_enemy = bool(_ENEMY_UNIT_MARKER.search(combined))
    if not has_player or not has_enemy:
        issues.append(
            ScaffoldQualityIssue(
                code="tactics_empty_unit_seed",
                message=(
                    "Tactics prompt expects seeded player and enemy units but generated "
                    "source lacks non-empty player/enemy unit definitions"
                ),
                path=path,
            )
        )
    has_seed_case = _seed_case_includes_both_sides(reducer_actions) or bool(
        re.search(r"INIT_GAME|START_GAME|NEW_GAME", combined, re.IGNORECASE)
    )
    if has_seed_case and not _init_applied_to_state(combined, reducer_actions):
        issues.append(
            ScaffoldQualityIssue(
                code="tactics_seed_not_applied",
                message=(
                    "Tactics seed/init action exists but canonical state starts empty or "
                    "init is never dispatched on mount/restart"
                ),
                path=path,
            )
        )
    elif _canonical_units_empty(combined) and not _has_mounted_game_init(combined):
        issues.append(
            ScaffoldQualityIssue(
                code="tactics_seed_not_applied",
                message=(
                    "Tactics units array is empty in initial state with no mount-time init dispatch"
                ),
                path=path,
            )
        )
    return issues


def _inspect_tactics_interaction_wiring(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_tactics_game(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    reducer_actions = _collect_reducer_actions(file_changes)
    if not reducer_actions:
        return []
    issues: list[ScaffoldQualityIssue] = []
    implemented = _implemented_tactics_actions(reducer_actions, _TACTICS_UI_ACTIONS)
    select_implemented = _implemented_tactics_actions(reducer_actions, _TACTICS_SELECT_ACTIONS)
    attack_implemented = _implemented_tactics_actions(reducer_actions, _TACTICS_ATTACK_ACTIONS)
    missing_dispatches = sorted(
        action
        for action in implemented
        if not _has_dispatch_for_action(combined, action)
        and not (
            action.upper() in _TACTICS_ATTACK_ACTIONS and _has_attack_ui_dispatch(combined)
        )
    )
    if missing_dispatches:
        path = _first_path_matching(
            _js_sources(file_changes),
            r"Grid|Board|Game|ActionBar|App",
        )
        select_missing = [
            action for action in missing_dispatches if action.upper() in _TACTICS_SELECT_ACTIONS
        ]
        attack_missing = [
            action for action in missing_dispatches if action.upper() in _TACTICS_ATTACK_ACTIONS
        ]
        message = (
            "Tactics reducer actions are implemented but UI never dispatches: "
            + ", ".join(missing_dispatches)
        )
        if select_missing:
            message += (
                "; clicking/tapping a player unit must dispatch "
                + "/".join(select_missing)
                + " so selectedUnit can change and enable move/attack decisions"
            )
        if attack_missing:
            message += (
                "; ATTACK/ATTACK_UNIT must be reachable from UI — dispatch when clicking/tapping "
                "an in-range enemy with a selected player unit, or from an Attack button/control "
                "using the selected attacker and target enemy"
            )
        issues.append(
            ScaffoldQualityIssue(
                code="tactics_action_not_wired",
                message=message,
                path=path,
            )
        )
    if _grid_source_present(combined) and implemented.intersection(
        {"SELECT_UNIT", "SELECT", "MOVE_UNIT", "MOVE", "ATTACK_UNIT", "ATTACK"}
    ):
        if not _grid_has_click_handlers(combined):
            path = _first_path_matching(_js_sources(file_changes), r"Grid|Board|tile|cell")
            issues.append(
                ScaffoldQualityIssue(
                    code="tactics_grid_not_wired",
                    message=(
                        "Tactics grid renders cells but lacks click handlers wired to "
                        "select/move/attack actions"
                    ),
                    path=path,
                )
            )
        elif select_implemented and not (
            _has_dispatch_for_action(combined, "SELECT_UNIT")
            or _has_dispatch_for_action(combined, "SELECT")
        ):
            path = _first_path_matching(_js_sources(file_changes), r"Grid|Board|tile|cell")
            issues.append(
                ScaffoldQualityIssue(
                    code="tactics_grid_not_wired",
                    message=(
                        "Tactics grid renders units/cells with click handlers but never wires "
                        "player unit selection (SELECT/SELECT_UNIT); selectedUnit cannot change"
                    ),
                    path=path,
                )
            )
        elif select_implemented and not _grid_has_select_click_handlers(combined):
            if _has_dispatch_for_action(combined, "SELECT_UNIT") or _has_dispatch_for_action(
                combined, "SELECT"
            ):
                pass
            else:
                path = _first_path_matching(_js_sources(file_changes), r"Grid|Board|tile|cell")
                issues.append(
                    ScaffoldQualityIssue(
                        code="tactics_grid_not_wired",
                        message=(
                            "Tactics grid lacks unit/cell click handlers that dispatch "
                            "SELECT/SELECT_UNIT for player units"
                        ),
                        path=path,
                    )
                )
    if select_implemented and re.search(
        r"selectedUnit|selectedUnitId",
        combined,
        re.IGNORECASE,
    ) and not (
        _has_dispatch_for_action(combined, "SELECT_UNIT")
        or _has_dispatch_for_action(combined, "SELECT")
    ):
        path = _first_path_matching(_js_sources(file_changes), r"Grid|Board|App|reducer")
        if not any(i.code == "tactics_action_not_wired" for i in issues):
            issues.append(
                ScaffoldQualityIssue(
                    code="tactics_action_not_wired",
                    message=(
                        "Tactics selectedUnit state exists but UI never dispatches "
                        "SELECT/SELECT_UNIT, so the player cannot change selection"
                    ),
                    path=path,
                )
            )
    if attack_implemented and not _has_attack_ui_dispatch(combined):
        path = _first_path_matching(_js_sources(file_changes), r"Grid|Board|ActionBar|App")
        if not any(
            i.code == "tactics_action_not_wired"
            and "ATTACK" in i.message.upper()
            for i in issues
        ):
            issues.append(
                ScaffoldQualityIssue(
                    code="tactics_action_not_wired",
                    message=(
                        "Tactics ATTACK/ATTACK_UNIT reducer case exists but UI never dispatches it; "
                        "wire enemy cell/unit click or an Attack button using selected player unit "
                        "and target enemy"
                    ),
                    path=path,
                )
            )
    return issues


def _inspect_tactics_ranges_and_enemy_turn(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_tactics_game(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    reducer_actions = _collect_reducer_actions(file_changes)
    issues: list[ScaffoldQualityIssue] = []
    path = _first_path_matching(_js_sources(file_changes), r"reducer|Game|move|attack")
    if _PROMPT_TACTICS_MOVEMENT_RANGE.search(plan.user_message):
        move_body = ""
        for action in sorted(_TACTICS_MOVE_ACTIONS):
            body = reducer_actions.get(action, "")
            if body and not _is_noop_case_body(body, action):
                move_body = body
                break
        move_missing_range = bool(
            move_body
            and _move_case_changes_position(move_body)
            and not _move_case_has_range_check(move_body)
        )
        if move_missing_range or (
            not move_body and not _MOVEMENT_RANGE_MARKERS.search(combined)
        ):
            issues.append(
                ScaffoldQualityIssue(
                    code="tactics_missing_movement_range",
                    message=(
                        "Tactics prompt requests constrained movement but MOVE action lacks "
                        "legal movement range/distance/adjacency/Manhattan checks before "
                        "changing unit position"
                    ),
                    path=path,
                )
            )
    if _PROMPT_TACTICS_ATTACK_RANGE.search(plan.user_message):
        attack_body = ""
        for action in sorted(_TACTICS_ATTACK_ACTIONS):
            body = reducer_actions.get(action, "")
            if body and not _is_noop_case_body(body, action):
                attack_body = body
                break
        attack_missing_range = bool(
            attack_body
            and _attack_case_mutates_hp(attack_body)
            and not _attack_case_has_range_check(attack_body)
        )
        if not attack_missing_range and not _reducer_has_player_attack_with_range(reducer_actions):
            player_attack_cases = [
                (action, body)
                for action, body in reducer_actions.items()
                if action != "default"
                and not _is_noop_case_body(body, action)
                and (_attack_case_mutates_hp(body) or _case_mutates_enemy_hp(body))
            ]
            attack_missing_range = bool(player_attack_cases) or bool(attack_body)
        if attack_missing_range:
            issues.append(
                ScaffoldQualityIssue(
                    code="tactics_missing_attack_range",
                    message=(
                        "Tactics prompt requests player attacks on enemies but ATTACK action "
                        "lacks player-side distance/range/adjacency/Manhattan checks before "
                        "HP mutation; enemy-turn range logic does not satisfy this requirement"
                    ),
                    path=path,
                )
            )
    if _PROMPT_TACTICS_ENEMY_TURN.search(
        plan.user_message
    ) and not _has_enemy_turn_mutation(combined, reducer_actions):
        issues.append(
            ScaffoldQualityIssue(
                code="tactics_enemy_turn_not_wired",
                message=(
                    "Tactics prompt requests an enemy turn but enemy units never move, "
                    "attack, or mutate player/enemy HP"
                ),
                path=path,
            )
        )
    return issues


def _inspect_tactics_attack_mutation(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_tactics_game(plan.user_message):
        return []
    reducer_actions = _collect_reducer_actions(file_changes)
    issues: list[ScaffoldQualityIssue] = []
    path = _first_path_matching(_js_sources(file_changes), r"reducer|attack|Game")
    for action in sorted(_TACTICS_ATTACK_ACTIONS):
        body = reducer_actions.get(action, "")
        if not body:
            continue
        if _attack_case_has_inplace_hp_mutation(body):
            issues.append(
                ScaffoldQualityIssue(
                    code="tactics_inplace_attack_mutation",
                    message=(
                        f"Tactics {action} mutates unit HP in place or returns stale state; "
                        "compute next units immutably, reduce target HP through returned state, "
                        "and remove/mark defeated enemies before win/loss checks"
                    ),
                    path=path,
                )
            )
            break
    return issues


def _inspect_tactics_battle_result_and_restart(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_tactics_game(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    reducer_actions = _collect_reducer_actions(file_changes)
    issues: list[ScaffoldQualityIssue] = []
    path = _first_path_matching(_js_sources(file_changes), r"result|Game|reducer|Restart")
    if (
        _PROMPT_TACTICS_WIN.search(plan.user_message)
        or _PROMPT_TACTICS_LOSS.search(plan.user_message)
    ) and not _has_tactics_battle_result(combined, plan.user_message):
        issues.append(
            ScaffoldQualityIssue(
                code="tactics_missing_battle_result",
                message=(
                    "Tactics prompt requires win/loss battle result but code lacks visible "
                    "win-on-all-enemies-defeated and loss-on-all-player-units-defeated handling"
                ),
                path=path,
            )
        )
    if _PROMPT_TACTICS_RESTART.search(plan.user_message) and re.search(
        r"RESTART|Restart|restart", combined, re.IGNORECASE
    ):
        if not _restart_reseeds_tactics(combined, reducer_actions):
            issues.append(
                ScaffoldQualityIssue(
                    code="tactics_restart_not_seeded",
                    message=(
                        "Tactics restart/new battle control resets to empty state without "
                        "re-seeding grid units"
                    ),
                    path=path,
                )
            )
    return issues


def _has_building_palette(combined: str) -> bool:
    if _BUILDING_PALETTE_MARKERS.search(combined):
        return True
    building_buttons = len(
        re.findall(
            r"['\"](?:house|farm|well|power|shop)['\"][^;]{0,120}(?:onClick|setSelectedBuilding|setActiveBuilding)",
            combined,
            re.IGNORECASE,
        )
    )
    return building_buttons >= 2


def _hardcoded_single_building_placement(combined: str) -> bool:
    if not _HARDCODED_HOUSE_PLACEMENT.search(combined):
        return False
    if _has_building_palette(combined):
        return False
    if re.search(
        r"building:\s*(?:selectedBuilding|activeBuilding|currentBuilding|buildingType)",
        combined,
        re.IGNORECASE,
    ):
        return False
    return True


def _place_case_blocks_occupied_cells(body: str) -> bool:
    if not body.strip():
        return False
    if _OCCUPIED_CELL_GUARD.search(body):
        return True
    if re.search(
        r"if\s*\([^)]*(?:null|undefined|empty|occupied)[^)]*\)\s*return",
        body,
        re.IGNORECASE,
    ):
        return True
    return bool(
        re.search(
            r"if\s*\([^)]*grid\[[^\]]+\][^)]*\)\s*\{[^}]*return\s+(?:state|\{\s*\.\.\.state)",
            body,
            re.IGNORECASE | re.DOTALL,
        )
    )


def _extract_brace_block(combined: str, open_brace_index: int) -> str:
    depth = 0
    for index in range(open_brace_index, len(combined)):
        char = combined[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return combined[open_brace_index : index + 1]
    return ""


def _expand_tick_bodies_with_helpers(combined: str, tick_bodies: list[str]) -> list[str]:
    expanded = list(tick_bodies)
    helper_names: set[str] = set()
    for body in tick_bodies:
        for match in re.finditer(
            r"return\s+(\w*(?:Day|Production|Tick|Results)\w*)\s*\(",
            body,
            re.IGNORECASE,
        ):
            helper_names.add(match.group(1))
    for name in helper_names:
        match = re.search(
            rf"(?:const|function)\s+{re.escape(name)}\s*=\s*(?:\([^)]*\)\s*)?(?:=>)?\s*\{{",
            combined,
            re.IGNORECASE,
        )
        if not match:
            continue
        block = _extract_brace_block(combined, match.end() - 1)
        if block:
            expanded.append(block)
    return expanded


def _collect_day_tick_bodies(combined: str, reducer_actions: dict[str, str]) -> list[str]:
    bodies: list[str] = []
    for action in _CITY_DAY_ACTIONS:
        body = reducer_actions.get(action, "")
        if body:
            bodies.append(body)
    for match in _CITY_DAY_TICK_FUNCTION.finditer(combined):
        block = _extract_brace_block(combined, match.end() - 1)
        if block:
            bodies.append(block)
    return _expand_tick_bodies_with_helpers(combined, bodies)


def _tick_body_mutates_resources(body: str) -> bool:
    return bool(
        re.search(
            r"food|coins|setResources|newFood|newCoins|resources\.food|resources\.coins",
            body,
            re.IGNORECASE,
        )
    )


def _end_day_derives_production_from_grid(body: str) -> bool:
    if not body.strip():
        return False
    if not re.search(r"food|coins|resource|production", body, re.IGNORECASE):
        return False
    if not _GRID_BUILDING_COUNT.search(body):
        return False
    if _POPULATION_ONLY_FOOD_FORMULA.search(body) and not re.search(
        r"grid|flat\s*\(|filter\s*\(",
        body,
        re.IGNORECASE,
    ):
        return False
    return True


def _has_unused_building_production_catalog(
    combined: str,
    tick_bodies: list[str],
) -> bool:
    if not _BUILDING_PRODUCTION_CATALOG.search(combined):
        return False
    tick_text = "\n".join(tick_bodies)
    for match in _BUILDING_PRODUCTION_CATALOG.finditer(combined):
        catalog_name = match.group(1)
        if not re.search(
            rf"\b{re.escape(catalog_name)}\b|Object\.values\s*\(\s*{re.escape(catalog_name)}\s*\)",
            tick_text,
            re.IGNORECASE,
        ):
            return True
    return False


def _prompt_requests_happiness(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(re.search(r"\bhappiness\b", prompt, re.IGNORECASE))


def _happiness_present_in_state(combined: str) -> bool:
    return bool(
        re.search(
            r"\bhappiness\b|setHappiness\s*\(",
            combined,
            re.IGNORECASE,
        )
    )


def _has_hardcoded_happiness_delta(search_text: str) -> bool:
    for match in _HARDCODED_HAPPINESS_DELTA.finditer(search_text):
        window = search_text[max(0, match.start() - 120) : match.end() + 120]
        if _HAPPINESS_DERIVED_FROM_CITY.search(window):
            continue
        return True
    for match in re.finditer(
        r"setHappiness\s*\(\s*happiness\s*\+\s*(\w+)\s*\)",
        search_text,
        re.IGNORECASE,
    ):
        var_name = match.group(1)
        if var_name.isdigit():
            window = search_text[max(0, match.start() - 120) : match.end() + 120]
            if not _HAPPINESS_DERIVED_FROM_CITY.search(window):
                return True
            continue
        derived_var = re.search(
            rf"\b{re.escape(var_name)}\s*=\s*[^;{{]+(?:grid|flat\s*\(|well|power|farm|house|food|resources|population|coins)",
            search_text,
            re.IGNORECASE,
        )
        if derived_var or _HAPPINESS_DERIVED_FROM_CITY.search(search_text):
            continue
        return True
    return False


def _happiness_wired_from_city_system(
    combined: str,
    reducer_actions: dict[str, str],
    tick_bodies: list[str],
) -> bool:
    if not _happiness_present_in_state(combined):
        return False
    search_text = "\n".join(tick_bodies) if tick_bodies else combined
    if not search_text.strip():
        search_text = combined
    if _has_hardcoded_happiness_delta(search_text):
        return False
    return bool(_HAPPINESS_DERIVED_FROM_CITY.search(search_text))


def _population_wired_from_city_system(
    combined: str,
    reducer_actions: dict[str, str],
    tick_bodies: list[str],
) -> bool:
    if _city_field_mutated(combined, reducer_actions, "population"):
        return True
    search_text = "\n".join(tick_bodies) + "\n" + combined
    return bool(
        re.search(
            r"(?:newPopulation|population\s*:)[^;{]{0,200}(?:grid|flat\s*\(|farm|house|well|power|building)",
            search_text,
            re.IGNORECASE | re.DOTALL,
        )
    )


def _placement_blocked_or_explained(
    combined: str,
    reducer_actions: dict[str, str],
) -> bool:
    for action in sorted(_CITY_PLACE_ACTIONS):
        body = reducer_actions.get(action, "")
        if body and _place_case_blocks_occupied_cells(body):
            return True
    if re.search(
        r"if\s*\(\s*!cell[^)]*\)\s*\{[^}]*dispatch\s*\(\s*\{\s*type:\s*['\"](?:PLACE_BUILDING|PLACE|BUILD)",
        combined,
        re.IGNORECASE | re.DOTALL,
    ):
        return True
    if re.search(
        r"Invalid placement|already occupied|occupied cell|cannot place",
        combined,
        re.IGNORECASE,
    ):
        return True
    return False


def _canonical_field_mutated(reducer_actions: dict[str, str], field: str) -> bool:
    mutation = re.compile(
        rf"{field}\s*:\s*(?:state\.{field}\s*[+\-]|Math\.|calculate|housing|"
        rf"(?!state\.{field}\s*[,}}\s])[^,\s{{])",
        re.IGNORECASE,
    )
    setter = re.compile(rf"set{field.title()}\s*\(|{field}\s*\+=|-=", re.IGNORECASE)
    for action, body in reducer_actions.items():
        if action.upper() in _CITY_RESTART_ACTIONS:
            continue
        if mutation.search(body) or setter.search(body):
            return True
    return False


def _city_field_mutated(
    combined: str,
    reducer_actions: dict[str, str],
    field: str,
) -> bool:
    if _canonical_field_mutated(reducer_actions, field):
        return True
    setter_name = field.title()
    if re.search(
        rf"set{setter_name}\s*\(\s*(?:prev\s*=>|new{setter_name}|[^0\s)])",
        combined,
        re.IGNORECASE,
    ):
        return True
    if re.search(
        rf"let\s+new{setter_name}\s*=|const\s+new{setter_name}\s*=",
        combined,
        re.IGNORECASE,
    ) and re.search(rf"set{setter_name}\s*\(\s*new{setter_name}", combined, re.IGNORECASE):
        return True
    return False


def _restart_reseeds_city(combined: str, reducer_actions: dict[str, str]) -> bool:
    for action_type, body in reducer_actions.items():
        if action_type.upper() not in _CITY_RESTART_ACTIONS:
            continue
        if re.search(r"return\s+initial(?:Game)?State\b", body, re.IGNORECASE):
            if re.search(r"grid:\s*Array|grid:\s*\[", combined, re.IGNORECASE):
                return True
        if re.search(r"return\s*\{[^}]*grid\s*:", body, re.IGNORECASE | re.DOTALL):
            if re.search(r"food:|coins:|day:", body, re.IGNORECASE):
                return True
        if _NOOP_RETURN.search(body.strip()):
            return False
    if re.search(
        r"(?:restartGame|restartCity|handleRestart|resetCity)\s*=\s*\([^)]*\)\s*=>\s*\{",
        combined,
        re.IGNORECASE,
    ):
        if re.search(
            r"setGrid\s*\(|setResources\s*\(|setDay\s*\(\s*1|setPopulation\s*\(\s*0|setGameResult\s*\(\s*null",
            combined,
            re.IGNORECASE,
        ):
            return True
    if re.search(
        r"onRestart[^;{]{0,160}dispatch\s*\(\s*\{\s*type:\s*['\"](?:RESTART|NEW_CITY|RESET)['\"]",
        combined,
        re.IGNORECASE | re.DOTALL,
    ):
        restart_body = ""
        for action_type, body in reducer_actions.items():
            if action_type.upper() in {"RESTART", "NEW_CITY", "RESET"}:
                restart_body = body
                break
        if restart_body and re.search(
            r"return\s+initial(?:Game)?State\b", restart_body, re.IGNORECASE
        ):
            return True
    return False


def _inspect_city_building_palette(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_city_builder_game(plan.user_message):
        return []
    if not _PROMPT_CITY_BUILDING_TYPES.search(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    path = _first_path_matching(
        _js_sources(file_changes),
        r"Palette|Grid|App|reducer|Game",
    )
    issues: list[ScaffoldQualityIssue] = []
    if not _has_building_palette(combined):
        issues.append(
            ScaffoldQualityIssue(
                code="city_missing_building_palette",
                message=(
                    "City-builder prompt expects multiple building types but no "
                    "selectable building palette or catalog exists"
                ),
                path=path,
            )
        )
    if _hardcoded_single_building_placement(combined):
        issues.append(
            ScaffoldQualityIssue(
                code="city_single_building_only",
                message=(
                    "City-builder placement hardcodes a single building type (e.g. house) "
                    "instead of using a selected palette choice"
                ),
                path=path,
            )
        )
    return issues


def _inspect_city_placement_validity(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_city_builder_game(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    reducer_actions = _collect_reducer_actions(file_changes)
    path = _first_path_matching(_js_sources(file_changes), r"PLACE|Grid|reducer|Game")
    has_place_case = any(reducer_actions.get(action) for action in _CITY_PLACE_ACTIONS)
    if not has_place_case:
        return []
    if _placement_blocked_or_explained(combined, reducer_actions):
        return []
    return [
        ScaffoldQualityIssue(
            code="city_invalid_placement_not_blocked",
            message=(
                "City-builder placement overwrites grid cells without rejecting "
                "occupied cells or showing invalid placement feedback"
            ),
            path=path,
        )
    ]


def _inspect_city_production_tick(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_city_builder_game(plan.user_message):
        return []
    if not re.search(
        r"day|turn|produce|production|food|coins|farm|house|well|power",
        plan.user_message,
        re.I,
    ):
        return []
    combined = _combined_js_source(file_changes)
    reducer_actions = _collect_reducer_actions(file_changes)
    tick_bodies = _collect_day_tick_bodies(combined, reducer_actions)
    path = _first_path_matching(
        _js_sources(file_changes),
        r"END_DAY|NEXT_DAY|endDay|nextDay|reducer|Game|App",
    )
    issues: list[ScaffoldQualityIssue] = []

    if not tick_bodies:
        if re.search(r"food|coins", combined, re.I):
            issues.append(
                ScaffoldQualityIssue(
                    code="city_production_not_wired",
                    message=(
                        "City-builder prompt expects day/turn production but no END_DAY/endDay "
                        "tick mutates resources from placed buildings"
                    ),
                    path=path,
                )
            )
        return issues

    resource_bodies = [body for body in tick_bodies if _tick_body_mutates_resources(body)]
    if not resource_bodies and re.search(r"food|coins", combined, re.I):
        issues.append(
            ScaffoldQualityIssue(
                code="city_resources_display_only",
                message=(
                    "City-builder resource counters exist but day/turn tick does not "
                    "mutate food/coins from grid building production"
                ),
                path=path,
            )
        )
        return issues

    grid_derived = all(
        _end_day_derives_production_from_grid(body) for body in resource_bodies
    )
    if not grid_derived:
        issues.append(
            ScaffoldQualityIssue(
                code="city_production_not_wired",
                message=(
                    "City-builder day/turn production uses hardcoded or population-only deltas "
                    "instead of counting placed farms/houses/wells/power on the grid"
                ),
                path=path,
            )
        )
    elif _has_unused_building_production_catalog(combined, tick_bodies):
        issues.append(
            ScaffoldQualityIssue(
                code="city_production_not_wired",
                message=(
                    "City-builder building production catalog exists but END_DAY/endDay "
                    "does not apply it to food/coins from grid building counts"
                ),
                path=path,
            )
        )
    return issues


def _inspect_city_population_happiness(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_city_builder_game(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    reducer_actions = _collect_reducer_actions(file_changes)
    tick_bodies = _collect_day_tick_bodies(combined, reducer_actions)
    path = _first_path_matching(
        _js_sources(file_changes),
        r"population|happiness|Resource|reducer|Game|App",
    )
    issues: list[ScaffoldQualityIssue] = []

    if _PROMPT_CITY_POPULATION_HAPPINESS.search(plan.user_message or ""):
        if re.search(r"population", combined, re.I) and not _population_wired_from_city_system(
            combined, reducer_actions, tick_bodies
        ):
            issues.append(
                ScaffoldQualityIssue(
                    code="city_population_not_wired",
                    message=(
                        "City-builder population is displayed but never mutated by placement "
                        "or day/turn production rules"
                    ),
                    path=path,
                )
            )

    if _prompt_requests_happiness(plan.user_message):
        if not _happiness_present_in_state(combined):
            issues.append(
                ScaffoldQualityIssue(
                    code="city_happiness_not_wired",
                    message=(
                        "City-builder prompt requests happiness but canonical state/UI "
                        "has no happiness counter or field"
                    ),
                    path=path,
                )
            )
        elif not _happiness_wired_from_city_system(combined, reducer_actions, tick_bodies):
            issues.append(
                ScaffoldQualityIssue(
                    code="city_happiness_not_wired",
                    message=(
                        "City-builder happiness must be derived from canonical grid/building/"
                        "resource state on day/turn ticks — not hardcoded deltas such as "
                        "happinessChange = 1 or setHappiness(happiness + 1)"
                    ),
                    path=path,
                )
            )
    return issues


def _inspect_city_goal_fail_restart(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_city_builder_game(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    reducer_actions = _collect_reducer_actions(file_changes)
    path = _first_path_matching(
        _js_sources(file_changes),
        r"result|Game|reducer|Restart|App",
    )
    issues: list[ScaffoldQualityIssue] = []
    if _PROMPT_CITY_POPULATION_GOAL.search(plan.user_message) and not _POPULATION_GOAL_WIN.search(
        combined
    ):
        issues.append(
            ScaffoldQualityIssue(
                code="city_goal_not_wired",
                message=(
                    "City-builder prompt requires population goal win by day limit but "
                    "code lacks population threshold win handling"
                ),
                path=path,
            )
        )
    if _PROMPT_CITY_FOOD_LOSS.search(plan.user_message) and not _FOOD_FAIL_CONDITION.search(
        combined
    ):
        issues.append(
            ScaffoldQualityIssue(
                code="city_fail_condition_not_wired",
                message=(
                    "City-builder prompt requires food-loss fail condition but code "
                    "does not check food <= 0 or equivalent"
                ),
                path=path,
            )
        )
    if _PROMPT_CITY_RESTART.search(plan.user_message) and re.search(
        r"RESTART|New City|restart", combined, re.IGNORECASE
    ):
        if not _restart_reseeds_city(combined, reducer_actions):
            issues.append(
                ScaffoldQualityIssue(
                    code="city_restart_not_seeded",
                    message=(
                        "City-builder restart/new city control does not reseed grid, "
                        "resources, day, and result state"
                    ),
                    path=path,
                )
            )
    return issues


def _inspect_city_builder_quality(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    issues: list[ScaffoldQualityIssue] = []
    issues.extend(_inspect_city_building_palette(plan, file_changes))
    issues.extend(_inspect_city_placement_validity(plan, file_changes))
    issues.extend(_inspect_city_production_tick(plan, file_changes))
    issues.extend(_inspect_city_population_happiness(plan, file_changes))
    issues.extend(_inspect_city_goal_fail_restart(plan, file_changes))
    return issues


def _inspect_tactics_quality(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    issues: list[ScaffoldQualityIssue] = []
    issues.extend(_inspect_tactics_unit_seeding(plan, file_changes))
    issues.extend(_inspect_tactics_interaction_wiring(plan, file_changes))
    issues.extend(_inspect_tactics_ranges_and_enemy_turn(plan, file_changes))
    issues.extend(_inspect_tactics_attack_mutation(plan, file_changes))
    issues.extend(_inspect_tactics_battle_result_and_restart(plan, file_changes))
    return issues


def _inspect_import_export(
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    files = _file_map(file_changes)
    default_exports: dict[str, str] = {}
    for path, content in files.items():
        if not path.endswith((".tsx", ".ts", ".jsx", ".js")):
            continue
        m = _DEFAULT_EXPORT.search(content)
        if m:
            default_exports[path] = m.group(1)

    issues: list[ScaffoldQualityIssue] = []
    for path, content in files.items():
        if not path.endswith((".tsx", ".ts", ".jsx", ".js")):
            continue
        for m in _NAMED_IMPORT.finditer(content):
            name, rel = m.group(1), m.group(2)
            target = _resolve_import_path(path, rel)
            target_base = target.rsplit("/", 1)[-1]
            for candidate, exported in default_exports.items():
                cand_base = candidate.rsplit("/", 1)[-1].replace(".tsx", "").replace(".ts", "")
                if exported == name and (
                    candidate == target
                    or candidate.endswith(f"/{target_base}.tsx")
                    or candidate.endswith(f"/{target_base}.ts")
                    or cand_base == target_base
                ):
                    issues.append(
                        ScaffoldQualityIssue(
                            code="import_export_mismatch",
                            message=(
                                f"Named import {{{name}}} from '{rel}' but "
                                f"{candidate} default-exports {exported}"
                            ),
                            path=path,
                        )
                    )
                    break
    return issues


def inspect_generated_scaffold_quality(
    file_changes: list[tuple[str, str]],
    *,
    plan: Plan | None = None,
) -> list[ScaffoldQualityIssue]:
    """Return playability issues found in generated scaffold files."""
    issues: list[ScaffoldQualityIssue] = []
    for path, content in file_changes:
        if not path.endswith((".tsx", ".ts", ".jsx", ".js")):
            continue
        issues.extend(_inspect_reducer_noops(path, content))
        issues.extend(_inspect_stub_comments(path, content))
        issues.extend(_inspect_empty_or_log_handlers(path, content))
        issues.extend(_inspect_stale_state_win_checks(path, content))
    if plan is not None:
        issues.extend(_inspect_timer_duration(plan, file_changes))
        issues.extend(_inspect_missing_result_state(plan, file_changes))
        issues.extend(_inspect_rhythm_miss_feedback_weak(plan, file_changes))
        issues.extend(_inspect_rhythm_result_state_weak(plan, file_changes))
        issues.extend(_inspect_empty_deck_seed(plan, file_changes))
        issues.extend(_inspect_empty_reward_pool(plan, file_changes))
        issues.extend(_inspect_reward_choice_not_wired(plan, file_changes))
        issues.extend(_inspect_discard_not_wired(plan, file_changes))
        issues.extend(_inspect_deck_builder_run_result_missing(plan, file_changes))
        issues.extend(_inspect_missing_victory_wiring(plan, file_changes))
        issues.extend(_inspect_ignored_seed_payload(plan, file_changes))
        issues.extend(_inspect_dashboard_quality(plan, file_changes))
        issues.extend(_inspect_tactics_quality(plan, file_changes))
        issues.extend(_inspect_city_builder_quality(plan, file_changes))
    issues.extend(_inspect_import_export(file_changes))
    issues.extend(_inspect_dispatch_reducer_mismatch(file_changes))
    # De-dupe by (code, path, message)
    seen: set[tuple[str, str | None, str]] = set()
    unique: list[ScaffoldQualityIssue] = []
    for issue in issues:
        key = (issue.code, issue.path, issue.message)
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique


def scaffold_quality_repair_enabled(env: dict[str, str] | None = None) -> bool:
    mapping = env if env is not None else os.environ
    raw = (mapping.get("HAM_SCAFFOLD_QUALITY_REPAIR") or "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def build_scaffold_repair_prompt(
    plan: Plan,
    file_changes: list[tuple[str, str]],
    issues: list[ScaffoldQualityIssue],
    *,
    base_system_prompt: str,
) -> list[dict[str, str]]:
    """Build LLM messages for a single focused scaffold repair pass."""
    issue_lines = "\n".join(
        f"- [{i.code}] {i.message}"
        + (f" ({i.path})" if i.path else "")
        + (f": {i.detail}" if i.detail else "")
        for i in issues[:12]
    )
    file_summary = "\n\n".join(
        f"--- {path} ---\n{content[:4000]}"
        for path, content in file_changes[:16]
    )
    repair_system = (
        base_system_prompt
        + "\n\nScaffold repair mode:\n"
        "- Keep the same file paths and architecture when possible.\n"
        "- Do not create a larger empty component shell.\n"
        "- Implement the missing core loop and wire controls to state transitions.\n"
        "- Remove no-op reducer cases; every declared primary action must mutate state meaningfully.\n"
        "- Verify every primary control changes canonical game state (not just logs or local UI text).\n"
        "- Compute next state values first; derive win/loss from those next values, not stale closure reads.\n"
        "- Do not check old HP/resources immediately after setState — use functional updates or local next values.\n"
        "- Avoid stale-state win/loss checks: compute next HP/resources before checking result conditions.\n"
        "- When the prompt specifies a duration (e.g. 60 seconds), use an explicit round constant "
        "(useState(60), ROUND_SECONDS = 60, or 60000 ms) and show a final score when time expires.\n"
        "- When the prompt requires winning/surviving/final score, add visible win/loss/result UI and restart/reset.\n"
        "- Make resource/turn loops strategically meaningful — allocations and day ticks must change resources.\n"
        "- Ensure visible feedback and result/win state where the plan requires them.\n"
        "- Fix import/export consistency (default export ↔ default import).\n"
        "- Output ONLY the same JSON object schema.\n"
    )
    issue_codes = {issue.code for issue in issues}
    if "timer_duration_mismatch" in issue_codes:
        repair_system += (
            "\nTimer repair focus:\n"
            "- Replace elapsed-only counters (e.g. elapsedTime from 0 to >= 59) with a 60-second countdown.\n"
            "- Initialize round duration to 60 seconds (or 60000 ms) and lock input when it reaches zero.\n"
            "- Display final score/WPM/accuracy on expiry.\n"
        )
    if "missing_result_state" in issue_codes or "missing_victory_wiring" in issue_codes:
        repair_system += (
            "\nResult-state repair focus:\n"
            "- Wire victory when enemy HP reaches zero (or survival goal met) into visible result UI.\n"
            "- Include win/loss/completion state and a restart or play-again control.\n"
        )
    rhythm_codes = issue_codes & {
        "missing_result_state",
        "rhythm_miss_feedback_weak",
        "rhythm_result_state_weak",
    }
    if _prompt_is_rhythm_timing_game(plan.user_message) and rhythm_codes:
        repair_system += (
            "\nRhythm/timing repair focus:\n"
            "- Miss taps must show visible feedback and/or update miss counters or score/result metrics, "
            "not only reset streak.\n"
            "- Derive final score from the current tally at round end (functional score read or local "
            "nextScore), not stale closure capture.\n"
            "- Show a result panel with final score, optional perfect/good/miss breakdown, and "
            "play-again/retry control.\n"
            "- Apply timing judgments to canonical state before checking round completion.\n"
        )
    card_codes = issue_codes & {
        "empty_deck_seed",
        "ignored_seed_payload",
        "missing_victory_wiring",
        "noop_reducer_action",
        "dispatch_reducer_mismatch",
    }
    if card_codes and _prompt_is_card_deck_game(plan.user_message):
        repair_system += (
            "\nCard-deck repair focus:\n"
            "- Define non-empty card objects (name, damage/power/effect) and a shuffled deck.\n"
            "- Seed an initial hand or provide an immediate draw path with playable cards.\n"
            "- If cards are generated in setup/useEffect, pass them into canonical game state.\n"
            "- If dispatching NEW_GAME/RESET/START with payload or deck/hand fields, the reducer "
            "must read action.payload (or action.deck/hand) and install them into state.\n"
            "- Do not generate card arrays disconnected from reducer state; deck/hand must be "
            "non-empty at game start, or Draw must immediately populate hand from a non-empty deck.\n"
            "- Do not leave deck/hand as empty arrays unless another implemented action immediately fills them.\n"
            "- On PLAY_CARD: remove from hand, apply effect to enemy/player HP, push card to discard.\n"
            "- When enemy HP reaches zero, set visible win/result state (dispatch END_GAME or equivalent).\n"
            "- Restart/new round resets deck, hand, discard, enemy HP, and result state.\n"
        )
    deck_builder_codes = issue_codes & {
        "empty_deck_seed",
        "empty_reward_pool",
        "reward_choice_not_wired",
        "discard_not_wired",
        "missing_restart_action",
        "ignored_seed_payload",
        "missing_victory_wiring",
        "noop_reducer_action",
    }
    if deck_builder_codes and _prompt_is_deck_builder_game(plan.user_message):
        repair_system += (
            "\nDeck-builder repair focus:\n"
            "- Seed a non-empty starter deck and initial hand with playable card objects.\n"
            "- If using INITIALIZE/NEW_GAME on mount, reducer must install deck/hand from payload "
            "or a non-empty card list — do not leave deck/hand empty after init.\n"
            "- Define a non-empty reward pool (2–3 card options) shown after each encounter win.\n"
            "- On reward choice: append the selected card to the canonical deck array.\n"
            "- On PLAY_CARD: remove from hand, apply effect to enemy/player HP, push card to discard.\n"
            "- Track encounter/run progress (encounter count or run-complete threshold).\n"
            "- Show visible run result / win-loss state when the run completes.\n"
            "- Add restart/new-run/play-again that resets deck, hand, discard, enemy, and run state.\n"
            "- Do not leave rewards[], discard, or deck disconnected from reducer mutations.\n"
        )
    tactics_codes = issue_codes & {
        "tactics_empty_unit_seed",
        "tactics_seed_not_applied",
        "tactics_grid_not_wired",
        "tactics_action_not_wired",
        "tactics_missing_movement_range",
        "tactics_missing_attack_range",
        "tactics_enemy_turn_not_wired",
        "tactics_missing_battle_result",
        "tactics_restart_not_seeded",
        "tactics_inplace_attack_mutation",
        "noop_reducer_action",
        "dispatch_reducer_mismatch",
    }
    if tactics_codes and _prompt_is_tactics_game(plan.user_message):
        repair_system += (
            "\nTurn-based tactics repair focus:\n"
            "- Use a fixed non-empty grid (e.g. 5x5) with player and enemy units in canonical state.\n"
            "- Dispatch INIT_GAME/START on mount or provide non-empty initial units in reducer state.\n"
            "- Clicking/tapping a player unit must dispatch SELECT/SELECT_UNIT; track selectedUnit "
            "visually/structurally and use it to enable move/attack decisions.\n"
            "- Wire grid/unit click handlers to SELECT/MOVE/ATTACK dispatches (not move-only clicks).\n"
            "- Constrain moves with legal movement range (prefer Manhattan distance), disallow "
            "moving outside range or onto occupied cells, and update unit position immutably.\n"
            "- Wire ATTACK/ATTACK_UNIT from UI: enemy cell/unit click with selected player unit, "
            "or an Attack button/control; never leave ATTACK reducer case undispatched.\n"
            "- Constrain player attacks with attack range or distance checks on the ATTACK case "
            "before mutating HP; reject/ignore/disable out-of-range attacks (enemy-turn range "
            "logic alone is insufficient).\n"
            "- For ATTACK/ATTACK_UNIT: compute next units immutably (map/filter), reduce target HP "
            "through returned state, remove/mark defeated enemies, and derive win/loss from next state.\n"
            "- After player end turn, run a simple enemy turn that moves or attacks and mutates state.\n"
            "- Win when all enemies are defeated; loss when all player units are defeated; show result UI.\n"
            "- Restart/new battle must reseed grid, player units, enemy units, turn state, selected unit, "
            "and result state; INIT/RESET must not be no-op.\n"
            "- Do not leave reducer cases for SELECT/MOVE/ATTACK/END_TURN that are never dispatched.\n"
        )
    city_builder_codes = issue_codes & {
        "city_missing_building_palette",
        "city_single_building_only",
        "city_invalid_placement_not_blocked",
        "city_production_not_wired",
        "city_resources_display_only",
        "city_population_not_wired",
        "city_happiness_not_wired",
        "city_goal_not_wired",
        "city_fail_condition_not_wired",
        "city_restart_not_seeded",
        "noop_reducer_action",
        "dispatch_reducer_mismatch",
    }
    if city_builder_codes and _prompt_is_city_builder_game(plan.user_message):
        repair_system += (
            "\nCity-builder repair focus:\n"
            "- Output ONLY valid JSON matching the original scaffold schema (file_changes array). "
            "No markdown, prose, or commentary outside JSON.\n"
            "- Keep existing file paths and architecture when possible; patch gameplay loops only.\n"
            "- Provide 3–5 building types (house, farm, well, power or prompt equivalents) "
            "in a selectable building palette/catalog.\n"
            "- Track selectedBuilding/buildingType in state; placement must use the selected type.\n"
            "- Reject occupied grid cells with a guarded no-op or visible invalid placement feedback; "
            "never silently overwrite existing buildings.\n"
            "- END_DAY/endDay/nextDay must count placed farms/houses/wells/power from canonical "
            "grid state and derive food/coins/production from those counts — avoid hardcoded daily "
            "deltas that ignore the grid.\n"
            "- Keep happiness in canonical state with a visible counter; on each day/turn tick "
            "derive next happiness from placed wells/power/service buildings, food/resources, "
            "and population/housing pressure — never use hardcoded happinessChange = 1.\n"
            "- Mutate population from housing/building effects on the grid.\n"
            "- Win when population goal is reached by the day limit; fail when food runs out or "
            "goal is missed.\n"
            "- Show result state with win/loss reason; New City/restart reseeds grid, resources, "
            "day, selected building, happiness, and result state.\n"
        )
    if (
        "city_happiness_not_wired" in issue_codes
        and _prompt_is_city_builder_game(plan.user_message)
    ):
        repair_system += (
            "\nCity-builder happiness repair focus:\n"
            "- Replace hardcoded happiness deltas (happinessChange = 1, setHappiness(happiness + 1), "
            "state.happiness + 1) with calculations derived from canonical city state.\n"
            "- Count placed wells/power/service buildings from the grid on END_DAY/endDay.\n"
            "- Factor food shortage, resource pressure, and population/housing into next happiness.\n"
            "- Compute nextHappiness from those counts and update happiness together with day production.\n"
            "- Output ONLY valid JSON/file_changes — no prose outside JSON.\n"
        )
    dashboard_codes = issue_codes & {
        "dashboard_missing_requested_filter",
        "dashboard_dead_filter_control",
        "dashboard_missing_loading_error_states",
        "dashboard_missing_semantic_landmarks",
        "dashboard_missing_requested_chart_type",
    }
    if dashboard_codes and _prompt_is_dashboard_ui_core(plan.user_message):
        repair_system += (
            "\nDashboard repair focus:\n"
            "- Preserve a read-only/static dashboard lane: no backend/live data/auth/CRUD/payments behavior.\n"
            "- Do not omit requested dashboard regions. If prompt requests a local filter/search bar, include it.\n"
            "- Wire filter/search to canonical state (e.g. useState + onChange) and map visible effect to KPI/chart/table data.\n"
            "- If a filter is illustrative only, render it explicitly disabled/non-interactive (do not fake behavior).\n"
            "- Provide visible Empty / Loading / Error examples as static cards or panels (no live fetch implied).\n"
            "- Use semantic dashboard shell landmarks: explicit <header>, <nav>, and <main>, clear h1, and a real table structure.\n"
            "- Render every requested chart type (e.g. both line and bar) with meaningful sample data and labels.\n"
            "- Output ONLY valid JSON matching file_changes schema.\n"
        )
    user_content = (
        f"User request: {plan.user_message}\n\n"
        f"The previous scaffold failed automated playability checks:\n{issue_lines}\n\n"
        f"Repair the scaffold below. Implement state mutations for primary actions.\n\n"
        f"Previous files:\n{file_summary}"
    )
    return [
        {"role": "system", "content": repair_system},
        {"role": "user", "content": user_content},
    ]


def maybe_repair_generated_scaffold(
    result: Any,
    *,
    plan: Plan,
    api_key: str,
    model: str,
    scaffold_timeout: float,
    base_system_prompt: str,
    parse_result: Any,
    complete_chat: Any,
    env: dict[str, str] | None = None,
) -> Any:
    """Run one repair LLM pass when quality issues are detected; else return as-is."""
    if not scaffold_quality_repair_enabled(env):
        return result
    issues = inspect_generated_scaffold_quality(result.file_changes, plan=plan)
    if not issues:
        return result
    _LOG.info(
        "Scaffold quality: %d issue(s) detected for plan=%s — running one repair pass",
        len(issues),
        plan.plan_id,
    )
    messages = build_scaffold_repair_prompt(
        plan,
        result.file_changes,
        issues,
        base_system_prompt=base_system_prompt,
    )
    try:
        raw = complete_chat(
            messages,
            model_override=model,
            api_key_override=api_key,
            timeout_sec=scaffold_timeout,
        )
        repaired = parse_result(raw)
        remaining = inspect_generated_scaffold_quality(repaired.file_changes, plan=plan)
        if remaining:
            summary = ", ".join(
                f"{issue.code}@{issue.path or '?'}" for issue in remaining[:8]
            )
            _LOG.warning(
                "Scaffold quality: %d issue(s) remain after repair for plan=%s: %s",
                len(remaining),
                plan.plan_id,
                summary,
            )
        else:
            _LOG.info(
                "Scaffold quality repair cleared all detected issues for plan=%s",
                plan.plan_id,
            )
        _LOG.info(
            "Scaffold quality repair produced %d file(s) for plan=%s",
            len(repaired.file_changes),
            plan.plan_id,
        )
        return repaired
    except Exception as exc:  # noqa: BLE001
        _LOG.warning(
            "Scaffold quality repair failed for plan=%s (%s) — keeping original output",
            plan.plan_id,
            exc,
        )
        return result
