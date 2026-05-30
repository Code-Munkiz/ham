"""Lightweight static inspection and bounded repair for LLM scaffold playability."""

from __future__ import annotations

import logging
import os
import re
import json
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

_PROMPT_SAAS_DASHBOARD_CORE = re.compile(
    r"\bsaas\b.{0,120}\bdashboard\b|\bdashboard\b.{0,120}\bsaas\b",
    re.IGNORECASE,
)

_PROMPT_SAAS_DASHBOARD_SIGNALS = re.compile(
    r"workspace|project/resource|resource\s+(?:list|table)|usage|plan/status|upgrade",
    re.IGNORECASE,
)

_PROMPT_SAAS_SEMANTIC_TABLE_REQUEST = re.compile(
    r"header/nav/main/list/table|resource\s+(?:list|table)|project/resource\s+list",
    re.IGNORECASE,
)

_PROMPT_ADMIN_DASHBOARD_CORE = re.compile(
    r"\badmin\s+(?:dashboard|control\s+panel|panel|shell|console)\b|"
    r"\binternal\s+operations\s+dashboard\b|"
    r"\bback[- ]?office\b",
    re.IGNORECASE,
)

_PROMPT_ADMIN_DASHBOARD_SIGNALS = re.compile(
    r"sidebar|topbar|user/team|user\s+team|role\s*(?:and|/)?\s*permission|"
    r"review\s+queue|resource/user\s+table|resource\s+table|"
    r"audit(?:/activity)?\s+log|system\s+status|demo-mode|read-only",
    re.IGNORECASE,
)

_PROMPT_ADMIN_SEMANTIC_TABLE_REQUEST = re.compile(
    r"header/nav/main/list/table|resource/user\s+table|resource\s+table|user\s+table",
    re.IGNORECASE,
)

_PROMPT_SALES_OPS_DASHBOARD_CORE = re.compile(
    r"\bsales\s+ops\s+dashboard\b|"
    r"\bsales\s+operations\s+dashboard\b|"
    r"\brevops\s+dashboard\b|"
    r"\brevenue\s+operations\s+dashboard\b|"
    r"\bcommission\s+dashboard\b|"
    r"\brevenue\s+recovery\s+dashboard\b",
    re.IGNORECASE,
)

_PROMPT_SALES_OPS_DASHBOARD_SIGNALS = re.compile(
    r"executive\s+summary|agent(?:/team)?\s+performance|team\s+performance|sales\s+activity|"
    r"pipeline(?:\s+stage)?\s+movement|commission\s+summary|commission\s+earned|commission\s+pending|"
    r"clawbacks?|chargebacks?|payout\s+status|revenue\s+recovery|recoverable\s+balance|"
    r"recovered\s+dollars|aging\s+buckets?|exception\s+queue|process\s+bottleneck|"
    r"activity(?:/audit)?\s+feed|filters?",
    re.IGNORECASE,
)

_PROMPT_SALES_OPS_SEMANTIC_REQUEST = re.compile(
    r"header/nav/main/table/list/chart|semantic|financial\s+table|table/list/chart",
    re.IGNORECASE,
)

_SAAS_LIVE_FETCH_IMPL = re.compile(
    r"\bfetch\s*\(|\baxios\b|\breact-query\b|\bswr\b|\bwebsocket\b|\beventsource\b|"
    r"/api\b|\bapi\s+call\b|simulate\s+api|mock\s+api|live\s+retry|retry\s+request",
    re.IGNORECASE,
)

_SAAS_ASYNC_LOADING_FLOW = re.compile(
    r"useEffect\s*\(|setTimeout\s*\(|setInterval\s*\(|async\s+function|await\s+|"
    r"if\s*\(\s*loading\s*\)\s*return|polling|retry",
    re.IGNORECASE,
)

_ADMIN_LIVE_FETCH_IMPL = re.compile(
    r"\bfetch\s*\(|\baxios\b|\bxmlhttprequest\b|\breact-query\b|\bswr\b|"
    r"\bwebsocket\b|\beventsource\b|/api\b|\bapi\s+call\b|simulate\s+api|"
    r"mock\s+api|live\s+retry|retry\s+request",
    re.IGNORECASE,
)

_ADMIN_ASYNC_LOADING_FLOW = re.compile(
    r"useEffect\s*\(|setTimeout\s*\(|setInterval\s*\(|async\s+function|await\s+|polling|retry",
    re.IGNORECASE,
)

_ADMIN_DESTRUCTIVE_VERBS = re.compile(
    r"\b(delete|remove|destroy|ban|suspend|revoke|approve|reject|edit|update|create|invite|provision)\b",
    re.IGNORECASE,
)

_ADMIN_MUTATION_IMPL = re.compile(
    r"\bset[A-Z]\w*\s*\(.*?(?:=>|filter\s*\(|map\s*\(|concat\s*\(|splice\s*\(|push\s*\(|pop\s*\(|shift\s*\(|unshift\s*\()|"
    r"\.(?:filter|map|concat|splice|push|pop|shift|unshift)\s*\(",
    re.IGNORECASE | re.DOTALL,
)

_SALES_OPS_FORBIDDEN_IMPL = re.compile(
    r"\bpayroll\s+system\b|"
    r"\bpayment\s+processing\b|"
    r"\baccounting\s+ledger\b|"
    r"\basc\s*606\s+engine\b|"
    r"\blegal\s+collections\s+automation\b|"
    r"\bcrm\s+sync\b|"
    r"\b(?:backend|api|database)\s+integrations?\b|"
    r"\blive\s+(?:crm|api|database)\b|"
    r"\breal\s+(?:customer\s+)?pii\b|"
    r"\bcustomer\s+database\b|"
    r"\breal\s+(?:bank|payment)\s+identifiers?\b|"
    r"\blive\s+dunning\b|"
    r"\b(?:telephony|sms)\s+automation\b|"
    r"\bregulated\s+financial\s+advice\b|"
    r"\bpayout\s+disbursement\b|"
    r"\b(?:trading|order\s+book|fintech)\b|"
    r"\bcompliance\s+certification\s+claims?\b",
    re.IGNORECASE,
)

_SALES_OPS_NEGATED_FORBIDDEN_IMPL_PATTERNS: tuple[str, ...] = (
    r"\b(?:no|without|sans|zero|free\s+of)\s+(?:a\s+|an\s+|any\s+|the\s+)?payroll(?:\s+system)?\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+payments?\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+payment\s+processing\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+accounting(?:\s+ledger)?\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+asc\s*606(?:\s+engine)?\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+legal\s+collections\s+automation\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+crm(?:\s+sync)?\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+(?:a\s+|an\s+|any\s+|the\s+)?backend\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+(?:a\s+|an\s+|any\s+|the\s+)?api\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+(?:a\s+|an\s+|any\s+|the\s+)?database\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+real\s+pii\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+real\s+bank\s+or\s+payment\s+identifiers?\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+real\s+(?:bank|payment)\s+identifiers?\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+bank\s+identifiers?\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+payment\s+identifiers?\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+live\s+dunning\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+telephony(?:\s+or\s+sms\s+automation)?\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+sms(?:\s+automation)?\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+regulated\s+financial\s+advice\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+real\s+payout\s+approval\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+payout\s+(?:approval|disbursement)\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+trading\s+dashboard\b",
    r"\b(?:no|without|sans|zero|free\s+of)\s+compliance\s+certification\s+claims?\b",
)

