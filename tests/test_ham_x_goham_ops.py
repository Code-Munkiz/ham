from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from src.ham.ham_x.autonomy import AutonomyDecisionResult
from src.ham.ham_x.config import HamXConfig
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.goham_ops import (
    check_goham_cap,
    dry_preflight_goham_candidate,
    show_goham_status,
    summarize_goham_journal,
)
from src.ham.ham_x.goham_policy import GOHAM_EXECUTION_KIND


def _test_config(
    tmp_path: Path,
    *,
    goham: bool = True,
    dry_run: bool = False,
    autonomy_enabled: bool = True,
    live_execution: bool = True,
    emergency_stop: bool = False,
    daily_cap: int = 1,
    per_run_cap: int = 1,
) -> HamXConfig:
    return HamXConfig(
        xai_api_key="xai-secret-value-1234567890",
        x_api_key="consumer-key-1234567890",
        x_api_secret="consumer-secret-1234567890",
        x_access_token="access-token-1234567890",
        x_access_token_secret="access-token-secret-1234567890",
        x_bearer_token="bearer-token-1234567890",
        tenant_id="ham-official",
        agent_id="ham-pr-rockstar",
        campaign_id="base-stealth-launch",
        account_id="ham-x-official",
        profile_id="ham.default",
        autonomy_mode="goham",
        policy_profile_id="platform-default",
        brand_voice_id="ham-canonical",
        catalog_skill_id="bundled.social-media.xurl",
        emergency_stop=emergency_stop,
        enable_live_smoke=False,
        enable_live_execution=live_execution,
        autonomy_enabled=autonomy_enabled,
        dry_run=dry_run,
        max_posts_per_hour=0,
        max_quotes_per_hour=0,
        max_searches_per_hour=30,
        execution_daily_cap=1,
        execution_per_run_cap=1,
        daily_spend_limit_usd=5.0,
        model="grok-4.20",
        xurl_bin="xurl",
        readonly_transport="direct",
        execution_transport="direct_oauth1",
        canary_allowed_actions="post,quote",
        enable_live_read_model_dry_run=False,
        live_dry_run_query="Base ecosystem autonomous agents",
        live_dry_run_max_results=10,
        live_dry_run_max_candidates=3,
        live_draft_max_output_tokens=120,
        live_draft_timeout_seconds=20,
        enable_goham_execution=goham,
        goham_autonomous_daily_cap=daily_cap,
        goham_autonomous_per_run_cap=per_run_cap,
        goham_min_score=0.90,
        goham_min_confidence=0.90,
        goham_allowed_actions="post",
        goham_block_links=True,
        review_queue_path=tmp_path / "review_queue.jsonl",
        exception_queue_path=tmp_path / "exception_queue.jsonl",
        execution_journal_path=tmp_path / "execution_journal.jsonl",
        audit_log_path=tmp_path / "audit.jsonl",
    )


