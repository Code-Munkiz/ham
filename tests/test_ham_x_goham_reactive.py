from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.ham.ham_x.config import HamXConfig
from src.ham.ham_x.goham_reactive import run_reactive_once
from src.ham.ham_x.inbound_client import InboundClient, ReactiveInboundItem
from src.ham.ham_x.reactive_governor import ReactiveGovernorState, response_fingerprint


def _test_config(
    tmp_path: Path,
    *,
    reactive: bool = True,
    dry_run: bool = True,
    live_canary: bool = False,
    emergency_stop: bool = False,
    max_per_15m: int = 5,
    max_per_hour: int = 20,
    max_per_user: int = 3,
    max_per_thread: int = 5,
    min_seconds: int = 60,
    min_relevance: float = 0.75,
    max_inbound: int = 25,
    max_replies: int = 1,
    broadcast_total_cap: int = 0,
    broadcast_post_cap: int = 0,
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
        enable_goham_controller=False,
        goham_controller_dry_run=True,
        goham_max_total_actions_per_day=broadcast_total_cap,
        goham_max_original_posts_per_day=broadcast_post_cap,
        goham_max_quotes_per_day=0,
        goham_min_spacing_minutes=120,
        goham_max_actions_per_run=1,
        goham_max_candidates_per_run=5,
        goham_consecutive_failure_stop=2,
        goham_policy_rejection_stop=5,
        goham_model_timeout_stop=3,
        enable_goham_live_controller=False,
        goham_live_controller_original_posts_only=True,
        goham_live_max_actions_per_run=1,
        enable_goham_reactive=reactive,
        goham_reactive_dry_run=dry_run,
        goham_reactive_live_canary=live_canary,
        goham_reactive_max_replies_per_15m=max_per_15m,
        goham_reactive_max_replies_per_hour=max_per_hour,
        goham_reactive_max_replies_per_user_per_day=max_per_user,
        goham_reactive_max_replies_per_thread_per_day=max_per_thread,
        goham_reactive_min_seconds_between_replies=min_seconds,
        goham_reactive_min_relevance=min_relevance,
        goham_reactive_block_links=True,
        goham_reactive_failure_stop=2,
        goham_reactive_policy_rejection_stop=10,
        goham_reactive_max_inbound_per_run=max_inbound,
        goham_reactive_max_replies_per_run=max_replies,
        enable_reactive_inbox_discovery=False,
        reactive_inbox_query="",
        reactive_inbox_max_results=25,
        reactive_inbox_max_threads=5,
        reactive_inbox_lookback_hours=24,
        reactive_handle="Ham",
        reactive_inbox_include_replies_to_own_posts=True,
        enable_goham_reactive_batch=False,
        goham_reactive_batch_dry_run=True,
        goham_reactive_batch_max_replies_per_run=3,
        goham_reactive_batch_stop_on_auth_failure=True,
        goham_reactive_batch_stop_on_provider_failures=2,
    )


def _item(idx: int = 1, **overrides: Any) -> ReactiveInboundItem:
    data = {
        "inbound_id": f"inbound-{idx}",
        "inbound_type": "mention",
        "text": f"Question for Ham: how does governed autonomy stay audited {idx}?",
        "author_id": f"user-{idx}",
        "author_handle": f"user{idx}",
        "post_id": f"post-{idx}",
        "thread_id": f"thread-{idx}",
        "conversation_id": f"thread-{idx}",
        "relevance_score": 0.95,
    }
    data.update(overrides)
    return ReactiveInboundItem(**data)


def _run(tmp_path: Path, items: list[ReactiveInboundItem], **cfg_overrides: Any):
    cfg = _test_config(tmp_path, **cfg_overrides)
    return run_reactive_once(items, config=cfg), cfg


def test_emergency_stop_blocks_all_replies(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, [_item()], emergency_stop=True)
    assert result.status == "blocked"
    assert result.processed_count == 0
    assert "emergency_stop" in result.reasons
    assert result.execution_allowed is False
    assert result.mutation_attempted is False


def test_inbound_spam_ignored(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, [_item(text="free money giveaway airdrop follow back #a #b #c #d #e #f")])
    assert result.items[0].policy_decision.classification == "spam_bot"
    assert result.items[0].status == "ignored"
    assert result.reply_candidate_count == 0


def test_off_topic_mention_ignored(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, [_item(text="what is your favorite sandwich?", relevance_score=0.1)])
    assert result.items[0].policy_decision.classification == "off_topic"
    assert result.items[0].status == "ignored"


def test_toxic_mention_routes_to_exception_no_reply(tmp_path: Path) -> None:
    result, cfg = _run(tmp_path, [_item(text="Ham is worthless idiot trash, go die")])
    assert result.items[0].policy_decision.classification == "toxic_harassing"
    assert result.items[0].status == "exception"
    assert cfg.exception_queue_path.exists()


def test_price_buy_token_bait_blocked(tmp_path: Path) -> None:
    result, cfg = _run(tmp_path, [_item(text="Ham token price 10x soon? should I buy now?")])
    assert result.items[0].policy_decision.classification == "price_token_bait"
    assert result.items[0].status == "exception"
    assert cfg.exception_queue_path.exists()


def test_genuine_question_produces_reply_candidate(tmp_path: Path) -> None:
    result, cfg = _run(tmp_path, [_item(text="Question for Ham: how do audit trails work for agents?")])
    assert result.items[0].policy_decision.classification == "genuine_question"
    assert result.items[0].status == "reply_candidate"
    assert result.reply_candidate_count == 1
    assert cfg.review_queue_path.exists()


