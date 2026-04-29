"""HERMES_GATEWAY_MODE=openrouter uses LiteLLM + OpenRouter for /api/chat adapter."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.integrations.nous_gateway_client import GatewayCallError, complete_chat_turn
from src.llm_client import stream_chat_messages_openrouter


def test_openrouter_mode_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    # Empty string overrides any OPENROUTER_API_KEY from .env loaded at import.
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    with pytest.raises(GatewayCallError) as ei:
        complete_chat_turn([{"role": "user", "content": "hi"}])
    # API key validation happens in stream_chat_messages_openrouter which raises CONFIG_ERROR
    assert ei.value.code in ("CONFIG_ERROR", "UPSTREAM_REJECTED")
    assert "OPENROUTER_API_KEY" in ei.value.message or "api" in ei.value.message.lower()


def test_openrouter_stream_rejects_poisoned_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "printf '%s' sk-or-v1-fake-key-0000000000000")
    with pytest.raises(RuntimeError, match="plausible"):
        next(stream_chat_messages_openrouter([{"role": "user", "content": "hi"}]))


def test_openrouter_mode_calls_litellm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    monkeypatch.setenv("DEFAULT_MODEL", "openai/gpt-4o-mini")

    def mock_completion(*args, **kwargs):
        assert kwargs.get("stream") is True
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "  Real reply  "
        yield chunk

    with patch("litellm.completion", side_effect=mock_completion) as mock_completion:
        out = complete_chat_turn([{"role": "user", "content": "hello"}])

    assert out == "Real reply"
    mock_completion.assert_called_once()
    call_kw = mock_completion.call_args.kwargs
    assert call_kw["model"] == "openrouter/openai/gpt-4o-mini"
    assert call_kw["messages"] == [{"role": "user", "content": "hello"}]
    assert "api.openrouter.ai" in call_kw["api_base"] or "openrouter" in call_kw["api_base"]
