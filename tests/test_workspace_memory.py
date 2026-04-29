from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.api.workspace_memory as workspace_memory
from src.api.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    workspace_memory.StatePath = None
    yield
    workspace_memory.StatePath = None


def test_list_create_patch_archive_delete_search(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "w"
    root.mkdir()
    monkeypatch.setenv("HAM_WORKSPACE_ROOT", str(root))
    workspace_memory.StatePath = None

    r = client.get("/api/workspace/memory/items")
    assert r.status_code == 200
    assert r.json() == {"items": []}

    c = client.post(
        "/api/workspace/memory/items",
        content=json.dumps(
            {"title": "Alpha note", "body": "hello", "tags": ["a", "b"], "kind": "note"}
        ),
        headers={"content-type": "application/json"},
    )
    assert c.status_code == 201
    mid = c.json()["id"]
    assert c.json()["title"] == "Alpha note"
    assert c.json()["kind"] == "note"
    assert c.json()["archived"] is False

    pref = client.post(
        "/api/workspace/memory/items",
        content=json.dumps(
            {
                "title": "Style",
                "body": "prefs",
                "tags": ["ui"],
                "kind": "preference",
            }
        ),
        headers={"content-type": "application/json"},
    )
    assert pref.status_code == 201
    pid = pref.json()["id"]

    lq = client.get("/api/workspace/memory/items", params={"q": "style"})
    assert lq.status_code == 200
    assert len(lq.json()["items"]) == 1

    p = client.patch(
        f"/api/workspace/memory/items/{mid}",
        content=json.dumps({"archived": True, "body": "updated"}),
        headers={"content-type": "application/json"},
    )
    assert p.status_code == 200
    assert p.json()["archived"] is True

    active = client.get("/api/workspace/memory/items", params={"archived": False})
    assert active.status_code == 200
    assert len(active.json()["items"]) == 1
    assert active.json()["items"][0]["id"] == pid

    arch = client.get("/api/workspace/memory/items", params={"archived": True})
    assert arch.status_code == 200
    assert len(arch.json()["items"]) == 1
    assert arch.json()["items"][0]["id"] == mid

    d = client.delete(f"/api/workspace/memory/items/{pid}")
    assert d.status_code == 204
    assert client.get(f"/api/workspace/memory/items/{pid}").status_code == 404
