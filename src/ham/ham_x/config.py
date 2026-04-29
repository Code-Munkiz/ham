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
    review_queue_path: Path
    exception_queue_path: Path
    execution_journal_path: Path
    audit_log_path: Path


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
        model=(os.environ.get("HAM_X_MODEL") or "grok-4.1-fast").strip() or "grok-4.1-fast",
        xurl_bin=(os.environ.get("HAM_X_XURL_BIN") or "xurl").strip() or "xurl",
        readonly_transport=(os.environ.get("HAM_X_READONLY_TRANSPORT") or DEFAULT_READONLY_TRANSPORT).strip()
        or DEFAULT_READONLY_TRANSPORT,
        execution_transport=(os.environ.get("HAM_X_EXECUTION_TRANSPORT") or DEFAULT_EXECUTION_TRANSPORT).strip()
        or DEFAULT_EXECUTION_TRANSPORT,
        canary_allowed_actions=(os.environ.get("HAM_X_CANARY_ALLOWED_ACTIONS") or DEFAULT_CANARY_ALLOWED_ACTIONS).strip()
        or DEFAULT_CANARY_ALLOWED_ACTIONS,
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
    )
