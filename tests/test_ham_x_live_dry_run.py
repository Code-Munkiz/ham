from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from src.ham.ham_x.config import HamXConfig
from src.ham.ham_x.live_dry_run import run_live_read_model_dry_run


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
    enabled: bool = True,
    dry_run: bool = True,
    autonomy_enabled: bool = False,
    live_execution: bool = False,
    emergency_stop: bool = False,
    bearer: str = "bearer-token-value",
    xai_key: str = "xai-key-value",
    max_results: int = 10,
    max_candidates: int = 3,
) -> HamXConfig:
    return HamXConfig(
        xai_api_key=xai_key,
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
        autonomy_mode="approval",
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
        execution_daily_cap=1,
        execution_per_run_cap=1,
        daily_spend_limit_usd=5.0,
        model="grok-4.20",
        xurl_bin="xurl",
        readonly_transport="direct",
        execution_transport="direct_oauth1",
        canary_allowed_actions="post,quote",
        enable_live_read_model_dry_run=enabled,
        live_dry_run_query="Base ecosystem autonomous agents",
        live_dry_run_max_results=max_results,
        live_dry_run_max_candidates=max_candidates,
        live_draft_max_output_tokens=120,
        live_draft_timeout_seconds=20,
        review_queue_path=tmp_path / "review_queue.jsonl",
        exception_queue_path=tmp_path / "exception_queue.jsonl",
        execution_journal_path=tmp_path / "execution_journal.jsonl",
        audit_log_path=tmp_path / "audit.jsonl",
    )


def _x_response(count: int = 1) -> FakeResponse:
    return FakeResponse(
        200,
        {
            "data": [
                {
                    "id": str(1000 + idx),
                    "text": f"Base ecosystem builders are shipping autonomous agent tooling demo {idx}.",
                }
                for idx in range(count)
            ],
            "meta": {"result_count": count},
        },
    )


def _xai_response(text: str = "HAM is watching Base builders ship useful agent tooling.") -> FakeResponse:
    return FakeResponse(200, {"output_text": text})


def _run_success(tmp_path: Path, *, x_count: int = 1, draft: str | None = None):
    x_calls: list[dict[str, object]] = []
    xai_calls: list[dict[str, object]] = []

    def http_get(url, **kwargs):
        x_calls.append({"url": url, **kwargs})
        return _x_response(x_count)

    def http_post(url, **kwargs):
        xai_calls.append({"url": url, **kwargs})
        return _xai_response(draft or "HAM is watching Base builders ship useful agent tooling.")

    result = run_live_read_model_dry_run(
        config=_test_config(tmp_path),
        x_http_get=http_get,
        xai_http_post=http_post,
    )
    return result, x_calls, xai_calls


def test_blocks_by_default(tmp_path: Path) -> None:
    result = run_live_read_model_dry_run(config=_test_config(tmp_path, enabled=False))
    assert result.status == "blocked"
    assert "HAM_X_ENABLE_LIVE_READ_MODEL_DRY_RUN_must_be_true" in result.gate_reasons
    assert result.execution_allowed is False
    assert result.mutation_attempted is False


def test_blocks_when_required_gates_are_unsafe(tmp_path: Path) -> None:
    cases = [
        (_test_config(tmp_path, dry_run=False), "HAM_X_DRY_RUN_must_remain_true"),
        (_test_config(tmp_path, autonomy_enabled=True), "HAM_X_AUTONOMY_ENABLED_must_remain_false"),
        (_test_config(tmp_path, live_execution=True), "HAM_X_ENABLE_LIVE_EXECUTION_must_remain_false"),
        (_test_config(tmp_path, emergency_stop=True), "HAM_X_EMERGENCY_STOP_must_remain_false"),
    ]
    for cfg, reason in cases:
        result = run_live_read_model_dry_run(config=cfg)
        assert result.status == "blocked"
        assert reason in result.gate_reasons
        assert result.execution_allowed is False
        assert result.mutation_attempted is False


def test_blocks_when_credentials_missing(tmp_path: Path) -> None:
    missing_bearer = run_live_read_model_dry_run(config=_test_config(tmp_path, bearer=""))
    missing_xai = run_live_read_model_dry_run(config=_test_config(tmp_path, xai_key=""))
    assert "X_BEARER_TOKEN_required" in missing_bearer.gate_reasons
    assert "XAI_API_KEY_required" in missing_xai.gate_reasons


