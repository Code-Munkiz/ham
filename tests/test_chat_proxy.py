"""HAM /api/chat proxy and session behavior (gateway mocked)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.integrations.nous_gateway_client import GatewayCallError

client = TestClient(app)


def test_root_is_not_404_json() -> None:
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data.get("service") == "HAM API"
    assert data.get("status") == "/api/status"


def test_post_chat_prepends_system_prompt_for_llm(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list] = {}

    def capture(messages: list, **_kwargs) -> str:
        captured["messages"] = messages
        return "stub-assistant"

    monkeypatch.setattr("src.api.chat.complete_chat_turn", capture)
    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert res.status_code == 200, res.text
    msgs = captured.get("messages") or []
    assert msgs and msgs[0].get("role") == "system"
    assert "Ham" in (msgs[0].get("content") or "")
    assert msgs[1] == {"role": "user", "content": "hi"}
    # Client-visible transcript has no system row
    body = res.json()["messages"]
    assert all(m["role"] != "system" for m in body)


@pytest.fixture
def mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


def test_post_chat_creates_session_and_assistant_roundtrip(mock_mode: None) -> None:
    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["session_id"]
    assert len(data["messages"]) == 2
    assert data["messages"][0] == {"role": "user", "content": "hello"}
    assert data["messages"][1]["role"] == "assistant"
    assert "Mock assistant reply" in data["messages"][1]["content"]


def test_post_chat_continues_session(mock_mode: None) -> None:
    r1 = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "first"}]},
    )
    assert r1.status_code == 200
    sid = r1.json()["session_id"]

    r2 = client.post(
        "/api/chat",
        json={
            "session_id": sid,
            "messages": [{"role": "user", "content": "second"}],
        },
    )
    assert r2.status_code == 200
    msgs = r2.json()["messages"]
    assert len(msgs) == 4
    assert msgs[0]["content"] == "first"
    assert msgs[1]["role"] == "assistant"
    assert msgs[2]["content"] == "second"
    assert msgs[3]["role"] == "assistant"


def test_post_chat_unknown_session() -> None:
    res = client.post(
        "/api/chat",
        json={
            "session_id": "00000000-0000-4000-8000-000000000001",
            "messages": [{"role": "user", "content": "x"}],
        },
    )
    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "SESSION_NOT_FOUND"


def test_post_chat_validation_empty_messages(mock_mode: None) -> None:
    res = client.post("/api/chat", json={"messages": []})
    assert res.status_code == 422


def test_post_chat_gateway_error_mapped(mock_mode: None) -> None:
    with patch(
        "src.api.chat.complete_chat_turn",
        side_effect=GatewayCallError("UPSTREAM_REJECTED", "gateway said no"),
    ):
        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert res.status_code == 502
    detail = res.json()["detail"]
    assert detail["error"]["code"] == "UPSTREAM_REJECTED"
    assert "gateway" in detail["error"]["message"].lower()


def test_post_chat_invalid_request_from_gateway(mock_mode: None) -> None:
    with patch(
        "src.api.chat.complete_chat_turn",
        side_effect=GatewayCallError("INVALID_REQUEST", "empty history"),
    ):
        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert res.status_code == 400
