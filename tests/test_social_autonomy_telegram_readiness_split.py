"""Tests for M2 Telegram readiness decoupling from Hermes gateway.

Assertions covered (see validation-contract.md):
- VAL-M15-M2-READINESS-DECOUPLED-FROM-HERMES-001
- VAL-M15-M2-READINESS-HERMES-PATH-INTACT-002
- VAL-M15-M2-READINESS-DEFAULT-NO-HERMES-003
- VAL-M15-M2-READINESS-REACTIVE-INBOUND-MISSING-004
- VAL-M15-M2-READINESS-PROFILE-FLAG-005
- VAL-M15-M2-CAPABILITIES-NEW-FIELDS-001
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_telegram_activity import plan_telegram_activity_once
from src.ham.social_telegram_autopilot import HamgomoonAutopilotConfig, run_hamgomoon_autopilot_once
from src.ham.social_telegram_inbound import discover_telegram_inbound_once

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _disable_clerk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)


def _set_telegram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure all required Telegram env vars without a real token."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "synthetic-token-for-test")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "1234567890")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "-1001234567890")
    monkeypatch.setenv("TELEGRAM_TEST_GROUP_ID", "-1009876543210")


def _clear_hermes_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear all Hermes environment variables."""
    monkeypatch.delenv("HERMES_GATEWAY_BASE_URL", raising=False)
    monkeypatch.delenv("HAM_HERMES_GATEWAY_STATUS_PATH", raising=False)
    monkeypatch.delenv("HAM_HERMES_HOME", raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)


# ---------------------------------------------------------------------------
# VAL-M15-M2-READINESS-PROFILE-FLAG-005
# ---------------------------------------------------------------------------


def test_default_profile_new_m2_fields() -> None:
    """A freshly-created GoHamSocialProfile defaults to
    activity_requires_hermes_gateway=False and telegram_self_probe_state='unknown'.

    VAL-M15-M2-READINESS-PROFILE-FLAG-005
    """
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    profile = GoHamSocialProfile(
        profile_id="test-m2",
        status="draft",
        goal="Test goal",
        persona_id="ham-canonical",
        channels={
            "telegram": {"enabled": False},
            "x": {"enabled": False},
            "discord": {"enabled": False},
        },
        actions_allowed_per_channel={"telegram": [], "x": [], "discord": []},
        daily_caps={"telegram": 0, "x": 0, "discord": 0},
        cadence="manual",
        forbidden_topics=[],
        safety_rules=[],
        learning_enabled=False,
        emergency_stop=False,
        created_at=now,
        updated_at=now,
    )
    assert profile.activity_requires_hermes_gateway is False
    assert profile.telegram_self_probe_state == "unknown"


# ---------------------------------------------------------------------------
# VAL-M15-M2-READINESS-HERMES-PATH-INTACT-002
# ---------------------------------------------------------------------------


def test_hermes_required_emits_not_ready_blocker() -> None:
    """When activity_requires_hermes_gateway=True and gateway disconnected,
    plan_telegram_activity_once emits telegram_gateway_not_connected.

    VAL-M15-M2-READINESS-HERMES-PATH-INTACT-002
    """
    result = plan_telegram_activity_once(
        readiness="ready",
        gateway_runtime_state="disconnected",
        activity_requires_hermes_gateway=True,
        telegram_self_probe_state="ok",
    )
    assert result.status == "blocked"
    assert "telegram_gateway_not_connected" in result.reasons


def test_hermes_required_unknown_gateway_also_emits_not_connected() -> None:
    """When activity_requires_hermes_gateway=True and gateway state is unknown,
    plan_telegram_activity_once emits telegram_gateway_not_connected.

    VAL-M15-M2-READINESS-HERMES-PATH-INTACT-002 (gateway unknown variant)
    """
    result = plan_telegram_activity_once(
        readiness="ready",
        gateway_runtime_state="unknown",
        activity_requires_hermes_gateway=True,
        telegram_self_probe_state="ok",
    )
    assert result.status == "blocked"
    assert "telegram_gateway_not_connected" in result.reasons


def test_hermes_required_path_connected_allows_when_probe_ok() -> None:
    """When activity_requires_hermes_gateway=True, Hermes connected, and
    self-probe ok, activity lane is not blocked by Hermes or probe gates.

    VAL-M15-M2-READINESS-HERMES-PATH-INTACT-002 (gateway connected variant)
    """
    result = plan_telegram_activity_once(
        readiness="ready",
        gateway_runtime_state="connected",
        activity_requires_hermes_gateway=True,
        telegram_self_probe_state="ok",
    )
    # gateway_runtime_state connected + readiness ready → NOT blocked by Hermes/probe
    assert "telegram_gateway_not_connected" not in result.reasons
    assert "telegram_self_probe_not_ok" not in result.reasons


