from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.ham.ham_x.config import HamXConfig
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.goham_campaign import GohamCampaignProfile
from src.ham.ham_x.goham_governor import (
    GohamGovernorCandidate,
    GohamGovernorState,
    evaluate_goham_governor,
)
from src.ham.ham_x.goham_policy import GOHAM_EXECUTION_KIND


def _test_config(
    tmp_path: Path,
    *,
    controller: bool = True,
    controller_dry_run: bool = True,
    emergency_stop: bool = False,
    total_cap: int = 1,
    post_cap: int = 1,
    quote_cap: int = 0,
    max_actions_per_run: int = 1,
    min_spacing: int = 120,
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
        enable_live_execution=False,
        autonomy_enabled=False,
        dry_run=True,
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
        enable_goham_execution=False,
        goham_autonomous_daily_cap=1,
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
        goham_max_quotes_per_day=quote_cap,
        goham_min_spacing_minutes=min_spacing,
        goham_max_actions_per_run=max_actions_per_run,
        goham_max_candidates_per_run=5,
        goham_consecutive_failure_stop=2,
        goham_policy_rejection_stop=5,
        goham_model_timeout_stop=3,
    )


def _profile(cfg: HamXConfig, *, allowed: list[str] | None = None, link_policy: bool = False) -> GohamCampaignProfile:
    return GohamCampaignProfile(
        campaign_id=cfg.campaign_id,
        topics=["base", "agents"],
        watch_queries=["base agents"],
        forbidden_topics=[],
        allowed_action_types=allowed or ["post"],
        daily_action_budget=cfg.goham_max_total_actions_per_day,
        max_posts_per_day=cfg.goham_max_original_posts_per_day,
        max_quotes_per_day=cfg.goham_max_quotes_per_day,
        min_spacing_minutes=cfg.goham_min_spacing_minutes,
        link_policy=link_policy,
        risk_tolerance="low",
        brand_voice_id=cfg.brand_voice_id,
        active_hours=[],
        stop_conditions=[],
    )


def _candidate(**overrides) -> GohamGovernorCandidate:
    data = {
        "action_id": "candidate-1",
        "source_action_id": "source-1",
        "idempotency_key": "idem-1",
        "action_type": "post",
        "text": "Ham is mapping useful Base builder workflows with guarded autonomy.",
        "topic": "base",
        "score": 0.95,
    }
    data.update(overrides)
    return GohamGovernorCandidate(**data)


def test_no_action_by_default(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, controller=False)
    result = evaluate_goham_governor(_candidate(), config=cfg, profile=_profile(cfg))
    assert result.allowed is False
    assert "controller_disabled" in result.reasons
    assert result.mutation_attempted is False


def test_emergency_stop_always_blocks(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, emergency_stop=True)
    result = evaluate_goham_governor(_candidate(), config=cfg, profile=_profile(cfg))
    assert result.allowed is False
    assert "emergency_stop" in result.reasons


def test_total_post_and_quote_caps(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, total_cap=0, post_cap=0, quote_cap=0)
    post = evaluate_goham_governor(_candidate(), config=cfg, profile=_profile(cfg))
    assert "daily_total_action_budget_exhausted" in post.reasons
    assert "daily_original_post_cap_exhausted" in post.reasons
    quote = evaluate_goham_governor(
        _candidate(action_type="quote", quote_target_id="target-1"),
        config=cfg,
        profile=_profile(cfg, allowed=["post", "quote"]),
    )
    assert "daily_quote_cap_exhausted" in quote.reasons


def test_spacing_enforcement(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, min_spacing=120)
    journal = ExecutionJournal(config=cfg)
    journal.append_executed(
        action_id="old-action",
        source_action_id="old-source",
        idempotency_key="old-idem",
        action_type="post",
        provider_post_id="post-1",
        execution_kind=GOHAM_EXECUTION_KIND,
    )
    result = evaluate_goham_governor(_candidate(idempotency_key="new-idem"), config=cfg, journal=journal, profile=_profile(cfg))
    assert "min_spacing_not_elapsed" in result.reasons
    assert result.budget.next_allowed_action_at is not None


def test_topic_and_target_cooldowns(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    now = datetime.now(timezone.utc)
    state = GohamGovernorState(
        per_topic_cooldowns={"base": now.isoformat().replace("+00:00", "Z")},
        per_target_cooldowns={"target-1": now.isoformat().replace("+00:00", "Z")},
    )
    result = evaluate_goham_governor(
        _candidate(target_post_id="target-1"),
        config=cfg,
        profile=_profile(cfg),
        state=state,
        now=now + timedelta(minutes=10),
    )
    assert "topic_cooldown_active" in result.reasons
    assert "target_cooldown_active" in result.reasons


def test_duplicate_source_text_and_idempotency_blocks(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    candidate = _candidate()
    state = GohamGovernorState(
        duplicate_text_keys={candidate.text_key()},
        duplicate_source_keys={candidate.source_action_id},
        duplicate_idempotency_keys={candidate.idempotency_key},
    )
    result = evaluate_goham_governor(candidate, config=cfg, profile=_profile(cfg), state=state)
    assert "duplicate_text" in result.reasons
    assert "duplicate_source" in result.reasons
    assert "duplicate_idempotency_key" in result.reasons


def test_link_block_and_quote_disabled_by_default(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    linked = evaluate_goham_governor(
        _candidate(text="Ham update https://example.com"),
        config=cfg,
        profile=_profile(cfg, link_policy=False),
    )
    assert "links_not_allowed" in linked.reasons
    quote = evaluate_goham_governor(
        _candidate(action_type="quote", quote_target_id="target-1"),
        config=cfg,
        profile=_profile(cfg),
    )
    assert "quote_disabled" in quote.reasons


def test_original_post_allowed_in_dry_run_when_all_gates_pass(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    result = evaluate_goham_governor(_candidate(), config=cfg, profile=_profile(cfg))
    assert result.allowed is True
    assert result.action_tier == "auto_original_post"
    assert result.provider_call_allowed is False
    assert result.provider_block_reasons == ["controller_dry_run_provider_call_block"]
    assert result.execution_allowed is False
    assert result.mutation_attempted is False


def test_governor_stops_after_max_actions(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, max_actions_per_run=1)
    result = evaluate_goham_governor(_candidate(), config=cfg, profile=_profile(cfg), actions_this_run=1)
    assert result.allowed is False
    assert "max_actions_per_run_reached" in result.reasons


def test_failure_circuit_breakers(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    state = GohamGovernorState(
        consecutive_provider_failures=2,
        last_provider_status_code=403,
        policy_rejection_count=5,
        model_timeout_count=3,
        risk_mode="stopped",
    )
    result = evaluate_goham_governor(_candidate(), config=cfg, profile=_profile(cfg), state=state)
    assert "provider_auth_stop" in result.reasons
    assert "consecutive_provider_failures_stop" in result.reasons
    assert "policy_rejection_stop" in result.reasons
    assert "model_timeout_stop" in result.reasons
    assert "risk_mode_stopped" in result.reasons


def test_governor_import_isolation() -> None:
    path = Path(__file__).parents[1] / "src" / "ham" / "ham_x" / "goham_governor.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    forbidden = {
        "src.ham.ham_x.x_executor",
        "src.ham.ham_x.manual_canary",
    }
    assert imported.isdisjoint(forbidden)