def _request(**overrides):
    data = {
        "tenant_id": "ham-official",
        "agent_id": "ham-pr-rockstar",
        "campaign_id": "base-stealth-launch",
        "account_id": "ham-x-official",
        "action_type": "post",
        "text": "Ham is live-checking guarded autonomy on X with one original post.",
        "action_id": "goham-action-1",
        "source_action_id": "phase2b-action-1",
        "idempotency_key": "goham-key-1",
        "target_post_id": None,
        "quote_target_id": None,
        "reply_target_id": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _decision(**overrides) -> AutonomyDecisionResult:
    data = {
        "decision": "auto_approve",
        "execution_state": "candidate_only",
        "execution_allowed": False,
        "confidence": 0.95,
        "risk_level": "low",
        "reasons": ["very_high_confidence_candidate"],
        "requires_human_review": False,
        "score_100": 95,
        "raw_score": 0.95,
        "safety_severity": "low",
        "tenant_id": "ham-official",
        "agent_id": "ham-pr-rockstar",
        "campaign_id": "base-stealth-launch",
        "account_id": "ham-x-official",
        "profile_id": "ham.default",
        "policy_profile_id": "platform-default",
        "brand_voice_id": "ham-canonical",
        "autonomy_mode": "goham",
        "catalog_skill_id": "bundled.social-media.xurl",
        "action_id": "goham-action-1",
    }
    data.update(overrides)
    return AutonomyDecisionResult(**data)


def _write_row(path: Path, **overrides) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "action_id": "goham-action-1",
        "source_action_id": "phase2b-action-1",
        "idempotency_key": "goham-key-1",
        "action_type": "post",
        "execution_kind": GOHAM_EXECUTION_KIND,
        "provider_post_id": "post-1",
        "status": "executed",
        "executed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    row.update(overrides)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def test_empty_missing_and_malformed_journal_handled_safely(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    summary = summarize_goham_journal(cfg)
    status = show_goham_status(cfg)
    assert summary.total_autonomous_count == 0
    assert summary.last_autonomous_post is None
    assert status.daily_cap_used == 0
    assert status.daily_cap_remaining == 1
    assert status.mutation_attempted is False

    cfg.execution_journal_path.write_text("{not-json}\n\n", encoding="utf-8")
    assert summarize_goham_journal(cfg).total_autonomous_count == 0
    assert check_goham_cap(cfg).daily_cap_used == 0


def test_latest_goham_autonomous_post_is_reported(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, daily_cap=3)
    _write_row(cfg.execution_journal_path, action_id="older", provider_post_id="post-older")
    _write_row(cfg.execution_journal_path, action_id="newer", provider_post_id="post-newer")
    status = show_goham_status(cfg)
    assert status.last_autonomous_post is not None
    assert status.last_autonomous_post["action_id"] == "newer"
    assert status.provider_post_id == "post-newer"
    assert status.daily_cap_used == 2
    assert status.daily_cap_remaining == 1


def test_manual_canary_rows_ignored_for_goham_status_and_cap(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    _write_row(
        cfg.execution_journal_path,
        action_id="manual-action",
        idempotency_key="manual-key",
        execution_kind="manual_canary",
        provider_post_id="manual-post",
    )
    status = show_goham_status(cfg)
    assert status.last_autonomous_post is None
    assert status.provider_post_id is None
    assert status.daily_cap_used == 0
    assert status.daily_cap_remaining == 1
    assert status.execution_allowed_now is True


def test_prior_day_rows_do_not_count_today(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    _write_row(cfg.execution_journal_path, action_id="yesterday", executed_at=yesterday)
    status = show_goham_status(cfg)
    assert status.daily_cap_used == 0
    assert status.daily_cap_remaining == 1
    assert status.last_autonomous_post is not None
    assert status.last_autonomous_post["action_id"] == "yesterday"


def test_emergency_stop_and_gate_state_reflected(tmp_path: Path) -> None:
    cfg = _test_config(
        tmp_path,
        goham=False,
        dry_run=True,
        autonomy_enabled=False,
        live_execution=False,
        emergency_stop=True,
    )
    status = show_goham_status(cfg)
    assert status.emergency_stop is True
    assert status.execution_allowed_now is False
    assert status.gate_state == {
        "enable_goham_execution": False,
        "autonomy_enabled": False,
        "dry_run": True,
        "enable_live_execution": False,
        "goham_allowed_actions": "post",
        "goham_block_links": True,
    }
    assert "read-only" in status.diagnostic


def test_no_secrets_or_opaque_tokens_appear_in_status_output(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    opaque = "tok_1234567890abcdefghijklmnopqrstuvwxyzSECRET"
    _write_row(
        cfg.execution_journal_path,
        idempotency_key=opaque,
        provider_post_id=opaque,
    )
    dumped = json.dumps(show_goham_status(cfg).redacted_dump(), sort_keys=True)
    assert "consumer-secret" not in dumped
    assert "access-token-secret" not in dumped
    assert opaque not in dumped
    assert "[REDACTED_TOKEN]" in dumped


def test_status_and_preflight_do_not_write_journal_or_audit(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    status = show_goham_status(cfg)
    result = dry_preflight_goham_candidate(_request(), _decision(), config=cfg)
    assert status.mutation_attempted is False
    assert result.mutation_attempted is False
    assert cfg.execution_journal_path.exists() is False
    assert cfg.audit_log_path.exists() is False


def test_dry_preflight_blocks_duplicate_idempotency_key(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, daily_cap=2)
    journal = ExecutionJournal(config=cfg)
    journal.append_executed(
        action_id="other-action",
        source_action_id="other-source",
        idempotency_key="goham-key-1",
        action_type="post",
        provider_post_id="post-1",
        execution_kind=GOHAM_EXECUTION_KIND,
    )
    result = dry_preflight_goham_candidate(_request(), _decision(), config=cfg, journal=journal)
    assert result.allowed is False
    assert "duplicate_execution" in result.reasons
    assert result.execution_allowed is False


def test_dry_preflight_reports_cap_block_at_one_per_day(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, daily_cap=1)
    journal = ExecutionJournal(config=cfg)
    journal.append_executed(
        action_id="old-action",
        source_action_id="old-source",
        idempotency_key="old-key",
        action_type="post",
        provider_post_id="post-1",
        execution_kind=GOHAM_EXECUTION_KIND,
    )
    result = dry_preflight_goham_candidate(_request(idempotency_key="new-key"), _decision(), config=cfg, journal=journal)
    assert result.allowed is False
    assert "goham_daily_cap_exceeded" in result.reasons
    assert result.mutation_attempted is False


def test_goham_ops_import_isolation() -> None:
    path = Path(__file__).parents[1] / "src" / "ham" / "ham_x" / "goham_ops.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = {
        "src.ham.ham_x.x_executor",
        "src.ham.ham_x.manual_canary",
        "src.ham.ham_x.goham_bridge",
        "src.ham.ham_x.smoke",
        "src.ham.ham_x.pipeline",
        "src.ham.ham_x.live_dry_run",
    }
    assert imported.isdisjoint(forbidden)
