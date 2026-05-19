"""Tests for src/ham/builder_llm_scaffold.py — Phase 2 Subsystem 9."""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.ham.builder_error_codes import STEP_MODEL_UNAVAILABLE, STEP_VERIFICATION_FAILED
from src.ham.builder_llm_scaffold import (
    LLMScaffoldError,
    ScaffoldResult,
    _build_scaffold_messages,
    _extract_json,
    _parse_scaffold_result,
    generate_scaffold,
)
from src.ham.builder_plan import Plan, Step


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_VALID_LLM_JSON = json.dumps(
    {
        "file_changes": [
            {
                "path": "src/App.tsx",
                "content": "const App = () => <div>Hello</div>; export default App;",
            },
            {"path": "src/index.css", "content": "body { margin: 0; }"},
        ],
        "assertions": [
            "The app renders without errors",
            "The UI matches the requested template kind",
        ],
    }
)

_MINIMAL_LLM_JSON = json.dumps(
    {
        "file_changes": [
            {"path": "index.html", "content": "<html><body>Hello</body></html>"},
        ],
        "assertions": [],
    }
)


def _make_plan(
    template_kind: str = "todo",
    *,
    workspace_id: str = "ws_test",
    project_id: str = "proj_test",
    steps: list[Step] | None = None,
) -> Plan:
    if steps is None:
        steps = [Step(title="Scaffold todo app", description="Create initial files")]
    return Plan(
        plan_id="pln_scaffold_test",
        workspace_id=workspace_id,
        project_id=project_id,
        user_message="Build a todo app",
        steps=steps,
        planner_confidence="high",
        metadata={"template_kind": template_kind},
    )


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_plain_json_passes_through(self):
        raw = '{"foo": "bar"}'
        assert _extract_json(raw) == raw

    def test_strips_markdown_json_fence(self):
        raw = '```json\n{"foo": "bar"}\n```'
        assert _extract_json(raw) == '{"foo": "bar"}'

    def test_strips_unmarked_fence(self):
        raw = '```\n{"x": 1}\n```'
        result = _extract_json(raw)
        assert '{"x": 1}' in result

    def test_extracts_outermost_braces_from_prose(self):
        raw = 'Here is the JSON: {"a": 1} and done.'
        assert _extract_json(raw) == '{"a": 1}'

    def test_empty_string_returns_empty(self):
        assert _extract_json("") == ""

    def test_nested_braces_preserved(self):
        raw = '{"outer": {"inner": 1}}'
        assert _extract_json(raw) == raw

    def test_no_brace_returns_stripped_text(self):
        raw = "no json here at all"
        result = _extract_json(raw)
        assert result == "no json here at all"


# ---------------------------------------------------------------------------
# _parse_scaffold_result
# ---------------------------------------------------------------------------


