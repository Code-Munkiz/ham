from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.goham_reactive_batch import run_reactive_batch_once
from src.ham.ham_x.reactive_governor import GOHAM_REACTIVE_EXECUTION_KIND, ReactiveGovernorState, response_fingerprint
from src.ham.ham_x.reactive_reply_executor import ReactiveReplyRequest, ReactiveReplyResult

from tests.test_ham_x_goham_reactive import _item, _test_config


def _batch_config(tmp_path: Path, **overrides: Any):
    values = {
        "enable_goham_reactive_batch": True,
        "goham_reactive_batch_dry_run": True,
        "goham_reactive_batch_max_replies_per_run": 3,
        "goham_reactive_batch_stop_on_auth_failure": True,
        "goham_reactive_batch_stop_on_provider_failures": 2,
    }
    values.update(overrides.pop("batch_overrides", {}))
    cfg = _test_config(tmp_path, **overrides)
    return cfg.__class__(**{**cfg.__dict__, **values})


def _success(request: ReactiveReplyRequest) -> ReactiveReplyResult:
    return ReactiveReplyResult(
        status="executed",
        execution_allowed=True,
        mutation_attempted=True,
        provider_status_code=201,
        provider_post_id=f"reply-{request.inbound_id}",
    )


def _failure(code: int = 500) -> ReactiveReplyResult:
    return ReactiveReplyResult(
        status="failed",
        execution_allowed=True,
        mutation_attempted=True,
        provider_status_code=code,
        diagnostic="provider failure access_token=access-token-1234567890",
    )


def _audit_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_batch_disabled_blocks(tmp_path: Path) -> None:
    calls = 0

    def run_reply(_: ReactiveReplyRequest) -> ReactiveReplyResult:
        nonlocal calls
        calls += 1
        return _success(_)

    result = run_reactive_batch_once([_item()], config=_test_config(tmp_path), run_reply=run_reply)

    assert result.status == "blocked"
    assert "reactive_batch_disabled" in result.reasons
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
    assert calls == 0


def test_dry_run_batch_never_calls_provider(tmp_path: Path) -> None:
    calls = 0

    def run_reply(_: ReactiveReplyRequest) -> ReactiveReplyResult:
        nonlocal calls
        calls += 1
        return _success(_)

    cfg = _batch_config(tmp_path)
    result = run_reactive_batch_once([_item(1), _item(2)], config=cfg, run_reply=run_reply)

    assert result.status == "completed"
    assert [item.status for item in result.items] == ["dry_run", "dry_run"]
    assert result.attempted_count == 2
    assert result.executed_count == 0
    assert calls == 0
    assert not cfg.execution_journal_path.exists()


def test_live_batch_calls_provider_at_most_max_replies_per_run(tmp_path: Path) -> None:
    calls: list[str] = []
    cfg = _batch_config(
        tmp_path,
        dry_run=False,
        batch_overrides={"goham_reactive_batch_dry_run": False, "goham_reactive_batch_max_replies_per_run": 2},
    )

    def run_reply(request: ReactiveReplyRequest) -> ReactiveReplyResult:
        calls.append(request.inbound_id)
        return _success(request)

    result = run_reactive_batch_once([_item(1), _item(2), _item(3)], config=cfg, run_reply=run_reply)

    assert calls == ["inbound-1", "inbound-2"]
    assert result.executed_count == 2
    assert result.items[2].status == "skipped"
    assert "max_replies_per_run_reached" in result.items[2].reasons


def test_emergency_stop_blocks_all(tmp_path: Path) -> None:
    cfg = _batch_config(tmp_path, emergency_stop=True)
    result = run_reactive_batch_once([_item()], config=cfg, run_reply=_success)
    assert result.status == "blocked"
    assert "emergency_stop" in result.reasons
    assert result.processed_count == 0


