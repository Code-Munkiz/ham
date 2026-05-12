"""Builder happy-path: system injection keeps greenfield prompts off managed-mission copy."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.api.chat import (
    _BUILDER_TURN_SYSTEM_INJECTION,
    _DEFAULT_CHAT_SYSTEM_PROMPT,
    _inject_builder_turn_system,
)
from src.api.server import app
from src.ham.builder_chat_hooks import _builder_ack_prefix

client = TestClient(app)


# ---------------------------------------------------------------------------
# Unit: _inject_builder_turn_system
# ---------------------------------------------------------------------------


class TestInjectBuilderTurnSystem:
    def test_no_injection_for_answer_question(self) -> None:
        msgs = [{"role": "system", "content": "base"}, {"role": "user", "content": "hi"}]
        result = _inject_builder_turn_system(msgs, "answer_question")
        assert result[0]["content"] == "base"

    def test_no_injection_for_plan_only(self) -> None:
        msgs = [{"role": "system", "content": "base"}]
        result = _inject_builder_turn_system(msgs, "plan_only")
        assert result[0]["content"] == "base"

    def test_injection_appended_for_build_or_create(self) -> None:
        msgs = [{"role": "system", "content": "base"}, {"role": "user", "content": "build a game"}]
        result = _inject_builder_turn_system(msgs, "build_or_create")
        assert "Builder turn override" in result[0]["content"]
        assert "base" in result[0]["content"]
        assert "Do NOT say" in result[0]["content"]

    def test_injection_creates_system_if_missing(self) -> None:
        msgs = [{"role": "user", "content": "build a game"}]
        result = _inject_builder_turn_system(msgs, "build_or_create")
        assert result[0]["role"] == "system"
        assert "Builder turn override" in result[0]["content"]
        assert result[1]["role"] == "user"

    def test_injection_prohibits_managed_mission_language(self) -> None:
        text = _BUILDER_TURN_SYSTEM_INJECTION
        assert "Launch a managed mission" in text
        assert "launch a Cloud Agent" in text
        assert "Plan with coding agents" in text
        assert "can't build directly from chat" in text


# ---------------------------------------------------------------------------
# Unit: _builder_ack_prefix
# ---------------------------------------------------------------------------


class TestBuilderAckPrefix:
    def test_tetris_prompt_yields_specific_copy(self) -> None:
        prefix = _builder_ack_prefix("build me a game like Tetris")
        assert "Tetris-style" in prefix
        assert "browser game" in prefix
        assert "Workbench" in prefix

    def test_landing_page_prompt(self) -> None:
        prefix = _builder_ack_prefix("build me a landing page for roofers")
        assert "landing page" in prefix
        assert "Workbench" in prefix

    def test_generic_build_prompt(self) -> None:
        prefix = _builder_ack_prefix("build something cool")
        assert "Workbench" in prefix

    def test_make_tetris_clone(self) -> None:
        prefix = _builder_ack_prefix("make a tetris clone")
        assert "Tetris-style" in prefix
        assert "Workbench" in prefix

    def test_create_dashboard(self) -> None:
        prefix = _builder_ack_prefix("create a SaaS dashboard")
        assert "dashboard" in prefix
        assert "Workbench" in prefix


# ---------------------------------------------------------------------------
# Unit: default system prompt boundary
# ---------------------------------------------------------------------------


class TestSystemPromptBoundary:
    def test_default_prompt_prohibits_managed_mission_for_builder(self) -> None:
        assert "Do NOT redirect builder prompts to Coding Plan" in _DEFAULT_CHAT_SYSTEM_PROMPT

    def test_default_prompt_still_has_coding_plan_for_repo_mutation(self) -> None:
        assert "Plan with coding agents" in _DEFAULT_CHAT_SYSTEM_PROMPT
        assert "Coding Plan card" in _DEFAULT_CHAT_SYSTEM_PROMPT
        assert "Managed workspace build approval panel" in _DEFAULT_CHAT_SYSTEM_PROMPT

    def test_default_prompt_forbids_managed_mission_language_for_builder(self) -> None:
        assert 'Do NOT say "Launch a managed mission"' in _DEFAULT_CHAT_SYSTEM_PROMPT
        assert '"Let me launch a Cloud Agent"' in _DEFAULT_CHAT_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Integration: stream endpoint with builder prompt (mock gateway)
# ---------------------------------------------------------------------------


def _parse_ndjson(text: str) -> list[dict]:
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


@pytest.fixture
def mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


class TestStreamBuilderPromptNoManagedMission:
    """Stream path must not produce managed-mission language for builder prompts."""

    def test_tetris_stream_no_managed_mission_copy(
        self, mock_mode: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even without scaffold, stream must not say 'managed mission' for builder prompts."""
        res = client.post(
            "/api/chat/stream",
            json={"messages": [{"role": "user", "content": "build me a game like Tetris"}]},
        )
        assert res.status_code == 200, res.text
        events = _parse_ndjson(res.text)
        done = [e for e in events if e.get("type") == "done"][0]
        assistant_text = done["messages"][-1]["content"]
        assert done.get("builder", {}).get("builder_intent") == "build_or_create"
        for forbidden in (
            "managed mission",
            "Cloud Agent",
            "Plan with coding agents",
            "can't build directly",
        ):
            assert forbidden.lower() not in assistant_text.lower(), (
                f"Forbidden phrase found in assistant response: {forbidden!r}"
            )

    def test_tetris_stream_builder_meta_present(self, mock_mode: None) -> None:
        res = client.post(
            "/api/chat/stream",
            json={"messages": [{"role": "user", "content": "make a tetris clone"}]},
        )
        assert res.status_code == 200
        events = _parse_ndjson(res.text)
        done = [e for e in events if e.get("type") == "done"][0]
        assert done.get("builder", {}).get("builder_intent") == "build_or_create"

    def test_repo_agent_prompt_still_routes_to_operator(
        self, mock_mode: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Repo-mutation prompts must not be blocked by builder injection."""
        monkeypatch.setenv("HAM_CHAT_OPERATOR", "false")
        res = client.post(
            "/api/chat/stream",
            json={
                "messages": [{"role": "user", "content": "use Cursor agent to fix this repo"}],
                "enable_operator": True,
            },
        )
        assert res.status_code == 200
        events = _parse_ndjson(res.text)
        done = [e for e in events if e.get("type") == "done"][0]
        intent = done.get("builder", {}).get("builder_intent", "")
        assert intent != "build_or_create"


class TestPostChatBuilderPromptNoManagedMission:
    """POST /api/chat must not produce managed-mission language for builder prompts."""

    def test_tetris_post_no_managed_mission_copy(self, mock_mode: None) -> None:
        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "build me a game like Tetris"}]},
        )
        assert res.status_code == 200
        data = res.json()
        assistant_text = data["messages"][-1]["content"]
        assert data.get("builder", {}).get("builder_intent") == "build_or_create"
        for forbidden in (
            "managed mission",
            "Cloud Agent",
            "Plan with coding agents",
            "can't build directly",
        ):
            assert forbidden.lower() not in assistant_text.lower(), (
                f"Forbidden phrase found: {forbidden!r}"
            )

    def test_open_pr_prompt_not_blocked(self, mock_mode: None) -> None:
        """Repo mutation prompt must not be treated as builder."""
        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "open a PR for this repo"}]},
        )
        assert res.status_code == 200
        data = res.json()
        assert data.get("builder", {}).get("builder_intent") != "build_or_create"
