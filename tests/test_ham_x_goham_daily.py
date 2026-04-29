from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from src.ham.ham_x.autonomy import AutonomyDecisionResult
from src.ham.ham_x.config import HamXConfig
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.goham_bridge import GohamExecutionRequest, GohamExecutionResult
from src.ham.ham_x.goham_daily import run_goham_daily_once
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


def _request(**overrides: Any) -> GohamExecutionRequest:
    data = {
        "tenant_id": "ham-official",
        "agent_id": "ham-pr-rockstar",
        "campaign_id": "base-stealth-launch",
        "account_id": "ham-x-official",
        "action_type": "post",
        "text": "Ham is live-checking guarded autonomy on X with one original post.",
        "source_action_id": "phase2b-action-1",
        "idempotency_key": "goham-key-1",
        "action_id": "goham-action-1",
    }
    data.update(overrides)
    return GohamExecutionRequest(**data)


def _decision(**overrides: Any) -> AutonomyDecisionResult:
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


def _execution_result(
    request: GohamExecutionRequest,
    config: HamXConfig,
    *,
    status: str = "executed",
    provider_post_id: str | None = "post-1",
    diagnostic: str = "",
    provider_response: dict[str, Any] | None = None,
) -> GohamExecutionResult:
    return GohamExecutionResult(
        status=status,  # type: ignore[arg-type]
        action_id=request.action_id,
        source_action_id=request.source_action_id,
        action_type=request.action_type,
        execution_allowed=True,
        mutation_attempted=True,
        provider_status_code=201 if status == "executed" else 403,
        provider_post_id=provider_post_id,
        provider_response=provider_response or {"status": status},
        audit_path=str(config.audit_log_path),
        diagnostic=diagnostic,
    )


def test_blocks_by_default_and_does_not_call_bridge(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, goham=False, dry_run=True, autonomy_enabled=False, live_execution=False)
    calls: list[dict[str, Any]] = []

    def fake_run_post(*args: Any, **kwargs: Any) -> GohamExecutionResult:
        calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("preflight block should not call run_post")

    result = run_goham_daily_once(_request(), _decision(), config=cfg, run_post=fake_run_post)
    assert result.status == "blocked"
    assert result.execution_result is None
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
    assert "goham_execution_disabled" in result.reasons
    assert calls == []


