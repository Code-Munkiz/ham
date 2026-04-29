from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.ham.ham_x.goham_reactive import run_reactive_once
from src.ham.ham_x.goham_reactive_live import run_reactive_live_once
from src.ham.ham_x.reactive_governor import (
    GOHAM_REACTIVE_EXECUTION_KIND,
    ReactiveGovernorState,
    response_fingerprint,
)
from src.ham.ham_x.reactive_reply_executor import ReactiveReplyRequest, ReactiveReplyResult

from tests.test_ham_x_goham_reactive import _item, _test_config


def _live_config(tmp_path: Path, **overrides: Any):
    values = {
        "reactive": True,
        "dry_run": False,
        "live_canary": True,
        "max_replies": 1,
    }
    values.update(overrides)
    return _test_config(tmp_path, **values)


def _success_reply(request: ReactiveReplyRequest) -> ReactiveReplyResult:
    return ReactiveReplyResult(
        status="executed",
        execution_allowed=True,
        mutation_attempted=True,
        provider_status_code=201,
        provider_post_id="reply-post-123",
    )


def test_blocked_by_default_without_provider_call(tmp_path: Path) -> None:
    calls = 0

    def run_reply(_: ReactiveReplyRequest) -> ReactiveReplyResult:
        nonlocal calls
        calls += 1
        return _success_reply(_)

    result = run_reactive_live_once(_item(), config=_test_config(tmp_path), run_reply=run_reply)

    assert result.status == "blocked"
    assert "reactive_dry_run_enabled" in result.reasons
    assert "reactive_live_canary_required" in result.reasons
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
    assert calls == 0


def test_dry_run_blocks_provider_call(tmp_path: Path) -> None:
    calls = 0
    cfg = _test_config(tmp_path, dry_run=True, live_canary=True)

    def run_reply(_: ReactiveReplyRequest) -> ReactiveReplyResult:
        nonlocal calls
        calls += 1
        return _success_reply(_)

    result = run_reactive_live_once(_item(), config=cfg, run_reply=run_reply)
    assert result.status == "blocked"
    assert "reactive_dry_run_enabled" in result.reasons
    assert calls == 0


def test_live_canary_flag_required(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, dry_run=False, live_canary=False)
    result = run_reactive_live_once(_item(), config=cfg, run_reply=_success_reply)
    assert result.status == "blocked"
    assert "reactive_live_canary_required" in result.reasons


def test_emergency_stop_blocks(tmp_path: Path) -> None:
    result = run_reactive_live_once(
        _item(),
        config=_live_config(tmp_path, emergency_stop=True),
        run_reply=_success_reply,
    )
    assert result.status == "blocked"
    assert "emergency_stop" in result.reasons


def test_missing_reply_target_blocks(tmp_path: Path) -> None:
    calls = 0

    def run_reply(_: ReactiveReplyRequest) -> ReactiveReplyResult:
        nonlocal calls
        calls += 1
        return _success_reply(_)

    result = run_reactive_live_once(
        _item(post_id=None, in_reply_to_post_id=None),
        config=_live_config(tmp_path),
        run_reply=run_reply,
    )
    assert result.status == "blocked"
    assert "reply_target_required" in result.reasons
    assert calls == 0


def test_spam_off_topic_toxic_and_price_bait_block(tmp_path: Path) -> None:
    cases = [
        ("free money giveaway airdrop follow back #a #b #c #d #e #f", "policy_route_ignore"),
        ("what is your favorite sandwich?", "policy_route_ignore"),
        ("Ham is worthless idiot trash, go die", "policy_route_exception"),
        ("Ham token price 10x soon? should I buy now?", "policy_route_exception"),
    ]
    for idx, (text, reason) in enumerate(cases, start=1):
        result = run_reactive_live_once(
            _item(idx, text=text, relevance_score=0.1 if "sandwich" in text else 0.95),
            config=_live_config(tmp_path),
            run_reply=_success_reply,
        )
        assert result.status == "blocked"
        assert reason in result.reasons


def test_duplicate_inbound_blocks(tmp_path: Path) -> None:
    state = ReactiveGovernorState(handled_inbound_ids={"inbound-1"})
    result = run_reactive_live_once(_item(), config=_live_config(tmp_path), state=state, run_reply=_success_reply)
    assert result.status == "blocked"
    assert "duplicate_inbound" in result.reasons


def test_duplicate_response_blocks(tmp_path: Path) -> None:
    expected = "@user1 Good question. Ham is designed to keep autonomous social actions governed by caps, policy checks, audit trails, and operator controls."
    state = ReactiveGovernorState(response_fingerprints={response_fingerprint(expected)})
    result = run_reactive_live_once(_item(), config=_live_config(tmp_path), state=state, run_reply=_success_reply)
    assert result.status == "blocked"
    assert "duplicate_response_text" in result.reasons


