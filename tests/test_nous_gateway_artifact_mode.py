from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from src.integrations.nous_gateway_client import (
    GatewayCallError,
    _artifact_timeout_sec,
    complete_artifact_turn,
    complete_chat_turn,
)

_BUNDLE = json.dumps({"status": "success", "files": {"src/App.tsx": "x"}})


def _sse_line(content: str) -> str:
    return f"data: {json.dumps({'choices': [{'delta': {'content': content}}]})}"


def _completion_body(content: str) -> dict[str, Any]:
    return {"choices": [{"message": {"content": content}}]}


class _PostResp:
    """Fake non-streaming response (one-shot JSON body)."""

    def __init__(self, status_code: int, *, body: Any = None, bad_json: bool = False) -> None:
        self.status_code = status_code
        self._body = body
        self._bad_json = bad_json

    def json(self) -> Any:
        if self._bad_json:
            raise json.JSONDecodeError("not json", "", 0)
        return self._body


class _StreamResp:
    """Fake streaming SSE response."""

    def __init__(self, status_code: int, lines: list[str]) -> None:
        self.status_code = status_code
        self._lines = lines

    def __enter__(self) -> _StreamResp:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def iter_lines(self) -> list[str]:
        return self._lines


class _Client:
    """Dual fake httpx client: serves non-streaming .post and streaming .stream from queues."""

    def __init__(
        self,
        *,
        post: list[_PostResp] | None = None,
        stream: list[_StreamResp] | None = None,
    ) -> None:
        self._post = list(post or [])
        self._stream = list(stream or [])
        self.post_payloads: list[dict[str, Any]] = []
        self.stream_payloads: list[dict[str, Any]] = []

    def __enter__(self) -> _Client:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def post(
        self,
        _url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> _PostResp:
        assert json is not None
        self.post_payloads.append(json)
        return self._post.pop(0)

    def stream(
        self,
        _method: str,
        _url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> _StreamResp:
        assert json is not None
        self.stream_payloads.append(json)
        return self._stream.pop(0)


def _http_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://10.0.0.1:8642")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "hermes-agent")
    monkeypatch.delenv("HERMES_BUILDER_MODEL", raising=False)
    monkeypatch.delenv("HERMES_ARTIFACT_STREAM", raising=False)
    monkeypatch.delenv("HERMES_ARTIFACT_TIMEOUT_SEC", raising=False)


def test_artifact_turn_prefers_non_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    """Artifact mode requests one blocking completion (stream=false), not SSE."""
    _http_env(monkeypatch)
    fake = _Client(post=[_PostResp(200, body=_completion_body(_BUNDLE))])
    diag: dict[str, Any] = {}
    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        out = complete_artifact_turn([{"role": "user", "content": "build"}], diag=diag)

    assert out == _BUNDLE
    assert fake.post_payloads[0]["stream"] is False
    assert fake.post_payloads[0]["response_format"] == {"type": "json_object"}
    assert fake.stream_payloads == []  # streaming transport not used
    assert diag["artifact_mode"] == "json_mode"
    assert diag["artifact_transport"] == "non_streaming"
    assert diag["gateway_capability_detected"] == "response_format_supported"
    assert diag["model_channel"] == "default"
    assert "elapsed_ms" in diag


def test_conversational_chat_turn_streams_without_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """User chat stays streaming and plain: no non-streaming post, no artifact response_format."""
    _http_env(monkeypatch)
    fake = _Client(stream=[_StreamResp(200, [_sse_line("hello"), "data: [DONE]"])])
    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        out = complete_chat_turn([{"role": "user", "content": "hi"}])

    assert out == "hello"
    assert fake.stream_payloads[0]["stream"] is True
    assert "response_format" not in fake.stream_payloads[0]
    assert fake.post_payloads == []  # chat never uses the non-streaming artifact transport


def test_artifact_turn_falls_back_to_plain_on_422(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the gateway rejects the JSON-mode field (422), retry once without it (still non-streaming)."""
    _http_env(monkeypatch)
    fake = _Client(
        post=[
            _PostResp(422, body=None),
            _PostResp(200, body=_completion_body(_BUNDLE)),
        ],
    )
    diag: dict[str, Any] = {}
    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        out = complete_artifact_turn([{"role": "user", "content": "build"}], diag=diag)

    assert out == _BUNDLE
    assert fake.post_payloads[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in fake.post_payloads[1]
    assert diag["artifact_mode"] == "plain_adapter"
    assert diag["artifact_transport"] == "non_streaming"
    assert diag["gateway_capability_detected"] == "response_format_unsupported"


def test_artifact_turn_propagates_non_capability_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 503 is not a capability rejection: do not retry, surface the gateway error."""
    _http_env(monkeypatch)
    fake = _Client(post=[_PostResp(503, body=None)])
    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        with pytest.raises(GatewayCallError):
            complete_artifact_turn([{"role": "user", "content": "build"}])
    assert len(fake.post_payloads) == 1


def test_artifact_turn_uses_builder_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    _http_env(monkeypatch)
    monkeypatch.setenv("HERMES_BUILDER_MODEL", "hermes-builder-profile")
    fake = _Client(post=[_PostResp(200, body=_completion_body(_BUNDLE))])
    diag: dict[str, Any] = {}
    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        complete_artifact_turn([{"role": "user", "content": "build"}], diag=diag)

    assert fake.post_payloads[0]["model"] == "hermes-builder-profile"
    assert diag["model_channel"] == "builder"


def test_artifact_turn_mock_mode_is_labeled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")
    monkeypatch.delenv("HERMES_GATEWAY_BASE_URL", raising=False)
    diag: dict[str, Any] = {}
    out = complete_artifact_turn([{"role": "user", "content": "build"}], diag=diag)
    assert "mock assistant reply" in out.lower()
    assert diag["artifact_mode"] == "mock"
    assert diag["artifact_transport"] == "mock"


def test_artifact_turn_falls_back_to_streaming_when_non_streaming_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the gateway can't return a one-shot JSON body, fall back to streaming with the artifact budget."""
    _http_env(monkeypatch)
    fake = _Client(
        post=[_PostResp(200, bad_json=True)],  # SSE/non-JSON body -> NON_STREAMING_UNSUPPORTED
        stream=[_StreamResp(200, [_sse_line(_BUNDLE), "data: [DONE]"])],
    )
    diag: dict[str, Any] = {}
    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        out = complete_artifact_turn([{"role": "user", "content": "build"}], diag=diag)

    assert out == _BUNDLE
    assert len(fake.post_payloads) == 1  # tried non-streaming once
    assert fake.stream_payloads[0]["stream"] is True  # then streamed
    assert fake.stream_payloads[0]["response_format"] == {"type": "json_object"}
    assert diag["artifact_transport"] == "streaming"
    assert diag["artifact_mode"] == "json_mode"


def test_artifact_turn_opt_in_streaming_skips_non_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    """HERMES_ARTIFACT_STREAM=1 forces the streaming transport with the artifact budget."""
    _http_env(monkeypatch)
    monkeypatch.setenv("HERMES_ARTIFACT_STREAM", "1")
    fake = _Client(stream=[_StreamResp(200, [_sse_line(_BUNDLE), "data: [DONE]"])])
    diag: dict[str, Any] = {}
    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        out = complete_artifact_turn([{"role": "user", "content": "build"}], diag=diag)

    assert out == _BUNDLE
    assert fake.post_payloads == []  # non-streaming skipped
    assert fake.stream_payloads[0]["stream"] is True
    assert diag["artifact_transport"] == "streaming"


def test_artifact_streaming_maps_stream_max_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    """The streaming transport's wall-clock cap surfaces as STREAM_MAX_DURATION."""
    _http_env(monkeypatch)
    monkeypatch.setenv("HERMES_ARTIFACT_STREAM", "1")
    monkeypatch.setenv("HERMES_ARTIFACT_TIMEOUT_SEC", "30")

    counter = {"n": 0}

    def _fake_monotonic() -> float:
        counter["n"] += 1
        return 0.0 if counter["n"] <= 2 else 100_000.0

    monkeypatch.setattr(
        "src.integrations.nous_gateway_client.time.monotonic", _fake_monotonic
    )
    fake = _Client(stream=[_StreamResp(200, [_sse_line("partial"), "data: [DONE]"])])
    diag: dict[str, Any] = {}
    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        with pytest.raises(GatewayCallError) as excinfo:
            complete_artifact_turn([{"role": "user", "content": "build"}], diag=diag)

    assert excinfo.value.code == "STREAM_MAX_DURATION"
    assert diag["artifact_transport"] == "streaming"


def test_artifact_timeout_sec_clamps_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_ARTIFACT_TIMEOUT_SEC", "5")
    assert _artifact_timeout_sec() == 30.0  # clamped up to floor
    monkeypatch.setenv("HERMES_ARTIFACT_TIMEOUT_SEC", "9999")
    assert _artifact_timeout_sec() == 600.0  # clamped down to ceiling
    monkeypatch.setenv("HERMES_ARTIFACT_TIMEOUT_SEC", "240")
    assert _artifact_timeout_sec() == 240.0
    monkeypatch.setenv("HERMES_ARTIFACT_TIMEOUT_SEC", "not-a-number")
    assert _artifact_timeout_sec() == 300.0  # invalid -> default
    monkeypatch.delenv("HERMES_ARTIFACT_TIMEOUT_SEC", raising=False)
    assert _artifact_timeout_sec() == 300.0  # unset -> default
