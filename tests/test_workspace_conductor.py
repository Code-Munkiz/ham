from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.api.workspace_conductor as workspace_conductor
from src.api.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_store_path() -> None:
    workspace_conductor.StatePath = None
    yield
    workspace_conductor.StatePath = None


def test_list_create_quick_run_settings(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "w"
    root.mkdir()
    monkeypatch.setenv("HAM_WORKSPACE_ROOT", str(root))
    workspace_conductor.StatePath = None

    r = client.get("/api/workspace/conductor/missions")
    assert r.status_code == 200
    assert r.json()["missions"] == []

    q = client.post(
        "/api/workspace/conductor/missions/quick",
        content=json.dumps({"quick": "research"}),
        headers={"content-type": "application/json"},
    )
    assert q.status_code == 201
    mid = q.json()["id"]
    assert q.json()["phase"] == "draft"
    assert q.json()["quickAction"] == "research"

    c = client.post(
        "/api/workspace/conductor/missions",
        content=json.dumps({"title": "T2", "body": "hello"}),
        headers={"content-type": "application/json"},
    )
    assert c.status_code == 201
    mid2 = c.json()["id"]

    run = client.post(f"/api/workspace/conductor/missions/{mid}/run")
    assert run.status_code == 200
    assert run.json()["phase"] == "completed"
    assert run.json()["costCents"] >= 25
    assert len(run.json()["outputs"]) >= 1

    hist = client.get("/api/workspace/conductor/missions", params={"historyOnly": True})
    assert hist.status_code == 200
    ids = {m["id"] for m in hist.json()["missions"]}
    assert mid in ids
    assert mid2 not in ids

    ap = client.post(
        f"/api/workspace/conductor/missions/{mid2}/output",
        content=json.dumps({"line": "log line"}),
        headers={"content-type": "application/json"},
    )
    assert ap.status_code == 200
    assert any("log line" in x["line"] for x in ap.json()["outputs"])

    gs = client.get("/api/workspace/conductor/settings")
    assert gs.status_code == 200
    assert "budgetCents" in gs.json()["settings"]

    ps = client.patch(
        "/api/workspace/conductor/settings",
        content=json.dumps({"budgetCents": 5000, "notes": "ok"}),
        headers={"content-type": "application/json"},
    )
    assert ps.status_code == 200
    assert ps.json()["settings"]["budgetCents"] == 5000

    d = client.delete(f"/api/workspace/conductor/missions/{mid2}")
    assert d.status_code == 204

