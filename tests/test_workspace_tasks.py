from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.api.workspace_tasks as workspace_tasks
from src.api.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_task_store() -> None:
    workspace_tasks.TasksStatePath = None
    yield
    workspace_tasks.TasksStatePath = None


def test_summary_list_create_patch_delete(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "w"
    root.mkdir()
    monkeypatch.setenv("HAM_WORKSPACE_ROOT", str(root))
    workspace_tasks.TasksStatePath = None

    s = client.get("/api/workspace/tasks/summary")
    assert s.status_code == 200
    assert s.json() == {
        "total": 0,
        "inProgress": 0,
        "overdue": 0,
        "done": 0,
        "donePercent": 0,
    }

    t = client.post(
        "/api/workspace/tasks",
        content=json.dumps({"title": "A", "body": "x", "status": "todo"}),
        headers={"content-type": "application/json"},
    )
    assert t.status_code == 201
    tid = t.json()["id"]

    t2 = client.post(
        "/api/workspace/tasks",
        content=json.dumps({"title": "B", "status": "in_progress"}),
        headers={"content-type": "application/json"},
    )
    assert t2.status_code == 201

    s2 = client.get("/api/workspace/tasks/summary")
    assert s2.json()["total"] == 2
    assert s2.json()["inProgress"] == 1

    listed = client.get("/api/workspace/tasks", params={"status": "in_progress"})
    assert len(listed.json()["tasks"]) == 1

    no_done = client.get("/api/workspace/tasks", params={"includeDone": "false"})
    # none done yet
    assert len(no_done.json()["tasks"]) == 2

    client.patch(
        f"/api/workspace/tasks/{tid}",
        content=json.dumps({"status": "done"}),
        headers={"content-type": "application/json"},
    )

    no_done2 = client.get("/api/workspace/tasks", params={"includeDone": "false"})
    assert len(no_done2.json()["tasks"]) == 1

    client.delete(f"/api/workspace/tasks/{tid}")
    assert client.get(f"/api/workspace/tasks/{tid}").status_code == 404