def test_mocked_x_search_creates_bounded_candidates_and_caps(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path, max_candidates=2)
    result = run_live_read_model_dry_run(
        config=cfg,
        x_http_get=lambda url, **kwargs: _x_response(5),
        xai_http_post=lambda url, **kwargs: _xai_response(),
    )
    assert result.status == "completed"
    assert result.candidate_count == 2
    assert len(result.candidates) == 2
    assert all(item.candidate.source == "live_x_readonly_search" for item in result.candidates)
    assert result.network_attempted_x is True
    assert result.network_attempted_xai is True


def test_safe_xai_draft_routes_to_review_with_false_execution_invariants(tmp_path: Path) -> None:
    result, x_calls, xai_calls = _run_success(tmp_path)
    assert result.ok is True
    assert result.reviewed_count == 1
    item = result.candidates[0]
    assert item.status == "queued_review"
    assert item.envelope is not None
    assert item.envelope.metadata["execution_allowed"] is False
    assert item.envelope.metadata["mutation_attempted"] is False
    assert item.autonomy_decision is not None
    assert item.autonomy_decision.execution_allowed is False
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
    assert x_calls and xai_calls
    assert xai_calls[0]["json"]["store"] is False


def test_unsafe_xai_draft_routes_to_exception(tmp_path: Path) -> None:
    result, _, _ = _run_success(tmp_path, draft="Guaranteed 10x gains if you buy now.")
    item = result.candidates[0]
    assert item.status == "queued_exception"
    assert item.exception_queue_path
    assert item.envelope is not None
    assert item.envelope.policy_result is not None
    assert item.envelope.policy_result["allowed"] is False


def test_redaction_prevents_secret_values_in_outputs_and_records(tmp_path: Path) -> None:
    secret = "abcdefghijklmnopqrstuvwxyz1234567890"
    cfg = _test_config(tmp_path, xai_key=secret, bearer=f"Bearer {secret}")
    result = run_live_read_model_dry_run(
        config=cfg,
        x_http_get=lambda url, **kwargs: _x_response(),
        xai_http_post=lambda url, **kwargs: _xai_response(f"Authorization: Bearer {secret}"),
    )
    dumped = json.dumps(result.redacted_dump())
    audit = cfg.audit_log_path.read_text(encoding="utf-8")
    queue_path = cfg.exception_queue_path if cfg.exception_queue_path.exists() else cfg.review_queue_path
    queue = queue_path.read_text(encoding="utf-8")
    assert secret not in dumped
    assert secret not in audit
    assert secret not in queue


def test_search_failure_does_not_call_xai(tmp_path: Path) -> None:
    xai_calls: list[dict[str, object]] = []
    result = run_live_read_model_dry_run(
        config=_test_config(tmp_path),
        x_http_get=lambda url, **kwargs: FakeResponse(401, {"title": "Unauthorized"}),
        xai_http_post=lambda url, **kwargs: xai_calls.append({"url": url}) or _xai_response(),
    )
    assert result.status == "failed"
    assert result.network_attempted_x is True
    assert result.network_attempted_xai is False
    assert xai_calls == []


def test_live_dry_run_pipeline_smoke_and_autonomy_do_not_import_executor() -> None:
    root = Path(__file__).parents[1] / "src" / "ham" / "ham_x"
    for name in ("live_dry_run.py", "pipeline.py", "smoke.py", "autonomy.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "manual_canary" not in text
        assert "x_executor" not in text


def test_result_caps_are_enforced_at_config_level(tmp_path: Path) -> None:
    cfg = replace(_test_config(tmp_path), live_dry_run_max_candidates=1, live_dry_run_max_results=100)
    result = run_live_read_model_dry_run(
        config=cfg,
        x_http_get=lambda url, **kwargs: _x_response(3),
        xai_http_post=lambda url, **kwargs: _xai_response(),
    )
    assert result.candidate_count == 1
    assert result.candidates[0].execution_allowed is False
    assert result.candidates[0].mutation_attempted is False
