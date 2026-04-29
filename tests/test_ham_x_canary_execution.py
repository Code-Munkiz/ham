from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from src.ham.ham_x.config import HamXConfig
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.manual_canary import ManualCanaryRequest, run_manual_canary_action
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
    live_execution: bool = False,
    dry_run: bool = True,
    autonomy_enabled: bool = False,
    emergency_stop: bool = False,
    daily_cap: int = 1,
    per_run_cap: int = 1,
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
        autonomy_mode="draft",
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
        execution_daily_cap=daily_cap,
        execution_per_run_cap=per_run_cap,
        daily_spend_limit_usd=5.0,
        model="grok-4.1-fast",
        xurl_bin="xurl",
        readonly_transport="direct",
        execution_transport="direct_oauth1",
        canary_allowed_actions="post,quote",
        review_queue_path=tmp_path / "review_queue.jsonl",
        exception_queue_path=tmp_path / "exception_queue.jsonl",
        execution_journal_path=tmp_path / "execution_journal.jsonl",
        audit_log_path=tmp_path / "audit.jsonl",
    )


def _request(**overrides) -> ManualCanaryRequest:
    data = {
        "tenant_id": "ham-official",
        "agent_id": "ham-pr-rockstar",
        "campaign_id": "base-stealth-launch",
        "account_id": "ham-x-official",
        "action_type": "post",
        "text": "HAM can safely test one manual canary post.",
        "manual_confirm": True,
        "action_id": "canary-action-1",
        "idempotency_key": "canary-key-1",
        "reason": "operator requested manual canary",
        "operator_label": "operator",
    }
    data.update(overrides)
    return ManualCanaryRequest(**data)


def _enabled_config(tmp_path: Path) -> HamXConfig:
    return _test_config(tmp_path, live_execution=True, dry_run=False)


def _executor(config: HamXConfig, response: FakeResponse, calls: list[dict[str, object]]):
    def http_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return response

    return XCanaryExecutor(config=config, http_post=http_post)


def test_execution_blocked_by_default(tmp_path: Path) -> None:
    result = run_manual_canary_action(_request(), config=_test_config(tmp_path))
    assert result.status == "blocked"
    assert "live_execution_disabled" in result.reasons
    assert "dry_run_enabled" in result.reasons
    assert result.execution_allowed is False
    assert result.mutation_attempted is False


def test_execution_blocked_when_live_flag_false(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, live_execution=False, dry_run=False)
    result = run_manual_canary_action(_request(), config=cfg)
    assert "live_execution_disabled" in result.reasons


def test_execution_blocked_when_dry_run_true(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, live_execution=True, dry_run=True)
    result = run_manual_canary_action(_request(), config=cfg)
    assert result.status == "blocked"
    assert "dry_run_enabled" in result.reasons


def test_execution_blocked_when_autonomy_enabled(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, live_execution=True, dry_run=False, autonomy_enabled=True)
    result = run_manual_canary_action(_request(), config=cfg)
    assert "autonomy_enabled" in result.reasons


def test_execution_blocked_when_emergency_stop_true(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, live_execution=True, dry_run=False, emergency_stop=True)
    result = run_manual_canary_action(_request(), config=cfg)
    assert "emergency_stop" in result.reasons


def test_execution_blocked_without_manual_confirm(tmp_path: Path) -> None:
    result = run_manual_canary_action(_request(manual_confirm=False), config=_enabled_config(tmp_path))
    assert "manual_confirm_required" in result.reasons


def test_execution_blocked_over_per_run_cap(tmp_path: Path) -> None:
    result = run_manual_canary_action(
        _request(),
        config=_enabled_config(tmp_path),
        per_run_count=1,
    )
    assert "per_run_cap_exceeded" in result.reasons


def test_execution_blocked_over_daily_cap(tmp_path: Path) -> None:
    cfg = _enabled_config(tmp_path)
    journal = ExecutionJournal(config=cfg)
    journal.append_executed(
        action_id="old-action",
        idempotency_key="old-key",
        action_type="post",
        provider_post_id="123",
    )
    result = run_manual_canary_action(_request(), config=cfg, journal=journal)
    assert "daily_cap_exceeded" in result.reasons


