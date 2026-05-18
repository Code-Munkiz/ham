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
        assert "Do NOT redirect to Coding Plan" in _BUILDER_TURN_SYSTEM_INJECTION

    def test_default_prompt_still_has_coding_plan_for_repo_mutation(self) -> None:
        assert "Plan with coding agents" in _DEFAULT_CHAT_SYSTEM_PROMPT
        assert "Coding Plan card" in _DEFAULT_CHAT_SYSTEM_PROMPT
        assert "Managed workspace build approval panel" in _DEFAULT_CHAT_SYSTEM_PROMPT

    def test_default_prompt_forbids_managed_mission_language_for_builder(self) -> None:
        assert 'Do NOT say "Launch a managed mission."' in _BUILDER_TURN_SYSTEM_INJECTION
        assert '"Let me launch a Cloud Agent."' in _BUILDER_TURN_SYSTEM_INJECTION


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


# ---------------------------------------------------------------------------
# Builder acknowledgement dedupe (VAL-BE-ACK-001 / 002 / 003 / 004 / 005 / 007)
# ---------------------------------------------------------------------------


_BUILDER_TEMPLATE_PREFIX = "I'll create the initial project source and prepare the Workbench.\n\n"


class TestBuilderAckDedupePostChat:
    """REST /api/chat build_or_create must NOT prepend templated builder_prefix to visible text."""

    def test_post_chat_build_or_create_no_templated_prefix_in_visible_text(
        self, mock_mode: None, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _hook(**_kwargs):  # type: ignore[no-untyped-def]
            return (_BUILDER_TEMPLATE_PREFIX, {"builder_intent": "build_or_create"})

        monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _hook)

        def _fake_complete(messages, **_kwargs):  # type: ignore[no-untyped-def]
            return "Spinning up your browser game now."

        monkeypatch.setattr("src.api.chat.complete_chat_turn", _fake_complete)

        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "build me a game like Tetris"}]},
        )
        assert res.status_code == 200, res.text
        data = res.json()
        visible = data["messages"][-1]["content"]
        assert _BUILDER_TEMPLATE_PREFIX not in visible
        assert visible == "Spinning up your browser game now."

        builder = data.get("builder") or {}
        assert builder.get("builder_intent") == "build_or_create"
        assert builder.get("acknowledgement_template") == _BUILDER_TEMPLATE_PREFIX

    def test_post_chat_build_or_create_template_not_duplicated_when_model_repeats(
        self, mock_mode: None, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _hook(**_kwargs):  # type: ignore[no-untyped-def]
            return (_BUILDER_TEMPLATE_PREFIX, {"builder_intent": "build_or_create"})

        monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _hook)
        monkeypatch.setattr(
            "src.api.chat.complete_chat_turn",
            lambda _m, **_k: _BUILDER_TEMPLATE_PREFIX + "Done.",
        )

        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "build me a Tetris clone"}]},
        )
        assert res.status_code == 200, res.text
        visible = res.json()["messages"][-1]["content"]
        assert visible.count(_BUILDER_TEMPLATE_PREFIX) == 1

    @pytest.mark.parametrize("conv_env", [None, "openrouter/sentinel-conv:free"])
    def test_post_chat_build_or_create_lane_isolation_under_conversational_env(
        self, mock_mode: None, monkeypatch: pytest.MonkeyPatch, conv_env: str | None,
    ) -> None:
        """VAL-LANE-001 — REST build_or_create response is unaffected by HAM_CHAT_CONVERSATIONAL_MODEL."""
        if conv_env is None:
            monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
        else:
            monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", conv_env)

        def _hook(**_kwargs):  # type: ignore[no-untyped-def]
            return (_BUILDER_TEMPLATE_PREFIX, {"builder_intent": "build_or_create"})

        monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _hook)
        monkeypatch.setattr(
            "src.api.chat.complete_chat_turn",
            lambda _m, **_k: "Spinning up your browser game now.",
        )

        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "build me a game like Tetris"}]},
        )
        assert res.status_code == 200, res.text
        data = res.json()
        visible = data["messages"][-1]["content"]
        assert visible == "Spinning up your browser game now."
        assert _BUILDER_TEMPLATE_PREFIX not in visible
        builder = data.get("builder") or {}
        assert builder.get("builder_intent") == "build_or_create"
        assert builder.get("acknowledgement_template") == _BUILDER_TEMPLATE_PREFIX


