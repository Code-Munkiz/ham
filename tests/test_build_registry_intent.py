"""Tests for Build Registry v2 prompt intent routing (ADR-0017 Phase 2E)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.ham.builder_chat_scaffold import _maybe_llm_scaffold_replace
from src.ham.builder_llm_scaffold import ScaffoldResult, _build_scaffold_messages
from src.ham.builder_plan import Plan, Step
from src.ham.build_registry.intent import (
    BRANCHING_NARRATIVE_APP_TYPE,
    IDLE_INCREMENTAL_APP_TYPE,
    TRIVIA_TIMER_APP_TYPE,
    enrich_plan_metadata_with_registry_v2,
    select_registry_v2_app_type_for_prompt,
)
from src.ham.clerk_auth import HamActor

_IDLE_POSITIVE_PROMPTS = (
    "build me an idle clicker game",
    "make a cookie clicker style game",
    "create an incremental tycoon game",
    "build a game where I earn coins and buy upgrades",
    "make a mining clicker with passive income",
)

_IDLE_NEGATIVE_PROMPTS = (
    "build me a SaaS dashboard",
    "make a landing page",
    "build Tetris",
    "make a platformer",
    "make a crypto trading dashboard",
    "build a game",
    "make an arcade game",
    "build an idle clicker game with trivia rounds",
)

_TRIVIA_POSITIVE_PROMPTS = (
    "Build me a trivia quiz with a timer",
    "Make a timed multiple choice quiz game",
    "Create a 10 question trivia game with score",
    "Build a quiz game with a countdown timer",
    "Make a history trivia game where each question has 15 seconds",
    "Create a multiple choice trivia challenge",
    "create a trivia game",
)

_TRIVIA_NEGATIVE_PROMPTS = (
    "Build me a survey form",
    "Make a flashcard app",
    "Create an education website",
    "Build a SaaS dashboard",
    "Make a generic quiz app",
    "Build a form with multiple choice questions",
    "Make a trading dashboard",
    "Build a memory card game",
)

_BRANCHING_POSITIVE_PROMPTS = (
    "Build me a branching story game",
    "Make a choose your own adventure game",
    "Create an interactive fiction game",
    "Build a dialogue choice RPG",
    "Make a story game where choices change the ending",
    "Create a narrative game with multiple endings",
    "Build a text adventure with inventory and choices",
)

_BRANCHING_NEGATIVE_PROMPTS = (
    "Build me a blog",
    "Make a chatbot",
    "Create a writing app",
    "Build an AI dungeon with live generated story text",
    "Build a SaaS dashboard",
    "Make a generic RPG",
    "Create a landing page for my book",
)

_CROSS_EXCLUSION_PROMPTS = (
    ("build me an idle clicker game", IDLE_INCREMENTAL_APP_TYPE),
    ("Build me a trivia quiz with a timer", TRIVIA_TIMER_APP_TYPE),
    ("Build me a branching story game", BRANCHING_NARRATIVE_APP_TYPE),
    ("make a cookie clicker style game", IDLE_INCREMENTAL_APP_TYPE),
    ("Make a timed multiple choice quiz game", TRIVIA_TIMER_APP_TYPE),
    ("Make a choose your own adventure game", BRANCHING_NARRATIVE_APP_TYPE),
)


class TestSelectRegistryV2AppTypeForPrompt:
    @pytest.mark.parametrize("prompt", _IDLE_POSITIVE_PROMPTS)
    def test_matches_idle_incremental_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == IDLE_INCREMENTAL_APP_TYPE

    @pytest.mark.parametrize("prompt", _IDLE_NEGATIVE_PROMPTS)
    def test_rejects_non_idle_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) is None

    @pytest.mark.parametrize("prompt", _TRIVIA_POSITIVE_PROMPTS)
    def test_matches_trivia_timer_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == TRIVIA_TIMER_APP_TYPE

    @pytest.mark.parametrize("prompt", _TRIVIA_NEGATIVE_PROMPTS)
    def test_rejects_non_trivia_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) is None

    @pytest.mark.parametrize("prompt", _BRANCHING_POSITIVE_PROMPTS)
    def test_matches_branching_narrative_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == BRANCHING_NARRATIVE_APP_TYPE

    @pytest.mark.parametrize("prompt", _BRANCHING_NEGATIVE_PROMPTS)
    def test_rejects_non_branching_prompts(self, prompt: str):
        assert select_registry_v2_app_type_for_prompt(prompt) is None

    @pytest.mark.parametrize("prompt,expected", _CROSS_EXCLUSION_PROMPTS)
    def test_recipes_do_not_steal_each_other(self, prompt: str, expected: str):
        assert select_registry_v2_app_type_for_prompt(prompt) == expected

    def test_idle_prompt_does_not_route_to_trivia(self):
        assert (
            select_registry_v2_app_type_for_prompt("Build an idle clicker game")
            == IDLE_INCREMENTAL_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("Build an idle clicker game")
            != TRIVIA_TIMER_APP_TYPE
        )

    def test_branching_prompt_does_not_route_to_idle_or_trivia(self):
        prompt = "Build me a branching story game"
        assert select_registry_v2_app_type_for_prompt(prompt) == BRANCHING_NARRATIVE_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != IDLE_INCREMENTAL_APP_TYPE
        assert select_registry_v2_app_type_for_prompt(prompt) != TRIVIA_TIMER_APP_TYPE

    def test_trivia_and_idle_prompts_do_not_route_to_branching(self):
        assert (
            select_registry_v2_app_type_for_prompt("Build me a trivia quiz with a timer")
            == TRIVIA_TIMER_APP_TYPE
        )
        assert (
            select_registry_v2_app_type_for_prompt("build me an idle clicker game")
            == IDLE_INCREMENTAL_APP_TYPE
        )


class TestEnrichPlanMetadataWithRegistryV2:
    def test_flag_disabled_does_not_add_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "build me an idle clicker game",
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_disabled_trivia_prompt_does_not_add_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a trivia quiz with a timer",
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_disabled_branching_prompt_does_not_add_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a branching story game",
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_enabled_idle_prompt_adds_registry_metadata(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic", "originated_from": "builder_chat_scaffold"},
            "build me an idle clicker game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        assert metadata["registry_v2_app_type"] == IDLE_INCREMENTAL_APP_TYPE
        assert metadata["template_kind"] == "generic"
        assert metadata["originated_from"] == "builder_chat_scaffold"

    def test_flag_enabled_trivia_prompt_adds_registry_metadata(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic", "originated_from": "builder_chat_scaffold"},
            "Build me a trivia quiz with a timer",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        assert metadata["registry_v2_app_type"] == TRIVIA_TIMER_APP_TYPE
        assert metadata["template_kind"] == "generic"
        assert metadata["originated_from"] == "builder_chat_scaffold"

    def test_flag_enabled_branching_prompt_adds_registry_metadata(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic", "originated_from": "builder_chat_scaffold"},
            "Build me a branching story game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        assert metadata["registry_v2_app_type"] == BRANCHING_NARRATIVE_APP_TYPE
        assert metadata["template_kind"] == "generic"
        assert metadata["originated_from"] == "builder_chat_scaffold"

    def test_flag_enabled_non_idle_prompt_leaves_registry_metadata_absent(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "landing-page"},
            "build me a landing page",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "landing-page"

    def test_flag_enabled_non_trivia_prompt_leaves_registry_metadata_absent(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Make a flashcard app",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"

    def test_flag_enabled_non_branching_prompt_leaves_registry_metadata_absent(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Make a chatbot",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
        )
        assert "registry_v2_app_type" not in metadata
        assert metadata["template_kind"] == "generic"


def _byo_actor() -> HamActor:
    return HamActor(
        user_id="user_registry_intent",
        org_id=None,
        session_id=None,
        email="user_registry_intent@example.com",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _synthetic_plan_metadata(user_message: str) -> dict:
    captured: dict = {}

    def _fake_generate_scaffold(plan, **_kw):
        captured["metadata"] = dict(plan.metadata or {})
        return ScaffoldResult(
            file_changes=[("src/App.tsx", "export default function App(){return null;}")],
            assertions=[],
        )

    with (
        patch(
            "src.llm_client.resolve_openrouter_api_key_for_actor",
            return_value="sk-or-v1-test_registry_intent",
        ),
        patch(
            "src.ham.builder_llm_scaffold._get_scaffold_model",
            return_value="openrouter/anthropic/claude-3.5-haiku",
        ),
        patch(
            "src.ham.builder_llm_scaffold.generate_scaffold",
            side_effect=_fake_generate_scaffold,
        ),
    ):
        _maybe_llm_scaffold_replace(
            user_message=user_message,
            workspace_id="ws_registry",
            project_id="proj_registry",
            files={"src/App.tsx": "// placeholder"},
            scaffold_meta={},
            ham_actor=_byo_actor(),
        )
    return captured["metadata"]


class TestChatScaffoldSyntheticPlanMetadata:
    def test_flag_disabled_idle_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = _synthetic_plan_metadata("build me an idle clicker game")
        assert metadata.get("template_kind") == "generic"
        assert "registry_v2_app_type" not in metadata

    def test_flag_disabled_trivia_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = _synthetic_plan_metadata("Build me a trivia quiz with a timer")
        assert metadata.get("template_kind") == "generic"
        assert "registry_v2_app_type" not in metadata

    def test_flag_disabled_branching_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = _synthetic_plan_metadata("Build me a branching story game")
        assert metadata.get("template_kind") == "generic"
        assert "registry_v2_app_type" not in metadata

    def test_flag_enabled_idle_prompt_adds_registry_metadata(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata("build me an idle clicker game")
        assert metadata.get("template_kind") == "generic"
        assert metadata.get("registry_v2_app_type") == IDLE_INCREMENTAL_APP_TYPE

    def test_flag_enabled_trivia_prompt_adds_registry_metadata(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata("Build me a trivia quiz with a timer")
        assert metadata.get("template_kind") == "generic"
        assert metadata.get("registry_v2_app_type") == TRIVIA_TIMER_APP_TYPE

    def test_flag_enabled_branching_prompt_adds_registry_metadata(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata("Build me a branching story game")
        assert metadata.get("template_kind") == "generic"
        assert metadata.get("registry_v2_app_type") == BRANCHING_NARRATIVE_APP_TYPE

    def test_flag_enabled_non_idle_prompt_has_no_registry_metadata(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        metadata = _synthetic_plan_metadata("build me a landing page for roofers")
        assert metadata.get("template_kind") == "landing-page"
        assert "registry_v2_app_type" not in metadata


class TestEndToEndScaffoldMessages:
    def test_flag_enabled_idle_prompt_produces_v2_context(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "build me an idle clicker game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        plan = Plan(
            plan_id="pln_registry_intent_e2e",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="build me an idle clicker game",
            steps=[Step(title="Scaffold game", description="Create idle clicker files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )[1]["content"]
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.idle-incremental" in content
        assert "Builder Kit context:" not in content

    def test_flag_enabled_trivia_prompt_produces_v2_context(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a trivia quiz with a timer",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        plan = Plan(
            plan_id="pln_registry_intent_trivia_e2e",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a trivia quiz with a timer",
            steps=[Step(title="Scaffold game", description="Create trivia quiz files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )[1]["content"]
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.trivia-timer" in content
        assert "stack.dom-game-minimal" in content
        assert "validator.timer-cleanup" in content
        assert "Builder Kit context:" not in content
        assert content.count("Builder Kit:") == 0

    def test_flag_enabled_branching_prompt_produces_v2_context(self):
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a branching story game",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )
        plan = Plan(
            plan_id="pln_registry_intent_branching_e2e",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a branching story game",
            steps=[Step(title="Scaffold game", description="Create branching story files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
        )[1]["content"]
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.branching-narrative" in content
        assert "stack.dom-game-minimal" in content
        assert "validator.story-graph-reachability" in content
        assert "validator.no-dead-end-choice" in content
        assert "Builder Kit context:" not in content
        assert content.count("Builder Kit:") == 0

    def test_flag_disabled_idle_prompt_produces_v1_context_only(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "build me an idle clicker game",
        )
        plan = Plan(
            plan_id="pln_registry_intent_v1",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="build me an idle clicker game",
            steps=[Step(title="Scaffold game", description="Create idle clicker files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(plan)[1]["content"]
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content

    def test_flag_disabled_trivia_prompt_produces_v1_context_only(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a trivia quiz with a timer",
        )
        plan = Plan(
            plan_id="pln_registry_intent_trivia_v1",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a trivia quiz with a timer",
            steps=[Step(title="Scaffold game", description="Create trivia quiz files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(plan)[1]["content"]
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content

    def test_flag_disabled_branching_prompt_produces_v1_context_only(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": "generic"},
            "Build me a branching story game",
        )
        plan = Plan(
            plan_id="pln_registry_intent_branching_v1",
            workspace_id="ws_test",
            project_id="proj_test",
            user_message="Build me a branching story game",
            steps=[Step(title="Scaffold game", description="Create branching story files")],
            planner_confidence="high",
            metadata=metadata,
        )
        content = _build_scaffold_messages(plan)[1]["content"]
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content
