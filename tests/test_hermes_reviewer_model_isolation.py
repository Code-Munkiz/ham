"""VAL-LANE-010 — HermesReviewer / swarm_agency critic path ignores HAM_CHAT_CONVERSATIONAL_MODEL.

`HermesReviewer` (via `src.llm_client.get_llm_client`) resolves models through
`resolve_openrouter_model_name()` — the non-`_for_chat` variant. The
conversational env var is read only in `src/api/chat.py` and never reaches
this code path.
"""
from __future__ import annotations

import pytest


_CONV_SENTINEL = "openrouter/sentinel-conv:free"
_OR_TEST_KEY = "sk-or-v1-hamtests-only-fake-key-000000000"


def test_hermes_reviewer_ignores_conversational_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_llm_client used by HermesReviewer resolves DEFAULT_MODEL, not the conv env."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", _CONV_SENTINEL)
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "guard-gateway:free")
    monkeypatch.setenv("DEFAULT_MODEL", "guard-default:free")
    monkeypatch.setenv("OPENROUTER_API_KEY", _OR_TEST_KEY)

    from src.llm_client import (
        get_llm_client,
        resolve_openrouter_model_name,
    )

    client = get_llm_client()
    model_used = getattr(client, "model", None) or getattr(client, "_model", None)
    assert model_used == "openrouter/guard-default:free"
    assert model_used != _CONV_SENTINEL
    assert _CONV_SENTINEL not in str(model_used)

    # The bare resolver used by HermesReviewer / swarm_agency must also ignore the conv env.
    assert resolve_openrouter_model_name() == "openrouter/guard-default:free"


def test_hermes_reviewer_evaluate_does_not_consume_conversational_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HermesReviewer.evaluate routes prompts through the non-chat LLM client only."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", _CONV_SENTINEL)
    monkeypatch.setenv("DEFAULT_MODEL", "guard-default:free")
    monkeypatch.setenv("OPENROUTER_API_KEY", _OR_TEST_KEY)

    seen: list[str] = []

    class _StubClient:
        model = "openrouter/guard-default:free"

        def call(self, prompt: str) -> str:
            seen.append(prompt)
            return '{"ok": true, "confidence": "high", "notes": []}'

    monkeypatch.setattr("src.llm_client.get_llm_client", lambda: _StubClient())

    from src.hermes_feedback import HermesReviewer

    reviewer = HermesReviewer()
    result = reviewer.evaluate("def x(): return 1", context="unit test")
    assert isinstance(result, dict)
    # No prompt the reviewer constructed should contain the conv env name or value.
    for prompt in seen:
        assert "HAM_CHAT_CONVERSATIONAL_MODEL" not in prompt
        assert _CONV_SENTINEL not in prompt