def test_calls_bridge_exactly_once_when_preflight_passes(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    request = _request()
    calls: list[dict[str, Any]] = []

    def fake_run_post(*args: Any, **kwargs: Any) -> GohamExecutionResult:
        calls.append({"args": args, "kwargs": kwargs})
        return _execution_result(request, cfg)

    result = run_goham_daily_once(request, _decision(), config=cfg, run_post=fake_run_post)
    assert result.status == "executed"
    assert len(calls) == 1
    assert calls[0]["args"] == (request,)
    assert calls[0]["kwargs"]["per_run_count"] == 0
    assert result.execution_result is not None
    assert result.execution_allowed is True
    assert result.mutation_attempted is True


def test_never_retries_after_provider_failure(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    request = _request()
    calls = 0

    def fake_run_post(*args: Any, **kwargs: Any) -> GohamExecutionResult:
        nonlocal calls
        calls += 1
        return _execution_result(request, cfg, status="failed", provider_post_id=None, diagnostic="provider rejected")

    result = run_goham_daily_once(request, _decision(), config=cfg, run_post=fake_run_post)
    assert calls == 1
    assert result.status == "failed"
    assert result.execution_allowed is True
    assert result.mutation_attempted is True
    assert result.diagnostic == "provider rejected"


def test_returns_before_and_after_status(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    request = _request()

    def fake_run_post(*args: Any, **kwargs: Any) -> GohamExecutionResult:
        return _execution_result(request, cfg)

    result = run_goham_daily_once(request, _decision(), config=cfg, run_post=fake_run_post)
    assert result.status_before.daily_cap_used == 0
    assert result.status_before.daily_cap_remaining == 1
    assert result.status_after.daily_cap_used == 0
    assert result.status_after.daily_cap_remaining == 1
    assert result.journal_path == str(cfg.execution_journal_path)
    assert result.audit_path == str(cfg.audit_log_path)


def test_redacted_bounded_summary(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    request = _request()
    secret = "tok_1234567890abcdefghijklmnopqrstuvwxyzSECRET"
    large = "x" * 1500

    def fake_run_post(*args: Any, **kwargs: Any) -> GohamExecutionResult:
        return _execution_result(
            request,
            cfg,
            provider_post_id=secret,
            provider_response={"token": secret, "body": large},
        )

    result = run_goham_daily_once(request, _decision(), config=cfg, run_post=fake_run_post)
    dumped = json.dumps(result.redacted_dump(), sort_keys=True)
    assert secret not in dumped
    assert large not in dumped
    assert "[REDACTED]" in dumped or "[REDACTED_TOKEN]" in dumped


def test_quote_reply_link_and_financial_text_block_before_execution(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    cases = [
        (_request(action_type="quote"), "unsupported_action_type"),
        (_request(reply_target_id="123"), "reply_target_not_allowed"),
        (_request(text="Ham update https://example.com"), "links_not_allowed"),
        (_request(text="Buy this token before the price moves."), "financial_or_buy_language"),
    ]
    for request, reason in cases:
        calls = 0

        def fake_run_post(*args: Any, **kwargs: Any) -> GohamExecutionResult:
            nonlocal calls
            calls += 1
            raise AssertionError("blocked content should not execute")

        result = run_goham_daily_once(request, _decision(), config=cfg, run_post=fake_run_post)
        assert result.status == "blocked"
        assert reason in result.reasons
        assert result.execution_result is None
        assert calls == 0


def test_existing_goham_autonomous_row_blocks_cap_one_per_day(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, daily_cap=1)
    journal = ExecutionJournal(config=cfg)
    journal.append_executed(
        action_id="old-action",
        source_action_id="old-source",
        idempotency_key="old-key",
        action_type="post",
        provider_post_id="old-post",
        execution_kind=GOHAM_EXECUTION_KIND,
    )
    result = run_goham_daily_once(_request(idempotency_key="new-key"), _decision(), config=cfg, journal=journal)
    assert result.status == "blocked"
    assert "goham_daily_cap_exceeded" in result.reasons
    assert result.status_before.daily_cap_used == 1
    assert result.status_after.daily_cap_used == 1


def test_manual_canary_rows_do_not_block_goham_daily_cap(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, daily_cap=1)
    journal = ExecutionJournal(config=cfg)
    journal.append_executed(
        action_id="manual-action",
        source_action_id="manual-source",
        idempotency_key="manual-key",
        action_type="post",
        provider_post_id="manual-post",
        execution_kind="manual_canary",
    )
    request = _request()
    calls = 0

    def fake_run_post(*args: Any, **kwargs: Any) -> GohamExecutionResult:
        nonlocal calls
        calls += 1
        return _execution_result(request, cfg)

    result = run_goham_daily_once(request, _decision(), config=cfg, journal=journal, run_post=fake_run_post)
    assert calls == 1
    assert result.status == "executed"
    assert result.status_before.daily_cap_used == 0
    assert result.status_before.daily_cap_remaining == 1


def test_successful_fake_execution_reflects_provider_post_id_and_updated_cap(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, daily_cap=1)
    journal = ExecutionJournal(config=cfg)
    request = _request()

    def fake_run_post(*args: Any, **kwargs: Any) -> GohamExecutionResult:
        journal.append_executed(
            action_id=request.action_id,
            source_action_id=request.source_action_id,
            idempotency_key=request.idempotency_key,
            action_type="post",
            provider_post_id="post-1",
            execution_kind=GOHAM_EXECUTION_KIND,
        )
        return _execution_result(request, cfg, provider_post_id="post-1")

    result = run_goham_daily_once(request, _decision(), config=cfg, journal=journal, run_post=fake_run_post)
    assert result.status == "executed"
    assert result.provider_post_id == "post-1"
    assert result.status_after.provider_post_id == "post-1"
    assert result.status_after.daily_cap_used == 1
    assert result.status_after.daily_cap_remaining == 0


def test_rejects_list_input() -> None:
    try:
        run_goham_daily_once([_request()], _decision())  # type: ignore[arg-type]
    except TypeError as exc:
        assert "exactly one" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("list input should be rejected")


def test_goham_daily_import_isolation() -> None:
    path = Path(__file__).parents[1] / "src" / "ham" / "ham_x" / "goham_daily.py"
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
        "src.ham.ham_x.pipeline",
        "src.ham.ham_x.smoke",
        "src.ham.ham_x.live_dry_run",
    }
    assert imported.isdisjoint(forbidden)