def test_per_user_cooldown_blocks_later_candidate(tmp_path: Path) -> None:
    cfg = _batch_config(tmp_path, min_seconds=3600)
    result = run_reactive_batch_once(
        [_item(1, author_id="same-user", thread_id="thread-1"), _item(2, author_id="same-user", thread_id="thread-2")],
        config=cfg,
        run_reply=_success,
    )
    assert result.items[0].status == "dry_run"
    assert result.items[1].status == "blocked"
    assert "per_user_cooldown_active" in result.items[1].reasons


def test_per_thread_cooldown_blocks_later_candidate(tmp_path: Path) -> None:
    cfg = _batch_config(tmp_path, min_seconds=3600)
    result = run_reactive_batch_once(
        [_item(1, author_id="user-1", thread_id="same-thread"), _item(2, author_id="user-2", thread_id="same-thread")],
        config=cfg,
        run_reply=_success,
    )
    assert result.items[0].status == "dry_run"
    assert result.items[1].status == "blocked"
    assert "per_thread_cooldown_active" in result.items[1].reasons


def test_duplicate_inbound_blocks(tmp_path: Path) -> None:
    cfg = _batch_config(tmp_path)
    state = ReactiveGovernorState(handled_inbound_ids={"inbound-1"})
    result = run_reactive_batch_once([_item()], config=cfg, state=state, run_reply=_success)
    assert result.items[0].status == "blocked"
    assert "duplicate_inbound" in result.items[0].reasons


def test_duplicate_response_blocks(tmp_path: Path) -> None:
    cfg = _batch_config(tmp_path)
    expected = "Good question. Ham is designed to keep autonomous social actions governed by caps, policy checks, audit trails, and operator controls."
    state = ReactiveGovernorState(response_fingerprints={response_fingerprint(expected)})
    result = run_reactive_batch_once([_item(author_handle=None)], config=cfg, state=state, run_reply=_success)
    assert result.items[0].status == "blocked"
    assert "duplicate_response_text" in result.items[0].reasons