_SAAS_BLOCKING_QUALITY_CODES = frozenset(
    {
        "saas_missing_loading_error_states",
        "saas_live_fetch_impl_detected",
        "saas_missing_semantic_resource_table",
    }
)

_ADMIN_BLOCKING_QUALITY_CODES = frozenset(
    {
        "admin_missing_loading_error_states",
        "admin_live_fetch_impl_detected",
        "admin_missing_semantic_resource_table",
        "admin_destructive_action_live_mutation",
    }
)

_SALES_OPS_BLOCKING_QUALITY_CODES = frozenset(
    {
        "sales_ops_missing_domain_regions",
        "sales_ops_missing_loading_error_states",
        "sales_ops_missing_semantic_financial_structure",
        "sales_ops_forbidden_financial_impl_detected",
    }
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


def _prompt_is_saas_dashboard_core(prompt: str | None) -> bool:
    if not prompt:
        return False
    if not _PROMPT_SAAS_DASHBOARD_CORE.search(prompt):
        return False
    return bool(_PROMPT_SAAS_DASHBOARD_SIGNALS.search(prompt))


def _prompt_requests_saas_state_examples(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_DASHBOARD_STATE_REQUEST.search(prompt))


def _prompt_requests_saas_semantic_table(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_SAAS_SEMANTIC_TABLE_REQUEST.search(prompt))


def _prompt_is_admin_dashboard_core(prompt: str | None) -> bool:
    if not prompt:
        return False
    if not _PROMPT_ADMIN_DASHBOARD_CORE.search(prompt):
        return False
    return bool(_PROMPT_ADMIN_DASHBOARD_SIGNALS.search(prompt))


def _prompt_requests_admin_state_examples(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_DASHBOARD_STATE_REQUEST.search(prompt))


def _prompt_requests_admin_semantic_table(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_ADMIN_SEMANTIC_TABLE_REQUEST.search(prompt))


def _prompt_is_sales_ops_dashboard_core(prompt: str | None) -> bool:
    if not prompt:
        return False
    if not _PROMPT_SALES_OPS_DASHBOARD_CORE.search(prompt):
        return False
    return bool(_PROMPT_SALES_OPS_DASHBOARD_SIGNALS.search(prompt))


def _prompt_requests_sales_ops_state_examples(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_DASHBOARD_STATE_REQUEST.search(prompt))


def _prompt_requests_sales_ops_semantic_structure(prompt: str | None) -> bool:
    if not prompt:
        return False
    if _PROMPT_SALES_OPS_SEMANTIC_REQUEST.search(prompt):
        return True
    return bool(_PROMPT_DASHBOARD_TABLE.search(prompt))


def _strip_sales_ops_negated_forbidden_markers(text: str) -> str:
    stripped = text
    for pattern in _SALES_OPS_NEGATED_FORBIDDEN_IMPL_PATTERNS:
        stripped = re.sub(pattern, " ", stripped, flags=re.IGNORECASE)
    return stripped


_SALES_OPS_REQUIRED_REGION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("executive summary", (r"\bexecutive\s+summary\b",)),
    ("agent/team performance", (r"\bagent(?:/team)?\s+performance\b", r"\bteam\s+performance\b")),
    ("sales activity metrics", (r"\bsales\s+activity\s+metrics?\b", r"\bsales\s+activity\b")),
    (
        "pipeline/stage movement",
        (r"\bpipeline(?:\s+stage)?\s+movement\b", r"\bstage\s+movement\b"),
    ),
    ("commission summary", (r"\bcommission\s+summary\b",)),
    (
        "commission earned/pending",
        (
            r"\bcommission\s+earned\b",
            r"\bcommission\s+pending\b",
            r"\bearned\s+and\s+pending\b",
        ),
    ),
    ("clawbacks/chargebacks", (r"\bclawbacks?\b", r"\bchargebacks?\b")),
    ("payout status display", (r"\bpayout\s+status\b",)),
    ("revenue recovery summary", (r"\brevenue\s+recovery\s+summary\b", r"\brecovery\s+summary\b")),
    (
        "recoverable balance/recovered dollars",
        (r"\brecoverable\s+balance\b", r"\brecovered\s+dollars\b"),
    ),
    ("aging buckets", (r"\baging\s+buckets?\b",)),
    ("recovery exception queue", (r"\brecovery\s+exception\s+queue\b", r"\bexception\s+queue\b")),
    ("process bottleneck panel", (r"\bprocess\s+bottleneck(?:\s+panel)?\b",)),
    ("activity/audit feed", (r"\bactivity(?:/audit)?\s+feed\b", r"\baudit\s+feed\b")),
    (
        "filters by date/team/agent/status/stage",
        (r"\bdate/team/agent/status/stage\b", r"\b(?:date|team|agent|status|stage)\s+filters?\b"),
    ),
)


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


