"""Routing precedence tests for the HAM_CHAT_CONVERSATIONAL_MODEL lane (VAL-ROUTE-001..015).

All scenarios run against the FastAPI TestClient with `litellm.completion`,
`stream_chat_messages_openrouter`, and `httpx.Client.stream` mocked as needed.
No live LLM / gateway calls.
"""
from __future__ import annotations

import json
import threading
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api import chat as chat_mod
from src.api.server import app
from src.integrations.nous_gateway_client import GatewayCallError

client = TestClient(app)


CONV_SLUG = "openrouter/anthropic/claude-3.5-haiku"
OR_TEST_KEY = "sk-or-v1-hamtests-only-fake-key-000000000"


@pytest.fixture(autouse=True)
def _reset_conversational_notice_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_mod, "_chat_conversational_model_notice_emitted", False, raising=True)
    monkeypatch.setattr(
        chat_mod,
        "_CHAT_CONVERSATIONAL_MODEL_NOTICE_LOCK",
        threading.Lock(),
        raising=True,
    )


def _stub_litellm_chunk(text: str) -> Any:
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta.content = text
    return chunk


def _stub_completion_factory(seen: list[dict[str, Any]], reply: str = "ok"):
    def _stub(*args: Any, **kwargs: Any):
        seen.append(dict(kwargs))
        yield _stub_litellm_chunk(reply)

    return _stub


@pytest.fixture
def or_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", OR_TEST_KEY)
    monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    monkeypatch.delenv("HERMES_GATEWAY_MODEL", raising=False)
    monkeypatch.delenv("HAM_CHAT_PREMIUM_MODEL", raising=False)
    monkeypatch.delenv("DEFAULT_MODEL", raising=False)


