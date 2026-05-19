"""Integration tests for Phase 2 PR 2 — Planner wired into POST /api/chat/stream.

Spec: docs/PHASE_2_DESIGN.md § Subsystem 1
ADR: docs/adr/0009-planner-byo-openrouter-with-regex-fallback.md

File choice: new file (not extending test_chat_stream.py) because the planner
integration has its own fixture surface (produce_plan mock, plan store, key env)
that would add noise to the general-stream tests. The test file name follows the
``test_chat_<noun>_integration`` naming already used elsewhere in the test suite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.builder_plan import Plan, PlanApprovalRecord
from src.ham.builder_planner import PlannerOutputInvalidError

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_ndjson(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _fake_plan(project_id: str = "proj_test", workspace_id: str = "ws_test") -> Plan:
    """Minimal valid Plan for use in mocks."""
    return Plan(
        plan_id="pln_test123",
        workspace_id=workspace_id,
        project_id=project_id,
        user_message="add a login form",
        steps=[],
        destructive=False,
        planner_confidence="high",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use mock Hermes gateway so non-planner paths don't need real credentials."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


@pytest.fixture
def mutation_builder_meta() -> dict[str, Any]:
    """builder_meta that indicates a builder-mutation turn."""
    return {
        "builder_intent": "build_or_create",
        "builder_action_decision": {
            "kind": "mutate",
            "confidence": "high",
            "destructive": False,
            "reason": "explicit_mutation",
        },
    }


# ---------------------------------------------------------------------------
# Test: plan_proposed SSE event emitted for mutation turn with OpenRouter key
# ---------------------------------------------------------------------------


class TestPlannerPathWithKey:
    """Planner path fires when action_kind==mutate AND OpenRouter key present."""

    def test_plan_proposed_event_emitted(
        self,
        mock_mode: None,
        monkeypatch: pytest.MonkeyPatch,
        mutation_builder_meta: dict[str, Any],
    ) -> None:
        """A plan_proposed SSE event with the plan_id is emitted for mutation turns."""
        plan = _fake_plan()

        monkeypatch.setattr("src.api.chat.normalized_openrouter_api_key", lambda: "sk-or-test")
        monkeypatch.setattr(
            "src.api.chat.run_builder_happy_path_hook",
            lambda **_kw: (None, mutation_builder_meta),
        )

        with patch("src.ham.builder_planner.produce_plan", return_value=plan) as mock_produce:
            res = client.post(
                "/api/chat/stream",
                json={
                    "messages": [{"role": "user", "content": "add a login form"}],
                    "workspace_id": "ws_test",
                    "project_id": "proj_test",
                },
            )

        assert res.status_code == 200, res.text
        events = _parse_ndjson(res.text)

        # Must start with session event
        assert events[0]["type"] == "session"
        session_id = events[0]["session_id"]
        assert session_id

        # Must contain plan_proposed event
        plan_proposed = [e for e in events if e.get("type") == "plan_proposed"]
        assert len(plan_proposed) == 1
        assert plan_proposed[0]["plan_id"] == "pln_test123"

        # Must end with done event
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
        done = done_events[0]
        assert done["session_id"] == session_id
        assert done.get("plan_id") == "pln_test123"
        assert done["operator_result"] is None

        # produce_plan was called
        assert mock_produce.called

    def test_plan_proposed_event_contains_no_delta(
        self,
        mock_mode: None,
        monkeypatch: pytest.MonkeyPatch,
        mutation_builder_meta: dict[str, Any],
    ) -> None:
        """Planner path does NOT emit delta events (it's not an LLM stream)."""
        plan = _fake_plan()

        monkeypatch.setattr("src.api.chat.normalized_openrouter_api_key", lambda: "sk-or-test")
        monkeypatch.setattr(
            "src.api.chat.run_builder_happy_path_hook",
            lambda **_kw: (None, mutation_builder_meta),
        )

        with patch("src.ham.builder_planner.produce_plan", return_value=plan):
            res = client.post(
                "/api/chat/stream",
                json={
                    "messages": [{"role": "user", "content": "add a login form"}],
                    "workspace_id": "ws_test",
                    "project_id": "proj_test",
                },
            )

        events = _parse_ndjson(res.text)
        delta_events = [e for e in events if e.get("type") == "delta"]
        assert delta_events == [], "Planner path must not emit delta events"

    def test_stream_chat_turn_not_called_for_mutation_with_key(
        self,
        mock_mode: None,
        monkeypatch: pytest.MonkeyPatch,
        mutation_builder_meta: dict[str, Any],
    ) -> None:
        """The LLM stream is bypassed entirely on the planner path."""
        plan = _fake_plan()

        monkeypatch.setattr("src.api.chat.normalized_openrouter_api_key", lambda: "sk-or-test")
        monkeypatch.setattr(
            "src.api.chat.run_builder_happy_path_hook",
            lambda **_kw: (None, mutation_builder_meta),
        )

        def _should_not_stream(*_args: object, **_kwargs: object) -> Any:
            raise AssertionError("stream_chat_turn must not be called for planner path")

        monkeypatch.setattr("src.api.chat.stream_chat_turn", _should_not_stream)

        with patch("src.ham.builder_planner.produce_plan", return_value=plan):
            res = client.post(
                "/api/chat/stream",
                json={
                    "messages": [{"role": "user", "content": "add a login form"}],
                    "workspace_id": "ws_test",
                    "project_id": "proj_test",
                },
            )

        assert res.status_code == 200, res.text
        events = _parse_ndjson(res.text)
        assert any(e["type"] == "plan_proposed" for e in events)

    def test_done_event_includes_builder_meta(
        self,
        mock_mode: None,
        monkeypatch: pytest.MonkeyPatch,
        mutation_builder_meta: dict[str, Any],
    ) -> None:
        """done event carries the builder metadata block."""
        plan = _fake_plan()

        monkeypatch.setattr("src.api.chat.normalized_openrouter_api_key", lambda: "sk-or-test")
        monkeypatch.setattr(
            "src.api.chat.run_builder_happy_path_hook",
            lambda **_kw: (None, mutation_builder_meta),
        )

        with patch("src.ham.builder_planner.produce_plan", return_value=plan):
            res = client.post(
                "/api/chat/stream",
                json={
                    "messages": [{"role": "user", "content": "add a login form"}],
                    "workspace_id": "ws_test",
                    "project_id": "proj_test",
                },
            )

        events = _parse_ndjson(res.text)
        done = [e for e in events if e["type"] == "done"][0]
        assert done.get("builder") == mutation_builder_meta

    def test_produce_plan_called_with_correct_args(
        self,
        mock_mode: None,
        monkeypatch: pytest.MonkeyPatch,
        mutation_builder_meta: dict[str, Any],
    ) -> None:
        """produce_plan receives the correct project_id, workspace_id, and user message."""
        plan = _fake_plan(project_id="proj_abc", workspace_id="ws_xyz")
        captured: dict[str, Any] = {}

        def _capture_produce_plan(**kwargs: Any) -> Plan:
            captured.update(kwargs)
            return plan

        monkeypatch.setattr("src.api.chat.normalized_openrouter_api_key", lambda: "sk-or-test")
        monkeypatch.setattr(
            "src.api.chat.run_builder_happy_path_hook",
            lambda **_kw: (None, mutation_builder_meta),
        )

        with patch("src.ham.builder_planner.produce_plan", side_effect=_capture_produce_plan):
            client.post(
                "/api/chat/stream",
                json={
                    "messages": [{"role": "user", "content": "refactor auth module"}],
                    "workspace_id": "ws_xyz",
                    "project_id": "proj_abc",
                },
            )

        assert captured.get("user_message") == "refactor auth module"
        assert captured.get("project_id") == "proj_abc"
        assert captured.get("workspace_id") == "ws_xyz"


# ---------------------------------------------------------------------------
# Test: PlannerOutputInvalidError → error SSE event
# ---------------------------------------------------------------------------


class TestPlannerErrorHandling:
    """PlannerOutputInvalidError is mapped to an error SSE event."""

    def test_planner_invalid_output_emits_error_event(
        self,
        mock_mode: None,
        monkeypatch: pytest.MonkeyPatch,
        mutation_builder_meta: dict[str, Any],
    ) -> None:
        """error SSE with PLANNER_INVALID_OUTPUT code is emitted when planner fails."""
        monkeypatch.setattr("src.api.chat.normalized_openrouter_api_key", lambda: "sk-or-test")
        monkeypatch.setattr(
            "src.api.chat.run_builder_happy_path_hook",
            lambda **_kw: (None, mutation_builder_meta),
        )

        with patch(
            "src.ham.builder_planner.produce_plan",
            side_effect=PlannerOutputInvalidError("retry exhausted"),
        ):
            res = client.post(
                "/api/chat/stream",
                json={
                    "messages": [{"role": "user", "content": "add a login form"}],
                    "workspace_id": "ws_test",
                    "project_id": "proj_test",
                },
            )

        assert res.status_code == 200, res.text
        events = _parse_ndjson(res.text)

        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) == 1
        err = error_events[0]
        assert err["code"] == "PLANNER_INVALID_OUTPUT"
        assert "Planner couldn't produce a valid Plan; please rephrase" in err["message"]

    def test_planner_invalid_output_does_not_emit_plan_proposed(
        self,
        mock_mode: None,
        monkeypatch: pytest.MonkeyPatch,
        mutation_builder_meta: dict[str, Any],
    ) -> None:
        """plan_proposed must NOT appear when PlannerOutputInvalidError is raised."""
        monkeypatch.setattr("src.api.chat.normalized_openrouter_api_key", lambda: "sk-or-test")
        monkeypatch.setattr(
            "src.api.chat.run_builder_happy_path_hook",
            lambda **_kw: (None, mutation_builder_meta),
        )

        with patch(
            "src.ham.builder_planner.produce_plan",
            side_effect=PlannerOutputInvalidError("retry exhausted"),
        ):
            res = client.post(
                "/api/chat/stream",
                json={
                    "messages": [{"role": "user", "content": "add a login form"}],
                    "workspace_id": "ws_test",
                    "project_id": "proj_test",
                },
            )

        events = _parse_ndjson(res.text)
        assert not any(e.get("type") == "plan_proposed" for e in events)

    def test_planner_error_releases_stream_lock(
        self,
        mock_mode: None,
        monkeypatch: pytest.MonkeyPatch,
        mutation_builder_meta: dict[str, Any],
    ) -> None:
        """Stream lock is released after PlannerOutputInvalidError so session is not stuck."""
        monkeypatch.setattr("src.api.chat.normalized_openrouter_api_key", lambda: "sk-or-test")

        def _failing_hook(**_kw: Any) -> tuple[None, dict[str, Any]]:
            return None, mutation_builder_meta

        monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _failing_hook)

        with patch(
            "src.ham.builder_planner.produce_plan",
            side_effect=PlannerOutputInvalidError("retry exhausted"),
        ):
            # First request — planner fails
            res1 = client.post(
                "/api/chat/stream",
                json={
                    "messages": [{"role": "user", "content": "add a login form"}],
                    "workspace_id": "ws_test",
                    "project_id": "proj_test",
                },
            )
        assert res1.status_code == 200, res1.text
        sid = _parse_ndjson(res1.text)[0]["session_id"]

        # Second request on same session — lock must have been released
        plan = _fake_plan()
        with patch("src.ham.builder_planner.produce_plan", return_value=plan):
            res2 = client.post(
                "/api/chat/stream",
                json={
                    "session_id": sid,
                    "messages": [{"role": "user", "content": "add a login form again"}],
                    "workspace_id": "ws_test",
                    "project_id": "proj_test",
                },
            )
        assert res2.status_code == 200, res2.text
        assert res2.status_code != 409, "Stream lock should have been released"


