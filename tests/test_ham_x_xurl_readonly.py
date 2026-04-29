from __future__ import annotations

import subprocess
from pathlib import Path

from src.ham.ham_x.config import HamXConfig
from src.ham.ham_x.xurl_wrapper import XurlWrapper


def _test_config(tmp_path: Path) -> HamXConfig:
    return HamXConfig(
        xai_api_key="",
        x_api_key="",
        x_api_secret="",
        x_access_token="",
        x_access_token_secret="",
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
        emergency_stop=False,
        enable_live_smoke=True,
        enable_live_execution=False,
        autonomy_enabled=False,
        dry_run=True,
        max_posts_per_hour=0,
        max_quotes_per_hour=0,
        max_searches_per_hour=30,
        execution_daily_cap=1,
        execution_per_run_cap=1,
        daily_spend_limit_usd=5.0,
        model="grok-4.1-fast",
        xurl_bin="xurl",
        readonly_transport="xurl",
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


def test_readonly_search_runner_receives_argv_list_and_shell_false(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def runner(argv, **kwargs):
        calls.append({"argv": argv, **kwargs})
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    result = XurlWrapper(
        config=_test_config(tmp_path),
        runner=runner,
        binary_resolver=lambda _: "/usr/bin/xurl",
    ).execute_readonly_search("Base ecosystem autonomous agents", max_results=10)

    assert result.executed is True
    assert result.blocked is False
    assert calls
    assert calls[0]["argv"] == [
        "xurl",
        "search",
        "Base ecosystem autonomous agents",
        "--max-results",
        "10",
    ]
    assert calls[0]["shell"] is False
    assert calls[0]["capture_output"] is True
    assert calls[0]["text"] is True


def test_missing_xurl_binary_returns_safe_blocked_result(tmp_path: Path) -> None:
    def runner(argv, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("runner should not be called")

    result = XurlWrapper(
        config=_test_config(tmp_path),
        runner=runner,
        binary_resolver=lambda _: None,
    ).execute_readonly_search("Base ecosystem autonomous agents")

    assert result.blocked is True
    assert result.executed is False
    assert result.exit_code is None
    assert result.reason == "xurl_binary_not_found"
    assert result.execution_allowed is False
    assert result.mutation_attempted is False


def test_readonly_search_redacts_stdout_and_stderr(tmp_path: Path) -> None:
    secret = "Bearer abcdefghijklmnopqrstuvwxyz123456"

    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv,
            1,
            stdout=f"token={secret}",
            stderr=f"auth failed: {secret}",
        )

    result = XurlWrapper(
        config=_test_config(tmp_path),
        runner=runner,
        binary_resolver=lambda _: "/usr/bin/xurl",
    ).execute_readonly_search("Base ecosystem autonomous agents")

    dumped = str(result.as_dict())
    assert result.executed is True
    assert result.exit_code == 1
    assert result.reason == "xurl_readonly_smoke_nonzero_exit"
    assert "abcdefghijklmnopqrstuvwxyz123456" not in dumped
    assert "[REDACTED" in dumped


def test_readonly_search_401_returns_actionable_diagnostic(tmp_path: Path) -> None:
    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv,
            1,
            stdout='{"title":"Unauthorized","type":"about:blank","status":401,"detail":"Unauthorized"}',
            stderr="",
        )

    result = XurlWrapper(
        config=_test_config(tmp_path),
        runner=runner,
        binary_resolver=lambda _: "/usr/bin/xurl",
    ).execute_readonly_search("Base ecosystem autonomous agents")

    data = result.as_dict()
    assert data["status"] == "failed"
    assert data["reason"] == "xurl_returned_401_unauthorized"
    assert data["exit_code"] == 1
    assert "Check xurl active profile" in str(data["diagnostic"])
    assert data["execution_allowed"] is False
    assert data["mutation_attempted"] is False


def test_mutating_actions_blocked_before_runner_invocation(tmp_path: Path) -> None:
    calls: list[object] = []

    def runner(argv, **kwargs):  # pragma: no cover - must not be called
        calls.append(argv)
        raise AssertionError("runner should not be called")

    wrapper = XurlWrapper(
        config=_test_config(tmp_path),
        runner=runner,
        binary_resolver=lambda _: "/usr/bin/xurl",
    )

    for action in ("post", "quote", "like"):
        result = wrapper.execute_readonly_action(
            action,
            query="Base ecosystem autonomous agents",
            max_results=10,
            timeout_seconds=1,
        )
        assert result.blocked is True
        assert result.executed is False
        assert result.reason == "mutating_action_blocked_before_runner"
        assert result.execution_allowed is False
        assert result.mutation_attempted is False

    assert calls == []
