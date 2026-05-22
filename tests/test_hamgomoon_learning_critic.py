"""Tests for the HAMgomoon Hermes social critic (stub default + env-gated Hermes)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.ham.hamgomoon_learning.hermes_critic import (
    SocialCritic,
    StubSocialCritic,
    get_default_social_critic,
)
from src.ham.hamgomoon_learning.models import HermesSocialCritique, SocialDraftRecord


def _make_draft(**kwargs: Any) -> SocialDraftRecord:
    defaults: dict[str, Any] = {
        "draft_id": "test-draft-001",
        "channel": "telegram",
        "proposed_action": "message",
        "draft_text": "Hello, this is a test post.",
        "prompt": "GoHAM autonomy tick.",
    }
    defaults.update(kwargs)
    return SocialDraftRecord(**defaults)


def _hermes_critique_payload(draft_id: str = "test-draft-001") -> dict[str, Any]:
    """Return a valid HermesSocialCritique JSON payload (matching model schema)."""
    return {
        "draft_id": draft_id,
        "brand_fit_score": 0.8,
        "safety_score": 0.9,
        "clarity_score": 0.7,
        "engagement_hypothesis": "This post will engage moderately.",
        "risk_flags": [],
        "suggested_improvement": None,
        "reusable_lesson": "Keep it concise.",
        "policy_suggestion": None,
        "should_update_strategy": False,
    }


def test_stub_critic_returns_full_critique() -> None:
    critic = StubSocialCritic()
    draft = SocialDraftRecord(draft_id="dx", channel="x", proposed_action="post", draft_text="hi")
    out = critic.critique(draft)
    assert isinstance(out, HermesSocialCritique)
    assert out.draft_id == "dx"
    assert 0.0 <= out.brand_fit_score <= 1.0
    assert 0.0 <= out.safety_score <= 1.0
    assert 0.0 <= out.clarity_score <= 1.0
    assert isinstance(out.risk_flags, list)
    assert out.engagement_hypothesis


def test_default_critic_is_stub() -> None:
    critic = get_default_social_critic()
    assert isinstance(critic, SocialCritic)
    assert isinstance(critic, StubSocialCritic)


# ---------------------------------------------------------------------------
# VAL-M15-M2-CRITIC-OPTIN-ENV-001
# ---------------------------------------------------------------------------


def test_resolver_returns_stub_unless_all_env_present_and_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_default_social_critic() returns StubSocialCritic when env is unset/0/false,
    and HermesSocialCritic only when HAM_SOCIAL_CRITIC_USE_HERMES=1 AND gateway
    envs are configured AND probe_hermes_http_gateway() returns status=healthy.
    """
    from src.ham.hamgomoon_learning.hermes_critic_real import HermesSocialCritic

    healthy_probe = {"status": "healthy", "reachable": True}

    # 1. env unset → StubSocialCritic
    monkeypatch.delenv("HAM_SOCIAL_CRITIC_USE_HERMES", raising=False)
    monkeypatch.delenv("HERMES_GATEWAY_BASE_URL", raising=False)
    critic = get_default_social_critic()
    assert isinstance(critic, StubSocialCritic)
    assert not isinstance(critic, HermesSocialCritic)

    # 2. env=0 → StubSocialCritic
    monkeypatch.setenv("HAM_SOCIAL_CRITIC_USE_HERMES", "0")
    critic = get_default_social_critic()
    assert isinstance(critic, StubSocialCritic)
    assert not isinstance(critic, HermesSocialCritic)

    # 3. env=false → StubSocialCritic
    monkeypatch.setenv("HAM_SOCIAL_CRITIC_USE_HERMES", "false")
    critic = get_default_social_critic()
    assert isinstance(critic, StubSocialCritic)
    assert not isinstance(critic, HermesSocialCritic)

    # 4. env=1 + gateway configured + probe healthy → HermesSocialCritic
    monkeypatch.setenv("HAM_SOCIAL_CRITIC_USE_HERMES", "1")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://hermes-test:8080")
    monkeypatch.setenv("HERMES_GATEWAY_API_KEY", "test-key")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "hermes-agent")
    with patch(
        "src.ham.hamgomoon_learning.hermes_critic.probe_hermes_http_gateway",
        return_value=healthy_probe,
    ):
        critic = get_default_social_critic()
    assert isinstance(critic, HermesSocialCritic)


# ---------------------------------------------------------------------------
# VAL-M15-M2-CRITIC-SUCCESS-RECORDED-002
# ---------------------------------------------------------------------------