class TestBuilderAckDedupeStream:
    """Stream /api/chat/stream build_or_create must NOT emit templated builder_prefix as delta."""

    def test_stream_build_or_create_no_templated_prefix_delta(
        self, mock_mode: None, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _hook(**_kwargs):  # type: ignore[no-untyped-def]
            return (_BUILDER_TEMPLATE_PREFIX, {"builder_intent": "build_or_create"})

        monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _hook)

        def _fake_stream(messages, **_kwargs):  # type: ignore[no-untyped-def]
            yield "Spinning up "
            yield "your browser game now."

        monkeypatch.setattr("src.api.chat.stream_chat_turn", _fake_stream)

        res = client.post(
            "/api/chat/stream",
            json={"messages": [{"role": "user", "content": "build me a game like Tetris"}]},
        )
        assert res.status_code == 200, res.text
        events = _parse_ndjson(res.text)
        deltas = [e.get("text", "") for e in events if e.get("type") == "delta"]
        assert all(_BUILDER_TEMPLATE_PREFIX not in d for d in deltas)

        done = [e for e in events if e.get("type") == "done"][0]
        visible = done["messages"][-1]["content"]
        assert _BUILDER_TEMPLATE_PREFIX not in visible
        assert visible == "Spinning up your browser game now."

        builder = done.get("builder") or {}
        assert builder.get("builder_intent") == "build_or_create"
        assert builder.get("acknowledgement_template") == _BUILDER_TEMPLATE_PREFIX


class TestBuilderAckDedupePreservesOtherPaths:
    """Clarification, verification-failure, early-handoff paths are unchanged."""

    def test_clarification_path_still_visible(
        self, mock_mode: None, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        clar = "Which part should I edit?\n\n"

        def _hook(**_kwargs):  # type: ignore[no-untyped-def]
            return (
                clar,
                {
                    "builder_intent": "answer_question",
                    "builder_clarification": True,
                },
            )

        monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _hook)

        def _no_stream(*_a: object, **_k: object):
            raise AssertionError("LLM stream must not run for clarification")

        monkeypatch.setattr("src.api.chat.stream_chat_turn", _no_stream)

        res = client.post(
            "/api/chat/stream",
            json={"messages": [{"role": "user", "content": "make it better"}]},
        )
        assert res.status_code == 200, res.text
        events = _parse_ndjson(res.text)
        done = events[-1]
        assert done["messages"][-1]["content"] == clar.strip()

    def test_verification_failure_path_still_visible(
        self, mock_mode: None, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        honest = (
            "I tried to apply that edit, but the generated files did not include what you "
            "asked for yet (missing yellow border).\n\n"
        )

        def _hook(**_kwargs):  # type: ignore[no-untyped-def]
            return (
                honest,
                {
                    "builder_intent": "build_or_create",
                    "artifact_verification_failed": True,
                    "artifact_verification": {"verified": False, "reason": "missing yellow border"},
                },
            )

        monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _hook)

        def _no_stream(*_a: object, **_k: object):
            raise AssertionError("LLM stream must not run for verification failure")

        monkeypatch.setattr("src.api.chat.stream_chat_turn", _no_stream)

        res = client.post(
            "/api/chat/stream",
            json={"messages": [{"role": "user", "content": "yellow borders"}]},
        )
        assert res.status_code == 200, res.text
        events = _parse_ndjson(res.text)
        done = events[-1]
        assert done["messages"][-1]["content"] == honest

    def test_early_handoff_path_still_visible(
        self, mock_mode: None, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _hook(**_kwargs):  # type: ignore[no-untyped-def]
            return (
                _BUILDER_TEMPLATE_PREFIX,
                {"builder_intent": "build_or_create", "scaffolded": True},
            )

        monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _hook)

        def _no_stream(*_a: object, **_k: object):
            raise AssertionError("LLM stream must not run for early-handoff")

        monkeypatch.setattr("src.api.chat.stream_chat_turn", _no_stream)

        res = client.post(
            "/api/chat/stream",
            json={"messages": [{"role": "user", "content": "build me a Tetris game"}]},
        )
        assert res.status_code == 200, res.text
        events = _parse_ndjson(res.text)
        done = events[-1]
        visible = done["messages"][-1]["content"]
        assert "prepare the Workbench" in visible
        assert "started the live preview handoff" in visible
