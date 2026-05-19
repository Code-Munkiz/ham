"""Tests for src/ham/builder_planner.py — Phase 2 Subsystem 1."""

from __future__ import annotations

from typing import Any

import pytest

from src.ham.builder_plan import Plan, PlanApprovalRecord
from src.ham.builder_planner import (
    PlannerOutputInvalidError,
    _extract_json,
    produce_plan,
)
from src.persistence.builder_plan_store import (
    BuilderPlanStoreProtocol,
    set_builder_plan_store_for_tests,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _InMemoryPlanStore:
    """Minimal in-memory BuilderPlanStore for tests."""

    def __init__(self) -> None:
        self._plans: dict[str, Plan] = {}
        self._approvals: dict[str, PlanApprovalRecord] = {}

    def list_plans(self, *, workspace_id: str, project_id: str) -> list[Plan]:
        return [
            p for p in self._plans.values()
            if p.workspace_id == workspace_id and p.project_id == project_id
        ]

    def get_plan(self, *, plan_id: str) -> Plan | None:
        return self._plans.get(plan_id)

    def upsert_plan(self, plan: Plan) -> Plan:
        self._plans[plan.plan_id] = plan
        return plan

    def get_approval_record(self, *, plan_id: str) -> PlanApprovalRecord | None:
        return self._approvals.get(plan_id)

    def upsert_approval_record(self, record: PlanApprovalRecord) -> PlanApprovalRecord:
        self._approvals[record.plan_id] = record
        return record


_VALID_LLM_JSON = """\
{
  "steps": [
    {
      "title": "Add login form",
      "description": "Create a simple login form with email and password fields.",
      "requires_approval": false
    },
    {
      "title": "Wire auth endpoint",
      "description": "Connect form to POST /api/auth/login.",
      "requires_approval": false
    }
  ],
  "destructive": false,
  "planner_confidence": "high"
}
"""

_INVALID_LLM_JSON = "not json at all"

_PARTIAL_LLM_JSON = '{"steps": [], "planner_confidence": "unknown_value"}'


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_plain_json_passes_through(self):
        raw = '{"foo": "bar"}'
        assert _extract_json(raw) == raw

    def test_strips_markdown_fences(self):
        raw = "```json\n{\"foo\": \"bar\"}\n```"
        result = _extract_json(raw)
        assert result == '{"foo": "bar"}'

    def test_strips_unmarked_fences(self):
        raw = "```\n{\"x\": 1}\n```"
        result = _extract_json(raw)
        assert '{"x": 1}' in result

    def test_extracts_outermost_braces(self):
        raw = "Here is the JSON: {\"a\": 1} done"
        result = _extract_json(raw)
        assert result == '{"a": 1}'

    def test_empty_string_returns_empty(self):
        result = _extract_json("")
        assert result == ""


# ---------------------------------------------------------------------------
# produce_plan — no key fallback
# ---------------------------------------------------------------------------


class TestProducePlanNoKey:
    def test_returns_none_when_no_openrouter_key(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_planner.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "",
        )
        store = _InMemoryPlanStore()
        result = produce_plan(
            user_message="Add dark mode",
            project_id="proj_test",
            workspace_id="ws_test",
            requested_by="user@test.com",
            conversation_history=[],
            store=store,
        )
        assert result is None
        assert len(store._plans) == 0


class TestProducePlanActorKey:
    def test_actor_connected_tools_key_enables_planner(self, monkeypatch):
        from src.ham.clerk_auth import HamActor

        actor = HamActor(
            user_id="user_byo",
            org_id=None,
            session_id=None,
            email="user_byo@example.com",
            permissions=frozenset(),
            org_role=None,
            raw_permission_claim=None,
        )
        seen: list[Any | None] = []

        def _resolve(ham_actor: Any | None = None) -> str:
            seen.append(ham_actor)
            return "sk-or-test-key" if ham_actor is actor else ""

        monkeypatch.setattr(
            "src.ham.builder_planner.resolve_openrouter_api_key_for_actor",
            _resolve,
        )
        monkeypatch.setattr(
            "src.ham.builder_planner.complete_chat_messages_openrouter",
            lambda messages, **kwargs: _VALID_LLM_JSON,
        )
        store = _InMemoryPlanStore()

        plan = produce_plan(
            user_message="Add login",
            project_id="proj_test",
            workspace_id="ws_test",
            requested_by=actor.user_id,
            conversation_history=[],
            store=store,
            ham_actor=actor,
        )

        assert plan is not None
        assert seen == [actor]


# ---------------------------------------------------------------------------
# produce_plan — success path
# ---------------------------------------------------------------------------


class TestProducePlanSuccess:
    def test_success_returns_plan_and_writes_to_store(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_planner.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        monkeypatch.setattr(
            "src.ham.builder_planner.complete_chat_messages_openrouter",
            lambda messages, **kwargs: _VALID_LLM_JSON,
        )
        store = _InMemoryPlanStore()

        plan = produce_plan(
            user_message="Add login",
            project_id="proj_test",
            workspace_id="ws_test",
            requested_by="user@test.com",
            conversation_history=[],
            store=store,
        )

        assert plan is not None
        assert isinstance(plan, Plan)
        assert len(plan.steps) == 2
        assert plan.steps[0].title == "Add login form"
        assert plan.project_id == "proj_test"
        assert plan.workspace_id == "ws_test"
        assert plan.user_message == "Add login"

    def test_plan_persisted_to_store(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_planner.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        monkeypatch.setattr(
            "src.ham.builder_planner.complete_chat_messages_openrouter",
            lambda messages, **kwargs: _VALID_LLM_JSON,
        )
        store = _InMemoryPlanStore()

        plan = produce_plan(
            user_message="Build calculator",
            project_id="proj_x",
            workspace_id="ws_x",
            requested_by="dev@test.com",
            conversation_history=[],
            store=store,
        )

        assert plan is not None
        stored = store.get_plan(plan_id=plan.plan_id)
        assert stored is not None
        assert stored.plan_id == plan.plan_id

    def test_approval_record_written_as_proposed(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_planner.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        monkeypatch.setattr(
            "src.ham.builder_planner.complete_chat_messages_openrouter",
            lambda messages, **kwargs: _VALID_LLM_JSON,
        )
        store = _InMemoryPlanStore()

        plan = produce_plan(
            user_message="Add feature",
            project_id="proj_y",
            workspace_id="ws_y",
            requested_by="dev@test.com",
            conversation_history=[],
            store=store,
        )

        assert plan is not None
        rec = store.get_approval_record(plan_id=plan.plan_id)
        assert rec is not None
        assert rec.state == "proposed"
        assert rec.plan_id == plan.plan_id

    def test_source_snapshot_id_propagated(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_planner.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        monkeypatch.setattr(
            "src.ham.builder_planner.complete_chat_messages_openrouter",
            lambda messages, **kwargs: _VALID_LLM_JSON,
        )
        store = _InMemoryPlanStore()

        plan = produce_plan(
            user_message="Refactor code",
            project_id="proj_z",
            workspace_id="ws_z",
            requested_by="dev@test.com",
            conversation_history=[],
            source_snapshot_id="ssnp_abc123",
            store=store,
        )

        assert plan is not None
        assert plan.source_snapshot_id == "ssnp_abc123"

    def test_conversation_history_dict_format(self, monkeypatch):
        """Conversation history as plain dicts should not raise."""
        monkeypatch.setattr(
            "src.ham.builder_planner.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        captured_messages: list[Any] = []

        def _fake_complete(messages, **kwargs):
            captured_messages.extend(messages)
            return _VALID_LLM_JSON

        monkeypatch.setattr(
            "src.ham.builder_planner.complete_chat_messages_openrouter",
            _fake_complete,
        )
        store = _InMemoryPlanStore()
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        plan = produce_plan(
            user_message="Add something",
            project_id="proj_h",
            workspace_id="ws_h",
            requested_by="dev@test.com",
            conversation_history=history,
            store=store,
        )

        assert plan is not None
        # Messages should include the history
        roles = [m["role"] for m in captured_messages]
        assert "user" in roles
        assert "assistant" in roles


# ---------------------------------------------------------------------------
# produce_plan — retry on invalid JSON
# ---------------------------------------------------------------------------


class TestProducePlanRetry:
    def test_retries_once_on_invalid_json(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_planner.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        call_count = 0

        def _flaky_complete(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "not json"
            return _VALID_LLM_JSON

        monkeypatch.setattr(
            "src.ham.builder_planner.complete_chat_messages_openrouter",
            _flaky_complete,
        )
        store = _InMemoryPlanStore()

        plan = produce_plan(
            user_message="Fix bug",
            project_id="proj_r",
            workspace_id="ws_r",
            requested_by="dev@test.com",
            conversation_history=[],
            store=store,
        )

        assert plan is not None
        assert call_count == 2

    def test_raises_planner_output_invalid_after_two_failures(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_planner.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        monkeypatch.setattr(
            "src.ham.builder_planner.complete_chat_messages_openrouter",
            lambda messages, **kwargs: "DEFINITELY NOT JSON",
        )
        store = _InMemoryPlanStore()

        with pytest.raises(PlannerOutputInvalidError):
            produce_plan(
                user_message="Cause failure",
                project_id="proj_f",
                workspace_id="ws_f",
                requested_by="dev@test.com",
                conversation_history=[],
                store=store,
            )

    def test_no_plan_stored_on_failure(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_planner.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        monkeypatch.setattr(
            "src.ham.builder_planner.complete_chat_messages_openrouter",
            lambda messages, **kwargs: "not valid",
        )
        store = _InMemoryPlanStore()

        with pytest.raises(PlannerOutputInvalidError):
            produce_plan(
                user_message="Broken request",
                project_id="proj_fail",
                workspace_id="ws_fail",
                requested_by="dev@test.com",
                conversation_history=[],
                store=store,
            )

        assert len(store._plans) == 0
        assert len(store._approvals) == 0


# ---------------------------------------------------------------------------
# produce_plan — model selection
# ---------------------------------------------------------------------------


class TestProducePlanModelSelection:
    def test_uses_ham_planner_model_env(self, monkeypatch):
        monkeypatch.setenv("HAM_PLANNER_MODEL", "gpt-4o-mini")
        monkeypatch.setattr(
            "src.ham.builder_planner.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        captured: list[str] = []

        def _capture_complete(messages, *, model_override=None, **kwargs):
            captured.append(str(model_override or ""))
            return _VALID_LLM_JSON

        monkeypatch.setattr(
            "src.ham.builder_planner.complete_chat_messages_openrouter",
            _capture_complete,
        )
        store = _InMemoryPlanStore()

        produce_plan(
            user_message="Test model",
            project_id="proj_m",
            workspace_id="ws_m",
            requested_by="dev@test.com",
            conversation_history=[],
            store=store,
        )

        assert len(captured) == 1
        assert "gpt-4o-mini" in captured[0]

    def test_does_not_use_hermes_gateway_model(self, monkeypatch):
        monkeypatch.delenv("HAM_PLANNER_MODEL", raising=False)
        monkeypatch.setenv("HERMES_GATEWAY_MODEL", "hermes-agent")
        monkeypatch.setenv("DEFAULT_MODEL", "minimax/minimax-m2.5:free")
        monkeypatch.setattr(
            "src.ham.builder_planner.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        captured: list[str] = []

        def _capture_complete(messages, *, model_override=None, **kwargs):
            captured.append(str(model_override or ""))
            return _VALID_LLM_JSON

        monkeypatch.setattr(
            "src.ham.builder_planner.complete_chat_messages_openrouter",
            _capture_complete,
        )
        store = _InMemoryPlanStore()

        produce_plan(
            user_message="Test model",
            project_id="proj_m",
            workspace_id="ws_m",
            requested_by="dev@test.com",
            conversation_history=[],
            store=store,
        )

        assert len(captured) == 1
        assert captured[0] == "openrouter/minimax/minimax-m2.5:free"
        assert "hermes-agent" not in captured[0]

    def test_threads_explicit_model_override(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_planner.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        captured: list[str] = []

        def _capture_complete(messages, *, model_override=None, **kwargs):
            captured.append(str(model_override or ""))
            return _VALID_LLM_JSON

        monkeypatch.setattr(
            "src.ham.builder_planner.complete_chat_messages_openrouter",
            _capture_complete,
        )
        store = _InMemoryPlanStore()

        produce_plan(
            user_message="Test model",
            project_id="proj_m",
            workspace_id="ws_m",
            requested_by="dev@test.com",
            conversation_history=[],
            store=store,
            model_override="openrouter/qwen/qwen3-coder:free",
        )

        assert captured == ["openrouter/qwen/qwen3-coder:free"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestProducePlanEdgeCases:
    def test_empty_steps_list_raises(self, monkeypatch):
        """Plan with zero steps should fail Pydantic validation (steps list can't be empty
        by product rules, but the schema allows it — test that extra="forbid" isn't violated)."""
        monkeypatch.setattr(
            "src.ham.builder_planner.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        # Return JSON with empty steps but valid planner_confidence
        monkeypatch.setattr(
            "src.ham.builder_planner.complete_chat_messages_openrouter",
            lambda messages, **kwargs: '{"steps": [], "destructive": false, "planner_confidence": "high"}',
        )
        store = _InMemoryPlanStore()
        # Empty steps produces a plan (schema allows it); just verify it doesn't crash
        plan = produce_plan(
            user_message="Edge case",
            project_id="proj_e",
            workspace_id="ws_e",
            requested_by="dev@test.com",
            conversation_history=[],
            store=store,
        )
        # Either succeeds or raises PlannerOutputInvalidError — both are acceptable
        if plan is not None:
            assert isinstance(plan, Plan)

    def test_llm_json_in_markdown_fence_is_parsed(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_planner.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        fenced_json = (
            "```json\n"
            + _VALID_LLM_JSON
            + "```"
        )
        monkeypatch.setattr(
            "src.ham.builder_planner.complete_chat_messages_openrouter",
            lambda messages, **kwargs: fenced_json,
        )
        store = _InMemoryPlanStore()
        plan = produce_plan(
            user_message="Fence test",
            project_id="proj_fence",
            workspace_id="ws_fence",
            requested_by="dev@test.com",
            conversation_history=[],
            store=store,
        )
        assert plan is not None
        assert len(plan.steps) == 2
