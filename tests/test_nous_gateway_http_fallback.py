"""HTTP Hermes gateway: optional HAM_CHAT_FALLBACK_MODEL retry on overload responses."""
from __future__ import annotations

import copy
import json
from unittest.mock import patch
from typing import Any

import httpx
import pytest

from src.integrations.nous_gateway_client import GatewayCallError, complete_chat_turn


def _sse_line(content: str) -> str:
    payload = json.dumps({"choices": [{"delta": {"content": content}}]})
    return f"data: {payload}"


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


class _FakeHttpxClient:
    """Records model ids per stream() call; returns queued FakeStreamResp contexts."""

    def __init__(
        self,
        responses: list[tuple[int, list[str]] | BaseException],
        *,
        reset_monotonic_before_indices: frozenset[int] | None = None,
        monotonic_state: list[float] | None = None,
        captured_messages_snapshots: list[list[dict[str, Any]]] | None = None,
    ) -> None:
        self._responses = list(responses)
        self._i = 0
        self.models_seen: list[str] = []
        self._reset_mono_before = reset_monotonic_before_indices or frozenset()
        self._mono_state = monotonic_state
        self._captured_messages = captured_messages_snapshots

    def __enter__(self) -> _FakeHttpxClient:
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
        if self._captured_messages is not None:
            self._captured_messages.append(copy.deepcopy(json["messages"]))
        if self._i in self._reset_mono_before and self._mono_state is not None:
            self._mono_state[0] = 0.0
        self.models_seen.append(str(json["model"]))
        item = self._responses[self._i]
        self._i += 1
        if isinstance(item, BaseException):
            raise item
        status, lines = item
        return _FakeStreamResp(status, lines)


def test_http_retries_fallback_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://10.0.0.1:8642")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "minimax/minimax-m2.5:free")
    monkeypatch.setenv("HAM_CHAT_FALLBACK_MODEL", "qwen/qwen3.5-flash-02-23")

    fake = _FakeHttpxClient(
        [
            (429, []),
            (
                200,
                [_sse_line("fallback-"), _sse_line("ok"), "data: [DONE]"],
            ),
        ],
    )

    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        out = complete_chat_turn([{"role": "user", "content": "hi"}])

    assert out == "fallback-ok"
    assert fake.models_seen == [
        "minimax/minimax-m2.5:free",
        "qwen/qwen3.5-flash-02-23",
    ]


def test_http_no_fallback_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://10.0.0.1:8642")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "model-a")
    monkeypatch.delenv("HAM_CHAT_FALLBACK_MODEL", raising=False)

    fake = _FakeHttpxClient([(429, [])])

    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        with pytest.raises(GatewayCallError) as ei:
            complete_chat_turn([{"role": "user", "content": "hi"}])

    assert ei.value.code == "UPSTREAM_REJECTED"
    assert ei.value.http_status == 429
    assert fake.models_seen == ["model-a"]


def test_http_retries_fallback_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://10.0.0.1:8642")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "minimax/minimax-m2.5:free")
    monkeypatch.setenv("HAM_CHAT_FALLBACK_MODEL", "qwen/qwen3.5-flash-02-23")

    fake = _FakeHttpxClient(
        [
            httpx.ReadTimeout("primary stalled"),
            (
                200,
                [_sse_line("ok"), "data: [DONE]"],
            ),
        ],
    )

    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        out = complete_chat_turn([{"role": "user", "content": "hi"}])

    assert out == "ok"
    assert fake.models_seen == [
        "minimax/minimax-m2.5:free",
        "qwen/qwen3.5-flash-02-23",
    ]


def test_http_retries_fallback_on_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://10.0.0.1:8642")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "model-a")
    monkeypatch.setenv("HAM_CHAT_FALLBACK_MODEL", "model-b")

    fake = _FakeHttpxClient(
        [
            httpx.ConnectError("reset"),
            (
                200,
                [_sse_line("recovered"), "data: [DONE]"],
            ),
        ],
    )

    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        out = complete_chat_turn([{"role": "user", "content": "hi"}])

    assert out == "recovered"
    assert fake.models_seen == ["model-a", "model-b"]


def test_http_retries_fallback_on_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://10.0.0.1:8642")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "primary-m")
    monkeypatch.setenv("HAM_CHAT_FALLBACK_MODEL", "fallback-m")

    fake = _FakeHttpxClient(
        [
            (503, []),
            (
                200,
                [_sse_line("fb"), "data: [DONE]"],
            ),
        ],
    )

    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        out = complete_chat_turn([{"role": "user", "content": "hi"}])

    assert out == "fb"
    assert fake.models_seen == ["primary-m", "fallback-m"]


