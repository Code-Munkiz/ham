"""Configuration for HAM-on-X Phase 1A.

Defaults are deliberately conservative: autonomy is disabled, dry-run is
enabled, and mutating action limits are zero.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TENANT_ID = "ham-official"
DEFAULT_AGENT_ID = "ham-pr-rockstar"
DEFAULT_CAMPAIGN_ID = "base-stealth-launch"
DEFAULT_ACCOUNT_ID = "ham-x-official"
DEFAULT_PROFILE_ID = "ham.default"
DEFAULT_AUTONOMY_MODE = "draft"
DEFAULT_POLICY_PROFILE_ID = "platform-default"
DEFAULT_BRAND_VOICE_ID = "ham-canonical"
DEFAULT_CATALOG_SKILL_ID = "bundled.social-media.xurl"
DEFAULT_READONLY_TRANSPORT = "direct"
DEFAULT_EXECUTION_TRANSPORT = "direct_oauth1"
DEFAULT_CANARY_ALLOWED_ACTIONS = "post,quote"
DEFAULT_LIVE_DRY_RUN_QUERY = "Base ecosystem autonomous agents"
DEFAULT_GOHAM_ALLOWED_ACTIONS = "post"


def _bool_env(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


def _path_env(name: str, default: str) -> Path:
    raw = (os.environ.get(name) or "").strip()
    return Path(raw or default).expanduser()


@dataclass(frozen=True)
class HamXConfig:
    xai_api_key: str
    x_api_key: str
    x_api_secret: str
    x_access_token: str
    x_access_token_secret: str
    x_bearer_token: str
    tenant_id: str
    agent_id: str
    campaign_id: str
    account_id: str
    profile_id: str
    autonomy_mode: str
    policy_profile_id: str
    brand_voice_id: str
    catalog_skill_id: str
    emergency_stop: bool
    enable_live_smoke: bool
    enable_live_execution: bool
    autonomy_enabled: bool
    dry_run: bool
    max_posts_per_hour: int
    max_quotes_per_hour: int
    max_searches_per_hour: int
    execution_daily_cap: int
    execution_per_run_cap: int
    daily_spend_limit_usd: float
    model: str
    xurl_bin: str
    readonly_transport: str
    execution_transport: str
    canary_allowed_actions: str
    enable_live_read_model_dry_run: bool
    live_dry_run_query: str
    live_dry_run_max_results: int
    live_dry_run_max_candidates: int
    live_draft_max_output_tokens: int
    live_draft_timeout_seconds: int
    enable_goham_execution: bool
    goham_autonomous_daily_cap: int
    goham_autonomous_per_run_cap: int
    goham_min_score: float
    goham_min_confidence: float
    goham_allowed_actions: str
    goham_block_links: bool
    review_queue_path: Path
    exception_queue_path: Path
    execution_journal_path: Path
    audit_log_path: Path
    enable_goham_controller: bool = False
    goham_controller_dry_run: bool = True
    goham_max_total_actions_per_day: int = 1
    goham_max_original_posts_per_day: int = 1
    goham_max_quotes_per_day: int = 0
    goham_min_spacing_minutes: int = 120
    goham_max_actions_per_run: int = 1
    goham_max_candidates_per_run: int = 5
    goham_consecutive_failure_stop: int = 2
    goham_policy_rejection_stop: int = 5
    goham_model_timeout_stop: int = 3
    enable_goham_live_controller: bool = False
    goham_live_controller_original_posts_only: bool = True
    goham_live_max_actions_per_run: int = 1
    enable_goham_reactive: bool = False
    goham_reactive_dry_run: bool = True
    goham_reactive_live_canary: bool = False
    goham_reactive_max_replies_per_15m: int = 5
    goham_reactive_max_replies_per_hour: int = 20
    goham_reactive_max_replies_per_user_per_day: int = 3
    goham_reactive_max_replies_per_thread_per_day: int = 5
    goham_reactive_min_seconds_between_replies: int = 60
    goham_reactive_min_relevance: float = 0.75
    goham_reactive_block_links: bool = True
    goham_reactive_failure_stop: int = 2
    goham_reactive_policy_rejection_stop: int = 10
    goham_reactive_max_inbound_per_run: int = 25
    goham_reactive_max_replies_per_run: int = 1


def load_ham_x_config() -> HamXConfig:
    """Load HAM-on-X settings from env with safe Phase 1A defaults."""
    return HamXConfig(
        xai_api_key=(os.environ.get("XAI_API_KEY") or "").strip(),
        x_api_key=(os.environ.get("X_API_KEY") or "").strip(),
        x_api_secret=(os.environ.get("X_API_SECRET") or "").strip(),
        x_access_token=(os.environ.get("X_ACCESS_TOKEN") or "").strip(),
        x_access_token_secret=(os.environ.get("X_ACCESS_TOKEN_SECRET") or "").strip(),
        x_bearer_token=(os.environ.get("X_BEARER_TOKEN") or "").strip(),
        tenant_id=(os.environ.get("HAM_X_TENANT_ID") or DEFAULT_TENANT_ID).strip()
        or DEFAULT_TENANT_ID,
        agent_id=(os.environ.get("HAM_X_AGENT_ID") or DEFAULT_AGENT_ID).strip()
        or DEFAULT_AGENT_ID,
        campaign_id=(os.environ.get("HAM_X_CAMPAIGN_ID") or DEFAULT_CAMPAIGN_ID).strip()
        or DEFAULT_CAMPAIGN_ID,
        account_id=(os.environ.get("HAM_X_ACCOUNT_ID") or DEFAULT_ACCOUNT_ID).strip()
        or DEFAULT_ACCOUNT_ID,
        profile_id=(os.environ.get("HAM_X_PROFILE_ID") or DEFAULT_PROFILE_ID).strip()
        or DEFAULT_PROFILE_ID,
        autonomy_mode=(os.environ.get("HAM_X_AUTONOMY_MODE") or DEFAULT_AUTONOMY_MODE).strip()
        or DEFAULT_AUTONOMY_MODE,
        policy_profile_id=(os.environ.get("HAM_X_POLICY_PROFILE_ID") or DEFAULT_POLICY_PROFILE_ID).strip()
        or DEFAULT_POLICY_PROFILE_ID,
        brand_voice_id=(os.environ.get("HAM_X_BRAND_VOICE_ID") or DEFAULT_BRAND_VOICE_ID).strip()
        or DEFAULT_BRAND_VOICE_ID,
        catalog_skill_id=(os.environ.get("HAM_X_CATALOG_SKILL_ID") or DEFAULT_CATALOG_SKILL_ID).strip()
        or DEFAULT_CATALOG_SKILL_ID,
        emergency_stop=_bool_env("HAM_X_EMERGENCY_STOP", False),
        enable_live_smoke=_bool_env("HAM_X_ENABLE_LIVE_SMOKE", False),
        enable_live_execution=_bool_env("HAM_X_ENABLE_LIVE_EXECUTION", False),
        autonomy_enabled=_bool_env("HAM_X_AUTONOMY_ENABLED", False),
        dry_run=_bool_env("HAM_X_DRY_RUN", True),
        max_posts_per_hour=_int_env("HAM_X_MAX_POSTS_PER_HOUR", 0),
        max_quotes_per_hour=_int_env("HAM_X_MAX_QUOTES_PER_HOUR", 0),
        max_searches_per_hour=_int_env("HAM_X_MAX_SEARCHES_PER_HOUR", 30),
        execution_daily_cap=_int_env("HAM_X_EXECUTION_DAILY_CAP", 1),
        execution_per_run_cap=_int_env("HAM_X_EXECUTION_PER_RUN_CAP", 1),
        daily_spend_limit_usd=_float_env("HAM_X_DAILY_SPEND_LIMIT_USD", 5.0),
        model=(os.environ.get("HAM_X_MODEL") or "grok-4.20").strip() or "grok-4.20",
        xurl_bin=(os.environ.get("HAM_X_XURL_BIN") or "xurl").strip() or "xurl",
        readonly_transport=(os.environ.get("HAM_X_READONLY_TRANSPORT") or DEFAULT_READONLY_TRANSPORT).strip()
        or DEFAULT_READONLY_TRANSPORT,
        execution_transport=(os.environ.get("HAM_X_EXECUTION_TRANSPORT") or DEFAULT_EXECUTION_TRANSPORT).strip()
        or DEFAULT_EXECUTION_TRANSPORT,
        canary_allowed_actions=(os.environ.get("HAM_X_CANARY_ALLOWED_ACTIONS") or DEFAULT_CANARY_ALLOWED_ACTIONS).strip()
        or DEFAULT_CANARY_ALLOWED_ACTIONS,
        enable_live_read_model_dry_run=_bool_env(
            "HAM_X_ENABLE_LIVE_READ_MODEL_DRY_RUN",
            False,
        ),
        live_dry_run_query=(os.environ.get("HAM_X_LIVE_DRY_RUN_QUERY") or DEFAULT_LIVE_DRY_RUN_QUERY).strip()
        or DEFAULT_LIVE_DRY_RUN_QUERY,
        live_dry_run_max_results=_int_env("HAM_X_LIVE_DRY_RUN_MAX_RESULTS", 10),
        live_dry_run_max_candidates=_int_env("HAM_X_LIVE_DRY_RUN_MAX_CANDIDATES", 3),
        live_draft_max_output_tokens=_int_env("HAM_X_LIVE_DRAFT_MAX_OUTPUT_TOKENS", 120),
        live_draft_timeout_seconds=_int_env("HAM_X_LIVE_DRAFT_TIMEOUT_SECONDS", 20),
        enable_goham_execution=_bool_env("HAM_X_ENABLE_GOHAM_EXECUTION", False),
        goham_autonomous_daily_cap=_int_env("HAM_X_GOHAM_AUTONOMOUS_DAILY_CAP", 1),
        goham_autonomous_per_run_cap=_int_env("HAM_X_GOHAM_AUTONOMOUS_PER_RUN_CAP", 1),
        goham_min_score=_float_env("HAM_X_GOHAM_MIN_SCORE", 0.90),
        goham_min_confidence=_float_env("HAM_X_GOHAM_MIN_CONFIDENCE", 0.90),
        goham_allowed_actions=(os.environ.get("HAM_X_GOHAM_ALLOWED_ACTIONS") or DEFAULT_GOHAM_ALLOWED_ACTIONS).strip()
        or DEFAULT_GOHAM_ALLOWED_ACTIONS,
        goham_block_links=_bool_env("HAM_X_GOHAM_BLOCK_LINKS", True),
        review_queue_path=_path_env(
            "HAM_X_REVIEW_QUEUE_PATH",
            ".data/ham-x/review_queue.jsonl",
        ),
        exception_queue_path=_path_env(
            "HAM_X_EXCEPTION_QUEUE_PATH",
            ".data/ham-x/exception_queue.jsonl",
        ),
        execution_journal_path=_path_env(
            "HAM_X_EXECUTION_JOURNAL_PATH",
            ".data/ham-x/execution_journal.jsonl",
        ),
        audit_log_path=_path_env("HAM_X_AUDIT_LOG_PATH", ".data/ham-x/audit.jsonl"),
        enable_goham_controller=_bool_env("HAM_X_ENABLE_GOHAM_CONTROLLER", False),
        goham_controller_dry_run=_bool_env("HAM_X_GOHAM_CONTROLLER_DRY_RUN", True),
        goham_max_total_actions_per_day=_int_env("HAM_X_GOHAM_MAX_TOTAL_ACTIONS_PER_DAY", 1),
        goham_max_original_posts_per_day=_int_env("HAM_X_GOHAM_MAX_ORIGINAL_POSTS_PER_DAY", 1),
        goham_max_quotes_per_day=_int_env("HAM_X_GOHAM_MAX_QUOTES_PER_DAY", 0),
        goham_min_spacing_minutes=_int_env("HAM_X_GOHAM_MIN_SPACING_MINUTES", 120),
        goham_max_actions_per_run=_int_env("HAM_X_GOHAM_MAX_ACTIONS_PER_RUN", 1),
        goham_max_candidates_per_run=_int_env("HAM_X_GOHAM_MAX_CANDIDATES_PER_RUN", 5),
        goham_consecutive_failure_stop=_int_env("HAM_X_GOHAM_CONSECUTIVE_FAILURE_STOP", 2),
        goham_policy_rejection_stop=_int_env("HAM_X_GOHAM_POLICY_REJECTION_STOP", 5),
        goham_model_timeout_stop=_int_env("HAM_X_GOHAM_MODEL_TIMEOUT_STOP", 3),
        enable_goham_live_controller=_bool_env("HAM_X_ENABLE_GOHAM_LIVE_CONTROLLER", False),
        goham_live_controller_original_posts_only=_bool_env(
            "HAM_X_GOHAM_LIVE_CONTROLLER_ORIGINAL_POSTS_ONLY",
            True,
        ),
        goham_live_max_actions_per_run=_int_env("HAM_X_GOHAM_LIVE_MAX_ACTIONS_PER_RUN", 1),
        enable_goham_reactive=_bool_env("HAM_X_ENABLE_GOHAM_REACTIVE", False),
        goham_reactive_dry_run=_bool_env("HAM_X_GOHAM_REACTIVE_DRY_RUN", True),
        goham_reactive_live_canary=_bool_env("HAM_X_GOHAM_REACTIVE_LIVE_CANARY", False),
        goham_reactive_max_replies_per_15m=_int_env("HAM_X_GOHAM_REACTIVE_MAX_REPLIES_PER_15M", 5),
        goham_reactive_max_replies_per_hour=_int_env("HAM_X_GOHAM_REACTIVE_MAX_REPLIES_PER_HOUR", 20),
        goham_reactive_max_replies_per_user_per_day=_int_env("HAM_X_GOHAM_REACTIVE_MAX_REPLIES_PER_USER_PER_DAY", 3),
        goham_reactive_max_replies_per_thread_per_day=_int_env("HAM_X_GOHAM_REACTIVE_MAX_REPLIES_PER_THREAD_PER_DAY", 5),
        goham_reactive_min_seconds_between_replies=_int_env("HAM_X_GOHAM_REACTIVE_MIN_SECONDS_BETWEEN_REPLIES", 60),
        goham_reactive_min_relevance=_float_env("HAM_X_GOHAM_REACTIVE_MIN_RELEVANCE", 0.75),
        goham_reactive_block_links=_bool_env("HAM_X_GOHAM_REACTIVE_BLOCK_LINKS", True),
        goham_reactive_failure_stop=_int_env("HAM_X_GOHAM_REACTIVE_FAILURE_STOP", 2),
        goham_reactive_policy_rejection_stop=_int_env("HAM_X_GOHAM_REACTIVE_POLICY_REJECTION_STOP", 10),
        goham_reactive_max_inbound_per_run=_int_env("HAM_X_GOHAM_REACTIVE_MAX_INBOUND_PER_RUN", 25),
        goham_reactive_max_replies_per_run=_int_env("HAM_X_GOHAM_REACTIVE_MAX_REPLIES_PER_RUN", 1),
    )
