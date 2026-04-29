from __future__ import annotations

import json
from pathlib import Path

from src.ham.ham_x.autonomy import AutonomyDecisionResult
from src.ham.ham_x.config import HamXConfig
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.goham_bridge import GohamExecutionRequest, run_goham_guarded_post
from src.ham.ham_x.goham_policy import GOHAM_EXECUTION_KIND
from src.ham.ham_x.x_executor import XCanaryExecutor


class FakeResponse:
    def __init__(self, status_code: int, body: dict[str, object], text: str = "") -> None:
        self.status_code = status_code
        self._body = body
        self.text = text

    def json(self) -> dict[str, object]:
        return self._body


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
    min_score: float = 0.90,
    min_confidence: float = 0.90,
) -> HamXConfig:
    return HamXConfig(
        xai_api_key="",
        x_api_key="consumer-key",
        x_api_secret="consumer-secret",
        x_access_token="access-token",
        x_access_token_secret="access-token-secret",
        x_bearer_token="",
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
        goham_min_score=min_score,
        goham_min_confidence=min_confidence,
        goham_allowed_actions="post",
        goham_block_links=True,
        review_queue_path=tmp_path / "review_queue.jsonl",
        exception_queue_path=tmp_path / "exception_queue.jsonl",
        execution_journal_path=tmp_path / "execution_journal.jsonl",
        audit_log_path=tmp_path / "audit.jsonl",

        enable_goham_controller=False,
        goham_controller_dry_run=True,
        goham_max_total_actions_per_day=1,
        goham_max_original_posts_per_day=1,
        goham_max_quotes_per_day=0,
        goham_min_spacing_minutes=120,
        goham_max_actions_per_run=1,
        goham_max_candidates_per_run=5,
        goham_consecutive_failure_stop=2,
        goham_policy_rejection_stop=5,
        goham_model_timeout_stop=3,
    )


def _request(**overrides) -> GohamExecutionRequest:
    data = {
        "tenant_id": "ham-official",
        "agent_id": "ham-pr-rockstar",
        "campaign_id": "base-stealth-launch",
        "account_id": "ham-x-official",
        "action_type": "post",
        "text": "Ham is live-checking guarded autonomy on X with one original post.",
        "source_action_id": "phase2b-action-1",
        "idempotency_key": "goham-key-1",
    }
    data.update(overrides)
    return GohamExecutionRequest(**data)


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
        "action_id": "phase2b-action-1",
    }
    data.update(overrides)
    return AutonomyDecisionResult(**data)


def _executor(config: HamXConfig, response: FakeResponse, calls: list[dict[str, object]]):
    def http_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return response

    return XCanaryExecutor(config=config, http_post=http_post)


def test_blocked_by_default(tmp_path: Path) -> None:
    result = run_goham_guarded_post(
        _request(),
        decision=_decision(),
        config=_test_config(tmp_path, goham=False, dry_run=True, autonomy_enabled=False, live_execution=False),
    )
    assert result.status == "blocked"
    assert "goham_execution_disabled" in result.reasons
    assert result.execution_allowed is False
    assert result.mutation_attempted is False


def test_blocked_when_required_gates_fail(tmp_path: Path) -> None:
    cases = [
        (_test_config(tmp_path, goham=False), "goham_execution_disabled"),
        (_test_config(tmp_path, dry_run=True), "dry_run_enabled"),
        (_test_config(tmp_path, emergency_stop=True), "emergency_stop"),
        (_test_config(tmp_path, autonomy_enabled=False), "autonomy_disabled"),
        (_test_config(tmp_path, live_execution=False), "live_execution_disabled"),
    ]
    for cfg, reason in cases:
        result = run_goham_guarded_post(_request(), decision=_decision(), config=cfg)
        assert result.status == "blocked"
        assert reason in result.reasons