def test_unsupported_action_blocked(tmp_path: Path) -> None:
    request = _request().model_copy(update={"action_type": "like"})
    result = run_manual_canary_action(request, config=_enabled_config(tmp_path))
    assert "unsupported_action_type" in result.reasons


def test_empty_overlong_and_unsafe_text_blocked(tmp_path: Path) -> None:
    cfg = _enabled_config(tmp_path)
    assert "empty_text" in run_manual_canary_action(_request(text=""), config=cfg).reasons
    assert "text_too_long" in run_manual_canary_action(_request(text="x" * 281), config=cfg).reasons
    unsafe = run_manual_canary_action(_request(text="This is guaranteed to deliver 10x gains."), config=cfg)
    assert any(reason.startswith("safety_policy:") for reason in unsafe.reasons)


def test_quote_without_target_id_blocked(tmp_path: Path) -> None:
    request = _request(action_type="quote", quote_target_id=None)
    result = run_manual_canary_action(request, config=_enabled_config(tmp_path))
    assert "quote_target_id_required" in result.reasons


def test_duplicate_action_or_idempotency_blocked(tmp_path: Path) -> None:
    cfg = _enabled_config(tmp_path)
    journal = ExecutionJournal(config=cfg)
    journal.append_executed(
        action_id="canary-action-1",
        idempotency_key="canary-key-1",
        action_type="post",
        provider_post_id="123",
    )
    cfg = replace(cfg, execution_daily_cap=2)
    result = run_manual_canary_action(_request(), config=cfg, journal=journal)
    assert "duplicate_execution" in result.reasons


def test_secrets_redacted_in_result_and_audit(tmp_path: Path) -> None:
    result = run_manual_canary_action(
        _request(text="Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456"),
        config=_enabled_config(tmp_path),
    )
    dumped = json.dumps(result.redacted_dump())
    audit = (_enabled_config(tmp_path).audit_log_path).read_text(encoding="utf-8")
    assert "abcdefghijklmnopqrstuvwxyz123456" not in dumped
    assert "abcdefghijklmnopqrstuvwxyz123456" not in audit
    assert "payload_contains_secret" in result.reasons


def test_mocked_successful_post_returns_executed(tmp_path: Path) -> None:
    cfg = _enabled_config(tmp_path)
    calls: list[dict[str, object]] = []
    executor = _executor(cfg, FakeResponse(201, {"data": {"id": "post-1", "text": "ok"}}), calls)
    result = run_manual_canary_action(_request(), config=cfg, executor=executor)
    assert result.status == "executed"
    assert result.provider_post_id == "post-1"
    assert result.mutation_attempted is True
    assert result.execution_allowed is False
    assert calls
    assert calls[0]["json"] == {"text": "HAM can safely test one manual canary post."}
    assert "Authorization" in calls[0]["headers"]  # Value is never asserted or printed.


def test_mocked_successful_quote_returns_executed(tmp_path: Path) -> None:
    cfg = _enabled_config(tmp_path)
    calls: list[dict[str, object]] = []
    executor = _executor(cfg, FakeResponse(201, {"data": {"id": "quote-1", "text": "ok"}}), calls)
    request = _request(action_type="quote", quote_target_id="2049175321996312863")
    result = run_manual_canary_action(request, config=cfg, executor=executor)
    assert result.status == "executed"
    assert result.provider_post_id == "quote-1"
    assert calls[0]["json"]["quote_tweet_id"] == "2049175321996312863"


def test_provider_failure_returns_failed_with_bounded_response(tmp_path: Path) -> None:
    cfg = _enabled_config(tmp_path)
    executor = _executor(
        cfg,
        FakeResponse(403, {"detail": "Forbidden", "token": "abcdefghijklmnopqrstuvwxyz1234567890"}),
        [],
    )
    result = run_manual_canary_action(_request(), config=cfg, executor=executor)
    dumped = json.dumps(result.redacted_dump())
    assert result.status == "failed"
    assert result.provider_status_code == 403
    assert "abcdefghijklmnopqrstuvwxyz1234567890" not in dumped


def test_autonomy_pipeline_and_smoke_do_not_import_executor() -> None:
    from pathlib import Path

    root = Path(__file__).parents[1] / "src" / "ham" / "ham_x"
    for name in ("autonomy.py", "pipeline.py", "smoke.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "manual_canary" not in text
        assert "x_executor" not in text
