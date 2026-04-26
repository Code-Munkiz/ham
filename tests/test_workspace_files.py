from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_workspace_files_list_write_read_roundtrip(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "wfs"
    root.mkdir()
    monkeypatch.setenv("HAM_WORKSPACE_FILES_ROOT", str(root))

    r = client.get("/api/workspace/files?action=list")
    assert r.status_code == 200
    data = r.json()
    assert "entries" in data

    w = client.post(
        "/api/workspace/files",
        content=json.dumps({"action": "write", "path": "hello.txt", "content": "ok"}),
        headers={"content-type": "application/json"},
    )
    assert w.status_code == 200

    r2 = client.get("/api/workspace/files?action=read&path=hello.txt")
    assert r2.status_code == 200
    body = r2.json()
    text = body.get("content") or body.get("text")
    assert text == "ok"
