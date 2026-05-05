"""Context engine dashboard routes — project root validation and payloads."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
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


def test_workspace_context_snapshot_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "ws_repo"
    root.mkdir()
    monkeypatch.delenv("HAM_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("HAM_WORKSPACE_FILES_ROOT", raising=False)
    monkeypatch.setenv("HAM_WORKSPACE_ROOT", str(root))
    with TestClient(app) as client:
        res = client.get("/api/workspace/context-snapshot")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["context_source"] == "local"
    assert body["cwd"] == str(root.resolve())


def test_workspace_context_snapshot_uses_configured_root_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "configured"
    root.mkdir()
    other = tmp_path / "other_cwd"
    other.mkdir()
    monkeypatch.delenv("HAM_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("HAM_WORKSPACE_FILES_ROOT", raising=False)
    monkeypatch.setenv("HAM_WORKSPACE_ROOT", str(root))
    monkeypatch.chdir(other)
    with TestClient(app) as client:
        res = client.get("/api/workspace/context-snapshot")
    assert res.status_code == 200, res.text
    assert res.json()["cwd"] == str(root.resolve())
    assert res.json()["cwd"] != str(other.resolve())


def test_workspace_context_snapshot_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("HAM_WORKSPACE_FILES_ROOT", raising=False)
    with TestClient(app) as client:
        res = client.get("/api/workspace/context-snapshot")
    assert res.status_code == 503, res.text
    body = res.json()
    assert body["detail"]["error"] == "WORKSPACE_ROOT_NOT_CONFIGURED"
    assert "message" in body["detail"]


def test_workspace_context_snapshot_not_configured_after_files_creates_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Files may create ``.ham_workspace_sandbox`` when env is unset; context-snapshot must still 503."""
    monkeypatch.delenv("HAM_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("HAM_WORKSPACE_FILES_ROOT", raising=False)
    with TestClient(app) as client:
        files_res = client.get("/api/workspace/files?action=list")
        assert files_res.status_code == 200, files_res.text
        snap = client.get("/api/workspace/context-snapshot")
    assert snap.status_code == 503, snap.text
    assert snap.json()["detail"]["error"] == "WORKSPACE_ROOT_NOT_CONFIGURED"
    assert "cwd" not in snap.json().get("detail", {})


def test_workspace_context_snapshot_root_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = tmp_path / "does_not_exist"
    monkeypatch.delenv("HAM_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("HAM_WORKSPACE_FILES_ROOT", raising=False)
    monkeypatch.setenv("HAM_WORKSPACE_ROOT", str(missing))
    with TestClient(app) as client:
        res = client.get("/api/workspace/context-snapshot")
    assert res.status_code == 400, res.text
    assert res.json()["detail"]["error"] == "WORKSPACE_ROOT_MISSING"


def test_workspace_context_snapshot_root_not_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "not_a_dir"
    f.write_text("x", encoding="utf-8")
    monkeypatch.delenv("HAM_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("HAM_WORKSPACE_FILES_ROOT", raising=False)
    monkeypatch.setenv("HAM_WORKSPACE_ROOT", str(f))
    with TestClient(app) as client:
        res = client.get("/api/workspace/context-snapshot")
    assert res.status_code == 400, res.text
    assert res.json()["detail"]["error"] == "WORKSPACE_ROOT_NOT_DIRECTORY"


def test_workspace_context_snapshot_root_unreadable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "locked"
    root.mkdir()
    monkeypatch.delenv("HAM_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("HAM_WORKSPACE_FILES_ROOT", raising=False)
    monkeypatch.setenv("HAM_WORKSPACE_ROOT", str(root))
    with mock.patch("os.listdir", side_effect=PermissionError("denied")):
        with TestClient(app) as client:
            res = client.get("/api/workspace/context-snapshot")
    assert res.status_code == 400, res.text
    assert res.json()["detail"]["error"] == "WORKSPACE_ROOT_UNREADABLE"


def test_global_context_engine_unchanged_after_workspace_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/context-engine must still reflect process cwd (not workspace env)."""
    root = tmp_path / "only_for_env"
    root.mkdir()
    monkeypatch.delenv("HAM_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("HAM_WORKSPACE_FILES_ROOT", raising=False)
    monkeypatch.setenv("HAM_WORKSPACE_ROOT", str(root))
    with TestClient(app) as client:
        snap = client.get("/api/workspace/context-snapshot")
        glob = client.get("/api/context-engine")
    assert snap.status_code == 200
    assert glob.status_code == 200
    gbody = glob.json()
    assert "context_source" not in gbody or gbody.get("context_source") != "local"
    assert gbody["cwd"] == str(Path.cwd().resolve())
