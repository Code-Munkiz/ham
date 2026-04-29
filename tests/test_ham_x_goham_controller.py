from __future__ import annotations

import ast
import json
from pathlib import Path

from src.ham.ham_x.config import HamXConfig
from src.ham.ham_x.goham_controller import run_controller_once
from src.ham.ham_x.goham_governor import GohamGovernorCandidate


def _test_config(
    tmp_path: Path,
    *,
    controller: bool = True,
    emergency_stop: bool = False,
    max_candidates: int = 5,
    max_actions: int = 1,
) -> HamXConfig:
    return HamXConfig(
        xai_api_key="secret-xai",
        x_api_key="consumer-key",
        x_api_secret="consumer-secret",
        x_access_token="access-token",
        x_access_token_secret="access-token-secret",
        x_bearer_token="bearer-token",
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
        goham_controller_dry_run=True,
        goham_max_total_actions_per_day=1,
        goham_max_original_posts_per_day=1,
        goham_max_quotes_per_day=0,
        goham_min_spacing_minutes=120,
        goham_max_actions_per_run=max_actions,
        goham_max_candidates_per_run=max_candidates,
        goham_consecutive_failure_stop=2,
        goham_policy_rejection_stop=5,
        goham_model_timeout_stop=3,
    )


def _candidate(idx: int = 1, **overrides) -> GohamGovernorCandidate:
    data = {
        "action_id": f"candidate-{idx}",
        "source_action_id": f"source-{idx}",
        "idempotency_key": f"idem-{idx}",
        "action_type": "post",
        "text": f"Ham is tracking Base builder workflows with guarded autonomy {idx}.",
        "topic": "base",
        "score": 0.95,
    }
    data.update(overrides)
    return GohamGovernorCandidate(**data)


def test_no_action_by_default(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, controller=False)
    result = run_controller_once([_candidate()], config=cfg)
    assert result.status == "blocked"
    assert "controller_disabled" in result.reasons
    assert result.allowed_dry_run == []
    assert result.mutation_attempted is False


def test_emergency_stop_blocks_controller(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, emergency_stop=True)
    result = run_controller_once([_candidate()], config=cfg)
    assert result.status == "blocked"
    assert "emergency_stop" in result.reasons
    assert result.processed_count == 0


def test_controller_dry_run_never_calls_provider(tmp_path: Path, monkeypatch) -> None:
    cfg = _test_config(tmp_path)

    def fail_if_called(*args, **kwargs):  # pragma: no cover
        raise AssertionError("Phase 3A controller must not call providers")

    monkeypatch.setattr("src.ham.ham_x.goham_bridge.run_goham_guarded_post", fail_if_called, raising=False)
    result = run_controller_once([_candidate()], config=cfg)
    assert len(result.allowed_dry_run) == 1
    decision = result.allowed_dry_run[0].governor_decision
    assert decision.allowed is True
    assert decision.provider_call_allowed is False
    assert "controller_dry_run_provider_call_block" in decision.provider_block_reasons
    assert result.execution_allowed is False
    assert result.mutation_attempted is False


def test_bounded_candidates_and_actions_prove_no_uncontrolled_loop(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, max_candidates=2, max_actions=1)
    result = run_controller_once([_candidate(1), _candidate(2), _candidate(3)], config=cfg)
    assert result.candidate_count == 3
    assert result.processed_count == 1
    assert len(result.allowed_dry_run) == 1
    assert result.max_candidates_per_run == 2
    assert result.max_actions_per_run == 1


def test_every_decision_audited(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, max_candidates=3, max_actions=2)
    result = run_controller_once(
        [
            _candidate(1),
            _candidate(2, text="Ham update https://example.com"),
        ],
        config=cfg,
    )
    audit = cfg.audit_log_path.read_text(encoding="utf-8")
    assert "goham_controller_started" in audit
    assert audit.count("goham_controller_candidate_decision") == result.processed_count
    assert "goham_controller_completed" in audit
    assert result.audit_ids


def test_failures_do_not_retry_endlessly(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, max_candidates=5, max_actions=1)
    result = run_controller_once(
        [
            _candidate(1, text="Ham update https://example.com"),
            _candidate(2, text="Buy this token before the price moves."),
            _candidate(3),
        ],
        config=cfg,
    )
    assert result.processed_count == 3
    assert len(result.allowed_dry_run) == 1
    assert len(result.blocked) == 2


def test_phase2b_and_smoke_still_cannot_execute_directly() -> None:
    root = Path(__file__).parents[1] / "src" / "ham" / "ham_x"
    for name in ("live_dry_run.py", "smoke.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "x_executor" not in text
        assert "manual_canary" not in text


def test_redacted_bounded_summary(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    secret = "tok_1234567890abcdefghijklmnopqrstuvwxyzSECRET"
    result = run_controller_once(
        [
            _candidate(
                1,
                text=f"Ham is tracking Base builders with {secret}.",
                metadata={"token": secret, "body": "x" * 5000},
            )
        ],
        config=cfg,
    )
    dumped = json.dumps(result.redacted_dump(), sort_keys=True)
    assert secret not in dumped
    assert "x" * 5000 not in dumped
    assert "[REDACTED]" in dumped or "[REDACTED_TOKEN]" in dumped


def test_controller_import_isolation() -> None:
    path = Path(__file__).parents[1] / "src" / "ham" / "ham_x" / "goham_controller.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    forbidden = {
        "src.ham.ham_x.x_executor",
        "src.ham.ham_x.manual_canary",
    }
    assert imported.isdisjoint(forbidden)
