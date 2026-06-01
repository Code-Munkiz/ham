from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from src.integrations.nous_gateway_client import (
    GatewayCallError,
    complete_artifact_turn,
    complete_chat_turn,
)

_BUNDLE = json.dumps({"status": "success", "files": {"src/App.tsx": "x"}})


def _sse_line(content: str) -> str:
    return f"data: {json.dumps({'choices': [{'delta': {'content': content}}]})}"


class _FakeStreamResp:
    def __init__(self, status_code: int, lines: list[str]) -> None:
        self.status_code = status_code
        self._lines = lines

    def __enter__(self) -> _FakeStreamResp:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def iter_lines(self) -> list[str]:
        return self._lines


class _RecordingClient:
    """Captures each POST payload and returns queued (status, lines) responses."""

    def __init__(self, responses: list[tuple[int, list[str]]]) -> None:
        self._responses = list(responses)
        self._i = 0
        self.payloads: list[dict[str, Any]] = []

    def __enter__(self) -> _RecordingClient:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def stream(
        self,
        _method: str,
        _url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> _FakeStreamResp:
        assert json is not None
        self.payloads.append(json)
        status, lines = self._responses[self._i]
        self._i += 1
        return _FakeStreamResp(status, lines)


def _http_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://10.0.0.1:8642")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "hermes-agent")
    monkeypatch.delenv("HERMES_BUILDER_MODEL", raising=False)


def test_artifact_turn_http_sends_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    _http_env(monkeypatch)
    fake = _RecordingClient([(200, [_sse_line(_BUNDLE), "data: [DONE]"])])
    diag: dict[str, Any] = {}
    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        out = complete_artifact_turn([{"role": "user", "content": "build"}], diag=diag)

    assert out == _BUNDLE
    assert fake.payloads[0]["response_format"] == {"type": "json_object"}
    assert diag["artifact_mode"] == "json_mode"
    assert diag["gateway_capability_detected"] == "response_format_supported"
    assert diag["model_channel"] == "default"


def test_conversational_chat_turn_does_not_send_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """User chat stays plain: the artifact-only response_format must not leak into chat."""
    _http_env(monkeypatch)
    fake = _RecordingClient([(200, [_sse_line("hello"), "data: [DONE]"])])
    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        out = complete_chat_turn([{"role": "user", "content": "hi"}])

    assert out == "hello"
    assert "response_format" not in fake.payloads[0]


def test_artifact_turn_falls_back_to_plain_on_422(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the gateway rejects the JSON-mode field (422), retry once without it."""
    _http_env(monkeypatch)
    fake = _RecordingClient(
        [
            (422, []),
            (200, [_sse_line(_BUNDLE), "data: [DONE]"]),
        ],
    )
    diag: dict[str, Any] = {}
    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        out = complete_artifact_turn([{"role": "user", "content": "build"}], diag=diag)

    assert out == _BUNDLE
    assert fake.payloads[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in fake.payloads[1]
    assert diag["artifact_mode"] == "plain_adapter"
    assert diag["gateway_capability_detected"] == "response_format_unsupported"


def test_artifact_turn_propagates_non_capability_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 503 is not a capability rejection: do not retry, surface the gateway error."""
    _http_env(monkeypatch)
    fake = _RecordingClient([(503, [])])
    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        with pytest.raises(GatewayCallError):
            complete_artifact_turn([{"role": "user", "content": "build"}])
    assert len(fake.payloads) == 1


def test_artifact_turn_uses_builder_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    _http_env(monkeypatch)
    monkeypatch.setenv("HERMES_BUILDER_MODEL", "hermes-builder-profile")
    fake = _RecordingClient([(200, [_sse_line(_BUNDLE), "data: [DONE]"])])
    diag: dict[str, Any] = {}
    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        complete_artifact_turn([{"role": "user", "content": "build"}], diag=diag)

    assert fake.payloads[0]["model"] == "hermes-builder-profile"
    assert diag["model_channel"] == "builder"


def test_artifact_turn_mock_mode_is_labeled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")
    monkeypatch.delenv("HERMES_GATEWAY_BASE_URL", raising=False)
    diag: dict[str, Any] = {}
    out = complete_artifact_turn([{"role": "user", "content": "build"}], diag=diag)
    assert "mock assistant reply" in out.lower()
    assert diag["artifact_mode"] == "mock"
