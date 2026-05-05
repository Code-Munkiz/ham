"""GET /api/chat/context-meters — safe aggregates, no message bodies."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)


@pytest.fixture
def mock_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


def _create_session() -> str:
    r = client.post("/api/chat/sessions")
    assert r.status_code == 200
    return r.json()["session_id"]


def _append_turn(session_id: str, role: str, content: str) -> None:
    r = client.post(
        f"/api/chat/sessions/{session_id}/turns",
        json={"turns": [{"role": role, "content": content}]},
    )
    assert r.status_code in (200, 204), r.text


class TestContextMetersEndpoint:
    def test_disabled_when_flag_off(self, mock_gateway: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HAM_CONTEXT_METERS", "0")
        sid = _create_session()
        r = client.get("/api/chat/context-meters", params={"session_id": sid})
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is False
        assert body["this_turn"] is None

    def test_requires_session(self, mock_gateway: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HAM_CONTEXT_METERS", raising=False)
        r = client.get("/api/chat/context-meters", params={"session_id": "nope-not-real"})
        assert r.status_code == 404

    def test_response_has_no_message_contents(self, mock_gateway: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HAM_CONTEXT_METERS", raising=False)
        sid = _create_session()
        secret = "super-secret-user-message-content-xyz"
        _append_turn(sid, "user", secret)
        r = client.get("/api/chat/context-meters", params={"session_id": sid, "model_id": "openrouter:default"})
        assert r.status_code == 200
        raw = r.text
        assert secret not in raw

    def test_thread_ratio_uses_char_length_not_turn_count(
        self,
        mock_gateway: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("HAM_CONTEXT_METERS", raising=False)
        sid = _create_session()
        _append_turn(sid, "user", "a" * 1000)
        r = client.get(
            "/api/chat/context-meters",
            params={"session_id": sid, "model_id": "openrouter:default"},
        )
        assert r.status_code == 200
        th = r.json().get("thread")
        assert th is not None
        assert th["approx_transcript_chars"] >= 1000

    def test_color_thresholds(self) -> None:
        from src.ham.chat_context_meters import meters_color_for_ratio

        assert meters_color_for_ratio(0.2) == "green"
        assert meters_color_for_ratio(0.70) == "amber"
        assert meters_color_for_ratio(0.90) == "red"

    def test_unknown_model_uses_conservative_default(self, mock_gateway: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HAM_CONTEXT_METERS", raising=False)
        sid = _create_session()
        _append_turn(sid, "user", "hi")
        r = client.get(
            "/api/chat/context-meters",
            params={"session_id": sid, "model_id": "unknown-model-zzzzzz"},
        )
        assert r.status_code == 200
        tt = r.json().get("this_turn")
        assert tt is not None
        assert tt["limit"] > 0

    def test_workspace_source_label_present_when_computed(
        self,
        mock_gateway: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("HAM_CONTEXT_METERS", raising=False)
        sid = _create_session()
        r = client.get("/api/chat/context-meters", params={"session_id": sid})
        assert r.status_code == 200
        ws = r.json().get("workspace")
        if ws is not None:
            assert ws.get("source") in ("local", "cloud", "unavailable")
