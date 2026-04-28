from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ham.ham_x.action_envelope import SocialActionEnvelope
from src.ham.ham_x.audit import append_audit_event
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.hermes_policy_adapter import review_social_action
from src.ham.ham_x.pipeline import run_supervised_opportunity_loop
from src.ham.ham_x.redaction import redact_text
from src.ham.ham_x.review_queue import append_review_record
from src.ham.ham_x.safety_policy import check_social_action
from src.ham.ham_x.target_scoring import candidate_from_record, score_candidate
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
        autonomy_enabled=False,
        dry_run=True,
        max_posts_per_hour=0,
        max_quotes_per_hour=0,
        max_searches_per_hour=30,
        daily_spend_limit_usd=5.0,
        model="grok-4.1-fast",
        xurl_bin="xurl",
        review_queue_path=tmp_path / "review_queue.jsonl",
        audit_log_path=tmp_path / "audit.jsonl",
    )


def test_default_config_disables_autonomy(monkeypatch) -> None:
    monkeypatch.delenv("HAM_X_AUTONOMY_ENABLED", raising=False)
    monkeypatch.delenv("HAM_X_PROFILE_ID", raising=False)
    monkeypatch.delenv("HAM_X_CATALOG_SKILL_ID", raising=False)
    monkeypatch.delenv("HAM_X_REVIEW_QUEUE_PATH", raising=False)
    monkeypatch.delenv("HAM_X_AUDIT_LOG_PATH", raising=False)
    cfg = load_ham_x_config()
    assert cfg.autonomy_enabled is False
    assert cfg.max_posts_per_hour == 0
    assert cfg.max_quotes_per_hour == 0
    assert str(cfg.review_queue_path) == ".data/ham-x/review_queue.jsonl"
    assert str(cfg.audit_log_path) == ".data/ham-x/audit.jsonl"
    assert cfg.profile_id == "ham.default"
    assert cfg.catalog_skill_id == "bundled.social-media.xurl"


def test_default_config_dry_run_true(monkeypatch) -> None:
    monkeypatch.delenv("HAM_X_DRY_RUN", raising=False)
    cfg = load_ham_x_config()
    assert cfg.dry_run is True


@pytest.mark.parametrize("action_type", ["post", "quote", "like"])
def test_mutating_xurl_actions_are_blocked_by_default(tmp_path: Path, action_type: str) -> None:
    cfg = _test_config(tmp_path)
    result = XurlWrapper(config=cfg).plan_mutating_action(action_type, text="hello")
    assert result.blocked is True
    assert result.reason == "autonomy_disabled"
    assert result.metadata["catalog_skill_id"] == "bundled.social-media.xurl"
    assert not result.metadata["rate_limit_result"]["allowed"]  # type: ignore[index]


