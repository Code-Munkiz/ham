"""HERMES_GATEWAY_MODE=openrouter uses LiteLLM + OpenRouter for /api/chat adapter."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.integrations.nous_gateway_client import GatewayCallError, complete_chat_turn


def test_openrouter_mode_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(GatewayCallError) as ei:
        complete_chat_turn([{"role": "user", "content": "hi"}])
    assert ei.value.code == "CONFIG_ERROR"
    assert "OPENROUTER_API_KEY" in ei.value.message


def test_openrouter_mode_calls_litellm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("DEFAULT_MODEL", "openai/gpt-4o-mini")

    fake_msg = MagicMock()
    fake_msg.content = "  Real reply  "
    fake_choice = MagicMock()
    fake_choice.message = fake_msg
    fake_resp = MagicMock()
    fake_resp.choices = [fake_choice]

    with patch("litellm.completion", return_value=fake_resp) as mock_completion:
        out = complete_chat_turn([{"role": "user", "content": "hello"}])

    assert out == "Real reply"
    mock_completion.assert_called_once()
    call_kw = mock_completion.call_args.kwargs
    assert call_kw["model"] == "openrouter/openai/gpt-4o-mini"
    assert call_kw["messages"] == [{"role": "user", "content": "hello"}]
    assert "api.openrouter.ai" in call_kw["api_base"] or "openrouter" in call_kw["api_base"]
