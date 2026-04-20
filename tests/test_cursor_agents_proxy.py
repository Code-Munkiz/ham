"""Ham proxies for Cursor Cloud Agents GET agent, conversation, followup."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.server import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    import pathlib

    from src.persistence import cursor_credentials as cc

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    cc.save_cursor_api_key("test-key-for-proxy")
    return TestClient(app)


def test_get_agent_requires_key(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    import pathlib

    from src.persistence import cursor_credentials as cc

    home = tmp_path / "home2"
    home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    if (home / ".ham" / "cursor_credentials.json").exists():
        (home / ".ham" / "cursor_credentials.json").unlink()
    cc.clear_saved_cursor_api_key()
    c = TestClient(app)
    r = c.get("/api/cursor/agents/bc_test")
    assert r.status_code == 400
    assert "No Cursor API key" in r.json()["detail"]


def test_get_agent_proxies_json(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.api.cursor_settings as cs

    def fake_get(path: str, *, api_key: str):
        assert path == "/v0/agents/bc_abc"
        assert api_key == "test-key-for-proxy"
        m = MagicMock()
        m.status_code = 200
        m.json = lambda: {"id": "bc_abc", "status": "RUNNING"}
        return m

    monkeypatch.setattr(cs, "_cursor_get", fake_get)
    r = client.get("/api/cursor/agents/bc_abc")
    assert r.status_code == 200
    assert r.json()["status"] == "RUNNING"


def test_get_conversation_proxies(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.api.cursor_settings as cs

    def fake_get(path: str, *, api_key: str):
        assert "/conversation" in path
        m = MagicMock()
        m.status_code = 200
        m.json = lambda: {"messages": []}
        return m

    monkeypatch.setattr(cs, "_cursor_get", fake_get)
    r = client.get("/api/cursor/agents/x/conversation")
    assert r.status_code == 200
    assert r.json() == {"messages": []}


def test_post_followup_proxies(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.api.cursor_settings as cs

    captured: dict = {}

    def fake_post(path: str, *, api_key: str, json_body: dict):
        captured["path"] = path
        captured["body"] = json_body
        m = MagicMock()
        m.status_code = 200
        m.json = lambda: {"ok": True}
        return m

    monkeypatch.setattr(cs, "_cursor_post", fake_post)
    r = client.post(
        "/api/cursor/agents/bc_z/followup",
        json={"prompt_text": "Continue with tests"},
    )
    assert r.status_code == 200
    assert captured["path"] == "/v0/agents/bc_z/followup"
    assert captured["body"] == {"prompt": {"text": "Continue with tests"}}