class TestParseScaffoldResult:
    def test_valid_json_returns_scaffold_result(self):
        result = _parse_scaffold_result(_VALID_LLM_JSON)
        assert isinstance(result, ScaffoldResult)

    def test_file_changes_has_correct_length(self):
        result = _parse_scaffold_result(_VALID_LLM_JSON)
        assert len(result.file_changes) == 2

    def test_file_changes_paths_correct(self):
        result = _parse_scaffold_result(_VALID_LLM_JSON)
        paths = [fc[0] for fc in result.file_changes]
        assert "src/App.tsx" in paths
        assert "src/index.css" in paths

    def test_file_content_preserved(self):
        result = _parse_scaffold_result(_VALID_LLM_JSON)
        content_map = dict(result.file_changes)
        assert "Hello" in content_map["src/App.tsx"]

    def test_assertions_parsed_correctly(self):
        result = _parse_scaffold_result(_VALID_LLM_JSON)
        assert len(result.assertions) == 2
        assert "renders without errors" in result.assertions[0]

    def test_empty_assertions_allowed(self):
        result = _parse_scaffold_result(_MINIMAL_LLM_JSON)
        assert result.assertions == []

    def test_single_file_is_valid(self):
        result = _parse_scaffold_result(_MINIMAL_LLM_JSON)
        assert len(result.file_changes) == 1

    def test_invalid_json_raises_json_decode_error(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_scaffold_result("not json at all")

    def test_empty_file_changes_raises_value_error(self):
        payload = json.dumps({"file_changes": [], "assertions": []})
        with pytest.raises(ValueError, match="empty"):
            _parse_scaffold_result(payload)

    def test_missing_file_changes_key_raises_value_error(self):
        payload = json.dumps({"assertions": ["OK"]})
        # file_changes defaults to [] which triggers the "empty" error
        with pytest.raises(ValueError):
            _parse_scaffold_result(payload)

    def test_empty_path_entries_are_skipped(self):
        payload = json.dumps(
            {
                "file_changes": [
                    {"path": "", "content": "ignored"},
                    {"path": "real.ts", "content": "kept"},
                ],
                "assertions": [],
            }
        )
        result = _parse_scaffold_result(payload)
        paths = [p for p, _ in result.file_changes]
        assert "" not in paths
        assert "real.ts" in paths

    def test_non_dict_items_skipped(self):
        payload = json.dumps(
            {
                "file_changes": [
                    "not a dict",
                    {"path": "good.ts", "content": "good"},
                ],
                "assertions": [],
            }
        )
        result = _parse_scaffold_result(payload)
        assert len(result.file_changes) == 1
        assert result.file_changes[0][0] == "good.ts"

    def test_file_changes_are_tuples(self):
        result = _parse_scaffold_result(_VALID_LLM_JSON)
        for item in result.file_changes:
            assert isinstance(item, tuple)
            assert len(item) == 2

    def test_non_string_assertions_skipped(self):
        payload = json.dumps(
            {
                "file_changes": [{"path": "a.ts", "content": "x"}],
                "assertions": ["OK", 42, None, "Also OK"],
            }
        )
        result = _parse_scaffold_result(payload)
        # Only string assertions are kept
        assert result.assertions == ["OK", "Also OK"]


# ---------------------------------------------------------------------------
# _build_scaffold_messages
# ---------------------------------------------------------------------------


class TestBuildScaffoldMessages:
    def test_returns_two_messages(self):
        plan = _make_plan()
        messages = _build_scaffold_messages(plan)
        assert len(messages) == 2

    def test_first_message_is_system(self):
        plan = _make_plan()
        messages = _build_scaffold_messages(plan)
        assert messages[0]["role"] == "system"

    def test_second_message_is_user(self):
        plan = _make_plan()
        messages = _build_scaffold_messages(plan)
        assert messages[1]["role"] == "user"

    def test_user_message_contains_template_kind(self):
        plan = _make_plan(template_kind="dashboard")
        messages = _build_scaffold_messages(plan)
        assert "dashboard" in messages[1]["content"]

    def test_user_message_contains_plan_user_message(self):
        plan = _make_plan()
        messages = _build_scaffold_messages(plan)
        assert plan.user_message in messages[1]["content"]

    def test_user_message_contains_step_titles(self):
        plan = _make_plan(
            steps=[
                Step(title="Create files", description="Generate initial scaffold"),
                Step(title="Add styling", description="Apply CSS"),
            ]
        )
        messages = _build_scaffold_messages(plan)
        content = messages[1]["content"]
        assert "Create files" in content
        assert "Add styling" in content

    def test_unknown_template_kind_shows_as_unknown(self):
        # Plan with no template_kind in metadata
        plan = Plan(
            plan_id="pln_x",
            workspace_id="ws_x",
            project_id="proj_x",
            user_message="Build something",
            steps=[Step(title="Step 1", description="Do it")],
            planner_confidence="medium",
        )
        messages = _build_scaffold_messages(plan)
        assert "unknown" in messages[1]["content"]


# ---------------------------------------------------------------------------
# generate_scaffold — no API key
# ---------------------------------------------------------------------------


class TestGenerateScaffoldNoKey:
    def test_raises_llm_scaffold_error_when_no_api_key(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "",
        )
        plan = _make_plan()
        with pytest.raises(LLMScaffoldError) as exc_info:
            generate_scaffold(plan, project_id="proj_test", workspace_id="ws_test")
        assert exc_info.value.error_code == STEP_MODEL_UNAVAILABLE

    def test_no_key_error_message_is_informative(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "",
        )
        plan = _make_plan()
        with pytest.raises(LLMScaffoldError) as exc_info:
            generate_scaffold(plan, project_id="proj_test", workspace_id="ws_test")
        assert "OpenRouter" in str(exc_info.value)


# ---------------------------------------------------------------------------
# generate_scaffold — success
# ---------------------------------------------------------------------------


class TestGenerateScaffoldSuccess:
    def test_passes_ham_actor_to_key_resolver(self, monkeypatch):
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
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            _resolve,
        )
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.complete_chat_messages_openrouter",
            lambda messages, **kwargs: _VALID_LLM_JSON,
        )
        plan = _make_plan()
        result = generate_scaffold(
            plan,
            project_id="proj_test",
            workspace_id="ws_test",
            ham_actor=actor,
        )
        assert isinstance(result, ScaffoldResult)
        assert seen == [actor]

    def test_returns_scaffold_result_on_success(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.complete_chat_messages_openrouter",
            lambda messages, **kwargs: _VALID_LLM_JSON,
        )
        plan = _make_plan()
        result = generate_scaffold(plan, project_id="proj_test", workspace_id="ws_test")
        assert isinstance(result, ScaffoldResult)

    def test_file_changes_populated(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.complete_chat_messages_openrouter",
            lambda messages, **kwargs: _VALID_LLM_JSON,
        )
        plan = _make_plan()
        result = generate_scaffold(plan, project_id="proj_test", workspace_id="ws_test")
        assert len(result.file_changes) == 2

    def test_assertions_populated(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.complete_chat_messages_openrouter",
            lambda messages, **kwargs: _VALID_LLM_JSON,
        )
        plan = _make_plan()
        result = generate_scaffold(plan, project_id="proj_test", workspace_id="ws_test")
        assert len(result.assertions) == 2

    def test_minimal_json_succeeds(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.complete_chat_messages_openrouter",
            lambda messages, **kwargs: _MINIMAL_LLM_JSON,
        )
        plan = _make_plan()
        result = generate_scaffold(plan, project_id="proj_test", workspace_id="ws_test")
        assert isinstance(result, ScaffoldResult)
        assert len(result.file_changes) == 1
        assert result.assertions == []

    def test_llm_receives_template_kind_in_messages(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        captured: list[list[dict]] = []

        def _capture(messages, **kwargs):
            captured.append(list(messages))
            return _VALID_LLM_JSON

        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.complete_chat_messages_openrouter",
            _capture,
        )
        plan = _make_plan(template_kind="dashboard")
        generate_scaffold(plan, project_id="proj_test", workspace_id="ws_test")
        assert captured, "complete_chat_messages_openrouter was not called"
        content = captured[0][1]["content"]  # user message
        assert "dashboard" in content