# ---------------------------------------------------------------------------
# VAL-M15-M2-READINESS-DEFAULT-NO-HERMES-003 (activity runner / autopilot)
# ---------------------------------------------------------------------------


def test_activity_lane_no_hermes_gate_when_activity_requires_hermes_false() -> None:
    """When activity_requires_hermes_gateway=False (default), Hermes gates are
    skipped; only self-probe is checked for the activity lane.

    VAL-M15-M2-READINESS-DEFAULT-NO-HERMES-003 (unit-level)
    """
    # Self-probe ok + readiness ready: activity lane should NOT emit Hermes codes
    result = plan_telegram_activity_once(
        readiness="ready",
        gateway_runtime_state="unknown",  # Hermes absent/unknown
        activity_requires_hermes_gateway=False,
        telegram_self_probe_state="ok",
    )
    assert "telegram_gateway_not_connected" not in result.reasons
    assert "telegram_readiness_not_ready" not in result.reasons
    assert "telegram_self_probe_not_ok" not in result.reasons


def test_activity_lane_runs_without_hermes_when_self_probe_ok(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When activity_requires_hermes_gateway=False, Hermes absent, self-probe
    mocked to 'ok': activity lane runs and blocked_reasons contains none of the
    Hermes-related codes.

    VAL-M15-M2-READINESS-DEFAULT-NO-HERMES-003 (tick-level)
    """
    from datetime import UTC, datetime

    import src.api.social as social_mod
    from src.ham.social_autonomy.store import apply_social_autonomy_profile
    from src.ham.social_autonomy.tick import run_social_autonomy_tick

    _now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    _token = "no-hermes-write-token"  # noqa: S105

    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _token)

    profile = GoHamSocialProfile(
        profile_id="no-hermes-test",
        status="running",
        goal="Test goal",
        persona_id="ham-canonical",
        channels={
            "telegram": {"enabled": True, "available": True},
            "x": {"enabled": False, "available": True},
            "discord": {"enabled": False, "available": False},
        },
        actions_allowed_per_channel={"telegram": ["message", "activity"], "x": [], "discord": []},
        daily_caps={"telegram": 3, "x": 0, "discord": 0},
        cadence="manual",
        forbidden_topics=[],
        safety_rules=[],
        learning_enabled=False,
        emergency_stop=False,
        created_at=_now,
        updated_at=_now,
    )
    apply_social_autonomy_profile(tmp_path, profile, token=_token, actor="pytest-seed")
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", raising=False)

    # Mock status response: self-probe ok, Hermes absent
    monkeypatch.setattr(
        social_mod,
        "_telegram_status_for_autonomy_tick",
        lambda: SimpleNamespace(
            overall_readiness="ready",
            hermes_gateway=SimpleNamespace(provider_runtime_state="unknown"),
            telegram_self_probe_state="ok",
        ),
    )
    # Pin transcript paths so reactive lane is deterministically blocked
    monkeypatch.delenv("HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH", raising=False)
    monkeypatch.delenv("HAM_HERMES_HOME", raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)

    def _zero_usage(channel: str, action: str, now: Any) -> int:
        return 0

    def _allowing_guard(*args: Any, **kwargs: Any) -> list[str]:
        return []

    result = run_social_autonomy_tick(
        store_path=tmp_path,
        now=_now,
        dry_run=True,
        usage_counter=_zero_usage,
        content_guard=_allowing_guard,
        run_once=True,
    )
    hermes_related = {
        "hermes_gateway_not_connected",
        "hermes_gateway_runtime_unknown",
        "hermes_gateway_not_ready",
        "telegram_gateway_not_connected",
        "telegram_readiness_not_ready",
    }
    emitted = set(result.blocked_reasons)
    assert not (emitted & hermes_related), (
        f"Unexpected Hermes-related blocked reasons: {emitted & hermes_related}"
    )


# ---------------------------------------------------------------------------
# VAL-M15-M2-READINESS-REACTIVE-INBOUND-MISSING-004
# ---------------------------------------------------------------------------


def test_emits_inbound_source_not_configured_when_neither_source_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When neither HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH nor
    HAM_TELEGRAM_TRANSCRIPT_BACKEND is configured, discover_telegram_inbound_once
    emits telegram_inbound_source_not_configured.

    VAL-M15-M2-READINESS-REACTIVE-INBOUND-MISSING-004
    """
    monkeypatch.delenv("HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH", raising=False)
    monkeypatch.delenv("HAM_TELEGRAM_TRANSCRIPT_BACKEND", raising=False)
    monkeypatch.delenv("HAM_HERMES_HOME", raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)

    result = discover_telegram_inbound_once()
    assert result.status == "blocked"
    assert "telegram_inbound_source_not_configured" in result.reasons


def test_file_path_env_set_uses_hermes_transcript_source_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """When HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH is set but the file doesn't
    exist, we get hermes_transcript_source_unavailable (source configured, not
    present) — NOT telegram_inbound_source_not_configured.

    VAL-M15-M2-READINESS-REACTIVE-INBOUND-MISSING-004 (configured-but-absent variant)
    """
    monkeypatch.setenv("HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH", str(tmp_path / "no_such.jsonl"))
    monkeypatch.delenv("HAM_TELEGRAM_TRANSCRIPT_BACKEND", raising=False)
    monkeypatch.delenv("HAM_HERMES_HOME", raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)

    result = discover_telegram_inbound_once()
    assert result.status == "blocked"
    assert "telegram_inbound_source_not_configured" not in result.reasons


def test_backend_env_set_uses_hermes_transcript_source_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When HAM_TELEGRAM_TRANSCRIPT_BACKEND=file, source IS configured, so
    telegram_inbound_source_not_configured should NOT be emitted.

    VAL-M15-M2-READINESS-REACTIVE-INBOUND-MISSING-004 (backend-configured variant)
    """
    monkeypatch.setenv("HAM_TELEGRAM_TRANSCRIPT_BACKEND", "file")
    monkeypatch.delenv("HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH", raising=False)
    monkeypatch.delenv("HAM_HERMES_HOME", raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)

    result = discover_telegram_inbound_once()
    assert result.status == "blocked"
    # Source IS configured (backend env is set), so NOT "not_configured"
    assert "telegram_inbound_source_not_configured" not in result.reasons


# ---------------------------------------------------------------------------
# VAL-M15-M2-READINESS-DECOUPLED-FROM-HERMES-001 (HTTP-level)
# ---------------------------------------------------------------------------


def test_telegram_status_readiness_decoupled_from_hermes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/social/providers/telegram/status returns overall_readiness='ready'
    when self-probe is ok and Hermes is absent.

    VAL-M15-M2-READINESS-DECOUPLED-FROM-HERMES-001
    """
    _disable_clerk(monkeypatch)
    _set_telegram_env(monkeypatch)
    _clear_hermes_env(monkeypatch)

    from datetime import UTC, datetime

    from src.ham.social_telegram_self_probe import _CACHE as probe_cache
    from src.ham.social_telegram_self_probe import TelegramSelfProbeResult

    # Seed the probe cache so no network call is made
    probe_cache.clear()
    now = datetime.now(UTC)
    import hashlib

    token = "synthetic-token-for-test"
    cache_key = hashlib.sha256(token.encode()).hexdigest()[:16]
    probe_cache[cache_key] = TelegramSelfProbeResult(
        state="ok",
        checked_at=now,
        error_code=None,
        bot_username_digest="abc123",
    )

    try:
        response = client.get("/api/social/providers/telegram/status")
        assert response.status_code == 200
        body = response.json()
        assert body["overall_readiness"] == "ready", (
            f"Expected overall_readiness='ready', got: {body['overall_readiness']}"
        )
        # readiness_reasons must not contain hermes_gateway_* codes
        hermes_codes = [r for r in body.get("readiness_reasons", []) if "hermes_gateway" in r]
        assert hermes_codes == [], (
            f"readiness_reasons contained Hermes gateway codes: {hermes_codes}"
        )
        # Hermes gateway block reports honestly
        assert body["hermes_gateway"]["provider_runtime_state"] == "unknown"
        # Self-probe state surfaced on response
        assert body["telegram_self_probe_state"] == "ok"
    finally:
        probe_cache.clear()


# ---------------------------------------------------------------------------
# VAL-M15-M2-CAPABILITIES-NEW-FIELDS-001
# ---------------------------------------------------------------------------


def test_capabilities_response_includes_new_m2_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/social/providers/telegram/capabilities returns the new M2 fields:
    telegram_readiness, telegram_self_probe_state, hermes_gateway_readiness.

    VAL-M15-M2-CAPABILITIES-NEW-FIELDS-001
    """
    _disable_clerk(monkeypatch)
    _set_telegram_env(monkeypatch)
    _clear_hermes_env(monkeypatch)

    import hashlib
    from datetime import UTC, datetime

    from src.ham.social_telegram_self_probe import _CACHE as probe_cache
    from src.ham.social_telegram_self_probe import TelegramSelfProbeResult

    # Seed the probe cache
    probe_cache.clear()
    now = datetime.now(UTC)
    token = "synthetic-token-for-test"
    cache_key = hashlib.sha256(token.encode()).hexdigest()[:16]
    probe_cache[cache_key] = TelegramSelfProbeResult(
        state="ok",
        checked_at=now,
        error_code=None,
        bot_username_digest="xyz",
    )

    try:
        response = client.get("/api/social/providers/telegram/capabilities")
        assert response.status_code == 200
        body = response.json()
        # New M2 fields must be present
        assert "telegram_readiness" in body, "Missing telegram_readiness in capabilities response"
        assert "telegram_self_probe_state" in body, (
            "Missing telegram_self_probe_state in capabilities response"
        )
        assert "hermes_gateway_readiness" in body, (
            "Missing hermes_gateway_readiness in capabilities response"
        )
        # Values are valid literals
        assert body["telegram_readiness"] in (
            "ready",
            "setup_required",
            "limited",
            "blocked",
            "unknown",
        )
        assert body["telegram_self_probe_state"] in ("ok", "not_ok", "unknown")
        assert body["hermes_gateway_readiness"] in (
            "ready",
            "not_configured",
            "limited",
            "blocked",
            "unknown",
        )
        # When Hermes is not configured, hermes_gateway_readiness must be not_configured
        assert body["hermes_gateway_readiness"] == "not_configured", (
            f"Expected not_configured when Hermes absent, got: {body['hermes_gateway_readiness']}"
        )
        # When probe is ok and all Telegram envs set, telegram_readiness must be ready
        assert body["telegram_readiness"] == "ready", (
            f"Expected telegram_readiness=ready when probe ok, got: {body['telegram_readiness']}"
        )
        assert body["telegram_self_probe_state"] == "ok"
        # Existing fields are unchanged
        assert "bot_token_present" in body
        assert "readiness" in body
        assert "hermes_gateway_runtime_state" in body
    finally:
        probe_cache.clear()


# ---------------------------------------------------------------------------
# Activity lane: self-probe gate checks
# ---------------------------------------------------------------------------


def test_activity_lane_self_probe_not_ok_emits_telegram_self_probe_not_ok() -> None:
    """When activity_requires_hermes_gateway=False and self-probe is not_ok,
    the activity lane emits telegram_self_probe_not_ok.
    """
    result = plan_telegram_activity_once(
        readiness="ready",
        gateway_runtime_state="unknown",
        activity_requires_hermes_gateway=False,
        telegram_self_probe_state="not_ok",
    )
    assert result.status == "blocked"
    assert "telegram_self_probe_not_ok" in result.reasons
    assert "telegram_gateway_not_connected" not in result.reasons


def test_activity_lane_self_probe_unknown_emits_telegram_self_probe_not_ok() -> None:
    """When activity_requires_hermes_gateway=False and self-probe is unknown,
    the activity lane emits telegram_self_probe_not_ok.
    """
    result = plan_telegram_activity_once(
        readiness="ready",
        gateway_runtime_state="connected",
        activity_requires_hermes_gateway=False,
        telegram_self_probe_state="unknown",
    )
    assert result.status == "blocked"
    assert "telegram_self_probe_not_ok" in result.reasons


def test_activity_lane_hermes_gate_skipped_when_activity_requires_hermes_false() -> None:
    """When activity_requires_hermes_gateway=False, Hermes disconnected state
    does NOT add telegram_gateway_not_connected to the activity lane reasons.
    """
    result = plan_telegram_activity_once(
        readiness="ready",
        gateway_runtime_state="disconnected",
        activity_requires_hermes_gateway=False,
        telegram_self_probe_state="ok",
    )
    # Self-probe ok → should NOT be blocked by gateway or probe
    assert "telegram_gateway_not_connected" not in result.reasons
    assert "telegram_self_probe_not_ok" not in result.reasons


# ---------------------------------------------------------------------------
# HamgomoonAutopilotConfig new fields
# ---------------------------------------------------------------------------


def test_autopilot_config_new_m2_fields_default() -> None:
    """HamgomoonAutopilotConfig defaults to activity_requires_hermes_gateway=False
    and telegram_self_probe_state='unknown'.

    VAL-M15-M2-READINESS-PROFILE-FLAG-005 (config variant)
    """
    cfg = HamgomoonAutopilotConfig()
    assert cfg.activity_requires_hermes_gateway is False
    assert cfg.telegram_self_probe_state == "unknown"


def test_autopilot_config_passes_probe_state_to_activity_runner() -> None:
    """HamgomoonAutopilotConfig.telegram_self_probe_state is propagated to the
    TelegramActivityRunConfig and from there to plan_telegram_activity_once.
    """
    captured: list[Any] = []

    import src.ham.social_telegram_activity_runner as runner_mod

    def spy_plan(**kwargs: Any) -> Any:
        captured.append(kwargs)
        from src.ham.social_telegram_activity import plan_telegram_activity_once as real

        return real(**kwargs)

    with patch.object(runner_mod, "plan_telegram_activity_once", side_effect=spy_plan):
        run_hamgomoon_autopilot_once(
            HamgomoonAutopilotConfig(
                dry_run=True,
                readiness="ready",
                gateway_runtime_state="connected",
                telegram_self_probe_state="ok",
                activity_requires_hermes_gateway=False,
            )
        )

    assert len(captured) >= 1
    assert captured[-1]["telegram_self_probe_state"] == "ok"
    assert captured[-1]["activity_requires_hermes_gateway"] is False


# ---------------------------------------------------------------------------
# Adapter new fields propagation
# ---------------------------------------------------------------------------


def test_adapter_reads_probe_state_from_status_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SocialAutonomyTelegramAdapter reads telegram_self_probe_state from
    _telegram_status_for_autonomy_tick and passes it to HamgomoonAutopilotConfig.
    """
    import src.api.social as social_mod
    from src.ham import social_telegram_autopilot
    from src.ham.social_autonomy.telegram_adapter import SocialAutonomyTelegramAdapter
    from src.ham.social_telegram_autopilot import HamgomoonAutopilotResult

    captured: list[Any] = []

    def spy(config: Any = None, **_kwargs: Any) -> HamgomoonAutopilotResult:
        captured.append(config)
        return HamgomoonAutopilotResult(
            status="blocked",
            dry_run=True,
            execution_allowed=False,
            mutation_attempted=False,
            lane_order=["reactive", "activity"],
            selected_lane=None,
            blocking_reasons=[],
            non_blocking_reasons=[],
            reasons=[],
            warnings=[],
        )

    monkeypatch.setattr(
        social_mod,
        "_telegram_status_for_autonomy_tick",
        lambda: SimpleNamespace(
            overall_readiness="ready",
            hermes_gateway=SimpleNamespace(provider_runtime_state="unknown"),
            telegram_self_probe_state="ok",
        ),
    )
    monkeypatch.setattr(social_telegram_autopilot, "run_hamgomoon_autopilot_once", spy)

    SocialAutonomyTelegramAdapter().dispatch({"action": "message"}, dry_run=True)

    assert len(captured) == 1
    assert captured[0].telegram_self_probe_state == "ok"
    assert captured[0].activity_requires_hermes_gateway is False


# ---------------------------------------------------------------------------
# Hermes-required path: adapter propagation test (M14 M1d variant)
# ---------------------------------------------------------------------------


def test_m14_m1d_propagation_adapter_still_passes_readiness_and_gateway_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The M14 M1d adapter still correctly propagates readiness and
    gateway_runtime_state to HamgomoonAutopilotConfig (byte-equal behavior
    for the fields those tests pin).

    VAL-M15-CROSS-SNAPSHOT-003 (compatibility check)
    """
    import src.api.social as social_mod
    from src.ham import social_telegram_autopilot
    from src.ham.social_autonomy.telegram_adapter import SocialAutonomyTelegramAdapter
    from src.ham.social_telegram_autopilot import HamgomoonAutopilotResult

    captured: list[Any] = []

    def spy(config: Any = None, **_kwargs: Any) -> HamgomoonAutopilotResult:
        captured.append(config)
        return HamgomoonAutopilotResult(
            status="blocked",
            dry_run=True,
            execution_allowed=False,
            mutation_attempted=False,
            lane_order=["reactive", "activity"],
            selected_lane=None,
            blocking_reasons=[],
            non_blocking_reasons=[],
            reasons=[],
            warnings=[],
        )

    monkeypatch.setattr(
        social_mod,
        "_telegram_status_for_autonomy_tick",
        lambda: SimpleNamespace(
            overall_readiness="ready",
            hermes_gateway=SimpleNamespace(provider_runtime_state="connected"),
        ),
    )
    monkeypatch.setattr(social_telegram_autopilot, "run_hamgomoon_autopilot_once", spy)

    SocialAutonomyTelegramAdapter().dispatch({"action": "message"}, dry_run=True)

    assert len(captured) == 1
    # These fields are still propagated (M14 M1d byte-equal check)
    assert captured[0].readiness == "ready"
    assert captured[0].gateway_runtime_state == "connected"