def _parse_ndjson(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_post_chat_uses_conversational_env_when_set_and_no_model_id(
    or_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-ROUTE-001 — env-derived model id reaches litellm.completion."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    seen: list[dict[str, Any]] = []
    with patch("litellm.completion", side_effect=_stub_completion_factory(seen)):
        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert res.status_code == 200, res.text
    assert seen, "litellm.completion was not invoked"
    assert seen[0].get("model") == CONV_SLUG


def test_post_chat_stream_uses_conversational_env_when_set_and_no_model_id(
    or_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-ROUTE-002 — same as VAL-ROUTE-001 for the streaming endpoint."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    seen: list[dict[str, Any]] = []
    with patch("litellm.completion", side_effect=_stub_completion_factory(seen)):
        res = client.post(
            "/api/chat/stream",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert res.status_code == 200, res.text
    assert len(seen) == 1
    assert seen[0].get("model") == CONV_SLUG


def test_conversational_env_does_not_mutate_body_model_id(
    or_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-ROUTE-003 — env-only fallback never coerces body.model_id; no 422."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    seen: list[dict[str, Any]] = []
    with patch("litellm.completion", side_effect=_stub_completion_factory(seen)):
        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hi"}], "model_id": None},
        )
    assert res.status_code == 200, res.text
    assert "MODEL_SELECTION_REQUIRES_OPENROUTER" not in res.text


def test_post_chat_explicit_model_id_beats_conversational_env(
    or_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-ROUTE-004 — explicit body.model_id wins over the conversational env on REST."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "minimax/minimax-m2.5:free")
    seen: list[dict[str, Any]] = []
    with patch("litellm.completion", side_effect=_stub_completion_factory(seen)):
        res = client.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "model_id": "openrouter:default",
            },
        )
    assert res.status_code == 200, res.text
    assert seen
    model_used = seen[0].get("model")
    assert model_used != CONV_SLUG
    assert model_used == "openrouter/minimax/minimax-m2.5:free"


def test_post_chat_stream_explicit_model_id_beats_conversational_env(
    or_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-ROUTE-005 — explicit body.model_id wins over the conversational env on stream."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "minimax/minimax-m2.5:free")
    seen: list[dict[str, Any]] = []
    with patch("litellm.completion", side_effect=_stub_completion_factory(seen)):
        res = client.post(
            "/api/chat/stream",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "model_id": "openrouter:default",
            },
        )
    assert res.status_code == 200, res.text
    assert seen and seen[0].get("model") == "openrouter/minimax/minimax-m2.5:free"


@pytest.mark.parametrize("value", ["   ", "\t", "\n  "])
def test_conversational_env_whitespace_only_is_treated_as_unset(
    or_mode: None, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """VAL-ROUTE-007 — whitespace-only env routes exactly like unset env."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", value)
    monkeypatch.setenv("DEFAULT_MODEL", "openai/gpt-4o-mini")
    seen: list[dict[str, Any]] = []
    with patch("litellm.completion", side_effect=_stub_completion_factory(seen)):
        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert res.status_code == 200, res.text
    assert seen and seen[0].get("model") == "openrouter/openai/gpt-4o-mini"


@pytest.mark.parametrize(
    ("conv_env", "gateway_model", "default_model", "expected"),
    [
        (CONV_SLUG, "minimax/minimax-m2.5:free", "openai/gpt-4o-mini", CONV_SLUG),
        (None, "minimax/minimax-m2.5:free", "openai/gpt-4o-mini", "openrouter/minimax/minimax-m2.5:free"),
        (None, None, "openai/gpt-4o-mini", "openrouter/openai/gpt-4o-mini"),
    ],
)
def test_chat_model_precedence_ordering(
    or_mode: None,
    monkeypatch: pytest.MonkeyPatch,
    conv_env: str | None,
    gateway_model: str | None,
    default_model: str,
    expected: str,
) -> None:
    """VAL-ROUTE-008 — four-signal precedence: conv-env > HERMES_GATEWAY_MODEL > DEFAULT_MODEL."""
    if conv_env is None:
        monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    else:
        monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", conv_env)
    if gateway_model is None:
        monkeypatch.delenv("HERMES_GATEWAY_MODEL", raising=False)
    else:
        monkeypatch.setenv("HERMES_GATEWAY_MODEL", gateway_model)
    monkeypatch.setenv("DEFAULT_MODEL", default_model)

    seen: list[dict[str, Any]] = []
    with patch("litellm.completion", side_effect=_stub_completion_factory(seen)):
        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert res.status_code == 200, res.text
    assert seen and seen[0].get("model") == expected


def test_chat_model_precedence_ordering_explicit_model_id_top(
    or_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-ROUTE-008 (top tier) — explicit body.model_id outranks everything else."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "minimax/minimax-m2.5:free")
    monkeypatch.setenv("DEFAULT_MODEL", "openai/gpt-4o-mini")
    seen: list[dict[str, Any]] = []
    with patch("litellm.completion", side_effect=_stub_completion_factory(seen)):
        res = client.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "model_id": "openrouter:default",
            },
        )
    assert res.status_code == 200, res.text
    assert seen and seen[0].get("model") == "openrouter/minimax/minimax-m2.5:free"


def test_http_hermes_branch_ignores_conversational_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-ROUTE-009 — HTTP-Hermes payload `model` stays HERMES_GATEWAY_MODEL when env is set."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://10.0.0.99:8642")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "hermes-agent")
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    monkeypatch.delenv("HAM_CHAT_FALLBACK_MODEL", raising=False)

    captured_models: list[str] = []

    class _FakeStreamResp:
        def __init__(self) -> None:
            self.status_code = 200

        def __enter__(self) -> "_FakeStreamResp":
            return self

        def __exit__(self, *_a: object) -> None:
            return None

        def iter_lines(self) -> list[str]:
            payload = json.dumps({"choices": [{"delta": {"content": "ok"}}]})
            return [f"data: {payload}", "data: [DONE]"]

    class _FakeClient:
        def __enter__(self) -> "_FakeClient":
            return self

        def __exit__(self, *_a: object) -> None:
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
            captured_models.append(str(json["model"]))
            return _FakeStreamResp()

    with patch(
        "src.integrations.nous_gateway_client.httpx.Client",
        return_value=_FakeClient(),
    ):
        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert res.status_code == 200, res.text
    assert captured_models == ["hermes-agent"]
    assert CONV_SLUG not in captured_models


def test_mock_mode_explicit_model_id_still_returns_422_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-ROUTE-010 — env-set lane does not alter mock-mode 422 for explicit model picks."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    res = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "model_id": "openrouter:default",
        },
    )
    assert res.status_code == 422, res.text
    body = res.json()
    assert body["detail"]["error"]["code"] == "MODEL_SELECTION_REQUIRES_OPENROUTER"


def test_mock_mode_with_conversational_env_set_no_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-ROUTE-011 — env-set lane alone never produces a 422 in mock mode."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["messages"][-1]["role"] == "assistant"


def test_vision_text_fallback_retry_reuses_conversational_override(
    or_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-ROUTE-012 — the single vision text-fallback retry passes the same env model_override."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    monkeypatch.setenv("HAM_CHAT_VISION_UPSTREAM_TEXT_FALLBACK", "1")

    overrides_seen: list[str | None] = []
    call_count = {"n": 0}

    def fake_stream(messages, **kwargs):  # type: ignore[no-untyped-def]
        overrides_seen.append(kwargs.get("openrouter_model_override"))
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise GatewayCallError("UPSTREAM_REJECTED", "vision rejected", http_status=400)
        yield "ok"

    monkeypatch.setattr("src.api.chat.stream_chat_turn", fake_stream)

    image_data = "data:image/png;base64,AAAA"
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "h": "ham_chat_user_v1",
                        "text": "describe this",
                        "images": [
                            {
                                "name": "tiny.png",
                                "mime": "image/png",
                                "data_url": image_data,
                            }
                        ],
                    },
                }
            ]
        },
    )
    assert res.status_code == 200, res.text
    if len(overrides_seen) >= 2:
        assert overrides_seen[0] == overrides_seen[1] == CONV_SLUG
    else:
        assert overrides_seen and overrides_seen[0] == CONV_SLUG


def test_post_chat_tier_premium_explicit_beats_conversational_env(
    or_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-ROUTE-013 — body.model_id="tier:premium" picks the premium-resolved slug, not the env."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    monkeypatch.setenv("HAM_CHAT_PREMIUM_MODEL", "anthropic/claude-3-opus")
    seen: list[dict[str, Any]] = []
    with patch("litellm.completion", side_effect=_stub_completion_factory(seen)):
        res = client.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "model_id": "tier:premium",
            },
        )
    assert res.status_code == 200, res.text
    model_used = seen[0].get("model")
    assert model_used != CONV_SLUG
    assert model_used == "openrouter/anthropic/claude-3-opus"


def test_post_chat_stream_tier_premium_explicit_beats_conversational_env(
    or_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-ROUTE-013 (stream counterpart) — tier:premium wins over the env on streaming."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    monkeypatch.setenv("HAM_CHAT_PREMIUM_MODEL", "anthropic/claude-3-opus")
    seen: list[dict[str, Any]] = []
    with patch("litellm.completion", side_effect=_stub_completion_factory(seen)):
        res = client.post(
            "/api/chat/stream",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "model_id": "tier:premium",
            },
        )
    assert res.status_code == 200, res.text
    assert seen and seen[0].get("model") == "openrouter/anthropic/claude-3-opus"


def _frame_shape(frame: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    type_key = "type" if "type" in frame else "event"
    return (str(frame.get(type_key) or ""), tuple(sorted(frame.keys())))


def test_ndjson_frame_schema_invariant_under_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-ROUTE-014 — NDJSON frame schema (ordered types + key sets) is identical with/without env."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")
    monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    baseline_res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "hi stable"}]},
    )
    assert baseline_res.status_code == 200, baseline_res.text
    baseline_frames = _parse_ndjson(baseline_res.text)

    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    env_set_res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "hi stable"}]},
    )
    assert env_set_res.status_code == 200, env_set_res.text
    env_set_frames = _parse_ndjson(env_set_res.text)

    assert [_frame_shape(f) for f in baseline_frames] == [_frame_shape(f) for f in env_set_frames]


def test_openrouter_missing_key_with_env_set_still_fails_same_way(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-ROUTE-015 — env-set lane never masks a missing OPENROUTER_API_KEY in openrouter mode."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert res.status_code == 200, res.text
    frames = _parse_ndjson(res.text)
    done = frames[-1]
    assert done.get("type") == "done"
    gateway_err = done.get("gateway_error") or {}
    assert gateway_err.get("code") in {"CONFIG_ERROR", "UPSTREAM_REJECTED"}
    assistant_msg = done["messages"][-1]["content"]
    assert "HAM_CHAT_CONVERSATIONAL_MODEL" not in assistant_msg


def test_litellm_path_no_automatic_retry_under_env_set(
    or_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-FALLBACK-010 (paired with VAL-ROUTE) — litellm.completion is called once even when raising."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    monkeypatch.setenv("HAM_CHAT_FALLBACK_MODEL", "openrouter/never-used:free")

    raises = MagicMock(side_effect=RuntimeError("model rejected"))
    with patch("litellm.completion", raises):
        res = client.post(
            "/api/chat/stream",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert res.status_code == 200, res.text
    assert raises.call_count == 1
    for call in raises.call_args_list:
        used_model = call.kwargs.get("model")
        assert used_model != "openrouter/never-used:free"
