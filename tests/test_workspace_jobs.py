from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.api.workspace_jobs as workspace_jobs
from src.api.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_job_store_path() -> None:
    workspace_jobs.StatePath = None
    yield
    workspace_jobs.StatePath = None


def test_list_create_run_pause_resume_delete(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "w"
    root.mkdir()
    monkeypatch.setenv("HAM_WORKSPACE_ROOT", str(root))
    workspace_jobs.StatePath = None

    r = client.get("/api/workspace/jobs")
    assert r.status_code == 200
    assert r.json() == {"jobs": []}

    c = client.post(
        "/api/workspace/jobs",
        content=json.dumps({"name": "Nightly", "description": "sync"}),
        headers={"content-type": "application/json"},
    )
    assert c.status_code == 201
    job = c.json()
    jid = job["id"]
    assert job["name"] == "Nightly"
    assert job["status"] == "idle"
    assert job["runs"] == []

    r_list = client.get("/api/workspace/jobs", params={"q": "night"})
    assert r_list.status_code == 200
    assert len(r_list.json()["jobs"]) == 1

    run = client.post(f"/api/workspace/jobs/{jid}/run")
    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "idle"
    assert len(body["runs"]) == 1
    assert "HAM workspace job run" in body["runs"][0]["output"]

    p = client.post(f"/api/workspace/jobs/{jid}/pause")
    assert p.status_code == 200
    assert p.json()["status"] == "paused"

    bad_run = client.post(f"/api/workspace/jobs/{jid}/run")
    assert bad_run.status_code == 400

    res = client.post(f"/api/workspace/jobs/{jid}/resume")
    assert res.status_code == 200
    assert res.json()["status"] == "idle"

    pat = client.patch(
        f"/api/workspace/jobs/{jid}",
        content=json.dumps({"name": "Nightly v2", "description": "x"}),
        headers={"content-type": "application/json"},
    )
    assert pat.status_code == 200
    assert pat.json()["name"] == "Nightly v2"

    d = client.delete(f"/api/workspace/jobs/{jid}")
    assert d.status_code == 204
    assert client.get(f"/api/workspace/jobs/{jid}").status_code == 404
