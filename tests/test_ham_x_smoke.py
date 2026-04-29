from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

from src.ham.ham_x.config import HamXConfig
from src.ham.ham_x.smoke import run_smoke


def _test_config(
    tmp_path: Path,
    *,
    live: bool = False,
    xai_api_key: str = "",
    readonly_transport: str = "direct",
) -> HamXConfig:
    return HamXConfig(
        xai_api_key=xai_api_key,
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
        enable_live_smoke=live,
        autonomy_enabled=False,
        dry_run=True,
        max_posts_per_hour=0,
        max_quotes_per_hour=0,
        max_searches_per_hour=30,
        daily_spend_limit_usd=5.0,
        model="grok-4.1-fast",
        xurl_bin="xurl",
        readonly_transport=readonly_transport,
        review_queue_path=tmp_path / "review_queue.jsonl",
        exception_queue_path=tmp_path / "exception_queue.jsonl",
        audit_log_path=tmp_path / "audit.jsonl",
    )


def _dump(result) -> str:
    return json.dumps(result.redacted_dump(), sort_keys=True)


def test_local_smoke_passes_with_fake_candidate(tmp_path: Path) -> None:
    result = run_smoke("local", config=_test_config(tmp_path))
    assert result.ok is True
    assert result.network_attempted is False
    assert result.mutation_attempted is False
    assert result.execution_allowed is False
    assert result.summary["candidate_count"] == 1
    assert result.audit_path == str(tmp_path / "audit.jsonl")


def test_env_smoke_redacts_secrets_and_reports_safe_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "xai-real-looking-secret-abcdefghijklmnopqrstuvwxyz")
    cfg = _test_config(tmp_path)
    result = run_smoke("env", config=cfg)
    dumped = _dump(result)
    assert result.ok is True
    assert result.summary["safe_defaults"]["HAM_X_AUTONOMY_ENABLED"] is True
    assert result.summary["safe_defaults"]["HAM_X_DRY_RUN"] is True
    assert result.summary["safe_defaults"]["HAM_X_ENABLE_LIVE_SMOKE"] is True
    assert "xai-real-looking-secret" not in dumped
    assert "[REDACTED" in dumped


def test_live_smoke_modes_disabled_by_default(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    for mode in ("x-readonly", "xai"):
        result = run_smoke(mode, config=cfg)
        assert result.ok is True
        assert result.live_enabled is False
        assert result.network_attempted is False
        assert result.execution_allowed is False
        assert result.summary["status"] in {"blocked", "disabled"}


def test_x_readonly_smoke_cannot_post_quote_or_like(tmp_path: Path) -> None:
    result = run_smoke("x-readonly", config=_test_config(tmp_path))
    planned = " ".join(result.summary["planned_command"])
    assert "post" not in planned
    assert "quote" not in planned
    assert "like" not in planned
    assert result.summary["catalog_skill_id"] == "bundled.social-media.xurl"
    assert result.execution_allowed is False
    assert result.mutation_attempted is False


def test_x_readonly_smoke_requires_all_live_gates(tmp_path: Path) -> None:
    live_but_not_dry = replace(_test_config(tmp_path, live=True), dry_run=False)
    live_but_autonomous = replace(_test_config(tmp_path, live=True), autonomy_enabled=True)
    for cfg in (live_but_not_dry, live_but_autonomous):
        result = run_smoke("x-readonly", config=cfg)
        assert result.network_attempted is False
        assert result.execution_allowed is False
        assert result.mutation_attempted is False
        assert result.summary["status"] == "blocked"


def test_x_readonly_smoke_runs_only_when_live_gates_pass(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def runner(argv, **kwargs):
        calls.append({"argv": argv, **kwargs})
        return subprocess.CompletedProcess(argv, 0, stdout="safe search output", stderr="")

    result = run_smoke(
        "x-readonly",
        config=_test_config(tmp_path, live=True, readonly_transport="xurl"),
        xurl_runner=runner,
        xurl_binary_resolver=lambda _: "/usr/bin/xurl",
    )

    assert result.ok is True
    assert result.network_attempted is True
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
    assert calls
    assert isinstance(calls[0]["argv"], list)
    assert calls[0]["shell"] is False
    assert result.summary["status"] == "executed"


def test_x_readonly_401_smoke_summary_remains_diagnostic(tmp_path: Path) -> None:
    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv,
            1,
            stdout='{"title":"Unauthorized","type":"about:blank","status":401,"detail":"Unauthorized"}',
            stderr="",
        )

    result = run_smoke(
        "x-readonly",
        config=_test_config(tmp_path, live=True, readonly_transport="xurl"),
        xurl_runner=runner,
        xurl_binary_resolver=lambda _: "/usr/bin/xurl",
    )
    data = result.redacted_dump()

    assert data["ok"] is False
    assert data["live_enabled"] is True
    assert data["network_attempted"] is True
    assert data["execution_allowed"] is False
    assert data["mutation_attempted"] is False
    assert data["summary"]["xurl_result"]["status"] == "failed"
    assert data["summary"]["xurl_result"]["reason"] == "xurl_returned_401_unauthorized"
    assert "Check xurl active profile" in data["summary"]["xurl_result"]["diagnostic"]
    assert data["exception_queue_path"] == str(tmp_path / "exception_queue.jsonl")


def test_xai_smoke_does_not_call_network_by_default(tmp_path: Path) -> None:
    result = run_smoke("xai", config=_test_config(tmp_path))
    assert result.network_attempted is False
    assert result.summary["status"] == "disabled"
    assert result.execution_allowed is False


def test_e2e_dry_run_does_not_execute_xurl_mutation(tmp_path: Path) -> None:
    result = run_smoke("e2e-dry-run", config=_test_config(tmp_path))
    assert result.ok is True
    assert result.network_attempted is False
    assert result.mutation_attempted is False
    assert result.execution_allowed is False
    assert result.summary["candidate_count"] == 1


def test_smoke_output_preserves_platform_context(tmp_path: Path) -> None:
    result = run_smoke("local", config=_test_config(tmp_path))
    assert result.tenant_id == "ham-official"
    assert result.agent_id == "ham-pr-rockstar"
    assert result.campaign_id == "base-stealth-launch"
    assert result.account_id == "ham-x-official"
    assert result.profile_id == "ham.default"
    assert result.policy_profile_id == "platform-default"
    assert result.brand_voice_id == "ham-canonical"
    assert result.autonomy_mode == "draft"
    assert result.catalog_skill_id == "bundled.social-media.xurl"


def test_no_secret_like_values_appear_in_smoke_output(tmp_path: Path, monkeypatch) -> None:
    secret = "sk-live-abcdefghijklmnopqrstuvwxyz1234567890"
    monkeypatch.setenv("X_BEARER_TOKEN", secret)
    result = run_smoke("env", config=_test_config(tmp_path))
    dumped = _dump(result)
    assert secret not in dumped
    assert "abcdefghijklmnopqrstuvwxyz1234567890" not in dumped