def _inspect_saas_missing_loading_error_states(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if (
        plan is None
        or not _prompt_is_saas_dashboard_core(plan.user_message)
        or not _prompt_requests_saas_state_examples(plan.user_message)
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
        r"SaaS|Dashboard|App|Resource|Activity|State",
    )
    return [
        ScaffoldQualityIssue(
            code="saas_missing_loading_error_states",
            message=(
                "SaaS dashboard prompt requests visible empty/loading/error examples, but missing: "
                + ", ".join(missing_parts)
            ),
            path=path,
        )
    ]


def _inspect_saas_live_fetch_impl(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_saas_dashboard_core(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    if not _SAAS_LIVE_FETCH_IMPL.search(combined) and not _SAAS_ASYNC_LOADING_FLOW.search(combined):
        return []
    path = _first_path_matching(
        _js_sources(file_changes),
        r"SaaS|Dashboard|App|Data|Resource|Activity|main",
    )
    return [
        ScaffoldQualityIssue(
            code="saas_live_fetch_impl_detected",
            message=(
                "SaaS dashboard must stay static/local; remove live-fetch/API-style async flow "
                "(fetch/useEffect/setTimeout loading simulation)"
            ),
            path=path,
        )
    ]


def _inspect_saas_missing_semantic_resource_table(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if (
        plan is None
        or not _prompt_is_saas_dashboard_core(plan.user_message)
        or not _prompt_requests_saas_semantic_table(plan.user_message)
    ):
        return []
    combined = _combined_js_source(file_changes)
    has_main = bool(_DASHBOARD_MAIN.search(combined))
    has_header = bool(_DASHBOARD_HEADER.search(combined))
    has_nav = bool(_DASHBOARD_NAV.search(combined))
    has_table = bool(_DASHBOARD_TABLE.search(combined))
    if has_main and has_header and has_nav and has_table:
        return []
    missing_parts: list[str] = []
    if not has_header:
        missing_parts.append("header")
    if not has_nav:
        missing_parts.append("nav")
    if not has_main:
        missing_parts.append("main")
    if not has_table:
        missing_parts.append("table")
    path = _first_path_matching(
        _js_sources(file_changes),
        r"SaaS|Dashboard|App|Resource|Table|Nav|Header",
    )
    return [
        ScaffoldQualityIssue(
            code="saas_missing_semantic_resource_table",
            message=(
                "SaaS dashboard semantic shell/table is incomplete; missing: "
                + ", ".join(missing_parts)
            ),
            path=path,
        )
    ]


def _inspect_saas_dashboard_quality(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    issues: list[ScaffoldQualityIssue] = []
    issues.extend(_inspect_saas_missing_loading_error_states(plan, file_changes))
    issues.extend(_inspect_saas_live_fetch_impl(plan, file_changes))
    issues.extend(_inspect_saas_missing_semantic_resource_table(plan, file_changes))
    return issues


def _has_saas_blocking_quality_issues(issues: list[ScaffoldQualityIssue]) -> bool:
    return any(issue.code in _SAAS_BLOCKING_QUALITY_CODES for issue in issues)


def _inspect_admin_missing_loading_error_states(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if (
        plan is None
        or not _prompt_is_admin_dashboard_core(plan.user_message)
        or not _prompt_requests_admin_state_examples(plan.user_message)
    ):
        return []
    combined = _combined_js_source(file_changes)
    has_empty = bool(_DASHBOARD_EMPTY_STATE.search(combined))
    has_loading = bool(_DASHBOARD_LOADING_STATE.search(combined))
    has_error = bool(_DASHBOARD_ERROR_STATE.search(combined))
    has_static_local = bool(
        re.search(r"\b(static|local|demo|illustrative|preview)\b", combined, re.IGNORECASE)
    )
    if has_empty and has_loading and has_error and has_static_local:
        return []
    missing_parts: list[str] = []
    if not has_empty:
        missing_parts.append("empty")
    if not has_loading:
        missing_parts.append("loading")
    if not has_error:
        missing_parts.append("error")
    if not has_static_local:
        missing_parts.append("static/local wording")
    path = _first_path_matching(
        _js_sources(file_changes),
        r"Admin|Dashboard|App|Resource|Review|Audit|Status",
    )
    return [
        ScaffoldQualityIssue(
            code="admin_missing_loading_error_states",
            message=(
                "Admin dashboard prompt requests visible static/local empty/loading/error examples, "
                "but missing: " + ", ".join(missing_parts)
            ),
            path=path,
        )
    ]


def _inspect_admin_live_fetch_impl(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_admin_dashboard_core(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    if not _ADMIN_LIVE_FETCH_IMPL.search(combined) and not _ADMIN_ASYNC_LOADING_FLOW.search(combined):
        return []
    path = _first_path_matching(
        _js_sources(file_changes),
        r"Admin|Dashboard|App|Data|Resource|Review|main",
    )
    return [
        ScaffoldQualityIssue(
            code="admin_live_fetch_impl_detected",
            message=(
                "Admin dashboard must stay static/local; remove live-fetch/API-style async flow "
                "(fetch/useEffect/setTimeout/axios/XMLHttpRequest)"
            ),
            path=path,
        )
    ]


def _inspect_admin_missing_semantic_resource_table(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if (
        plan is None
        or not _prompt_is_admin_dashboard_core(plan.user_message)
        or not _prompt_requests_admin_semantic_table(plan.user_message)
    ):
        return []
    combined = _combined_js_source(file_changes)
    has_main = bool(_DASHBOARD_MAIN.search(combined))
    has_header = bool(_DASHBOARD_HEADER.search(combined))
    has_nav = bool(_DASHBOARD_NAV.search(combined))
    has_table = bool(_DASHBOARD_TABLE.search(combined))
    has_list = bool(re.search(r"<ul\b|<ol\b", combined, re.IGNORECASE))
    if has_main and has_header and has_nav and has_table and has_list:
        return []
    missing_parts: list[str] = []
    if not has_header:
        missing_parts.append("header")
    if not has_nav:
        missing_parts.append("nav")
    if not has_main:
        missing_parts.append("main")
    if not has_table:
        missing_parts.append("table")
    if not has_list:
        missing_parts.append("list")
    path = _first_path_matching(
        _js_sources(file_changes),
        r"Admin|Dashboard|App|Resource|Table|Nav|Header",
    )
    return [
        ScaffoldQualityIssue(
            code="admin_missing_semantic_resource_table",
            message=(
                "Admin dashboard semantic shell/resource structure is incomplete; missing: "
                + ", ".join(missing_parts)
            ),
            path=path,
        )
    ]


def _inspect_admin_destructive_action_live_mutation(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_admin_dashboard_core(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    if not _ADMIN_DESTRUCTIVE_VERBS.search(combined):
        return []
    if not _ADMIN_MUTATION_IMPL.search(combined):
        return []
    path = _first_path_matching(
        _js_sources(file_changes),
        r"Admin|Dashboard|App|Table|Queue|Users|Resources|Actions",
    )
    return [
        ScaffoldQualityIssue(
            code="admin_destructive_action_live_mutation",
            message=(
                "Admin dashboard appears to implement destructive/live mutation behavior "
                "(create/edit/delete/approve/revoke) instead of demo-bounded static controls"
            ),
            path=path,
        )
    ]


def _inspect_admin_dashboard_quality(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    issues: list[ScaffoldQualityIssue] = []
    issues.extend(_inspect_admin_missing_loading_error_states(plan, file_changes))
    issues.extend(_inspect_admin_live_fetch_impl(plan, file_changes))
    issues.extend(_inspect_admin_missing_semantic_resource_table(plan, file_changes))
    issues.extend(_inspect_admin_destructive_action_live_mutation(plan, file_changes))
    return issues


def _has_admin_blocking_quality_issues(issues: list[ScaffoldQualityIssue]) -> bool:
    return any(issue.code in _ADMIN_BLOCKING_QUALITY_CODES for issue in issues)


def _inspect_sales_ops_missing_domain_regions(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_sales_ops_dashboard_core(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    missing: list[str] = []
    for label, patterns in _SALES_OPS_REQUIRED_REGION_PATTERNS:
        if not any(re.search(pattern, combined, re.IGNORECASE) for pattern in patterns):
            missing.append(label)
    if not missing:
        return []
    path = _first_path_matching(
        _js_sources(file_changes),
        r"Sales|Ops|Dashboard|Commission|Recovery|Pipeline|Activity|Filter|App",
    )
    return [
        ScaffoldQualityIssue(
            code="sales_ops_missing_domain_regions",
            message=(
                "Sales Ops dashboard is missing required visible domain regions: "
                + ", ".join(missing)
            ),
            path=path,
        )
    ]


def _inspect_sales_ops_missing_loading_error_states(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if (
        plan is None
        or not _prompt_is_sales_ops_dashboard_core(plan.user_message)
        or not _prompt_requests_sales_ops_state_examples(plan.user_message)
    ):
        return []
    combined = _combined_js_source(file_changes)
    has_empty = bool(_DASHBOARD_EMPTY_STATE.search(combined))
    has_loading = bool(_DASHBOARD_LOADING_STATE.search(combined))
    has_error = bool(_DASHBOARD_ERROR_STATE.search(combined))
    has_static_local = bool(
        re.search(r"\b(static|local|sample|demo|illustrative|preview)\b", combined, re.IGNORECASE)
    )
    if has_empty and has_loading and has_error and has_static_local:
        return []
    missing_parts: list[str] = []
    if not has_empty:
        missing_parts.append("empty")
    if not has_loading:
        missing_parts.append("loading")
    if not has_error:
        missing_parts.append("error")
    if not has_static_local:
        missing_parts.append("static/local wording")
    path = _first_path_matching(
        _js_sources(file_changes),
        r"Sales|Ops|Dashboard|State|Status|Loading|Error|App",
    )
    return [
        ScaffoldQualityIssue(
            code="sales_ops_missing_loading_error_states",
            message=(
                "Sales Ops dashboard prompt requests visible static/local empty/loading/error examples, "
                "but missing: " + ", ".join(missing_parts)
            ),
            path=path,
        )
    ]


def _inspect_sales_ops_missing_semantic_financial_structure(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if (
        plan is None
        or not _prompt_is_sales_ops_dashboard_core(plan.user_message)
        or not _prompt_requests_sales_ops_semantic_structure(plan.user_message)
    ):
        return []
    combined = _combined_js_source(file_changes)
    has_main = bool(_DASHBOARD_MAIN.search(combined))
    has_header = bool(_DASHBOARD_HEADER.search(combined))
    has_nav = bool(_DASHBOARD_NAV.search(combined))
    has_table = bool(_DASHBOARD_TABLE.search(combined))
    has_list = bool(re.search(r"<ul\b|<ol\b", combined, re.IGNORECASE))
    has_chart = bool(
        re.search(
            r"\bchart\b|line\s+chart|bar\s+chart|<svg\b|<canvas\b|aria-label=[\"'][^\"']*chart",
            combined,
            re.IGNORECASE,
        )
    )
    if has_header and has_nav and has_main and has_table and has_list and has_chart:
        return []
    missing_parts: list[str] = []
    if not has_header:
        missing_parts.append("header")
    if not has_nav:
        missing_parts.append("nav")
    if not has_main:
        missing_parts.append("main")
    if not has_table:
        missing_parts.append("table")
    if not has_list:
        missing_parts.append("list")
    if not has_chart:
        missing_parts.append("chart")
    path = _first_path_matching(
        _js_sources(file_changes),
        r"Sales|Ops|Dashboard|Commission|Recovery|Table|Chart|Nav|Header|App",
    )
    return [
        ScaffoldQualityIssue(
            code="sales_ops_missing_semantic_financial_structure",
            message=(
                "Sales Ops semantic shell/financial structure is incomplete; missing: "
                + ", ".join(missing_parts)
            ),
            path=path,
        )
    ]


def _inspect_sales_ops_forbidden_financial_impl(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_is_sales_ops_dashboard_core(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    effective = _strip_sales_ops_negated_forbidden_markers(combined)
    matched = _SALES_OPS_FORBIDDEN_IMPL.search(effective)
    if not matched:
        return []
    offending = matched.group(0).strip()
    path = _first_path_matching(
        _js_sources(file_changes),
        r"Sales|Ops|Dashboard|Commission|Recovery|Finance|Payment|Backend|Api|App",
    )
    return [
        ScaffoldQualityIssue(
            code="sales_ops_forbidden_financial_impl_detected",
            message=(
                "Sales Ops output includes forbidden financial/backend/compliance implementation cues: "
                f"{offending}"
            ),
            path=path,
        )
    ]


def _inspect_sales_ops_dashboard_quality(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    issues: list[ScaffoldQualityIssue] = []
    issues.extend(_inspect_sales_ops_missing_domain_regions(plan, file_changes))
    issues.extend(_inspect_sales_ops_missing_loading_error_states(plan, file_changes))
    issues.extend(_inspect_sales_ops_missing_semantic_financial_structure(plan, file_changes))
    issues.extend(_inspect_sales_ops_forbidden_financial_impl(plan, file_changes))
    return issues


def _has_sales_ops_blocking_quality_issues(issues: list[ScaffoldQualityIssue]) -> bool:
    return any(issue.code in _SALES_OPS_BLOCKING_QUALITY_CODES for issue in issues)


def _build_sales_ops_static_dashboard_fallback_payload(
    file_changes: list[tuple[str, str]],
) -> dict[str, Any]:
    file_map = _file_map(file_changes)

    file_map.setdefault(
        "package.json",
        """{
  "name": "sales-ops-dashboard-static",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.4",
    "vite": "^5.4.0"
  }
}
""",
    )
    file_map.setdefault(
        "vite.config.ts",
        "import { defineConfig } from 'vite';\nimport react from '@vitejs/plugin-react';\n\nexport default defineConfig({ plugins: [react()] });\n",
    )
    file_map.setdefault(
        "index.html",
        """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Sales Ops Dashboard</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
""",
    )
    file_map["src/main.tsx"] = (
        "import React from 'react';\n"
        "import ReactDOM from 'react-dom/client';\n"
        "import App from './App';\n"
        "import './index.css';\n\n"
        "ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(\n"
        "  <React.StrictMode>\n"
        "    <App />\n"
        "  </React.StrictMode>,\n"
        ");\n"
    )
    # Always overwrite fallback CSS so responsive/semantic guarantees are deterministic
    # even when earlier repair passes returned non-responsive styling.
    file_map["src/index.css"] = (
        "body { margin: 0; font-family: Inter, Arial, sans-serif; background: #f5f7fb; color: #111827; }\n"
        ".shell { display: grid; grid-template-columns: 240px 1fr; min-height: 100vh; }\n"
        ".sidebar { background: #111827; color: #e5e7eb; padding: 16px; }\n"
        ".sidebar ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }\n"
        ".content { display: grid; grid-template-rows: auto 1fr; }\n"
        ".topbar { background: #ffffff; border-bottom: 1px solid #d1d5db; padding: 14px 18px; }\n"
        "main { padding: 18px; display: grid; gap: 14px; }\n"
        ".cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; }\n"
        ".panel { background: #fff; border: 1px solid #d1d5db; border-radius: 10px; padding: 12px; }\n"
        "table { width: 100%; border-collapse: collapse; }\n"
        "th, td { border: 1px solid #d1d5db; padding: 8px; text-align: left; }\n"
        ".states { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }\n"
        "@media (max-width: 920px) { .shell { grid-template-columns: 1fr; } }\n"
    )
    file_map["src/App.tsx"] = """import React from 'react';

const executiveSummary = [
  { label: 'Pipeline value', value: '$182,400' },
  { label: 'Commission earned', value: '$26,880' },
  { label: 'Commission pending', value: '$9,240' },
  { label: 'Recovered dollars', value: '$14,120' },
];

const agentPerformance = [
  { agent: 'Avery', meetings: 18, winRate: '41%', earned: '$7,920' },
  { agent: 'Jordan', meetings: 15, winRate: '38%', earned: '$6,540' },
  { agent: 'Kai', meetings: 12, winRate: '35%', earned: '$5,980' },
];

const pipelineRows = [
  { stage: 'Discovery', movedIn: 22, movedOut: 17 },
  { stage: 'Proposal', movedIn: 14, movedOut: 10 },
  { stage: 'Negotiation', movedIn: 9, movedOut: 6 },
];

const payoutRows = [
  { agent: 'Avery', earned: '$7,920', pending: '$1,840', clawbacks: '$320', chargebacks: '$95', payoutStatus: 'Review' },
  { agent: 'Jordan', earned: '$6,540', pending: '$1,760', clawbacks: '$210', chargebacks: '$70', payoutStatus: 'Queued' },
  { agent: 'Kai', earned: '$5,980', pending: '$1,320', clawbacks: '$180', chargebacks: '$60', payoutStatus: 'Hold' },
];

const agingBuckets = [
  { bucket: '0-15 days', recoverable: '$6,200', recovered: '$4,100' },
  { bucket: '16-30 days', recoverable: '$5,400', recovered: '$3,280' },
  { bucket: '31-60 days', recoverable: '$4,700', recovered: '$2,640' },
];

const exceptionQueue = [
  'Invoice INV-1082 missing disposition code',
  'Chargeback case CB-22 awaiting note update',
];

const bottlenecks = [
  'Proposal to negotiation cycle time increased by 1.4 days',
  'Recovery queue handoff delayed for Team East',
];

const activityFeed = [
  'Audit feed: payout status updated for Avery (static sample)',
  'Activity feed: exception queue item CB-22 reassigned',
];

export default function App() {
  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Sales ops navigation">
        <h1>Sales Ops Shell</h1>
        <ul>
          <li>Executive summary</li>
          <li>Performance</li>
          <li>Pipeline</li>
          <li>Commission and payouts</li>
          <li>Recovery and aging</li>
        </ul>
      </nav>
      <div className="content">
        <header className="topbar">
          Filters by date/team/agent/status/stage (static local sample controls)
        </header>
        <main>
          <section className="panel" aria-label="Executive summary row">
            <h2>Executive summary</h2>
            <div className="cards">
              {executiveSummary.map((item) => (
                <article className="panel" key={item.label}>
                  <h3>{item.label}</h3>
                  <p>{item.value}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="panel" aria-label="Agent and team performance">
            <h2>Agent/team performance and sales activity metrics</h2>
            <ul>
              {agentPerformance.map((row) => (
                <li key={row.agent}>
                  {row.agent}: {row.meetings} activities, {row.winRate} win rate, {row.earned} commission earned
                </li>
              ))}
            </ul>
          </section>

          <section className="panel" aria-label="Pipeline stage movement and process bottleneck panel">
            <h2>Pipeline/stage movement and process bottleneck panel</h2>
            <table aria-label="Pipeline stage movement table">
              <caption>Local static movement counts</caption>
              <thead>
                <tr>
                  <th scope="col">Stage</th>
                  <th scope="col">Moved in</th>
                  <th scope="col">Moved out</th>
                </tr>
              </thead>
              <tbody>
                {pipelineRows.map((row) => (
                  <tr key={row.stage}>
                    <td>{row.stage}</td>
                    <td>{row.movedIn}</td>
                    <td>{row.movedOut}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul>
              {bottlenecks.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <div role="img" aria-label="Pipeline stage movement chart">
              Chart placeholder: stage movement trend (static local sample)
            </div>
          </section>

          <section className="panel" aria-label="Commission summary and payout status display">
            <h2>Commission summary, earned/pending, clawbacks/chargebacks, payout status display</h2>
            <table aria-label="Commission and payout status table">
              <caption>Illustrative local sample payout rows</caption>
              <thead>
                <tr>
                  <th scope="col">Agent</th>
                  <th scope="col">Earned</th>
                  <th scope="col">Pending</th>
                  <th scope="col">Clawbacks</th>
                  <th scope="col">Chargebacks</th>
                  <th scope="col">Payout status</th>
                </tr>
              </thead>
              <tbody>
                {payoutRows.map((row) => (
                  <tr key={row.agent}>
                    <td>{row.agent}</td>
                    <td>{row.earned}</td>
                    <td>{row.pending}</td>
                    <td>{row.clawbacks}</td>
                    <td>{row.chargebacks}</td>
                    <td>{row.payoutStatus}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="panel" aria-label="Revenue recovery summary">
            <h2>Revenue recovery summary, recoverable balance, recovered dollars, aging buckets</h2>
            <table aria-label="Recovery aging buckets table">
              <caption>Local static recovery sample data</caption>
              <thead>
                <tr>
                  <th scope="col">Aging bucket</th>
                  <th scope="col">Recoverable balance</th>
                  <th scope="col">Recovered dollars</th>
                </tr>
              </thead>
              <tbody>
                {agingBuckets.map((row) => (
                  <tr key={row.bucket}>
                    <td>{row.bucket}</td>
                    <td>{row.recoverable}</td>
                    <td>{row.recovered}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="panel" aria-label="Recovery exception queue and activity/audit feed">
            <h2>Recovery exception queue and activity/audit feed</h2>
            <ul>
              {exceptionQueue.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <ul>
              {activityFeed.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>

          <section className="panel states" aria-label="Visible static state examples">
            <article className="panel">
              <strong>Empty example</strong>
              <p>No recovery exceptions match this static local filter.</p>
            </article>
            <article className="panel">
              <strong>Loading preview example</strong>
              <p>Loading local static sample preview.</p>
            </article>
            <article className="panel">
              <strong>Error preview example</strong>
              <p>Unable to load local static sample segment.</p>
            </article>
          </section>
        </main>
      </div>
    </div>
  );
}
"""

    preferred_order = [
        "package.json",
        "vite.config.ts",
        "index.html",
        "src/main.tsx",
        "src/App.tsx",
        "src/index.css",
    ]
    ordered_paths = [path for path in preferred_order if path in file_map]
    ordered_paths.extend(sorted(path for path in file_map if path not in set(ordered_paths)))
    payload_changes = [{"path": path, "content": file_map[path]} for path in ordered_paths]
    return {
        "file_changes": payload_changes,
        "assertions": [
            "Sales ops shell includes required executive/performance/activity/pipeline/commission/recovery regions",
            "Visible static empty/loading/error examples are rendered",
            "Semantic header/nav/main/table/list/chart structure is present with local sample data only",
        ],
    }


def _build_admin_static_dashboard_fallback_payload(
    file_changes: list[tuple[str, str]],
) -> dict[str, Any]:
    file_map = _file_map(file_changes)

    file_map.setdefault(
        "package.json",
        """{
  "name": "admin-dashboard-static",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.4",
    "vite": "^5.4.0"
  }
}
""",
    )
    file_map.setdefault(
        "vite.config.ts",
        "import { defineConfig } from 'vite';\nimport react from '@vitejs/plugin-react';\n\nexport default defineConfig({ plugins: [react()] });\n",
    )
    file_map.setdefault(
        "index.html",
        """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Admin Dashboard</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
""",
    )
    file_map["src/main.tsx"] = (
        "import React from 'react';\n"
        "import ReactDOM from 'react-dom/client';\n"
        "import App from './App';\n"
        "import './index.css';\n\n"
        "ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(\n"
        "  <React.StrictMode>\n"
        "    <App />\n"
        "  </React.StrictMode>,\n"
        ");\n"
    )
    file_map["src/App.tsx"] = """import React from 'react';

const App = () => {
  return (
    <div className="app-shell">
      <header className="topbar">
        <h1>Admin Dashboard (Static Demo)</h1>
      </header>
      <div className="layout">
        <nav className="sidebar" aria-label="Admin navigation">
          <ul>
            <li>Overview</li>
            <li>Users and teams</li>
            <li>Review queue</li>
            <li>Audit activity</li>
            <li>System status</li>
          </ul>
        </nav>
        <main className="content">
          <section>
            <h2>Overview and status cards</h2>
            <div className="cards">
              <article className="card"><h3>Pending reviews</h3><p>14</p></article>
              <article className="card"><h3>Active users</h3><p>128</p></article>
              <article className="card"><h3>System health</h3><p>Operational</p></article>
            </div>
          </section>

          <section>
            <h2>User and team summary</h2>
            <ul>
              <li>Platform team: 12 members</li>
              <li>Support team: 6 members</li>
              <li>Moderation team: 5 members</li>
            </ul>
          </section>

          <section>
            <h2>Static role and permission summary</h2>
            <ul>
              <li>Admin: review and status access (demo only)</li>
              <li>Operator: queue and audit visibility (demo only)</li>
              <li>Viewer: read-only dashboard access</li>
            </ul>
          </section>

          <section>
            <h2>Review queue</h2>
            <ul>
              <li>Pending moderation: 5 items</li>
              <li>Pending verification: 9 items</li>
            </ul>
          </section>

          <section>
            <h2>Resource/user table</h2>
            <table>
              <caption>Static local demo rows</caption>
              <thead>
                <tr>
                  <th scope="col">Resource</th>
                  <th scope="col">Owner</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                <tr><td>Workspace Alpha</td><td>Team Core</td><td>Healthy</td></tr>
                <tr><td>Workspace Beta</td><td>Team Ops</td><td>Needs review</td></tr>
              </tbody>
            </table>
          </section>

          <section>
            <h2>Audit and activity log</h2>
            <ul>
              <li>09:15 — Demo role summary viewed</li>
              <li>09:12 — Demo queue snapshot refreshed</li>
            </ul>
          </section>

          <section>
            <h2>System status panel</h2>
            <p>All systems operational (static local sample)</p>
          </section>

          <section>
            <h2>Demo-mode action controls</h2>
            <button type="button" disabled>Preview action (demo only)</button>
            <p>Read-only illustrative control. No data mutation occurs.</p>
          </section>

          <section aria-label="Static state examples">
            <h2>Empty, loading, and error examples</h2>
            <div role="status">Empty: No users match this filter (static local example)</div>
            <div role="status">Loading: Loading admin preview example (illustrative only)</div>
            <div role="alert">Error: Unable to load local demo data (static example)</div>
          </section>
        </main>
      </div>
    </div>
  );
};

export default App;
"""
    file_map["src/index.css"] = (
        "* { box-sizing: border-box; }\n"
        "body { margin: 0; font-family: Inter, Arial, sans-serif; background: #f5f7fb; color: #111827; }\n"
        ".topbar { padding: 12px 16px; background: #111827; color: #f9fafb; }\n"
        ".layout { display: grid; grid-template-columns: 240px 1fr; min-height: calc(100vh - 56px); }\n"
        ".sidebar { padding: 12px; background: #1f2937; color: #e5e7eb; }\n"
        ".sidebar ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 8px; }\n"
        ".content { padding: 16px; display: grid; gap: 16px; }\n"
        ".cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }\n"
        ".card { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px; }\n"
        "section { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; }\n"
        "table { width: 100%; border-collapse: collapse; }\n"
        "th, td { border: 1px solid #d1d5db; padding: 8px; text-align: left; }\n"
        "@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }\n"
    )

    ordered_paths = [
        "package.json",
        "vite.config.ts",
        "index.html",
        "src/main.tsx",
        "src/App.tsx",
        "src/index.css",
    ]
    ordered = [(path, file_map[path]) for path in ordered_paths if path in file_map]
    for path in sorted(file_map):
        if path not in {p for p, _ in ordered}:
            ordered.append((path, file_map[path]))
    return {"file_changes": [{"path": p, "content": c} for p, c in ordered], "assertions": []}


def _build_saas_static_dashboard_fallback_payload(
    file_changes: list[tuple[str, str]],
) -> dict[str, Any]:
    file_map = _file_map(file_changes)

    file_map.setdefault(
        "package.json",
        """{
  "name": "saas-dashboard-static",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.4",
    "vite": "^5.4.0"
  }
}
""",
    )
    file_map.setdefault(
        "vite.config.ts",
        "import { defineConfig } from 'vite';\nimport react from '@vitejs/plugin-react';\n\nexport default defineConfig({ plugins: [react()] });\n",
    )
    file_map.setdefault(
        "index.html",
        """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>SaaS Dashboard</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
""",
    )
    file_map["src/main.tsx"] = (
        "import React from 'react';\n"
        "import ReactDOM from 'react-dom/client';\n"
        "import App from './App';\n"
        "import './index.css';\n\n"
        "ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(\n"
        "  <React.StrictMode>\n"
        "    <App />\n"
        "  </React.StrictMode>\n"
        ");\n"
    )
    file_map.setdefault(
        "src/index.css",
        ":root { font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }\nbody { margin: 0; background: #f4f6fb; color: #0f172a; }\n* { box-sizing: border-box; }\n",
    )
    file_map["src/App.tsx"] = """import React from 'react';

const usageCards = [
  { label: 'Monthly active users', value: '2,480' },
  { label: 'API usage', value: '64%' },
  { label: 'Seats used', value: '18 / 25' },
];

const activityItems = [
  'Workspace Alpha onboarded two teammates',
  'Model sandbox run completed successfully',
  'Usage alert threshold updated',
];

const resourceRows = [
  { project: 'Workspace Alpha', resource: 'Prompt Library', status: 'Healthy' },
  { project: 'Workspace Beta', resource: 'Vector Index', status: 'Warning' },
  { project: 'Workspace Gamma', resource: 'Feature Flags', status: 'Healthy' },
];

export default function App() {
  return (
    <div style={{ minHeight: '100vh', display: 'grid', gridTemplateColumns: '240px 1fr' }}>
      <aside aria-label="Sidebar" style={{ background: '#0f172a', color: '#e2e8f0', padding: '16px' }}>
        <h1 style={{ marginTop: 0 }}>AI Dev Platform</h1>
        <nav aria-label="Primary navigation">
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: 8 }}>
            <li>Overview</li>
            <li>Projects</li>
            <li>Usage</li>
            <li>Settings</li>
            <li>Help</li>
          </ul>
        </nav>
      </aside>
      <div style={{ display: 'grid', gridTemplateRows: 'auto 1fr' }}>
        <header style={{ background: '#ffffff', borderBottom: '1px solid #dbe3ef', padding: '16px 20px' }}>
          <strong>Topbar</strong> · SaaS product dashboard preview
        </header>
        <main style={{ padding: 20, display: 'grid', gap: 16 }}>
          <section aria-label="Workspace selector placeholder" style={{ background: '#fff', border: '1px solid #dbe3ef', borderRadius: 12, padding: 12 }}>
            Workspace/project selector placeholder: Workspace Alpha (local sample)
          </section>

          <section aria-label="Usage cards" style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
            {usageCards.map((card) => (
              <article key={card.label} style={{ background: '#fff', border: '1px solid #dbe3ef', borderRadius: 12, padding: 12 }}>
                <h2 style={{ margin: '0 0 6px 0', fontSize: 14 }}>{card.label}</h2>
                <p style={{ margin: 0, fontWeight: 700 }}>{card.value}</p>
              </article>
            ))}
          </section>

          <section aria-label="Plan and status card" style={{ background: '#fff', border: '1px solid #dbe3ef', borderRadius: 12, padding: 12 }}>
            <h2 style={{ marginTop: 0 }}>Plan/status</h2>
            <p style={{ marginBottom: 0 }}>Current plan: Pro · Renewal window opens in 18 days.</p>
          </section>

          <section aria-label="Recent activity" style={{ background: '#fff', border: '1px solid #dbe3ef', borderRadius: 12, padding: 12 }}>
            <h2 style={{ marginTop: 0 }}>Recent activity</h2>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {activityItems.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>

          <section aria-label="Project and resource inventory" style={{ background: '#fff', border: '1px solid #dbe3ef', borderRadius: 12, padding: 12 }}>
            <h2 style={{ marginTop: 0 }}>Project/resource list</h2>
            <table aria-label="Projects and resources" style={{ width: '100%', borderCollapse: 'collapse' }}>
              <caption style={{ textAlign: 'left', paddingBottom: 8 }}>Project and resource overview</caption>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', borderBottom: '1px solid #dbe3ef', padding: '6px 8px' }}>Project</th>
                  <th style={{ textAlign: 'left', borderBottom: '1px solid #dbe3ef', padding: '6px 8px' }}>Resource</th>
                  <th style={{ textAlign: 'left', borderBottom: '1px solid #dbe3ef', padding: '6px 8px' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {resourceRows.map((row) => (
                  <tr key={`${row.project}-${row.resource}`}>
                    <td style={{ borderBottom: '1px solid #eef2f7', padding: '6px 8px' }}>{row.project}</td>
                    <td style={{ borderBottom: '1px solid #eef2f7', padding: '6px 8px' }}>{row.resource}</td>
                    <td style={{ borderBottom: '1px solid #eef2f7', padding: '6px 8px' }}>{row.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section aria-label="Upgrade CTA and shortcuts" style={{ background: '#fff', border: '1px solid #dbe3ef', borderRadius: 12, padding: 12 }}>
            <h2 style={{ marginTop: 0 }}>Upgrade</h2>
            <p>Upgrade CTA: unlock additional model seats and larger quota.</p>
            <p style={{ marginBottom: 0 }}>Shortcuts: Settings · Help</p>
          </section>

          <section aria-label="Static state examples" style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
            <article style={{ background: '#fff', border: '1px solid #dbe3ef', borderRadius: 12, padding: 12 }}>
              <strong>Empty example</strong>
              <p style={{ marginBottom: 0 }}>No projects yet</p>
            </article>
            <article style={{ background: '#fff', border: '1px solid #dbe3ef', borderRadius: 12, padding: 12 }}>
              <strong>Loading preview example</strong>
              <p style={{ marginBottom: 0 }}>Loading preview example</p>
            </article>
            <article style={{ background: '#fff', border: '1px solid #dbe3ef', borderRadius: 12, padding: 12 }}>
              <strong>Error preview example</strong>
              <p style={{ marginBottom: 0 }}>Unable to load local sample</p>
            </article>
          </section>
        </main>
      </div>
    </div>
  );
}
"""

    preferred_order = [
        "package.json",
        "vite.config.ts",
        "index.html",
        "src/main.tsx",
        "src/App.tsx",
        "src/index.css",
    ]
    ordered_paths = [path for path in preferred_order if path in file_map]
    ordered_paths.extend(sorted(path for path in file_map if path not in set(ordered_paths)))
    payload_changes = [
        {"path": path, "content": file_map[path]}
        for path in ordered_paths
    ]
    return {
        "file_changes": payload_changes,
        "assertions": [
            "Dashboard renders with semantic sidebar/topbar/header/nav/main structure",
            "Static empty/loading/error example cards are visible",
            "Project/resource inventory is rendered with semantic table tags",
        ],
    }


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
        issues.extend(_inspect_saas_dashboard_quality(plan, file_changes))
        issues.extend(_inspect_admin_dashboard_quality(plan, file_changes))
        issues.extend(_inspect_sales_ops_dashboard_quality(plan, file_changes))
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
    saas_codes = issue_codes & {
        "saas_missing_loading_error_states",
        "saas_missing_semantic_resource_table",
        "saas_live_fetch_impl_detected",
    }
    if saas_codes and _prompt_is_saas_dashboard_core(plan.user_message):
        repair_system += (
            "\nSaaS dashboard repair focus:\n"
            "- Preserve the static SaaS lane: no backend/live data/auth/billing/admin/CRUD implementations.\n"
            "- Add visible Empty / Loading / Error example cards or panels rendered in UI (not comments/text-only).\n"
            "- Use static/local copy examples such as: 'No projects yet', 'Loading preview example', 'Unable to load local sample'.\n"
            "- Keep state examples static/local and never require fetch, async calls, API endpoints, backend, timers, polling, or live data.\n"
            "- Remove fetch/axios/API calls/useEffect live-loading simulations/timers/server endpoints and any fake network retry flows.\n"
            "- Do not use '/api', fetch(, axios, async backend simulation, or live polling.\n"
            "- For project/resource rows, render a semantic <table> with <thead>, <tbody>, <th>, and <td> (plus caption/aria-label when practical).\n"
            "- Do not use div-soup cards pretending to be a table; semantic list is only acceptable for clearly non-tabular output.\n"
            "- For this gate prompt, prefer table structure for project/resource rows.\n"
            "- Use semantic <header>, <nav>, and <main> landmarks around the SaaS shell.\n"
            "- Keep settings/help shortcuts and upgrade CTA honest placeholders only.\n"
            "- Output ONLY valid JSON matching file_changes schema.\n"
        )
    admin_codes = issue_codes & {
        "admin_missing_loading_error_states",
        "admin_live_fetch_impl_detected",
        "admin_missing_semantic_resource_table",
        "admin_destructive_action_live_mutation",
    }
    if admin_codes and _prompt_is_admin_dashboard_core(plan.user_message):
        repair_system += (
            "\nAdmin dashboard repair focus:\n"
            "- Preserve the static admin lane: no backend/live data/auth/RBAC/CRUD/destructive implementations.\n"
            "- Add visible static/local Empty / Loading / Error examples rendered in UI (not comments/text-only).\n"
            "- Include explicit examples such as: 'No users match this filter', 'Loading admin preview example', 'Unable to load local demo data'.\n"
            "- Keep state examples static/local and never require fetch, async calls, API endpoints, backend, timers, polling, or live data.\n"
            "- Do not use '/api', fetch(, axios, XMLHttpRequest, async backend simulation, useEffect polling, or timer-based live loading.\n"
            "- Use semantic <header>, <nav>, and <main> landmarks around the admin shell.\n"
            "- For resource/user rows, render semantic <table> with <thead>, <tbody>, <th>, and <td>; keep queue/audit as semantic list structures.\n"
            "- Keep controls demo-mode/read-only only; do not implement create/edit/delete/approve/revoke mutations.\n"
            "- Output ONLY valid JSON matching file_changes schema.\n"
        )
    sales_ops_codes = issue_codes & {
        "sales_ops_missing_domain_regions",
        "sales_ops_missing_loading_error_states",
        "sales_ops_missing_semantic_financial_structure",
        "sales_ops_forbidden_financial_impl_detected",
    }
    if sales_ops_codes and _prompt_is_sales_ops_dashboard_core(plan.user_message):
        repair_system += (
            "\nSales Ops dashboard repair focus:\n"
            "- Add missing Sales Ops regions visibly in UI: executive summary, agent/team performance, sales activity metrics, pipeline/stage movement, commission summary, commission earned/pending, clawbacks/chargebacks, payout status display, revenue recovery summary, recoverable balance/recovered dollars, aging buckets, recovery exception queue, process bottleneck panel, activity/audit feed, and filters by date/team/agent/status/stage.\n"
            "- Use local/static sample data only; keep calculations illustrative but internally coherent.\n"
            "- Add visible static Empty / Loading / Error examples rendered in UI (not comments/text-only).\n"
            "- Use semantic <header>, <nav>, and <main> landmarks plus meaningful <table>, list, and chart structure.\n"
            "- Use semantic tables for commission, payout, recovery, and aging data (<table>/<thead>/<tbody>/<th>/<td>).\n"
            "- Remove backend/API/CRM/payment/payroll/accounting/ASC606/legal-collections/live-integration code or claims.\n"
            "- Remove real PII and real account/bank/payment identifiers.\n"
            "- Remove live dunning, telephony, SMS automation, payout disbursement, trading/order-book, regulated financial advice, and compliance certification claims.\n"
            "- Avoid aggressive collections language and gamified surveillance patterns.\n"
            "- Do not expose build-kit internals, registry internals, or prompt policy text in generated output.\n"
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

        # Escalate SaaS repair once more when blocking SaaS issues remain.
        if remaining and _prompt_is_saas_dashboard_core(plan.user_message) and _has_saas_blocking_quality_issues(remaining):
            _LOG.info(
                "Scaffold quality: SaaS blocking issues remain after first repair for plan=%s — running one escalated SaaS repair pass",
                plan.plan_id,
            )
            escalated_system = messages[0]["content"] + (
                "\n\nSaaS enforcement (must satisfy all):\n"
                "- Output must include visible static/local Empty, Loading, and Error example cards.\n"
                "- Output must include semantic project/resource <table> with <thead>/<tbody>/<th>/<td>.\n"
                "- Output must contain no fetch/useEffect/setTimeout/axios/api endpoint behavior.\n"
                "- If constraints cannot be met, replace the affected regions with static semantic markup that does meet them.\n"
            )
            escalated_user = (
                messages[1]["content"]
                + "\n\nRemaining SaaS blocking issues to fix now:\n"
                + "\n".join(
                    f"- [{issue.code}] {issue.message}"
                    for issue in remaining
                    if issue.code in _SAAS_BLOCKING_QUALITY_CODES
                )
            )
            raw = complete_chat(
                [
                    {"role": "system", "content": escalated_system},
                    {"role": "user", "content": escalated_user},
                ],
                model_override=model,
                api_key_override=api_key,
                timeout_sec=scaffold_timeout,
            )
            repaired = parse_result(raw)
            remaining = inspect_generated_scaffold_quality(repaired.file_changes, plan=plan)

        # Deterministic SaaS fallback to guarantee gate-critical static semantics.
        if remaining and _prompt_is_saas_dashboard_core(plan.user_message) and _has_saas_blocking_quality_issues(remaining):
            _LOG.warning(
                "Scaffold quality: SaaS blocking issues remain after escalated repair for plan=%s — applying deterministic static SaaS fallback",
                plan.plan_id,
            )
            fallback_payload = _build_saas_static_dashboard_fallback_payload(repaired.file_changes)
            repaired = parse_result(json.dumps(fallback_payload))
            remaining = inspect_generated_scaffold_quality(repaired.file_changes, plan=plan)

        # Escalate admin repair once more when blocking admin issues remain.
        if remaining and _prompt_is_admin_dashboard_core(plan.user_message) and _has_admin_blocking_quality_issues(remaining):
            _LOG.info(
                "Scaffold quality: Admin blocking issues remain after first repair for plan=%s — running one escalated Admin repair pass",
                plan.plan_id,
            )
            escalated_system = messages[0]["content"] + (
                "\n\nAdmin enforcement (must satisfy all):\n"
                "- Output must include visible static/local Empty, Loading, and Error example cards/panels.\n"
                "- Output must include semantic admin shell landmarks (<header>/<nav>/<main>) and resource/user <table> with <thead>/<tbody>/<th>/<td>.\n"
                "- Output must contain no fetch/useEffect polling/setTimeout loading simulation/axios/XMLHttpRequest/API endpoint behavior.\n"
                "- Output must keep controls demo-bounded read-only; no create/edit/delete/approve/revoke live mutation behavior.\n"
                "- If constraints cannot be met, replace affected regions with static semantic markup that does meet them.\n"
            )
            escalated_user = (
                messages[1]["content"]
                + "\n\nRemaining Admin blocking issues to fix now:\n"
                + "\n".join(
                    f"- [{issue.code}] {issue.message}"
                    for issue in remaining
                    if issue.code in _ADMIN_BLOCKING_QUALITY_CODES
                )
            )
            raw = complete_chat(
                [
                    {"role": "system", "content": escalated_system},
                    {"role": "user", "content": escalated_user},
                ],
                model_override=model,
                api_key_override=api_key,
                timeout_sec=scaffold_timeout,
            )
            repaired = parse_result(raw)
            remaining = inspect_generated_scaffold_quality(repaired.file_changes, plan=plan)

        # Deterministic admin fallback to guarantee gate-critical static semantics.
        if remaining and _prompt_is_admin_dashboard_core(plan.user_message) and _has_admin_blocking_quality_issues(remaining):
            _LOG.warning(
                "Scaffold quality: Admin blocking issues remain after escalated repair for plan=%s — applying deterministic static Admin fallback",
                plan.plan_id,
            )
            fallback_payload = _build_admin_static_dashboard_fallback_payload(repaired.file_changes)
            repaired = parse_result(json.dumps(fallback_payload))
            remaining = inspect_generated_scaffold_quality(repaired.file_changes, plan=plan)

        # Escalate Sales Ops repair once more when blocking Sales Ops issues remain.
        if remaining and _prompt_is_sales_ops_dashboard_core(plan.user_message) and _has_sales_ops_blocking_quality_issues(remaining):
            _LOG.info(
                "Scaffold quality: Sales Ops blocking issues remain after first repair for plan=%s — running one escalated Sales Ops repair pass",
                plan.plan_id,
            )
            escalated_system = messages[0]["content"] + (
                "\n\nSales Ops enforcement (must satisfy all):\n"
                "- Output must include all required Sales Ops regions and filter coverage explicitly.\n"
                "- Output must include visible static/local Empty, Loading, and Error example panels/cards.\n"
                "- Output must include semantic <header>/<nav>/<main>, plus financial <table> structures and meaningful list/chart regions.\n"
                "- Output must contain no payroll/payment/accounting/ASC606/legal-collections/backend/API/CRM/live-integration code or claims.\n"
                "- Output must contain no real PII/bank/payment identifiers, live dunning/telephony/SMS, payout disbursement, trading/order-book, or compliance certification claims.\n"
                "- If constraints cannot be met, replace affected regions with static semantic markup that does meet them.\n"
            )
            escalated_user = (
                messages[1]["content"]
                + "\n\nRemaining Sales Ops blocking issues to fix now:\n"
                + "\n".join(
                    f"- [{issue.code}] {issue.message}"
                    for issue in remaining
                    if issue.code in _SALES_OPS_BLOCKING_QUALITY_CODES
                )
            )
            raw = complete_chat(
                [
                    {"role": "system", "content": escalated_system},
                    {"role": "user", "content": escalated_user},
                ],
                model_override=model,
                api_key_override=api_key,
                timeout_sec=scaffold_timeout,
            )
            repaired = parse_result(raw)
            remaining = inspect_generated_scaffold_quality(repaired.file_changes, plan=plan)

        # Deterministic Sales Ops fallback to guarantee gate-critical static semantics.
        if remaining and _prompt_is_sales_ops_dashboard_core(plan.user_message) and _has_sales_ops_blocking_quality_issues(remaining):
            _LOG.warning(
                "Scaffold quality: Sales Ops blocking issues remain after escalated repair for plan=%s — applying deterministic static Sales Ops fallback",
                plan.plan_id,
            )
            fallback_payload = _build_sales_ops_static_dashboard_fallback_payload(repaired.file_changes)
            repaired = parse_result(json.dumps(fallback_payload))
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
