"""GET /api/cursor-skills"""
from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)


def test_get_cursor_skills_returns_list() -> None:
    res = client.get("/api/cursor-skills")
    assert res.status_code == 200
    data = res.json()
    assert "skills" in data
    assert "count" in data
    assert isinstance(data["skills"], list)
    assert data["count"] == len(data["skills"])
    ids = {s["id"] for s in data["skills"]}
    assert "agent-context-wiring" in ids