def test_per_user_and_thread_cooldowns_block(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    user_state = ReactiveGovernorState(per_user_last_reply_at={"user-1": now})
    user = run_reactive_live_once(
        _item(),
        config=_live_config(tmp_path, min_seconds=3600),
        state=user_state,
        run_reply=_success_reply,
    )
    assert "per_user_cooldown_active" in user.reasons

    thread_state = ReactiveGovernorState(per_thread_last_reply_at={"thread-1": now})
    thread = run_reactive_live_once(
        _item(),
        config=_live_config(tmp_path, min_seconds=3600),
        state=thread_state,
        run_reply=_success_reply,
    )
    assert "per_thread_cooldown_active" in thread.reasons


def test_max_replies_per_run_must_be_one(tmp_path: Path) -> None:
    result = run_reactive_live_once(
        _item(),
        config=_live_config(tmp_path, max_replies=2),
        run_reply=_success_reply,
    )
    assert result.status == "blocked"
    assert "reactive_max_replies_per_run_must_equal_one" in result.reasons


def test_provider_failure_does_not_retry(tmp_path: Path) -> None:
    calls = 0

    def fail(_: ReactiveReplyRequest) -> ReactiveReplyResult:
        nonlocal calls
        calls += 1
        return ReactiveReplyResult(
            status="failed",
            execution_allowed=True,
            mutation_attempted=True,
            provider_status_code=500,
            diagnostic="provider failed",
        )

    result = run_reactive_live_once(_item(), config=_live_config(tmp_path), run_reply=fail)
    assert calls == 1
    assert result.status == "failed"
    assert result.mutation_attempted is True


def test_successful_mocked_live_reply_writes_reactive_journal_only(tmp_path: Path) -> None:
    cfg = _live_config(tmp_path, broadcast_total_cap=0, broadcast_post_cap=0)
    result = run_reactive_live_once(_item(), config=cfg, run_reply=_success_reply)

    assert result.status == "executed"
    assert result.execution_allowed is True
    assert result.mutation_attempted is True
    assert result.execution_request is not None
    assert result.execution_request.execution_kind == GOHAM_REACTIVE_EXECUTION_KIND
    assert result.execution_result is not None
    assert result.execution_result.provider_post_id == "reply-post-123"
    rows = [json.loads(line) for line in cfg.execution_journal_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["action_type"] == "reply"
    assert rows[0]["execution_kind"] == GOHAM_REACTIVE_EXECUTION_KIND


def test_phase4a_reply_candidate_can_be_consumed(tmp_path: Path) -> None:
    dry_cfg = _test_config(tmp_path, dry_run=True, live_canary=False)
    dry = run_reactive_once([_item()], config=dry_cfg)
    assert dry.items[0].status == "reply_candidate"

    live = run_reactive_live_once(dry.items[0], config=_live_config(tmp_path), run_reply=_success_reply)
    assert live.status == "executed"


def test_provider_401_403_trips_stop_state(tmp_path: Path) -> None:
    state = ReactiveGovernorState()
    calls = 0

    def auth_fail(_: ReactiveReplyRequest) -> ReactiveReplyResult:
        nonlocal calls
        calls += 1
        return ReactiveReplyResult(
            status="failed",
            execution_allowed=True,
            mutation_attempted=True,
            provider_status_code=401,
        )

    first = run_reactive_live_once(_item(), config=_live_config(tmp_path), state=state, run_reply=auth_fail)
    assert first.status == "failed"
    assert state.last_provider_status_code == 401
    second = run_reactive_live_once(_item(2), config=_live_config(tmp_path), state=state, run_reply=auth_fail)
    assert second.status == "blocked"
    assert "provider_auth_stop" in second.reasons
    assert calls == 1


def test_secrets_redacted(tmp_path: Path) -> None:
    secret = "tok_1234567890abcdefghijklmnopqrstuvwxyzSECRET"

    def fail(_: ReactiveReplyRequest) -> ReactiveReplyResult:
        return ReactiveReplyResult(
            status="failed",
            execution_allowed=True,
            mutation_attempted=True,
            provider_status_code=403,
            diagnostic=f"bad credential {secret}",
        )

    result = run_reactive_live_once(
        _item(text=f"Question for Ham: how is audit handled with {secret}?"),
        config=_live_config(tmp_path),
        run_reply=fail,
    )
    dumped = json.dumps(result.redacted_dump(), sort_keys=True)
    assert secret not in dumped
    assert "[REDACTED" in dumped


def test_no_scheduler_loop_or_forbidden_imports() -> None:
    root = Path(__file__).parents[1] / "src" / "ham" / "ham_x"
    for name in ("goham_reactive_live.py", "reactive_reply_executor.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "while True" not in text
        assert "schedule" not in text
        assert "daemon" not in text
        assert "xurl" not in text
        assert "manual_canary" not in text
        assert "x_executor" not in text
        assert "quote_tweet_id" not in text
        tree = ast.parse(text)
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
            "src.ham.ham_x.goham_live_controller",
            "src.ham.ham_x.live_dry_run",
        }
        assert imported.isdisjoint(forbidden)
