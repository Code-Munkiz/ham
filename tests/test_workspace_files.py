from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_workspace_ham_root_list_write_read(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HAM_WORKSPACE_ROOT is honored; round-trip read under that root."""
    root = tmp_path / "wroot"
    root.mkdir()
    monkeypatch.setenv("HAM_WORKSPACE_ROOT", str(root))
    monkeypatch.delenv("HAM_WORKSPACE_FILES_ROOT", raising=False)

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
    p = root / "hello.txt"
    assert p.is_file() and p.read_text(encoding="utf-8") == "ok"

    r2 = client.get("/api/workspace/files?action=read&path=hello.txt")
    assert r2.status_code == 200
    body = r2.json()
    text = body.get("content") or body.get("text")
    assert text == "ok"


def test_workspace_files_root_legacy_fallback(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If HAM_WORKSPACE_ROOT is unset, HAM_WORKSPACE_FILES_ROOT still works."""
    root = tmp_path / "legacy"
    root.mkdir()
    monkeypatch.delenv("HAM_WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("HAM_WORKSPACE_FILES_ROOT", str(root))

    (root / "seed.txt").write_text("x", encoding="utf-8")
    r = client.get("/api/workspace/files?action=list")
    assert r.status_code == 200
    names = {e["name"] for e in r.json()["entries"] if e["type"] == "file"}
    assert "seed.txt" in names


def test_workspace_root_wins_over_legacy(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HAM_WORKSPACE_ROOT takes precedence over HAM_WORKSPACE_FILES_ROOT."""
    a = tmp_path / "primary"
    b = tmp_path / "secondary"
    a.mkdir()
    b.mkdir()
    (a / "a.txt").write_text("a", encoding="utf-8")
    (b / "b.txt").write_text("b", encoding="utf-8")
    monkeypatch.setenv("HAM_WORKSPACE_ROOT", str(a))
    monkeypatch.setenv("HAM_WORKSPACE_FILES_ROOT", str(b))
    r = client.get("/api/workspace/files?action=list")
    names = {e["name"] for e in r.json()["entries"] if e["type"] == "file"}
    assert "a.txt" in names
    assert "b.txt" not in names


def test_mkdir_rename_delete(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "mrd"
    root.mkdir()
    monkeypatch.setenv("HAM_WORKSPACE_ROOT", str(root))

    assert (
        client.post(
            "/api/workspace/files",
            content=json.dumps({"action": "mkdir", "path": "d1"}),
            headers={"content-type": "application/json"},
        ).status_code
        == 200
    )
    assert (root / "d1").is_dir()

    assert (
        client.post(
            "/api/workspace/files",
            content=json.dumps(
                {
                    "action": "write",
                    "path": "d1/inner.txt",
                    "content": "inner",
                }
            ),
            headers={"content-type": "application/json"},
        ).status_code
        == 200
    )
    assert (root / "d1" / "inner.txt").read_text() == "inner"

    assert (
        client.post(
            "/api/workspace/files",
            content=json.dumps(
                {
                    "action": "rename",
                    "from": "d1/inner.txt",
                    "to": "d1/renamed.txt",
                }
            ),
            headers={"content-type": "application/json"},
        ).status_code
        == 200
    )
    assert not (root / "d1" / "inner.txt").exists()
    assert (root / "d1" / "renamed.txt").read_text() == "inner"

    assert (
        client.post(
            "/api/workspace/files",
            content=json.dumps({"action": "delete", "path": "d1/renamed.txt"}),
            headers={"content-type": "application/json"},
        ).status_code
        == 200
    )
    assert not (root / "d1" / "renamed.txt").exists()


def test_path_traversal_read_rejected(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    monkeypatch.setenv("HAM_WORKSPACE_ROOT", str(root))

    r = client.get("/api/workspace/files?action=read&path=../outside.txt")
    assert r.status_code == 400
    detail = str(r.json().get("detail", ""))
    assert "escape" in detail.lower() or "workspace" in detail.lower()


def test_workspace_health(client: TestClient) -> None:
    r = client.get("/api/workspace/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert "workspaceRootConfigured" in body
    assert isinstance(body.get("features"), list) and "files" in body["features"]
