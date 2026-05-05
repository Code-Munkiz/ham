"""Unit tests for workspace tool API key HTTP validation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.ham.workspace_tool_key_validation import validate_anthropic_api_key


@patch("src.ham.workspace_tool_key_validation.httpx.get")
def test_validate_anthropic_models_list_200(mock_get: MagicMock) -> None:
    mock_get.return_value = MagicMock(status_code=200)
    key = "sk-ant-api03-" + "a" * 40
    assert validate_anthropic_api_key(key) is True
    mock_get.assert_called_once()
    args, kwargs = mock_get.call_args
    assert args[0] == "https://api.anthropic.com/v1/models"
    assert kwargs["params"] == {"limit": 1}


@patch("src.ham.workspace_tool_key_validation.httpx.get")
def test_validate_anthropic_models_list_401(mock_get: MagicMock) -> None:
    mock_get.return_value = MagicMock(status_code=401)
    assert validate_anthropic_api_key("sk-ant-api03-" + "b" * 40) is False


def test_validate_anthropic_rejects_wrong_prefix() -> None:
    with patch("src.ham.workspace_tool_key_validation.httpx.get") as mock_get:
        assert validate_anthropic_api_key("sk-or-v1-not-anthropic") is False
        mock_get.assert_not_called()


def test_validate_anthropic_rejects_too_short() -> None:
    with patch("src.ham.workspace_tool_key_validation.httpx.get") as mock_get:
        assert validate_anthropic_api_key("sk-ant-short") is False
        mock_get.assert_not_called()