# ---------------------------------------------------------------------------
# generate_scaffold — retry on invalid JSON
# ---------------------------------------------------------------------------


class TestGenerateScaffoldRetry:
    def test_retries_once_on_invalid_json(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        call_count = 0

        def _flaky_complete(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "not json at all"
            return _VALID_LLM_JSON

        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.complete_chat_messages_openrouter",
            _flaky_complete,
        )
        plan = _make_plan()
        result = generate_scaffold(plan, project_id="proj_test", workspace_id="ws_test")
        assert isinstance(result, ScaffoldResult)
        assert call_count == 2

    def test_raises_after_two_json_failures(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.complete_chat_messages_openrouter",
            lambda messages, **kwargs: "definitely not json",
        )
        plan = _make_plan()
        with pytest.raises(LLMScaffoldError) as exc_info:
            generate_scaffold(plan, project_id="proj_test", workspace_id="ws_test")
        assert exc_info.value.error_code == STEP_VERIFICATION_FAILED

    def test_raises_after_two_empty_file_changes(self, monkeypatch):
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        # Produces valid JSON but empty file_changes — both attempts fail
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.complete_chat_messages_openrouter",
            lambda messages, **kwargs: json.dumps({"file_changes": [], "assertions": []}),
        )
        plan = _make_plan()
        with pytest.raises(LLMScaffoldError) as exc_info:
            generate_scaffold(plan, project_id="proj_test", workspace_id="ws_test")
        assert exc_info.value.error_code == STEP_VERIFICATION_FAILED

    def test_retry_uses_stricter_system_prompt(self, monkeypatch):
        """Second attempt's system message should contain the strictness text."""
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test-key",
        )
        system_prompts: list[str] = []
        call_count = 0

        def _capture(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            system_prompts.append(messages[0]["content"])
            if call_count == 1:
                return "not json"
            return _VALID_LLM_JSON

        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.complete_chat_messages_openrouter",
            _capture,
        )
        plan = _make_plan()
        generate_scaffold(plan, project_id="proj_test", workspace_id="ws_test")
        assert len(system_prompts) == 2
        # Second prompt should differ (stricter)
        assert system_prompts[0] != system_prompts[1]
        assert "previous response" in system_prompts[1].lower() or "not valid" in system_prompts[1].lower()


# ---------------------------------------------------------------------------
# LLMScaffoldError
# ---------------------------------------------------------------------------


class TestLLMScaffoldError:
    def test_error_code_attribute_set(self):
        exc = LLMScaffoldError("Test error", error_code=STEP_VERIFICATION_FAILED)
        assert exc.error_code == STEP_VERIFICATION_FAILED

    def test_model_unavailable_code(self):
        exc = LLMScaffoldError("No key", error_code=STEP_MODEL_UNAVAILABLE)
        assert exc.error_code == STEP_MODEL_UNAVAILABLE

    def test_is_exception_subclass(self):
        exc = LLMScaffoldError("msg", error_code=STEP_VERIFICATION_FAILED)
        assert isinstance(exc, Exception)

    def test_str_contains_message(self):
        exc = LLMScaffoldError("LLM failed badly", error_code=STEP_VERIFICATION_FAILED)
        assert "LLM failed badly" in str(exc)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(LLMScaffoldError) as exc_info:
            raise LLMScaffoldError("raised", error_code=STEP_VERIFICATION_FAILED)
        assert exc_info.value.error_code == STEP_VERIFICATION_FAILED


# ---------------------------------------------------------------------------
# ScaffoldResult dataclass
# ---------------------------------------------------------------------------


class TestScaffoldResult:
    def test_file_changes_is_list(self):
        result = ScaffoldResult(file_changes=[("a.ts", "content")])
        assert isinstance(result.file_changes, list)

    def test_assertions_default_is_empty_list(self):
        result = ScaffoldResult(file_changes=[("a.ts", "x")])
        assert result.assertions == []

    def test_assertions_can_be_set(self):
        result = ScaffoldResult(
            file_changes=[("a.ts", "x")],
            assertions=["The app works"],
        )
        assert len(result.assertions) == 1