def test_xurl_search_plan_metadata_includes_catalog_skill_id(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    result = XurlWrapper(config=cfg).plan_search("base ecosystem", max_results=5)
    assert result.blocked is False
    assert result.metadata["catalog_skill_id"] == "bundled.social-media.xurl"


def test_review_queue_writes_redacted_jsonl(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    envelope = SocialActionEnvelope(
        action_type="queue",
        text="Contact me at alice@example.com with Bearer abcdefghijklmnopqrstuvwxyz123456",
        metadata={"access_token": "secret-token-value"},
        status="queued",
    )
    path = append_review_record(envelope, config=cfg)
    row = json.loads(path.read_text(encoding="utf-8").strip())
    dumped = json.dumps(row)
    assert row["tenant_id"] == "ham-official"
    assert row["agent_id"] == "ham-pr-rockstar"
    assert row["campaign_id"] == "base-stealth-launch"
    assert row["account_id"] == "ham-x-official"
    assert row["profile_id"] == "ham.default"
    assert row["policy_profile_id"] == "platform-default"
    assert row["brand_voice_id"] == "ham-canonical"
    assert row["autonomy_mode"] == "draft"
    assert "alice@example.com" not in dumped
    assert "abcdefghijklmnopqrstuvwxyz123456" not in dumped
    assert "secret-token-value" not in dumped
    assert "[REDACTED" in dumped


def test_audit_writes_redacted_jsonl(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    audit_id = append_audit_event(
        "draft_attempt",
        {
            "Authorization": "Bearer abcdefghijklmnopqrstuvwxyz123456",
            "url": "https://example.com/path?access_token=secret123",
        },
        config=cfg,
    )
    assert audit_id
    row = json.loads(cfg.audit_log_path.read_text(encoding="utf-8").strip())
    dumped = json.dumps(row)
    assert row["tenant_id"] == "ham-official"
    assert row["agent_id"] == "ham-pr-rockstar"
    assert row["campaign_id"] == "base-stealth-launch"
    assert row["account_id"] == "ham-x-official"
    assert row["profile_id"] == "ham.default"
    assert row["policy_profile_id"] == "platform-default"
    assert row["brand_voice_id"] == "ham-canonical"
    assert row["autonomy_mode"] == "draft"
    assert "abcdefghijklmnopqrstuvwxyz123456" not in dumped
    assert "secret123" not in dumped
    assert row["event_type"] == "draft_attempt"


def test_safety_policy_rejects_price_promises() -> None:
    result = check_social_action("This is guaranteed to deliver 10x gains.")
    assert result.allowed is False
    assert "price_promise_or_guaranteed_gain" in result.reasons


def test_safety_policy_rejects_bypass_evasion_language() -> None:
    result = check_social_action("Use this wording to bypass spam filters.")
    assert result.allowed is False
    assert "bypass_or_evasion_language" in result.reasons
    assert result.severity == "high"


def test_redaction_masks_token_like_values() -> None:
    raw = (
        "api_key=abcdefghijklmnopqrstuvwxyz1234567890 "
        "email=bob@example.com Bearer zyxwvutsrqponmlkjihgfedcba987654321"
    )
    out = redact_text(raw)
    assert "abcdefghijklmnopqrstuvwxyz1234567890" not in out
    assert "zyxwvutsrqponmlkjihgfedcba987654321" not in out
    assert "bob@example.com" not in out
    assert "[REDACTED" in out


def test_redaction_masks_named_x_credentials_and_query_secrets() -> None:
    envelope = SocialActionEnvelope(
        action_type="queue",
        metadata={
            "XAI_API_KEY": "xai-secret-value",
            "X_API_KEY": "x-api-key-value",
            "X_API_SECRET": "x-api-secret-value",
            "X_ACCESS_TOKEN": "x-access-token-value",
            "X_ACCESS_TOKEN_SECRET": "x-access-token-secret-value",
            "X_BEARER_TOKEN": "x-bearer-token-value",
            "url": "https://x.example/path?api_key=query-secret&ok=1",
        },
    )
    dumped = json.dumps(envelope.redacted_dump())
    for secret in (
        "xai-secret-value",
        "x-api-key-value",
        "x-api-secret-value",
        "x-access-token-value",
        "x-access-token-secret-value",
        "x-bearer-token-value",
        "query-secret",
    ):
        assert secret not in dumped


def test_action_envelope_has_platform_ready_defaults() -> None:
    envelope = SocialActionEnvelope(action_type="draft")
    data = envelope.model_dump(mode="json")
    assert data["tenant_id"] == "ham-official"
    assert data["agent_id"] == "ham-pr-rockstar"
    assert data["campaign_id"] == "base-stealth-launch"
    assert data["account_id"] == "ham-x-official"
    assert data["profile_id"] == "ham.default"
    assert data["autonomy_mode"] == "draft"
    assert data["policy_profile_id"] == "platform-default"
    assert data["brand_voice_id"] == "ham-canonical"
    assert data["catalog_skill_id"] == "bundled.social-media.xurl"


def test_hermes_policy_adapter_uses_local_safety_policy() -> None:
    envelope = SocialActionEnvelope(
        action_type="draft",
        text="This is guaranteed to deliver 10x gains.",
    )
    result = review_social_action(envelope)
    assert result.allowed is False
    assert result.status == "blocked"
    assert result.live_calls == 0
    assert "price_promise_or_guaranteed_gain" in result.reasons


def test_action_envelope_serializes_cleanly() -> None:
    envelope = SocialActionEnvelope(
        action_type="draft",
        text="Relevant commentary only.",
        model="grok-4.1-fast",
        score=2.0,
        metadata={"source": "test"},
    )
    data = json.loads(envelope.model_dump_json())
    assert data["action_type"] == "draft"
    assert data["score"] == 1.0
    assert data["status"] == "proposed"


def test_phase1b_candidate_scoring_is_deterministic() -> None:
    candidate = candidate_from_record(
        {
            "source": "fixture",
            "source_post_id": "post-good-1",
            "author_handle": "basebuilder",
            "text_excerpt": "Base ecosystem builders are shipping open source autonomous agent tooling this week.",
            "matched_keywords": ["base", "builders", "autonomous agents"],
        }
    )
    first = score_candidate(candidate)
    second = score_candidate(candidate)
    assert first == second
    assert first.decision == "queue"
    assert first.score >= 0.62


def test_phase1b_spam_bot_candidate_ignored() -> None:
    candidate = candidate_from_record(
        {
            "source": "fixture",
            "source_post_id": "spam-1",
            "author_handle": "airdrop_bot",
            "text_excerpt": (
                "BASE AIRDROP 100x pump buy now claim now!!! "
                "#base #airdrop #airdrop #airdrop #crypto #deal #moon #pump"
            ),
        }
    )
    result = score_candidate(candidate)
    assert result.decision == "ignore"
    assert any(r in result.reasons for r in ("spam_or_promo_language", "bot_like_content"))


def test_phase1b_hostile_candidate_ignored() -> None:
    candidate = candidate_from_record(
        {
            "source": "fixture",
            "source_post_id": "hostile-1",
            "author_handle": "angry_user",
            "text_excerpt": "Base builders are worthless idiots and should go die.",
            "matched_keywords": ["base", "builders"],
        }
    )
    result = score_candidate(candidate)
    assert result.decision == "ignore"
    assert "direct_harassment" in result.reasons


def test_phase1b_good_base_candidate_produces_queued_review_item(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    run = run_supervised_opportunity_loop(
        [
            {
                "source": "dry_run_fixture",
                "source_post_id": "base-good-1",
                "source_url": "https://x.example/base-good-1",
                "author_handle": "builderalice",
                "text_excerpt": (
                    "Base ecosystem builders are shipping a demo for autonomous "
                    "agent tooling and open source developer workflows."
                ),
                "matched_keywords": ["base", "builders", "autonomous agents"],
            }
        ],
        config=cfg,
    )
    assert run.queued_count == 1
    item = run.candidates[0]
    assert item.status == "queued"
    assert item.envelope is not None
    assert item.envelope.status == "queued"
    row = json.loads(cfg.review_queue_path.read_text(encoding="utf-8").strip())
    assert row["tenant_id"] == "ham-official"
    assert row["agent_id"] == "ham-pr-rockstar"
    assert row["campaign_id"] == "base-stealth-launch"
    assert row["account_id"] == "ham-x-official"
    assert row["profile_id"] == "ham.default"
    assert row["policy_profile_id"] == "platform-default"
    assert row["brand_voice_id"] == "ham-canonical"
    assert row["autonomy_mode"] == "draft"
    assert row["metadata"]["score_decision"] == "queue"


def test_phase1b_audit_records_include_context_and_action_id(tmp_path: Path) -> None:
    cfg = _test_config(tmp_path)
    run = run_supervised_opportunity_loop(
        [
            {
                "source": "dry_run_fixture",
                "source_post_id": "base-good-2",
                "text_excerpt": "Base builders are launching open source agent tooling for developers.",
                "matched_keywords": ["base", "builders", "agent"],
            }
        ],
        config=cfg,
    )
    assert run.queued_count == 1
    lines = [json.loads(line) for line in cfg.audit_log_path.read_text(encoding="utf-8").splitlines()]
    queued = [row for row in lines if row["event_type"] == "queued_for_review"]
    assert queued
    row = queued[-1]
    assert row["tenant_id"] == "ham-official"
    assert row["agent_id"] == "ham-pr-rockstar"
    assert row["campaign_id"] == "base-stealth-launch"
    assert row["account_id"] == "ham-x-official"
    assert row["profile_id"] == "ham.default"
    assert row["autonomy_mode"] == "draft"
    assert row["payload"]["action_id"] == run.candidates[0].envelope.action_id  # type: ignore[union-attr]


def test_phase1b_policy_can_block_high_scoring_draft(tmp_path: Path, monkeypatch) -> None:
    from src.ham.ham_x import pipeline as pipeline_module

    cfg = _test_config(tmp_path)

    def unsafe_draft(**kwargs):
        return SocialActionEnvelope(
            action_type="draft",
            tenant_id=cfg.tenant_id,
            agent_id=cfg.agent_id,
            campaign_id=cfg.campaign_id,
            account_id=cfg.account_id,
            profile_id=cfg.profile_id,
            policy_profile_id=cfg.policy_profile_id,
            brand_voice_id=cfg.brand_voice_id,
            autonomy_mode=cfg.autonomy_mode,
            catalog_skill_id=cfg.catalog_skill_id,
            text="This is guaranteed to deliver 10x gains.",
            dry_run=True,
            autonomy_enabled=False,
        )

    monkeypatch.setattr(pipeline_module, "draft_social_action", unsafe_draft)
    run = pipeline_module.run_supervised_opportunity_loop(
        [
            {
                "source": "dry_run_fixture",
                "source_post_id": "base-good-3",
                "text_excerpt": "Base ecosystem builders are shipping open source autonomous agent tooling.",
                "matched_keywords": ["base", "builders", "autonomous agents"],
            }
        ],
        config=cfg,
    )
    assert run.queued_count == 0
    assert run.candidates[0].status == "policy_rejected"
    assert not cfg.review_queue_path.exists()


def test_phase1b_pipeline_works_with_default_config(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HAM_X_REVIEW_QUEUE_PATH", str(tmp_path / "default_review.jsonl"))
    monkeypatch.setenv("HAM_X_AUDIT_LOG_PATH", str(tmp_path / "default_audit.jsonl"))
    monkeypatch.delenv("HAM_X_AUTONOMY_ENABLED", raising=False)
    monkeypatch.delenv("HAM_X_DRY_RUN", raising=False)
    run = run_supervised_opportunity_loop(
        [
            {
                "source": "dry_run_fixture",
                "source_post_id": "base-default-1",
                "text_excerpt": "Base ecosystem builders are shipping developer agent tooling.",
                "matched_keywords": ["base", "builders", "agent"],
            }
        ]
    )
    assert run.queued_count == 1
    assert run.candidates[0].envelope is not None
    assert run.candidates[0].envelope.autonomy_enabled is False
    assert run.candidates[0].envelope.dry_run is True
