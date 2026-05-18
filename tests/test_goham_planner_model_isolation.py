"""VAL-LANE-009 — `src/api/goham_planner.py` ignores HAM_CHAT_CONVERSATIONAL_MODEL.

The planner resolves its model via `resolve_openrouter_model_name_for_chat()`
(which consults HERMES_GATEWAY_MODEL → DEFAULT_MODEL) — never the
conversational env var.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


_CONV_SENTINEL = "openrouter/sentinel-conv:free"
_GATEWAY_GUARD = "guard-gateway:free"
_OR_TEST_KEY = "sk-or-v1-hamtests-only-fake-key-000000000"


def test_goham_planner_ignores_conversational_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The planner's litellm.completion call uses HERMES_GATEWAY_MODEL, not the conv env."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", _CONV_SENTINEL)
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", _GATEWAY_GUARD)
    monkeypatch.setenv("OPENROUTER_API_KEY", _OR_TEST_KEY)
    monkeypatch.delenv("GOHAM_LLM_PLANNER_MODEL", raising=False)

    seen: list[dict] = []

    def _capture(*args, **kwargs):  # type: ignore[no-untyped-def]
        seen.append(dict(kwargs))
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = '{"type": "done", "reason": "ok", "confidence": 0.5}'
        return resp

    from src.api import goham_planner

    with patch("litellm.completion", side_effect=_capture):
        goham_planner._call_planner_model("plan something")

    assert seen, "litellm.completion was not invoked"
    model_used = str(seen[0].get("model") or "")
    assert model_used == f"openrouter/{_GATEWAY_GUARD}"
    assert model_used != _CONV_SENTINEL
    assert _CONV_SENTINEL not in model_used


def test_goham_planner_uses_default_when_gateway_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With HERMES_GATEWAY_MODEL unset, planner falls back to DEFAULT_MODEL — not the conv env."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", _CONV_SENTINEL)
    monkeypatch.delenv("HERMES_GATEWAY_MODEL", raising=False)
    monkeypatch.setenv("DEFAULT_MODEL", "guard-default:free")
    monkeypatch.setenv("OPENROUTER_API_KEY", _OR_TEST_KEY)
    monkeypatch.delenv("GOHAM_LLM_PLANNER_MODEL", raising=False)

    seen: list[dict] = []

    def _capture(*args, **kwargs):  # type: ignore[no-untyped-def]
        seen.append(dict(kwargs))
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = '{"type": "done", "reason": "ok", "confidence": 0.5}'
        return resp

    from src.api import goham_planner

    with patch("litellm.completion", side_effect=_capture):
        goham_planner._call_planner_model("plan something")

    assert seen, "litellm.completion was not invoked"
    model_used = str(seen[0].get("model") or "")
    assert model_used == "openrouter/guard-default:free"
    assert _CONV_SENTINEL not in model_used
