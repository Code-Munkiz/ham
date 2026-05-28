"""Tests for Build Registry v2 opt-in scaffold context wiring (ADR-0017 Phase 2C)."""

from __future__ import annotations

from pathlib import Path

from src.ham.builder_llm_scaffold import _build_scaffold_messages
from src.ham.builder_plan import Plan, Step

REPO_ROOT = Path(__file__).resolve().parent.parent


def _make_plan(
    template_kind: str = "todo",
    *,
    metadata: dict | None = None,
) -> Plan:
    plan_metadata = {"template_kind": template_kind}
    if metadata:
        plan_metadata.update(metadata)
    return Plan(
        plan_id="pln_registry_context_test",
        workspace_id="ws_test",
        project_id="proj_test",
        user_message="Build a todo app",
        steps=[Step(title="Scaffold app", description="Create initial files")],
        planner_confidence="high",
        metadata=plan_metadata,
    )


def _user_content(messages: list[dict]) -> str:
    return messages[1]["content"]


class TestRegistryContextFlagDisabled:
    def test_build_scaffold_messages_remain_v1_style(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        messages = _build_scaffold_messages(_make_plan(template_kind="todo"))
        content = _user_content(messages)
        assert "Builder Kit context:" in content
        assert "Builder Kit: todo" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content


class TestRegistryContextMetadataMissing:
    def test_flag_enabled_without_app_type_falls_back_to_v1(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "true")
        messages = _build_scaffold_messages(_make_plan(template_kind="landing-page"))
        content = _user_content(messages)
        assert "Builder Kit context:" in content
        assert "Builder Kit: landing-page" in content
        assert "Build Registry v2 playbook context:" not in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content


class TestRegistryContextV2Success:
    def test_flag_enabled_with_app_type_injects_v2_playbook(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "1")
        plan = _make_plan(
            template_kind="generic",
            metadata={"registry_v2_app_type": "game.idle-incremental"},
        )
        messages = _build_scaffold_messages(plan)
        content = _user_content(messages)
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.idle-incremental" in content
        assert "stack.dom-game-minimal" in content
        assert "validator.no-negative-currency" in content
        assert "Builder Kit context:" not in content
        assert content.count("Builder Kit:") == 0

    def test_flag_enabled_with_landing_page_app_type_injects_v2_playbook(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "1")
        plan = _make_plan(
            template_kind="landing-page",
            metadata={"registry_v2_app_type": "site.landing-page-core"},
        )
        messages = _build_scaffold_messages(plan)
        content = _user_content(messages)
        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "site.landing-page-core" in content
        assert "stack.dom-marketing-minimal" in content
        assert "section.landing-hero" in content
        assert "section.final-conversion" in content
        assert "Builder Kit context:" not in content
        assert content.count("Builder Kit:") == 0


class TestRegistryContextBadAppType:
    def test_unknown_app_type_falls_back_to_v1_without_exception(self, monkeypatch):
        monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "yes")
        plan = _make_plan(
            template_kind="todo",
            metadata={"registry_v2_app_type": "game.does-not-exist"},
        )
        messages = _build_scaffold_messages(plan)
        content = _user_content(messages)
        assert "Builder Kit context:" in content
        assert "Builder Kit: todo" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content


class TestRegistryContextExplicitEnv:
    def test_env_override_can_disable_v2_even_with_metadata(self):
        plan = _make_plan(
            template_kind="generic",
            metadata={"registry_v2_app_type": "game.idle-incremental"},
        )
        messages = _build_scaffold_messages(
            plan,
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "false"},
        )
        content = _user_content(messages)
        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content
