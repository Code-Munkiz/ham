"""Tests for readiness and gateway_runtime_state propagation through the Telegram adapter.

These tests verify that ``SocialAutonomyTelegramAdapter.dispatch`` correctly
reads the canonical Telegram status via ``_telegram_status_response()`` and
propagates the real ``readiness`` and ``gateway_runtime_state`` values into the
``HamgomoonAutopilotConfig`` it constructs, rather than hard-coding pessimistic
defaults.  They also verify the graceful failure-tolerant path (exception, None,
or partial response) that preserves safe defaults without crashing dispatch.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.ham.social_telegram_autopilot import HamgomoonAutopilotResult


def _blocked_autopilot_result(**overrides: Any) -> HamgomoonAutopilotResult:
    """Return a minimal valid ``HamgomoonAutopilotResult`` for spy callbacks."""
    payload: dict[str, Any] = {
        "status": "blocked",
        "dry_run": True,
        "execution_allowed": False,
        "mutation_attempted": False,
        "lane_order": ["reactive", "activity"],
        "selected_lane": None,
        "blocking_reasons": [],
        "non_blocking_reasons": [],
        "reasons": [],
        "warnings": [],
    }
    payload.update(overrides)
    return HamgomoonAutopilotResult(**payload)


def _make_status(overall_readiness: str, provider_runtime_state: str) -> SimpleNamespace:
    """Build a minimal status namespace matching ``SocialMessagingProviderStatusResponse``."""
    return SimpleNamespace(
        overall_readiness=overall_readiness,
        hermes_gateway=SimpleNamespace(provider_runtime_state=provider_runtime_state),
    )


def test_happy_path_ready_connected_propagates_to_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When _telegram_status_response returns ready/connected, those exact values
    must be passed to HamgomoonAutopilotConfig (not the bare defaults)."""
    import src.api.social as social_mod
    from src.ham import social_telegram_autopilot
    from src.ham.social_autonomy.telegram_adapter import SocialAutonomyTelegramAdapter

    captured: list[Any] = []

    def spy(config: Any = None, **_kwargs: Any) -> HamgomoonAutopilotResult:
        captured.append(config)
        return _blocked_autopilot_result()

    monkeypatch.setattr(
        social_mod, "_telegram_status_response", lambda: _make_status("ready", "connected")
    )
    monkeypatch.setattr(social_telegram_autopilot, "run_hamgomoon_autopilot_once", spy)

    SocialAutonomyTelegramAdapter().dispatch({"action": "message"}, dry_run=True)

    assert len(captured) == 1
    assert captured[0].readiness == "ready"
    assert captured[0].gateway_runtime_state == "connected"


def test_setup_required_path_preserves_pessimistic_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When _telegram_status_response returns setup_required/unknown, those values
    must be forwarded verbatim — no silent rewriting to 'ready'."""
    import src.api.social as social_mod
    from src.ham import social_telegram_autopilot
    from src.ham.social_autonomy.telegram_adapter import SocialAutonomyTelegramAdapter

    captured: list[Any] = []

    def spy(config: Any = None, **_kwargs: Any) -> HamgomoonAutopilotResult:
        captured.append(config)
        return _blocked_autopilot_result()

    monkeypatch.setattr(
        social_mod,
        "_telegram_status_response",
        lambda: _make_status("setup_required", "unknown"),
    )
    monkeypatch.setattr(social_telegram_autopilot, "run_hamgomoon_autopilot_once", spy)

    SocialAutonomyTelegramAdapter().dispatch({"action": "message"}, dry_run=True)

    assert len(captured) == 1
    assert captured[0].readiness == "setup_required"
    assert captured[0].gateway_runtime_state == "unknown"


def test_status_helper_raises_falls_back_to_defaults_without_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When _telegram_status_response raises, dispatch must NOT propagate the
    exception and must fall back to safe defaults (setup_required / unknown)."""
    import src.api.social as social_mod
    from src.ham import social_telegram_autopilot
    from src.ham.social_autonomy.telegram_adapter import SocialAutonomyTelegramAdapter

    captured: list[Any] = []

    def spy(config: Any = None, **_kwargs: Any) -> HamgomoonAutopilotResult:
        captured.append(config)
        return _blocked_autopilot_result()

    def raise_on_call() -> None:
        raise RuntimeError("status helper unavailable")

    monkeypatch.setattr(social_mod, "_telegram_status_response", raise_on_call)
    monkeypatch.setattr(social_telegram_autopilot, "run_hamgomoon_autopilot_once", spy)

    # Must not raise
    SocialAutonomyTelegramAdapter().dispatch({"action": "message"}, dry_run=True)

    assert len(captured) == 1
    assert captured[0].readiness == "setup_required"
    assert captured[0].gateway_runtime_state == "unknown"


def test_status_helper_returns_none_preserves_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When _telegram_status_response returns None, defaults must be preserved."""
    import src.api.social as social_mod
    from src.ham import social_telegram_autopilot
    from src.ham.social_autonomy.telegram_adapter import SocialAutonomyTelegramAdapter

    captured: list[Any] = []

    def spy(config: Any = None, **_kwargs: Any) -> HamgomoonAutopilotResult:
        captured.append(config)
        return _blocked_autopilot_result()

    monkeypatch.setattr(social_mod, "_telegram_status_response", lambda: None)
    monkeypatch.setattr(social_telegram_autopilot, "run_hamgomoon_autopilot_once", spy)

    SocialAutonomyTelegramAdapter().dispatch({"action": "message"}, dry_run=True)

    assert len(captured) == 1
    assert captured[0].readiness == "setup_required"
    assert captured[0].gateway_runtime_state == "unknown"


def test_status_helper_returns_partial_uses_real_value_for_present_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When _telegram_status_response returns a partial object (hermes_gateway
    exists but has no provider_runtime_state attribute), the present field must
    be propagated and the missing field must fall back to its default."""
    import src.api.social as social_mod
    from src.ham import social_telegram_autopilot
    from src.ham.social_autonomy.telegram_adapter import SocialAutonomyTelegramAdapter

    captured: list[Any] = []

    def spy(config: Any = None, **_kwargs: Any) -> HamgomoonAutopilotResult:
        captured.append(config)
        return _blocked_autopilot_result()

    # Partial: overall_readiness is present but hermes_gateway lacks
    # provider_runtime_state (simulates an incomplete status payload).
    partial_status = SimpleNamespace(
        overall_readiness="ready",
        hermes_gateway=SimpleNamespace(),  # no provider_runtime_state attribute
    )
    monkeypatch.setattr(social_mod, "_telegram_status_response", lambda: partial_status)
    monkeypatch.setattr(social_telegram_autopilot, "run_hamgomoon_autopilot_once", spy)

    SocialAutonomyTelegramAdapter().dispatch({"action": "message"}, dry_run=True)

    assert len(captured) == 1
    assert captured[0].readiness == "ready"  # real value for present field
    assert captured[0].gateway_runtime_state == "unknown"  # default for missing field