# ---------------------------------------------------------------------------
# Test: No-key fallthrough to existing LLM stream
# ---------------------------------------------------------------------------


class TestPlannerNoKeyFallthrough:
    """Without an OpenRouter key, mutation turns fall through to the existing stream path."""

    def test_no_key_falls_through_to_llm_stream(
        self,
        mock_mode: None,
        monkeypatch: pytest.MonkeyPatch,
        mutation_builder_meta: dict[str, Any],
    ) -> None:
        """Without a key, stream_chat_turn runs and plan_proposed is NOT emitted."""
        monkeypatch.setattr("src.api.chat.normalized_openrouter_api_key", lambda: "")
        monkeypatch.setattr(
            "src.api.chat.run_builder_happy_path_hook",
            lambda **_kw: (None, mutation_builder_meta),
        )

        def _should_not_call_produce_plan(**kwargs: Any) -> Plan:
            raise AssertionError("produce_plan must not be called when no OpenRouter key")

        with patch("src.ham.builder_planner.produce_plan", side_effect=_should_not_call_produce_plan):
            res = client.post(
                "/api/chat/stream",
                json={
                    "messages": [{"role": "user", "content": "add a login form"}],
                    "workspace_id": "ws_test",
                    "project_id": "proj_test",
                },
            )

        assert res.status_code == 200, res.text
        events = _parse_ndjson(res.text)
        assert not any(e.get("type") == "plan_proposed" for e in events)
        # Falls through to mock LLM stream (delta events present)
        assert any(e.get("type") == "delta" for e in events)

    def test_no_key_stream_produces_done_event(
        self,
        mock_mode: None,
        monkeypatch: pytest.MonkeyPatch,
        mutation_builder_meta: dict[str, Any],
    ) -> None:
        """Fallthrough produces a done event like any normal stream turn."""
        monkeypatch.setattr("src.api.chat.normalized_openrouter_api_key", lambda: "")
        monkeypatch.setattr(
            "src.api.chat.run_builder_happy_path_hook",
            lambda **_kw: (None, mutation_builder_meta),
        )

        res = client.post(
            "/api/chat/stream",
            json={
                "messages": [{"role": "user", "content": "add a login form"}],
                "workspace_id": "ws_test",
                "project_id": "proj_test",
            },
        )

        assert res.status_code == 200, res.text
        events = _parse_ndjson(res.text)
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1