def test_hermes_success_path_writes_critique_to_learning_record(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Mock successful gateway response → critique recorded in LearningRecord.critique."""
    from src.ham.hamgomoon_learning.hermes_critic_real import HermesSocialCritic
    from src.ham.social_autonomy.learning_hook import append_tick_learning

    # Configure Hermes critic
    monkeypatch.setenv("HAM_SOCIAL_CRITIC_USE_HERMES", "1")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://hermes-test:8080")

    config = {"model": "hermes-agent", "timeout": 10.0, "max_input": 4096}
    hermes_critic = HermesSocialCritic(config)

    draft = _make_draft()
    payload = _hermes_critique_payload(draft_id=draft.draft_id)

    with patch(
        "src.ham.hamgomoon_learning.hermes_critic_real.complete_chat_turn",
        return_value=json.dumps(payload),
    ):
        critique = hermes_critic.critique(draft)

    assert isinstance(critique, HermesSocialCritique)
    assert critique.draft_id == draft.draft_id
    assert abs(critique.brand_fit_score - 0.8) < 1e-9
    assert abs(critique.safety_score - 0.9) < 1e-9
    assert abs(critique.clarity_score - 0.7) < 1e-9
    assert critique.notes is None  # no notes on success

    # Verify it gets recorded via append_tick_learning
    learning_records: list[Any] = []

    def _capture_record(record: Any) -> Any:
        learning_records.append(record)
        return record

    tick_result = {
        "ran": True,
        "dry_run": True,
        "profile_status": "running",
        "actions_taken": ["telegram:message"],
        "blocked_reasons": [],
    }

    profile = _make_profile(tmp_path, learning_enabled=True)

    with patch(
        "src.ham.hamgomoon_learning.hermes_critic_real.complete_chat_turn",
        return_value=json.dumps(payload),
    ):
        with patch(
            "src.ham.hamgomoon_learning.hermes_critic.probe_hermes_http_gateway",
            return_value={"status": "healthy"},
        ):
            append_tick_learning(
                profile,
                tick_result,
                critic=hermes_critic,
                learning_store=_capture_record,
            )

    assert len(learning_records) == 1
    record = learning_records[0]
    assert record.critique is not None


# ---------------------------------------------------------------------------
# VAL-M15-M2-CRITIC-MISSING-CONFIG-FALLBACK-003
# ---------------------------------------------------------------------------


def test_missing_gateway_config_falls_back_to_stub_with_unavailable_notes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """HAM_SOCIAL_CRITIC_USE_HERMES=1 but HERMES_GATEWAY_BASE_URL unset →
    resolver returns StubSocialCritic; critique notes == hermes_critique_unavailable.
    """
    monkeypatch.setenv("HAM_SOCIAL_CRITIC_USE_HERMES", "1")
    monkeypatch.delenv("HERMES_GATEWAY_BASE_URL", raising=False)

    critic = get_default_social_critic()
    # Resolver returns a StubSocialCritic (or subclass) — not HermesSocialCritic
    assert isinstance(critic, StubSocialCritic)

    draft = _make_draft()
    critique = critic.critique(draft)
    assert critique.notes == "hermes_critique_unavailable"


# ---------------------------------------------------------------------------
# VAL-M15-M2-CRITIC-GATEWAY-FAILURE-FALLBACK-004
# ---------------------------------------------------------------------------


def test_gateway_call_error_falls_back_to_stub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GatewayCallError → fallback critique with notes=hermes_critique_unavailable."""
    from src.ham.hamgomoon_learning.hermes_critic_real import HermesSocialCritic
    from src.integrations.nous_gateway_client import GatewayCallError

    config = {"model": "hermes-agent", "timeout": 10.0, "max_input": 4096}
    critic = HermesSocialCritic(config)
    draft = _make_draft()

    with patch(
        "src.ham.hamgomoon_learning.hermes_critic_real.complete_chat_turn",
        side_effect=GatewayCallError("UPSTREAM_TIMEOUT", "Gateway timed out"),
    ):
        critique = critic.critique(draft)

    assert isinstance(critique, HermesSocialCritique)
    assert critique.notes == "hermes_critique_unavailable"
    # Shape should match stub (non-zero scores)
    assert 0.0 <= critique.brand_fit_score <= 1.0


# ---------------------------------------------------------------------------
# VAL-M15-M2-CRITIC-PARSE-FAILURE-FALLBACK-005
# ---------------------------------------------------------------------------


def test_parse_failure_falls_back_to_stub_with_parse_failed_notes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-JSON gateway response → fallback with notes=hermes_critique_parse_failed."""
    from src.ham.hamgomoon_learning.hermes_critic_real import HermesSocialCritic

    config = {"model": "hermes-agent", "timeout": 10.0, "max_input": 4096}
    critic = HermesSocialCritic(config)
    draft = _make_draft()

    with patch(
        "src.ham.hamgomoon_learning.hermes_critic_real.complete_chat_turn",
        return_value="This is not valid JSON {broken",
    ):
        critique = critic.critique(draft)

    assert critique.notes == "hermes_critique_parse_failed"
    assert 0.0 <= critique.brand_fit_score <= 1.0


# ---------------------------------------------------------------------------
# VAL-M15-M2-CRITIC-UNHEALTHY-PROBE-FALLBACK-006
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "probe_status",
    ["unreachable", "auth_required", "degraded", "unknown"],
)
def test_unhealthy_probe_forces_stub_no_gateway_call(
    monkeypatch: pytest.MonkeyPatch,
    probe_status: str,
) -> None:
    """Unhealthy probe_hermes_http_gateway() → resolver returns StubSocialCritic;
    zero complete_chat_turn calls.
    """
    from src.ham.hamgomoon_learning.hermes_critic_real import HermesSocialCritic

    monkeypatch.setenv("HAM_SOCIAL_CRITIC_USE_HERMES", "1")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://hermes-test:8080")

    mock_chat = MagicMock()
    with patch(
        "src.ham.hamgomoon_learning.hermes_critic.probe_hermes_http_gateway",
        return_value={"status": probe_status, "reachable": False},
    ):
        with patch(
            "src.ham.hamgomoon_learning.hermes_critic_real.complete_chat_turn",
            mock_chat,
        ):
            critic = get_default_social_critic()

    assert isinstance(critic, StubSocialCritic)
    assert not isinstance(critic, HermesSocialCritic)
    assert mock_chat.call_count == 0


# ---------------------------------------------------------------------------
# VAL-M15-M2-CRITIC-NO-SECRET-IN-PROMPT-008
# ---------------------------------------------------------------------------


def test_hermes_critic_prompt_redacts_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hermes critic prompt must not carry literal secrets or banned env-var names."""
    from src.ham.hamgomoon_learning.hermes_critic_real import HermesSocialCritic
    from src.integrations.nous_gateway_client import GatewayCallError

    config = {"model": "hermes-agent", "timeout": 10.0, "max_input": 4096}
    critic = HermesSocialCritic(config)

    # Bait strings that must never appear in the outgoing prompt.
    # These are clearly synthetic test fixtures, not real credentials.
    _FAKE_APPLY_VALUE = "fake-apply-tok-XXXX"
    _FAKE_BOT_VALUE = "bot99999:FakeTokenXXXXXXX"
    _FAKE_XAI_VALUE = "xai-fakekeyXXXXXXXXXXXXXX"
    _FAKE_EXTERNAL_ID = "123456789012345678"  # 18-digit numeric ID

    bait_token = f"HAM_SOCIAL_LIVE_APPLY_TOKEN={_FAKE_APPLY_VALUE}"
    bait_bot = f"TELEGRAM_BOT_TOKEN={_FAKE_BOT_VALUE}"
    bait_xai = _FAKE_XAI_VALUE
    bait_id = _FAKE_EXTERNAL_ID

    draft = _make_draft(
        draft_text=(
            f"Post with secret {bait_xai} in text."
            f" Also {bait_id} and {bait_token}."
        ),
        prompt=f"Prompt with {bait_bot} in it.",
    )

    captured_messages: list[Any] = []

    def _capture_and_raise(messages: list[Any], **kwargs: Any) -> str:
        captured_messages.extend(messages)
        raise GatewayCallError("UPSTREAM_TIMEOUT", "test")

    with patch(
        "src.ham.hamgomoon_learning.hermes_critic_real.complete_chat_turn",
        side_effect=_capture_and_raise,
    ):
        critic.critique(draft)

    assert len(captured_messages) >= 1
    full_prompt = json.dumps(captured_messages)

    # None of the bait values should appear verbatim in the outgoing messages.
    assert _FAKE_APPLY_VALUE not in full_prompt
    assert _FAKE_BOT_VALUE not in full_prompt
    assert bait_xai not in full_prompt
    assert bait_id not in full_prompt


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _make_profile(tmp_path: Path, *, learning_enabled: bool = True) -> Any:
    """Build a minimal GoHamSocialProfile for tests."""
    from datetime import UTC, datetime

    from src.ham.social_autonomy.schema import GoHamSocialProfile

    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    return GoHamSocialProfile.model_validate(
        {
            "profile_id": "test-profile",
            "workspace_id": "ws-1",
            "project_id": "proj-1",
            "persona_id": "test-persona",
            "status": "running",
            "goal": "Test goal.",
            "channels": {"telegram": {"enabled": True, "available": True}},
            "actions_allowed_per_channel": {"telegram": ["message"]},
            "daily_caps": {"telegram": 3},
            "cadence": "manual",
            "forbidden_topics": [],
            "safety_rules": [],
            "learning_enabled": learning_enabled,
            "emergency_stop": False,
            "created_at": now,
            "updated_at": now,
        }
    )
