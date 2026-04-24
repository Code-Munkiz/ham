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


def test_launch_accepts_mission_handling_merged_response(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.api.cursor_settings as cs

    posted: list[dict] = []

    def fake_post(path: str, *, api_key: str, json_body: dict):
        assert path == "/v0/agents"
        assert "mission_handling" not in json_body
        assert "ham_mission_handling" not in json_body
        posted.append(json_body)
        m = MagicMock()
        m.status_code = 200
        m.json = lambda: {"id": "cm_test_agent", "status": "CREATING"}
        return m

    monkeypatch.setattr(cs, "_cursor_post", fake_post)
    r = client.post(
        "/api/cursor/agents/launch",
        json={
            "prompt_text": "do the thing",
            "repository": "https://github.com/foo/bar",
            "mission_handling": "managed",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "cm_test_agent"
    assert data["ham_mission_handling"] == "managed"
    assert posted[0] == {
        "prompt": {"text": "do the thing"},
        "source": {"repository": "https://github.com/foo/bar"},
        "model": "default",
    }


def test_launch_omits_mission_handling_compatible(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.api.cursor_settings as cs

    posted: list[dict] = []

    def fake_post(path: str, *, api_key: str, json_body: dict):
        posted.append(json_body)
        m = MagicMock()
        m.status_code = 200
        m.json = lambda: {"id": "cm_legacy"}
        return m

    monkeypatch.setattr(cs, "_cursor_post", fake_post)
    r = client.post(
        "/api/cursor/agents/launch",
        json={
            "prompt_text": "x",
            "repository": "https://github.com/foo/bar",
        },
    )
    assert r.status_code == 200
    assert r.json()["id"] == "cm_legacy"
    assert r.json()["ham_mission_handling"] is None
    assert "mission_handling" not in posted[0]


def test_launch_rejects_invalid_mission_handling(client: TestClient) -> None:
    r = client.post(
        "/api/cursor/agents/launch",
        json={
            "prompt_text": "x",
            "repository": "https://github.com/foo/bar",
            "mission_handling": "bogus",
        },
    )
    assert r.status_code == 422


def test_post_sync_404_when_no_managed_mission(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import src.api.cursor_settings as cs

    monkeypatch.setenv("HAM_MANAGED_MISSIONS_DIR", str(tmp_path))

    def fake_get(path: str, *, api_key: str):
        m = MagicMock()
        m.status_code = 200
        m.json = lambda: {"id": "bc_orphan", "status": "RUNNING"}
        return m

    monkeypatch.setattr(cs, "_cursor_get", fake_get)
    r = client.post("/api/cursor/agents/bc_orphan/sync")
    assert r.status_code == 404
    body = r.json()
    assert body["detail"]["error"]["code"] == "MANAGED_MISSION_NOT_FOUND"


def test_post_sync_returns_managed_mission_json(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from src.persistence.control_plane_run import utc_now_iso
    from src.persistence.managed_mission import ManagedMission, ManagedMissionStore, new_mission_registry_id

    import src.api.cursor_settings as cs

    monkeypatch.setenv("HAM_MANAGED_MISSIONS_DIR", str(tmp_path))

    n = utc_now_iso()
    st = ManagedMissionStore()
    mid = new_mission_registry_id()
    m = ManagedMission(
        mission_registry_id=mid,
        cursor_agent_id="bc_sync_ok",
        control_plane_ham_run_id=None,
        mission_handling="managed",
        uplink_id=None,
        repo_key="o/r",
        mission_lifecycle="open",
        cursor_status_last_observed="CREATING",
        status_reason_last_observed="init",
        created_at=n,
        updated_at=n,
        last_server_observed_at=n,
    )
    st.save(m)

    def fake_get(path: str, *, api_key: str):
        assert "/bc_sync_ok" in path
        mock = MagicMock()
        mock.status_code = 200
        mock.json = lambda: {"id": "bc_sync_ok", "status": "FINISHED"}
        return mock

    monkeypatch.setattr(cs, "_cursor_get", fake_get)
    r = client.post("/api/cursor/agents/bc_sync_ok/sync")
    assert r.status_code == 200
    j = r.json()
    assert j["kind"] == "managed_mission"
    assert j["cursor_agent_id"] == "bc_sync_ok"
    assert j["mission_lifecycle"] in ("succeeded", "open", "failed", "archived")
