from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_workspace_terminal_create_output_close(client: TestClient) -> None:
    r = client.post("/api/workspace/terminal/sessions")
    assert r.status_code == 200
    sid = r.json().get("sessionId")
    assert isinstance(sid, str) and sid

    out = client.get(f"/api/workspace/terminal/sessions/{sid}/output?after=0")
    assert out.status_code == 200
    body = out.json()
    assert "text" in body
    assert "next" in body

    d = client.delete(f"/api/workspace/terminal/sessions/{sid}")
    assert d.status_code == 204
