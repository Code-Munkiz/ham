from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.api.workspace_skills as workspace_skills
from src.api.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    workspace_skills.StatePath = None
    yield
    workspace_skills.StatePath = None


def test_catalog_list_custom_patch_delete(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "w"
    root.mkdir()
    monkeypatch.setenv("HAM_WORKSPACE_ROOT", str(root))
    workspace_skills.StatePath = None

    r = client.get("/api/workspace/skills/items")
    assert r.status_code == 200
    j = r.json()
    assert "skills" in j
    assert len(j["skills"]) >= 2
    assert any(s["id"] == "ham-local-docs" for s in j["skills"])

    c = client.post(
        "/api/workspace/skills/items",
        content=json.dumps({"name": "My skill", "description": "test"}),
        headers={"content-type": "application/json"},
    )
    assert c.status_code == 201
    sid = c.json()["id"]
    assert c.json()["installed"] is True
    assert c.json()["enabled"] is True

    p = client.patch(
        f"/api/workspace/skills/items/{sid}",
        content=json.dumps({"enabled": False, "config": "x=1"}),
        headers={"content-type": "application/json"},
    )
    assert p.status_code == 200
    assert p.json()["enabled"] is False
    assert p.json()["config"] == "x=1"

    bad = client.delete("/api/workspace/skills/items/ham-local-docs")
    assert bad.status_code == 400

    d = client.delete(f"/api/workspace/skills/items/{sid}")
    assert d.status_code == 204

    lq = client.get("/api/workspace/skills/items", params={"q": "documentation"})
    assert lq.status_code == 200
    assert any(x["id"] == "ham-local-docs" for x in lq.json()["skills"])