def test_support_request_produces_reply_candidate(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, [_item(text="Ham support: I hit an error, can you help?")])
    assert result.items[0].policy_decision.classification == "support_request"
    assert result.items[0].status == "reply_candidate"


def test_constructive_criticism_gets_non_defensive_reply(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, [_item(text="Ham seems confusing and I am skeptical about autonomy")])
    assert result.items[0].policy_decision.classification == "criticism"
    assert result.items[0].status == "reply_candidate"
    assert "Fair pushback" in (result.items[0].reply_text or "")


def test_duplicate_inbound_source_blocked(tmp_path: Path) -> None:
    state = ReactiveGovernorState(handled_inbound_ids={"inbound-1"})
    cfg = _test_config(tmp_path)
    result = run_reactive_once([_item()], config=cfg, state=state)
    assert result.items[0].status == "blocked"
    assert "duplicate_inbound" in result.items[0].governor_decision.reasons


def test_duplicate_response_text_blocked(tmp_path: Path) -> None:
    expected = "@user1 Good question. Ham is designed to keep autonomous social actions governed by caps, policy checks, audit trails, and operator controls."
    state = ReactiveGovernorState(response_fingerprints={response_fingerprint(expected)})
    cfg = _test_config(tmp_path)
    result = run_reactive_once([_item(text="Question for Ham: how do audit trails work?")], config=cfg, state=state)
    assert result.items[0].status == "blocked"
    assert "duplicate_response_text" in result.items[0].governor_decision.reasons


def test_per_user_cooldown_enforced(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    state = ReactiveGovernorState(per_user_last_reply_at={"user-1": now})
    cfg = _test_config(tmp_path, min_seconds=3600)
    result = run_reactive_once([_item()], config=cfg, state=state)
    assert "per_user_cooldown_active" in result.items[0].governor_decision.reasons


def test_per_thread_cooldown_enforced(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    state = ReactiveGovernorState(per_thread_last_reply_at={"thread-1": now})
    cfg = _test_config(tmp_path, min_seconds=3600)
    result = run_reactive_once([_item()], config=cfg, state=state)
    assert "per_thread_cooldown_active" in result.items[0].governor_decision.reasons


def test_15_minute_cap_enforced(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    state = ReactiveGovernorState(recent_reply_times=[now])
    cfg = _test_config(tmp_path, max_per_15m=1, max_per_hour=20)
    result = run_reactive_once([_item()], config=cfg, state=state)
    assert "reply_15m_cap_reached" in result.items[0].governor_decision.reasons


def test_hourly_cap_enforced(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    state = ReactiveGovernorState(recent_reply_times=[now])
    cfg = _test_config(tmp_path, max_per_15m=5, max_per_hour=1)
    result = run_reactive_once([_item()], config=cfg, state=state)
    assert "reply_hour_cap_reached" in result.items[0].governor_decision.reasons


def test_reactive_reply_budget_independent_from_broadcast_post_cap(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, [_item()], broadcast_total_cap=0, broadcast_post_cap=0)
    assert result.items[0].status == "reply_candidate"
    assert result.reply_candidate_count == 1


def test_dry_run_never_calls_provider_and_live_path_blocked(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, [_item()])
    dumped = json.dumps(result.redacted_dump(), sort_keys=True)
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
    assert "provider_status_code" not in dumped
    blocked, _ = _run(tmp_path, [_item()], live_canary=True)
    assert blocked.status == "blocked"
    assert "reactive_live_canary_disabled_phase4a" in blocked.reasons


def test_every_inbound_decision_audited(tmp_path: Path) -> None:
    result, cfg = _run(tmp_path, [_item(), _item(2, text="free money giveaway")], max_replies=2)
    audit = cfg.audit_log_path.read_text(encoding="utf-8")
    assert "goham_reactive_started" in audit
    assert audit.count("goham_reactive_inbound_seen") == result.processed_count
    assert audit.count("goham_reactive_classified") == result.processed_count
    assert audit.count("goham_reactive_governor_decision") == result.processed_count
    assert "goham_reactive_completed" in audit


def test_redaction_removes_secrets_and_tokens(tmp_path: Path) -> None:
    secret = "tok_1234567890abcdefghijklmnopqrstuvwxyzSECRET"
    result, _ = _run(tmp_path, [_item(text=f"Question for Ham with {secret}: how audited?")])
    dumped = json.dumps(result.redacted_dump(), sort_keys=True)
    assert secret not in dumped
    assert "[REDACTED]" in dumped or "[REDACTED_TOKEN]" in dumped


def test_inbound_client_fails_closed_without_live_http(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    client = InboundClient(config=cfg)
    result = client.fetch_mentions(query="@ham")
    assert result.status == "blocked"
    assert result.mutation_attempted is False


def test_no_forbidden_imports_or_uncontrolled_runtime_paths() -> None:
    root = Path(__file__).parents[1] / "src" / "ham" / "ham_x"
    for name in ("goham_reactive.py", "reactive_governor.py", "reactive_policy.py", "inbound_client.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "while True" not in text
        assert "schedule" not in text
        assert "daemon" not in text
        assert "xurl" not in text
        assert "manual_canary" not in text
        assert "x_executor" not in text
        assert "goham_controller" not in text
        assert "goham_live_controller" not in text
        assert "live_dry_run" not in text


def test_reactive_import_isolation() -> None:
    path = Path(__file__).parents[1] / "src" / "ham" / "ham_x" / "goham_reactive.py"
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
        "src.ham.ham_x.goham_controller",
        "src.ham.ham_x.goham_live_controller",
        "src.ham.ham_x.live_dry_run",
    }
    assert imported.isdisjoint(forbidden)