def test_blocked_when_decision_safety_score_or_confidence_fail(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    assert "decision_not_auto_approve" in run_goham_guarded_post(
        _request(), decision=_decision(decision="queue_review"), config=cfg
    ).reasons
    assert "score_below_goham_threshold" in run_goham_guarded_post(
        _request(), decision=_decision(score_100=89, raw_score=0.89), config=cfg
    ).reasons
    assert "confidence_below_goham_threshold" in run_goham_guarded_post(
        _request(), decision=_decision(confidence=0.89), config=cfg
    ).reasons
    assert "risk_not_low" in run_goham_guarded_post(
        _request(), decision=_decision(risk_level="medium"), config=cfg
    ).reasons
    unsafe = run_goham_guarded_post(
        _request(text="This is guaranteed to deliver 10x gains."),
        decision=_decision(),
        config=cfg,
    )
    assert any(reason.startswith("safety_policy:") for reason in unsafe.reasons)


def test_blocked_for_unsupported_actions_targets_links_and_finance_language(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    for action in ("quote", "reply", "like", "follow", "dm"):
        assert "unsupported_action_type" in run_goham_guarded_post(
            _request(action_type=action), decision=_decision(), config=cfg
        ).reasons
    assert "target_post_not_allowed" in run_goham_guarded_post(
        _request(target_post_id="123"), decision=_decision(), config=cfg
    ).reasons
    assert "quote_target_not_allowed" in run_goham_guarded_post(
        _request(quote_target_id="123"), decision=_decision(), config=cfg
    ).reasons
    assert "reply_target_not_allowed" in run_goham_guarded_post(
        _request(reply_target_id="123"), decision=_decision(), config=cfg
    ).reasons
    assert "links_not_allowed" in run_goham_guarded_post(
        _request(text="Ham update https://example.com"), decision=_decision(), config=cfg
    ).reasons
    assert "financial_or_buy_language" in run_goham_guarded_post(
        _request(text="Buy this token before the price moves."), decision=_decision(), config=cfg
    ).reasons


def test_blocked_over_caps_and_duplicate_idempotency(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    journal = ExecutionJournal(config=cfg)
    result = run_goham_guarded_post(
        _request(),
        decision=_decision(),
        config=cfg,
        journal=journal,
        per_run_count=1,
    )
    assert "goham_per_run_cap_exceeded" in result.reasons
    journal.append_executed(
        action_id="old-action",
        source_action_id="old-source",
        idempotency_key="old-key",
        action_type="post",
        provider_post_id="123",
        execution_kind=GOHAM_EXECUTION_KIND,
    )
    daily = run_goham_guarded_post(_request(idempotency_key="new-key"), decision=_decision(), config=cfg, journal=journal)
    assert "goham_daily_cap_exceeded" in daily.reasons
    cfg2 = _test_config(tmp_path, daily_cap=2)
    duplicate = run_goham_guarded_post(_request(idempotency_key="old-key"), decision=_decision(), config=cfg2, journal=journal)
    assert "duplicate_execution" in duplicate.reasons


def test_mocked_successful_autonomous_original_post_records_journal_and_audit(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    calls: list[dict[str, object]] = []
    executor = _executor(cfg, FakeResponse(201, {"data": {"id": "post-1", "text": "ok"}}), calls)
    result = run_goham_guarded_post(_request(), decision=_decision(), config=cfg, executor=executor)
    assert result.status == "executed"
    assert result.execution_allowed is True
    assert result.mutation_attempted is True
    assert result.provider_status_code == 201
    assert result.provider_post_id == "post-1"
    assert result.execution_kind == GOHAM_EXECUTION_KIND
    assert calls and calls[0]["json"] == {"text": _request().text}
    records = ExecutionJournal(config=cfg).records()
    assert records[0]["execution_kind"] == GOHAM_EXECUTION_KIND
    audit = cfg.audit_log_path.read_text(encoding="utf-8")
    assert "goham_execution_allowed" in audit
    assert "goham_execution_executed" in audit


def test_provider_failure_after_gates_pass_sets_attempted_flags(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    executor = _executor(cfg, FakeResponse(403, {"detail": "Forbidden"}), [])
    result = run_goham_guarded_post(_request(), decision=_decision(), config=cfg, executor=executor)
    assert result.status == "failed"
    assert result.execution_allowed is True
    assert result.mutation_attempted is True
    assert result.provider_status_code == 403
    audit = cfg.audit_log_path.read_text(encoding="utf-8")
    assert "goham_execution_failed" in audit


def test_blocked_audit_events_are_specialized(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    run_goham_guarded_post(_request(text="Buy this token."), decision=_decision(), config=cfg)
    run_goham_guarded_post(_request(), decision=_decision(), config=cfg, per_run_count=1)
    journal = ExecutionJournal(config=cfg)
    journal.append_executed(
        action_id="old-action",
        idempotency_key="goham-key-1",
        action_type="post",
        provider_post_id="123",
        execution_kind=GOHAM_EXECUTION_KIND,
    )
    run_goham_guarded_post(_request(), decision=_decision(), config=_test_config(tmp_path, daily_cap=2), journal=journal)
    audit = cfg.audit_log_path.read_text(encoding="utf-8")
    assert "goham_execution_policy_blocked" in audit
    assert "goham_execution_cap_blocked" in audit
    assert "goham_execution_duplicate_blocked" in audit


def test_phase2b_smoke_pipeline_and_autonomy_still_do_not_import_executor() -> None:
    root = Path(__file__).parents[1] / "src" / "ham" / "ham_x"
    for name in ("live_dry_run.py", "pipeline.py", "smoke.py", "autonomy.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "manual_canary" not in text
        assert "x_executor" not in text


def test_only_goham_bridge_and_manual_canary_import_x_executor() -> None:
    root = Path(__file__).parents[1] / "src" / "ham" / "ham_x"
    importers = []
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "import XCanaryExecutor" in text or "from src.ham.ham_x.x_executor" in text:
            importers.append(path.name)
    assert sorted(importers) == ["goham_bridge.py", "manual_canary.py"]
