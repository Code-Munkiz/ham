"""Context engine dashboard routes — project root validation and payloads."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.api.server import app


def _register_project(client: TestClient, *, name: str, root: Path) -> str:
    res = client.post(
        "/api/projects",
        json={"name": name, "root": str(root), "description": ""},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_project_context_engine_ok(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    with TestClient(app) as client:
        pid = _register_project(client, name="ctx-ok", root=root)
        res = client.get(f"/api/projects/{pid}/context-engine")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["cwd"] == str(root.resolve())


def test_project_context_engine_missing_root(tmp_path: Path) -> None:
    root = tmp_path / "gone"
    root.mkdir()
    with TestClient(app) as client:
        pid = _register_project(client, name="ctx-missing", root=root)
    root.rmdir()
    with TestClient(app) as client:
        res = client.get(f"/api/projects/{pid}/context-engine")
    assert res.status_code == 404, res.text
    body = res.json()
    assert body["detail"]["error"]["code"] == "PROJECT_ROOT_MISSING"


def test_project_context_engine_unknown_project() -> None:
    with TestClient(app) as client:
        res = client.get("/api/projects/not-a-real-uuid/context-engine")
    assert res.status_code == 404, res.text