def test_rolling_15m_and_hourly_caps_block(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    recent_15m = [
        (now - timedelta(minutes=idx)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        for idx in range(5)
    ]
    cfg_15m = _batch_config(tmp_path, max_per_15m=5, max_per_hour=20)
    blocked_15m = run_reactive_batch_once(
        [_item()],
        config=cfg_15m,
        state=ReactiveGovernorState(recent_reply_times=recent_15m),
        run_reply=_success,
    )
    assert "reply_15m_cap_reached" in blocked_15m.items[0].reasons

    recent_hour = [
        (now - timedelta(minutes=idx + 16)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        for idx in range(20)
    ]
    cfg_hour = _batch_config(tmp_path, max_per_15m=99, max_per_hour=20)
    blocked_hour = run_reactive_batch_once(
        [_item()],
        config=cfg_hour,
        state=ReactiveGovernorState(recent_reply_times=recent_hour),
        run_reply=_success,
    )
    assert "reply_hour_cap_reached" in blocked_hour.items[0].reasons


def test_provider_401_403_stops_remaining_replies(tmp_path: Path) -> None:
    calls = 0
    cfg = _batch_config(tmp_path, batch_overrides={"goham_reactive_batch_dry_run": False})

    def auth_fail(_: ReactiveReplyRequest) -> ReactiveReplyResult:
        nonlocal calls
        calls += 1
        return _failure(401)

    result = run_reactive_batch_once([_item(1), _item(2)], config=cfg, run_reply=auth_fail)

    assert calls == 1
    assert result.status == "stopped"
    assert result.stop_reason == "provider_auth_stop"
    assert result.items[1].status == "skipped"


def test_provider_failure_does_not_retry_same_item(tmp_path: Path) -> None:
    calls = 0
    cfg = _batch_config(
        tmp_path,
        batch_overrides={"goham_reactive_batch_dry_run": False, "goham_reactive_batch_stop_on_provider_failures": 5},
    )

    def fail(_: ReactiveReplyRequest) -> ReactiveReplyResult:
        nonlocal calls
        calls += 1
        return _failure(500)

    result = run_reactive_batch_once([_item()], config=cfg, run_reply=fail)
    assert calls == 1
    assert result.failed_count == 1
    assert result.items[0].status == "failed"


def test_repeated_provider_failures_stop_run(tmp_path: Path) -> None:
    calls = 0
    cfg = _batch_config(
        tmp_path,
        batch_overrides={"goham_reactive_batch_dry_run": False, "goham_reactive_batch_stop_on_provider_failures": 2},
    )

    def fail(_: ReactiveReplyRequest) -> ReactiveReplyResult:
        nonlocal calls
        calls += 1
        return _failure(500)

    result = run_reactive_batch_once([_item(1), _item(2), _item(3)], config=cfg, run_reply=fail)
    assert calls == 2
    assert result.status == "stopped"
    assert result.stop_reason == "provider_failure_stop"
    assert result.items[2].status == "skipped"


def test_every_inbound_item_gets_audited(tmp_path: Path) -> None:
    cfg = _batch_config(tmp_path)
    result = run_reactive_batch_once([_item(1), _item(2)], config=cfg, run_reply=_success)
    rows = _audit_rows(cfg.audit_log_path)
    assert result.processed_count == 2
    assert sum(1 for row in rows if row["event_type"] == "goham_reactive_inbound_seen") == 2
    assert sum(1 for row in rows if row["event_type"] == "goham_reactive_governor_decision") == 2


def test_every_executed_reply_gets_journaled(tmp_path: Path) -> None:
    cfg = _batch_config(tmp_path, batch_overrides={"goham_reactive_batch_dry_run": False})
    result = run_reactive_batch_once([_item(1), _item(2)], config=cfg, run_reply=_success)
    rows = [json.loads(line) for line in cfg.execution_journal_path.read_text(encoding="utf-8").splitlines()]

    assert result.executed_count == 2
    assert len(rows) == 2
    assert {row["execution_kind"] for row in rows} == {GOHAM_REACTIVE_EXECUTION_KIND}
    assert {row["action_type"] for row in rows} == {"reply"}


def test_journal_duplicate_prevents_reexecution_across_retries(tmp_path: Path) -> None:
    cfg = _batch_config(tmp_path, batch_overrides={"goham_reactive_batch_dry_run": False})
    journal = ExecutionJournal(config=cfg)
    first = run_reactive_batch_once([_item()], config=cfg, journal=journal, run_reply=_success)
    calls = 0

    def fail_if_called(_: ReactiveReplyRequest) -> ReactiveReplyResult:
        nonlocal calls
        calls += 1
        return _success(_)

    second = run_reactive_batch_once([_item()], config=cfg, journal=journal, run_reply=fail_if_called)
    assert first.executed_count == 1
    assert second.items[0].status == "blocked"
    assert "duplicate_execution" in second.items[0].reasons or "duplicate_inbound" in second.items[0].reasons
    assert calls == 0


def test_redaction_masks_tokens_and_secrets(tmp_path: Path) -> None:
    cfg = _batch_config(
        tmp_path,
        batch_overrides={"goham_reactive_batch_dry_run": False, "goham_reactive_batch_stop_on_provider_failures": 5},
    )
    result = run_reactive_batch_once([_item()], config=cfg, run_reply=lambda _: _failure(500))
    dumped = json.dumps(result.redacted_dump(), sort_keys=True)
    assert "access-token-1234567890" not in dumped
    assert "[REDACTED]" in dumped


def test_no_forbidden_imports_or_batch_loop_constructs() -> None:
    path = Path("src/ham/ham_x/goham_reactive_batch.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    forbidden = [
        "src.ham.ham_x.xurl",
        "src.ham.ham_x.manual_canary",
        "src.ham.ham_x.x_executor",
        "src.ham.ham_x.goham_live_controller",
        "src.ham.ham_x.goham_controller",
    ]
    assert not any(name in imports for name in forbidden)
    assert "while " not in source
    assert "schedule" not in source.lower()
    assert "daemon" not in source.lower()
    forbidden_terms = ["like", "follow", "quote", "send_dm", "direct_message"]
    assert not any(term in source.lower() for term in forbidden_terms)
