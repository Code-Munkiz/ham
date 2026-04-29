from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from src.ham.ham_x.config import HamXConfig
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.goham_live_controller import (
    GohamExecutionRequest,
    GohamExecutionResult,
    run_live_controller_once,
)
from src.ham.ham_x.goham_governor import GohamGovernorCandidate
from src.ham.ham_x.goham_policy import GOHAM_EXECUTION_KIND


def _test_config(
    tmp_path: Path,
    *,
    live_controller: bool = True,
    controller: bool = True,
    controller_dry_run: bool = False,
    goham: bool = True,
    dry_run: bool = False,
    autonomy_enabled: bool = True,
    live_execution: bool = True,
    emergency_stop: bool = False,
    total_cap: int = 1,
    post_cap: int = 1,
    daily_cap: int = 1,
    max_live_actions: int = 1,
    min_spacing: int = 120,
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
        goham_autonomous_per_run_cap=1,
        goham_min_score=0.90,
        goham_min_confidence=0.90,
        goham_allowed_actions="post",
        goham_block_links=True,
        review_queue_path=tmp_path / "review_queue.jsonl",
        exception_queue_path=tmp_path / "exception_queue.jsonl",
        execution_journal_path=tmp_path / "execution_journal.jsonl",
        audit_log_path=tmp_path / "audit.jsonl",
        enable_goham_controller=controller,
        goham_controller_dry_run=controller_dry_run,
        goham_max_total_actions_per_day=total_cap,
        goham_max_original_posts_per_day=post_cap,
        goham_max_quotes_per_day=0,
        goham_min_spacing_minutes=min_spacing,
        goham_max_actions_per_run=1,
        goham_max_candidates_per_run=5,
        goham_consecutive_failure_stop=2,
        goham_policy_rejection_stop=5,
        goham_model_timeout_stop=3,
        enable_goham_live_controller=live_controller,
        goham_live_controller_original_posts_only=True,
        goham_live_max_actions_per_run=max_live_actions,
    )


def _candidate(idx: int = 1, **overrides: Any) -> GohamGovernorCandidate:
    data = {
        "action_id": f"candidate-{idx}",
        "source_action_id": f"source-{idx}",
        "idempotency_key": "caller-supplied-key-is-normalized",
        "action_type": "post",
        "text": f"Ham is mapping useful Base builder workflows with guarded autonomy {idx}.",
        "topic": "base",
        "score": 0.95,
    }
    data.update(overrides)
    return GohamGovernorCandidate(**data)


def _execution_result(
    request: GohamExecutionRequest,
    config: HamXConfig,
    *,
    status: str = "executed",
    provider_post_id: str | None = "post-1",
    diagnostic: str = "",
) -> GohamExecutionResult:
    return GohamExecutionResult(
        status=status,  # type: ignore[arg-type]
        action_id=request.action_id,
        source_action_id=request.source_action_id,
        action_type=request.action_type,
        execution_allowed=True,
        mutation_attempted=True,
        provider_status_code=201 if status == "executed" else 500,
        provider_post_id=provider_post_id,
        provider_response={"status": status},
        audit_path=str(config.audit_log_path),
        reasons=[],
        diagnostic=diagnostic,
    )


def test_blocked_by_default(tmp_path: Path) -> None:
    cfg = _test_config(
        tmp_path,
        live_controller=False,
        controller=False,
        controller_dry_run=True,
        goham=False,
        dry_run=True,
        autonomy_enabled=False,
        live_execution=False,
    )
    calls = 0

    def fake_run_post(*args: Any, **kwargs: Any) -> GohamExecutionResult:
        nonlocal calls
        calls += 1
        raise AssertionError("disabled live controller must not call bridge")

    result = run_live_controller_once([_candidate()], config=cfg, run_post=fake_run_post)
    assert result.status == "blocked"
    assert "live_controller_disabled" in result.reasons
    assert "controller_dry_run_enabled" in result.reasons
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
    assert calls == 0


def test_dry_run_controller_never_calls_bridge(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, controller_dry_run=True)

    def fake_run_post(*args: Any, **kwargs: Any) -> GohamExecutionResult:
        raise AssertionError("dry-run controller flag must block live bridge")

    result = run_live_controller_once([_candidate()], config=cfg, run_post=fake_run_post)
    assert result.status == "blocked"
    assert "controller_dry_run_enabled" in result.reasons
    assert result.processed_count == 0


