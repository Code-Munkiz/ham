from __future__ import annotations

from pathlib import Path

from src.ham.ham_x.config import HamXConfig
from src.ham.ham_x.smoke import run_smoke
from src.ham.ham_x.x_readonly_client import XDirectReadonlyClient


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
    live: bool = True,
    bearer: str = "bearer-token-value",
) -> HamXConfig:
    return HamXConfig(
        xai_api_key="",
        x_api_key="",
        x_api_secret="",
        x_access_token="",
        x_access_token_secret="",
        x_bearer_token=bearer,
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


def test_direct_readonly_search_success_with_mocked_http(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def http_get(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return FakeResponse(
            200,
            {
                "data": [{"id": "1", "text": "Base ecosystem autonomous agents"}],
                "meta": {"result_count": 1},
            },
        )

    result = XDirectReadonlyClient(
        config=_test_config(tmp_path),
        http_get=http_get,
    ).search_recent("Base ecosystem autonomous agents")

    assert result.status == "ok"
    assert result.reason == "x_direct_search_ok"
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
    assert calls
    assert calls[0]["params"] == {
        "query": "Base ecosystem autonomous agents",
        "max_results": 10,
    }
    assert "Authorization" in calls[0]["headers"]  # Value is not asserted or printed.


def test_direct_readonly_missing_bearer_blocks_safely(tmp_path: Path) -> None:
    def http_get(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("HTTP should not be called")

    result = XDirectReadonlyClient(
        config=_test_config(tmp_path, bearer=""),
        http_get=http_get,
    ).search_recent("Base ecosystem autonomous agents")

    assert result.blocked is True
    assert result.executed is False
    assert result.reason == "x_bearer_token_missing"
    assert result.execution_allowed is False
    assert result.mutation_attempted is False


def test_direct_readonly_401_has_diagnostic_and_redacts_secret(tmp_path: Path) -> None:
    secret = "Bearer abcdefghijklmnopqrstuvwxyz123456"

    def http_get(*args, **kwargs):
        return FakeResponse(
            401,
            {"title": "Unauthorized", "status": 401, "detail": "Unauthorized"},
            text=f"Authorization: {secret}",
        )

    result = XDirectReadonlyClient(
        config=_test_config(tmp_path, bearer=secret),
        http_get=http_get,
    ).search_recent("Base ecosystem autonomous agents")

    dumped = str(result.as_dict())
    assert result.status == "failed"
    assert result.reason == "x_direct_search_401_unauthorized"
    assert "bearer token" in result.diagnostic
    assert "abcdefghijklmnopqrstuvwxyz123456" not in dumped
    assert "[REDACTED" in dumped
    assert result.execution_allowed is False
    assert result.mutation_attempted is False


def test_x_readonly_smoke_uses_direct_transport(tmp_path: Path) -> None:
    def http_get(*args, **kwargs):
        return FakeResponse(200, {"data": [{"id": "1", "text": "ok"}], "meta": {"result_count": 1}})

    result = run_smoke(
        "x-readonly",
        config=_test_config(tmp_path),
        x_http_get=http_get,
    )

    assert result.ok is True
    assert result.network_attempted is True
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
    assert result.summary["transport"] == "direct_bearer"
    assert result.summary["readonly_result"]["status"] == "ok"