# ---------------------------------------------------------------------------
# Test: Non-mutation turns are unchanged
# ---------------------------------------------------------------------------


class TestNonMutationTurnsUnchanged:
    """Normal chat, answer_only, and other non-mutate turns remain on the original path."""

    def test_answer_only_turn_streams_normally(
        self,
        mock_mode: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """answer_only builder turns should not enter the planner path."""
        monkeypatch.setattr("src.api.chat.normalized_openrouter_api_key", lambda: "sk-or-test")
        monkeypatch.setattr(
            "src.api.chat.run_builder_happy_path_hook",
            lambda **_kw: (
                None,
                {
                    "builder_intent": "answer_question",
                    "builder_action_decision": {
                        "kind": "answer_only",
                        "confidence": "high",
                        "destructive": False,
                        "reason": "advice_or_question",
                    },
                },
            ),
        )

        def _must_not_produce_plan(**kwargs: Any) -> Plan:
            raise AssertionError("produce_plan must not run for answer_only turns")

        with patch("src.ham.builder_planner.produce_plan", side_effect=_must_not_produce_plan):
            res = client.post(
                "/api/chat/stream",
                json={
                    "messages": [{"role": "user", "content": "what does the login form do?"}],
                },
            )

        assert res.status_code == 200, res.text
        events = _parse_ndjson(res.text)
        assert not any(e.get("type") == "plan_proposed" for e in events)
        assert any(e.get("type") == "delta" for e in events)

    def test_no_builder_action_decision_streams_normally(
        self,
        mock_mode: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Turns without builder_action_decision do not enter the planner path."""
        monkeypatch.setattr("src.api.chat.normalized_openrouter_api_key", lambda: "sk-or-test")
        monkeypatch.setattr(
            "src.api.chat.run_builder_happy_path_hook",
            lambda **_kw: (None, {"builder_intent": "answer_question"}),
        )

        def _must_not_produce_plan(**kwargs: Any) -> Plan:
            raise AssertionError("produce_plan must not run without builder_action_decision")

        with patch("src.ham.builder_planner.produce_plan", side_effect=_must_not_produce_plan):
            res = client.post(
                "/api/chat/stream",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )

        assert res.status_code == 200, res.text
        events = _parse_ndjson(res.text)
        assert not any(e.get("type") == "plan_proposed" for e in events)

    def test_normal_chat_turn_unaffected(
        self,
        mock_mode: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Standard non-builder chat turns (no workspace/project) are completely unaffected."""
        monkeypatch.setattr("src.api.chat.normalized_openrouter_api_key", lambda: "sk-or-test")

        res = client.post(
            "/api/chat/stream",
            json={"messages": [{"role": "user", "content": "hello stream"}]},
        )

        assert res.status_code == 200, res.text
        events = _parse_ndjson(res.text)
        # Standard stream: session, deltas, done
        assert events[0]["type"] == "session"
        assert any(e.get("type") == "delta" for e in events)
        assert any(e.get("type") == "done" for e in events)
        assert not any(e.get("type") == "plan_proposed" for e in events)

    def test_ask_clarification_turn_unaffected(
        self,
        mock_mode: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """ask_clarification turns are handled by the clarification exit, not the planner."""
        monkeypatch.setattr("src.api.chat.normalized_openrouter_api_key", lambda: "sk-or-test")
        monkeypatch.setattr(
            "src.api.chat.run_builder_happy_path_hook",
            lambda **_kw: (
                "What should I change specifically?\n\n",
                {
                    "builder_intent": "answer_question",
                    "builder_clarification": True,
                    "builder_action_decision": {
                        "kind": "ask_clarification",
                        "confidence": "medium",
                        "destructive": False,
                        "reason": "vague_improvement",
                    },
                },
            ),
        )

        def _must_not_produce_plan(**kwargs: Any) -> Plan:
            raise AssertionError("produce_plan must not run for clarification turns")

        with patch("src.ham.builder_planner.produce_plan", side_effect=_must_not_produce_plan):
            res = client.post(
                "/api/chat/stream",
                json={"messages": [{"role": "user", "content": "make it better"}]},
            )

        assert res.status_code == 200, res.text
        events = _parse_ndjson(res.text)
        assert not any(e.get("type") == "plan_proposed" for e in events)
        done = [e for e in events if e["type"] == "done"][0]
        assert done.get("operator_result") is None