def test_live_controller_calls_bridge_at_most_once(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, min_spacing=0, daily_cap=3, total_cap=3, post_cap=3)
    journal = ExecutionJournal(config=cfg)
    calls: list[GohamExecutionRequest] = []

    def fake_run_post(request: GohamExecutionRequest, **kwargs: Any) -> GohamExecutionResult:
        calls.append(request)
        return _execution_result(request, cfg)

    result = run_live_controller_once([_candidate(1), _candidate(2), _candidate(3)], config=cfg, journal=journal, run_post=fake_run_post)
    assert result.status == "executed"
    assert len(calls) == 1
    assert result.processed_count == 1
    assert result.selected_candidate is not None
    assert result.execution_request is not None
    assert result.execution_request.idempotency_key.startswith("goham-live-")


def test_stops_after_one_blocked_when_no_candidate_passes(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    result = run_live_controller_once([_candidate(text="Ham update https://example.com")], config=cfg)
    assert result.status == "blocked"
    assert result.processed_count == 1
    assert result.execution_result is None
    assert "links_not_allowed" in result.reasons


def test_quote_reply_like_follow_dm_blocked(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    for action in ("quote", "reply", "like", "follow", "dm"):
        result = run_live_controller_once([_candidate(action_type=action)], config=cfg)
        assert result.status == "blocked"
        assert "unsupported_action_type" in result.reasons or "governor_tier_not_auto_original_post" in result.reasons
        assert result.mutation_attempted is False
    reply = run_live_controller_once([_candidate(metadata={"reply_target_id": "123"})], config=cfg)
    assert "reply_target_not_allowed" in reply.reasons


def test_link_text_blocked(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    result = run_live_controller_once([_candidate(text="Ham update https://example.com")], config=cfg)
    assert result.status == "blocked"
    assert "links_not_allowed" in result.reasons


def test_duplicate_source_idempotency_blocked_before_bridge(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, daily_cap=2, total_cap=2, post_cap=2)
    journal = ExecutionJournal(config=cfg)
    candidate = _candidate()
    first = run_live_controller_once([candidate], config=cfg, journal=journal, run_post=lambda request, **kwargs: _execution_result(request, cfg))
    journal.append_executed(
        action_id=first.execution_request.action_id if first.execution_request else "candidate-1",
        source_action_id="source-1",
        idempotency_key=first.execution_request.idempotency_key if first.execution_request else "missing",
        action_type="post",
        provider_post_id="post-1",
        execution_kind=GOHAM_EXECUTION_KIND,
    )
    calls = 0

    def fake_run_post(*args: Any, **kwargs: Any) -> GohamExecutionResult:
        nonlocal calls
        calls += 1
        raise AssertionError("duplicate should block before bridge")

    result = run_live_controller_once([candidate], config=cfg, journal=journal, run_post=fake_run_post)
    assert result.status == "blocked"
    assert "duplicate_execution" in result.reasons
    assert calls == 0


def test_spacing_block(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, daily_cap=2, total_cap=2, post_cap=2, min_spacing=120)
    journal = ExecutionJournal(config=cfg)
    journal.append_executed(
        action_id="old-action",
        source_action_id="old-source",
        idempotency_key="old-idem",
        action_type="post",
        provider_post_id="post-1",
        execution_kind=GOHAM_EXECUTION_KIND,
    )
    result = run_live_controller_once([_candidate(idempotency_key="new-idem")], config=cfg, journal=journal)
    assert result.status == "blocked"
    assert "min_spacing_not_elapsed" in result.reasons


def test_daily_cap_block(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, daily_cap=1, total_cap=1, post_cap=1)
    journal = ExecutionJournal(config=cfg)
    journal.append_executed(
        action_id="old-action",
        source_action_id="old-source",
        idempotency_key="old-idem",
        action_type="post",
        provider_post_id="post-1",
        execution_kind=GOHAM_EXECUTION_KIND,
    )
    result = run_live_controller_once([_candidate(idempotency_key="new-idem")], config=cfg, journal=journal)
    assert result.status == "blocked"
    assert "daily_total_action_budget_exhausted" in result.reasons


def test_emergency_stop_block(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, emergency_stop=True)
    result = run_live_controller_once([_candidate()], config=cfg)
    assert result.status == "blocked"
    assert "emergency_stop" in result.reasons
    assert result.processed_count == 0


def test_provider_failure_does_not_retry(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, min_spacing=0, daily_cap=3, total_cap=3, post_cap=3)
    calls = 0

    def fake_run_post(request: GohamExecutionRequest, **kwargs: Any) -> GohamExecutionResult:
        nonlocal calls
        calls += 1
        return _execution_result(request, cfg, status="failed", provider_post_id=None, diagnostic="provider failed")

    result = run_live_controller_once([_candidate(1), _candidate(2)], config=cfg, run_post=fake_run_post)
    assert calls == 1
    assert result.status == "failed"
    assert result.mutation_attempted is True
    assert result.diagnostic == "provider failed"


def test_successful_mocked_governed_post(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, min_spacing=0)
    journal = ExecutionJournal(config=cfg)

    def fake_run_post(request: GohamExecutionRequest, **kwargs: Any) -> GohamExecutionResult:
        journal.append_executed(
            action_id=request.action_id,
            source_action_id=request.source_action_id,
            idempotency_key=request.idempotency_key,
            action_type="post",
            provider_post_id="post-1",
            execution_kind=GOHAM_EXECUTION_KIND,
        )
        return _execution_result(request, cfg, provider_post_id="post-1")

    result = run_live_controller_once([_candidate()], config=cfg, journal=journal, run_post=fake_run_post)
    assert result.status == "executed"
    assert result.provider_post_id == "post-1"
    assert result.status_after.daily_cap_used == 1
    assert result.execution_allowed is True
    assert result.mutation_attempted is True


def test_bridge_result_reflected_in_summary(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)

    def fake_run_post(request: GohamExecutionRequest, **kwargs: Any) -> GohamExecutionResult:
        return _execution_result(request, cfg, provider_post_id="post-xyz")

    result = run_live_controller_once([_candidate()], config=cfg, run_post=fake_run_post)
    assert result.execution_result is not None
    assert result.provider_post_id == "post-xyz"
    assert result.provider_status_code == 201
    dumped = json.dumps(result.redacted_dump(), sort_keys=True)
    assert "consumer-secret-1234567890" not in dumped


def test_audit_emitted_for_every_candidate_and_completion(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, min_spacing=0, daily_cap=3, total_cap=3, post_cap=3)
    result = run_live_controller_once(
        [_candidate(1, text="Ham update https://example.com"), _candidate(2)],
        config=cfg,
        run_post=lambda request, **kwargs: _execution_result(request, cfg),
    )
    audit = cfg.audit_log_path.read_text(encoding="utf-8")
    assert "goham_live_controller_started" in audit
    assert audit.count("goham_live_controller_candidate_decision") == result.processed_count
    assert "goham_live_controller_completed" in audit
    assert len(result.audit_ids) == result.processed_count + 2


def test_no_scheduler_daemon_infinite_loop_or_xurl_mutation() -> None:
    path = Path(__file__).parents[1] / "src" / "ham" / "ham_x" / "goham_live_controller.py"
    text = path.read_text(encoding="utf-8")
    forbidden = ("schedule", "daemon", "while True", "xurl", "subprocess", "XCanaryExecutor")
    assert not any(item in text for item in forbidden)


def test_smoke_and_phase2b_still_cannot_execute_directly() -> None:
    root = Path(__file__).parents[1] / "src" / "ham" / "ham_x"
    for name in ("smoke.py", "live_dry_run.py", "pipeline.py", "autonomy.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "x_executor" not in text
        assert "manual_canary" not in text
        assert "goham_bridge" not in text


def test_goham_controller_remains_dry_run_only() -> None:
    path = Path(__file__).parents[1] / "src" / "ham" / "ham_x" / "goham_controller.py"
    text = path.read_text(encoding="utf-8")
    assert "dry-run-only" in text
    assert "goham_bridge" not in text
    assert "run_goham_guarded_post" not in text


def test_live_controller_import_isolation() -> None:
    path = Path(__file__).parents[1] / "src" / "ham" / "ham_x" / "goham_live_controller.py"
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
        "src.ham.ham_x.live_dry_run",
        "src.ham.ham_x.smoke",
    }
    assert imported.isdisjoint(forbidden)
