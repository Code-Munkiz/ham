"""Stream/REST honest-failure surfacing for net-new builder scaffold turns."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.builder_error_codes import STEP_MODEL_UNAVAILABLE

client = TestClient(app)


def _parse_ndjson(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


@pytest.fixture
def mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


def _net_new_fail_meta() -> dict[str, Any]:
    return {
        "builder_intent": "build_or_create",
        "llm_scaffold_failed": True,
        "llm_scaffold_error_code": STEP_MODEL_UNAVAILABLE,
        "builder_action_decision": {
            "kind": "mutate",
            "confidence": "high",
            "destructive": False,
            "reason": "explicit_mutation",
        },
    }


def test_gattica_stream_returns_honest_failure_not_502(
    mock_mode: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fail_prefix = (
        "I couldn't build this yet because the OpenRouter model call failed. "
        "Check Connected Tools (OpenRouter key) and your selected chat model, then try again.\n\n"
    )
    monkeypatch.setattr(
        "src.api.chat.run_builder_happy_path_hook",
        lambda **_kw: (fail_prefix, _net_new_fail_meta()),
    )

    with patch("src.ham.builder_planner.produce_plan") as mock_produce:
        res = client.post(
            "/api/chat/stream",
            json={
                "messages": [{"role": "user", "content": "ham build me a game like gattica"}],
                "workspace_id": "ws_gattica",
                "project_id": "proj_gattica",
            },
        )

    assert res.status_code == 200, res.text
    mock_produce.assert_not_called()
    events = _parse_ndjson(res.text)
    done = [e for e in events if e["type"] == "done"][0]
    assistant = done["messages"][-1]["content"]
    assert "couldn't build" in assistant.lower()
    assert "apply that edit" not in assistant.lower()
    assert "interrupted before" not in assistant.lower()
    assert done.get("builder", {}).get("llm_scaffold_failed") is True


def test_spaceship_stream_model_access_required_rest(
    mock_mode: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prefix = (
        "I cannot build this without model access. "
        "Connect OpenRouter in Settings (Connected Tools) and try again.\n\n"
    )
    meta = {
        "builder_intent": "build_or_create",
        "model_access_required": True,
        "builder_action_decision": {
            "kind": "mutate",
            "confidence": "high",
            "destructive": False,
            "reason": "explicit_mutation",
        },
    }
    monkeypatch.setattr(
        "src.api.chat.run_builder_happy_path_hook",
        lambda **_kw: (prefix, meta),
    )

    res = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "build a game where i can shoot things in a spaceship"}],
            "workspace_id": "ws_ship",
            "project_id": "proj_ship",
        },
    )

    assert res.status_code == 200, res.json()
    data = res.json()
    assistant = data["messages"][-1]["content"]
    assert "cannot build this without model access" in assistant.lower()
    assert data.get("builder", {}).get("model_access_required") is True
