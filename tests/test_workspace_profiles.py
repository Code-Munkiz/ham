from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.api.workspace_profiles as workspace_profiles
from src.api.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    workspace_profiles.StatePath = None
    yield
    workspace_profiles.StatePath = None


def test_list_create_set_default_delete(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "w"
    root.mkdir()
    monkeypatch.setenv("HAM_WORKSPACE_ROOT", str(root))
    workspace_profiles.StatePath = None

    r = client.get("/api/workspace/profiles")
    assert r.status_code == 200
    assert r.json() == {"profiles": [], "defaultProfileId": None}

    c = client.post(
        "/api/workspace/profiles",
        content=json.dumps(
            {
                "name": "A",
                "emoji": "🦾",
                "model": "m1",
                "systemPrompt": "hello",
            }
        ),
        headers={"content-type": "application/json"},
    )
    assert c.status_code == 201
    pid = c.json()["id"]
    assert c.json()["isDefault"] is True
    assert c.json()["emoji"] == "🦾"

    c2 = client.post(
        "/api/workspace/profiles",
        content=json.dumps(
            {
                "name": "B",
                "emoji": "🤖",
                "model": "m2",
                "systemPrompt": "",
            }
        ),
        headers={"content-type": "application/json"},
    )
    assert c2.status_code == 201
    pid2 = c2.json()["id"]
    assert c2.json()["isDefault"] is False

    sd = client.post(f"/api/workspace/profiles/{pid2}/set-default")
    assert sd.status_code == 200
    assert sd.json()["defaultProfileId"] == pid2

    ls = client.get("/api/workspace/profiles", params={"q": "A"})
    assert ls.status_code == 200
    assert len(ls.json()["profiles"]) == 1

    pat = client.patch(
        f"/api/workspace/profiles/{pid}",
        content=json.dumps({"name": "A2", "systemPrompt": "p2"}),
        headers={"content-type": "application/json"},
    )
    assert pat.status_code == 200
    assert pat.json()["name"] == "A2"
    assert pat.json()["isDefault"] is False

    d = client.delete(f"/api/workspace/profiles/{pid2}")
    assert d.status_code == 204
    g = client.get("/api/workspace/profiles")
    assert g.status_code == 200
    # Remaining profile becomes default
    assert g.json()["defaultProfileId"] == pid

    d2 = client.delete(f"/api/workspace/profiles/{pid}")
    assert d2.status_code == 204
    g2 = client.get("/api/workspace/profiles")
    assert g2.json() == {"profiles": [], "defaultProfileId": None}