def test_http_no_fallback_when_fallback_same_as_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://10.0.0.1:8642")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "qwen/qwen3.5-flash-02-23")
    monkeypatch.setenv("HAM_CHAT_FALLBACK_MODEL", "qwen/qwen3.5-flash-02-23")

    fake = _FakeHttpxClient([(503, [])])

    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        with pytest.raises(GatewayCallError) as ei:
            complete_chat_turn([{"role": "user", "content": "hi"}])

    assert ei.value.http_status == 503
    assert fake.models_seen == ["qwen/qwen3.5-flash-02-23"]


def test_http_both_primary_and_fallback_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://10.0.0.1:8642")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "primary-m")
    monkeypatch.setenv("HAM_CHAT_FALLBACK_MODEL", "fallback-m")

    fake = _FakeHttpxClient([(503, []), (503, [])])

    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        with pytest.raises(GatewayCallError) as ei:
            complete_chat_turn([{"role": "user", "content": "hi"}])

    assert ei.value.http_status == 503
    assert fake.models_seen == ["primary-m", "fallback-m"]


def _sse_empty_delta() -> str:
    payload = json.dumps({"choices": [{"delta": {}}]})
    return f"data: {payload}"


def test_http_retries_fallback_on_stream_max_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wall-clock cap triggers fallback when the stream runs too long (no content chunks yet)."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://10.0.0.1:8642")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "primary-m")
    monkeypatch.setenv("HAM_CHAT_FALLBACK_MODEL", "fallback-m")
    monkeypatch.setenv("HAM_CHAT_HTTP_STREAM_MAX_SEC", "50")

    t = [0.0]

    def mono() -> float:
        t[0] += 45.0
        return t[0]

    monkeypatch.setattr("src.integrations.nous_gateway_client.time.monotonic", mono)

    # Empty deltas only: no assistant tokens until MAX_DURATION on the second SSE line.
    fake = _FakeHttpxClient(
        [
            (200, [_sse_empty_delta(), _sse_empty_delta()]),
            (200, [_sse_line("recovered")]),
        ],
        reset_monotonic_before_indices=frozenset({1}),
        monotonic_state=t,
    )

    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        out = complete_chat_turn([{"role": "user", "content": "hi"}])

    assert out == "recovered"
    assert fake.models_seen == ["primary-m", "fallback-m"]


def test_http_no_fallback_after_primary_emitted_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    """After at least one primary delta was streamed, do not switch models — re-raise."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://10.0.0.1:8642")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "primary-m")
    monkeypatch.setenv("HAM_CHAT_FALLBACK_MODEL", "fallback-m")

    def make_iter(**_kwargs: object):
        yield "partial-"
        raise GatewayCallError("STREAM_MAX_DURATION", "cap")

    with patch(
        "src.integrations.nous_gateway_client._iter_http_chat_completions",
        side_effect=make_iter,
    ):
        with pytest.raises(GatewayCallError) as ei:
            complete_chat_turn([{"role": "user", "content": "hi"}])

    assert ei.value.code == "STREAM_MAX_DURATION"


def test_http_no_fallback_on_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://10.0.0.1:8642")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "model-a")
    monkeypatch.setenv("HAM_CHAT_FALLBACK_MODEL", "model-b")

    fake = _FakeHttpxClient([(400, [])])

    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        with pytest.raises(GatewayCallError) as ei:
            complete_chat_turn([{"role": "user", "content": "hi"}])

    assert ei.value.http_status == 400
    assert fake.models_seen == ["model-a"]


def test_gateway_call_error_backward_compatible_http_status() -> None:
    err = GatewayCallError("UPSTREAM_REJECTED", "Gateway HTTP 500")
    assert err.http_status is None


def test_http_context_budget_sent_upstream_excludes_boilerplate_assistant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://10.0.0.1:8642")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "m1")
    monkeypatch.delenv("HAM_CHAT_FALLBACK_MODEL", raising=False)
    monkeypatch.setenv("HAM_HERMES_HTTP_CONTEXT_MAX_CHARS", "100000")

    boiler = (
        "The model gateway rejected the request. Try again or contact support if it continues."
    )
    history = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "prior"},
        {"role": "assistant", "content": boiler},
        {"role": "user", "content": "next"},
        {"role": "assistant", "content": boiler},
        {"role": "user", "content": "last"},
    ]
    snaps: list[list[dict[str, Any]]] = []

    fake = _FakeHttpxClient(
        [(200, [_sse_line("ok"), "data: [DONE]"])],
        captured_messages_snapshots=snaps,
    )

    with patch("src.integrations.nous_gateway_client.httpx.Client", return_value=fake):
        complete_chat_turn(history)

    assert len(snaps) == 1
    upstream_roles = [m.get("role") for m in snaps[0]]
    assert upstream_roles.count("assistant") == 0
    assert json.dumps(snaps[0]).count("model gateway rejected") == 0
