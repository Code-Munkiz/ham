from __future__ import annotations

import json
from pathlib import Path

from src.ham.ham_x.config import HamXConfig
from src.ham.ham_x.grok_client import XAI_SMOKE_EXPECTED, XAI_SMOKE_MAX_OUTPUT_TOKENS
from src.ham.ham_x.smoke import run_smoke


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
    live: bool = False,
    xai_api_key: str = "",
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


def _dump(result) -> str:
    return json.dumps(result.redacted_dump(), sort_keys=True)


def test_xai_smoke_disabled_by_default_does_not_call_http(tmp_path: Path) -> None:
    def http_post(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("HTTP should not be called")

    result = run_smoke(
        "xai",
        config=_test_config(tmp_path, xai_api_key="xai-secret-value"),
        xai_http_post=http_post,
    )

    assert result.ok is True
    assert result.network_attempted is False
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
    assert result.summary["status"] == "disabled"


def test_xai_smoke_requires_api_key_when_live_enabled(tmp_path: Path) -> None:
    def http_post(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("HTTP should not be called")

    result = run_smoke(
        "xai",
        config=_test_config(tmp_path, live=True),
        xai_http_post=http_post,
    )

    assert result.ok is True
    assert result.network_attempted is False
    assert result.summary["status"] == "blocked"
    assert result.summary["reason"] == "xai_api_key_missing"
    assert result.execution_allowed is False
    assert result.mutation_attempted is False


def test_xai_smoke_success_uses_tiny_prompt_and_token_cap(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def http_post(*args, **kwargs):
        calls.append({"args": args, **kwargs})
        return FakeResponse(200, {"output_text": XAI_SMOKE_EXPECTED})

    result = run_smoke(
        "xai",
        config=_test_config(tmp_path, live=True, xai_api_key="xai-secret-value"),
        xai_http_post=http_post,
    )

    assert result.ok is True
    assert result.network_attempted is True
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
    assert calls
    payload = calls[0]["json"]
    assert isinstance(payload, dict)
    assert payload["model"] == "grok-4.1-fast"
    assert payload["max_output_tokens"] == XAI_SMOKE_MAX_OUTPUT_TOKENS
    assert payload["store"] is False
    assert result.summary["status"] == "xai_smoke_ok"


def test_xai_smoke_auth_failure_redacts_error_and_secret(tmp_path: Path) -> None:
    secret = "xai-secret-abcdefghijklmnopqrstuvwxyz123456"

    def http_post(*args, **kwargs):
        return FakeResponse(
            401,
            {"error": {"message": f"bad Authorization: Bearer {secret}"}},
            text=f"Bearer {secret}",
        )

    result = run_smoke(
        "xai",
        config=_test_config(tmp_path, live=True, xai_api_key=secret),
        xai_http_post=http_post,
    )

    dumped = _dump(result)
    assert result.ok is False
    assert result.network_attempted is True
    assert result.summary["status"] == "xai_smoke_nonzero_status"
    assert secret not in dumped
    assert "abcdefghijklmnopqrstuvwxyz123456" not in dumped
    assert "[REDACTED" in dumped
    assert result.execution_allowed is False
    assert result.mutation_attempted is False


def test_xai_smoke_does_not_touch_xurl_path(tmp_path: Path) -> None:
    def http_post(*args, **kwargs):
        return FakeResponse(200, {"output_text": XAI_SMOKE_EXPECTED})

    def xurl_runner(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("xurl runner should not be called by xAI smoke")

    result = run_smoke(
        "xai",
        config=_test_config(tmp_path, live=True, xai_api_key="xai-secret-value"),
        xai_http_post=http_post,
        xurl_runner=xurl_runner,
    )

    assert result.ok is True
    assert result.network_attempted is True
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
