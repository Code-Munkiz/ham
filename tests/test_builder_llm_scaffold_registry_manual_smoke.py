"""Phase 2D — internal manual opt-in smoke for Build Registry v2 scaffold context.

Safe operator smoke: exercises ``_build_scaffold_messages()`` only. No OpenRouter,
no ``generate_scaffold()`` network path, no chat/API wiring.

Run locally:
    pytest tests/test_builder_llm_scaffold_registry_manual_smoke.py -q

Opt-in requires both:
    HAM_BUILD_REGISTRY_V2_ENABLED=1  (or true/yes/on)
    plan.metadata["registry_v2_app_type"] = "<app-type-id>"
"""

from __future__ import annotations

from src.ham.builder_llm_scaffold import _build_scaffold_messages
from src.ham.builder_plan import Plan, Step

_V2_ENABLED_ENV = {"HAM_BUILD_REGISTRY_V2_ENABLED": "1"}
_V2_DISABLED_ENV = {"HAM_BUILD_REGISTRY_V2_ENABLED": "false"}


def _synthetic_idle_incremental_plan() -> Plan:
    """Synthetic Plan an internal operator could construct for manual v2 smoke."""
    return Plan(
        plan_id="pln_manual_registry_v2_smoke",
        workspace_id="ws_manual_smoke",
        project_id="proj_manual_smoke",
        user_message="Build an idle incremental game with upgrades and save/load.",
        steps=[
            Step(
                title="Scaffold idle incremental shell",
                description="Create DOM game shell, economy loop, and upgrade UI.",
            ),
            Step(
                title="Wire save/load",
                description="Persist player progress locally.",
            ),
        ],
        planner_confidence="high",
        metadata={
            "template_kind": "generic",
            "registry_v2_app_type": "game.idle-incremental",
        },
    )


def _user_content(messages: list[dict]) -> str:
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    return messages[1]["content"]


class TestManualRegistryV2SmokeEnabled:
    """Synthetic Plan + env override → v2 playbook in scaffold user message."""

    def test_scaffold_messages_include_v2_playbook_without_v1_duplicate(self):
        plan = _synthetic_idle_incremental_plan()
        messages = _build_scaffold_messages(plan, env=_V2_ENABLED_ENV)
        content = _user_content(messages)

        assert "Build Registry v2 playbook context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" in content
        assert "game.idle-incremental" in content
        assert "stack.dom-game-minimal" in content
        assert "validator.no-negative-currency" in content
        assert "Builder Kit context:" not in content


class TestManualRegistryV2SmokeDisabled:
    """Same synthetic Plan with flag off → unchanged v1 Builder Kit path."""

    def test_scaffold_messages_remain_v1_when_env_disabled(self):
        plan = _synthetic_idle_incremental_plan()
        messages = _build_scaffold_messages(plan, env=_V2_DISABLED_ENV)
        content = _user_content(messages)

        assert "Builder Kit context:" in content
        assert "Builder Kit: generic" in content
        assert "Build Registry v2 playbook context:" not in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content

    def test_scaffold_messages_remain_v1_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
        plan = _synthetic_idle_incremental_plan()
        messages = _build_scaffold_messages(plan)
        content = _user_content(messages)

        assert "Builder Kit context:" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content


class TestManualRegistryV2SmokeBadAppType:
    """Bad app type with flag on → safe v1 fallback, no exception."""

    def test_unknown_app_type_falls_back_to_v1(self):
        plan = _synthetic_idle_incremental_plan()
        plan.metadata["registry_v2_app_type"] = "game.does-not-exist"
        messages = _build_scaffold_messages(plan, env=_V2_ENABLED_ENV)
        content = _user_content(messages)

        assert "Builder Kit context:" in content
        assert "Builder Kit: generic" in content
        assert "Build Kit Registry v2 — BuildRecipe" not in content
