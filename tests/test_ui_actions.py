"""Parse and validate HAM_UI_ACTIONS_JSON from assistant replies."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.ui_actions import split_assistant_ui_actions

client = TestClient(app)


def test_split_strips_marker_and_parses_actions() -> None:
    raw = (
        "Opening Context settings for you.\n\n"
        'HAM_UI_ACTIONS_JSON: {"actions":[{"type":"open_settings","tab":"context-memory"}]}'
    )
    visible, actions = split_assistant_ui_actions(raw)
    assert "HAM_UI_ACTIONS_JSON" not in visible
    assert len(actions) == 1
    assert actions[0]["type"] == "open_settings"
    assert actions[0]["tab"] == "context-memory"


def test_split_rejects_bad_nav_path() -> None:
    raw = 'Hi\nHAM_UI_ACTIONS_JSON: {"actions":[{"type":"navigate","path":"https://evil"}]}'
    visible, actions = split_assistant_ui_actions(raw)
    assert visible == "Hi"
    assert actions == []


def test_split_accepts_settings_query_path() -> None:
    raw = (
        'HAM_UI_ACTIONS_JSON: {"actions":[{"type":"navigate","path":"/settings?tab=context-memory"}]}'
    )
    _, actions = split_assistant_ui_actions(raw)
    assert len(actions) == 1
    assert actions[0]["path"] == "/settings?tab=context-memory"


def test_split_accepts_set_workbench_view() -> None:
    raw = (
        'Done.\nHAM_UI_ACTIONS_JSON: {"actions":[{"type":"set_workbench_view","mode":"war_room"}]}'
    )
    visible, actions = split_assistant_ui_actions(raw)
    assert visible == "Done."
    assert actions == [{"type": "set_workbench_view", "mode": "war_room"}]


def test_split_rejects_invalid_workbench_mode() -> None:
    raw = 'HAM_UI_ACTIONS_JSON: {"actions":[{"type":"set_workbench_view","mode":"fullscreen"}]}'
    _, actions = split_assistant_ui_actions(raw)
    assert actions == []


@pytest.fixture
def mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


def test_post_chat_returns_actions_array(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_turn(_msgs: list, **_kwargs) -> str:
        return (
            "Done.\n"
            'HAM_UI_ACTIONS_JSON: {"actions":[{"type":"toast","level":"success","message":"ok"}]}'
        )

    monkeypatch.setattr("src.api.chat.complete_chat_turn", fake_turn)
    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "x"}], "enable_ui_actions": True},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["actions"] == [{"type": "toast", "level": "success", "message": "ok"}]
    assert data["messages"][-1]["content"] == "Done."
