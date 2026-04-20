"""GET /api/cursor-subagents"""
from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)


def test_get_cursor_subagents_returns_list() -> None:
    res = client.get("/api/cursor-subagents")
    assert res.status_code == 200, res.text
    data = res.json()
    assert "subagents" in data
    assert "count" in data
    assert isinstance(data["subagents"], list)
    assert data["count"] == len(data["subagents"])
    ids = {s["id"] for s in data["subagents"]}
    assert "subagent-context-engine-auditor" in ids
    sample = next(s for s in data["subagents"] if s["id"] == "subagent-context-engine-auditor")
    assert sample["path"].endswith("subagent-context-engine-auditor.mdc")
    assert "title" in sample and "description" in sample
    assert "globs" in sample and "always_apply" in sample
