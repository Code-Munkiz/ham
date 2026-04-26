from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.api.workspace_operations as workspace_operations
from src.api.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_store_path() -> None:
    workspace_operations.StatePath = None
    yield
    workspace_operations.StatePath = None


def test_agents_play_pause_delete_scheduled_settings(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "w"
    root.mkdir()
    monkeypatch.setenv("HAM_WORKSPACE_ROOT", str(root))
    workspace_operations.StatePath = None

    r = client.get("/api/workspace/operations/agents")
    assert r.status_code == 200
    assert r.json()["agents"] == []

    c = client.post(
        "/api/workspace/operations/agents",
        content=json.dumps({"name": "Alpha", "model": "m1"}),
        headers={"content-type": "application/json"},
    )
    assert c.status_code == 201
    aid = c.json()["id"]

    p = client.post(f"/api/workspace/operations/agents/{aid}/play")
    assert p.status_code == 200
    assert p.json()["status"] == "active"
    assert len(p.json()["outputs"]) >= 1

    pa = client.post(f"/api/workspace/operations/agents/{aid}/pause")
    assert pa.status_code == 200
    assert pa.json()["status"] == "paused"

    pat = client.patch(
        f"/api/workspace/operations/agents/{aid}",
        content=json.dumps({"name": "Alpha2", "cronEnabled": True, "cronExpr": "0 0 * * *"}),
        headers={"content-type": "application/json"},
    )
    assert pat.status_code == 200
    assert pat.json()["name"] == "Alpha2"
    assert pat.json()["cronEnabled"] is True

    sj = client.post(
        "/api/workspace/operations/scheduled-jobs",
        content=json.dumps({"name": "nightly", "cronExpr": "15 * * * *"}),
        headers={"content-type": "application/json"},
    )
    assert sj.status_code == 201
    jid = sj.json()["id"]

    ls = client.get("/api/workspace/operations/scheduled-jobs")
    assert ls.status_code == 200
    assert len(ls.json()["scheduledJobs"]) == 1

    gs = client.get("/api/workspace/operations/settings")
    assert gs.status_code == 200
    ps = client.patch(
        "/api/workspace/operations/settings",
        content=json.dumps({"outputsRetention": 10, "notes": "x"}),
        headers={"content-type": "application/json"},
    )
    assert ps.status_code == 200
    assert ps.json()["settings"]["outputsRetention"] == 10

    c_emoji = client.post(
        "/api/workspace/operations/agents",
        content=json.dumps(
            {"name": "Emoji", "model": "m2", "emoji": "🦾", "systemPrompt": "Hello world"}
        ),
        headers={"content-type": "application/json"},
    )
    assert c_emoji.status_code == 201
    assert c_emoji.json()["emoji"] == "🦾"
    assert "Hello" in c_emoji.json()["systemPrompt"]
    aid2 = c_emoji.json()["id"]

    msg = client.post(
        f"/api/workspace/operations/agents/{aid2}/message",
        content=json.dumps({"message": "ping"}),
        headers={"content-type": "application/json"},
    )
    assert msg.status_code == 200
    lines = [o["line"] for o in msg.json()["outputs"]]
    assert any("You: ping" in ln for ln in lines)

    d2 = client.delete(f"/api/workspace/operations/agents/{aid2}")
    assert d2.status_code == 204

    d = client.delete(f"/api/workspace/operations/agents/{aid}")
    assert d.status_code == 204

    dj = client.delete(f"/api/workspace/operations/scheduled-jobs/{jid}")
    assert dj.status_code == 204
