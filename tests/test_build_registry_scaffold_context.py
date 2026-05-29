"""Tests for build_registry scaffold context resolver (ADR-0017 Phase 2B)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.ham.build_registry.scaffold_context import (
    V1_HEADER,
    V2_HEADER,
    resolve_pack_root,
    resolve_scaffold_context,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestResolveScaffoldContextFlagDisabled:
    def test_returns_v1_when_flag_disabled(self):
        result = resolve_scaffold_context(
            metadata={"registry_v2_app_type": "game.idle-incremental"},
            template_kind="todo",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "false"},
            repo_root=REPO_ROOT,
        )
        assert result.source == "v1"
        assert result.fallback_reason == "registry_v2_disabled"
        assert result.header == V1_HEADER
        assert "Builder Kit: todo" in result.context
        assert result.registry_v2_app_type is None


class TestResolvePackRoot:
    def test_resolves_site_prefix_to_website_pack(self):
        path = resolve_pack_root(
            metadata=None,
            repo_root=REPO_ROOT,
            app_type_id="site.dashboard-ui-core",
        )
        assert path.as_posix().endswith("docs/build-kit-registry-v2/website-pack")

    def test_resolves_app_prefix_to_website_pack(self):
        path = resolve_pack_root(
            metadata=None,
            repo_root=REPO_ROOT,
            app_type_id="app.saas-dashboard-core",
        )
        assert path.as_posix().endswith("docs/build-kit-registry-v2/website-pack")

    def test_resolves_game_prefix_to_game_pack(self):
        path = resolve_pack_root(
            metadata=None,
            repo_root=REPO_ROOT,
            app_type_id="game.idle-incremental",
        )
        assert path.as_posix().endswith("docs/build-kit-registry-v2/game-pack")

    def test_unknown_prefix_falls_back_to_game_pack(self):
        path = resolve_pack_root(
            metadata=None,
            repo_root=REPO_ROOT,
            app_type_id="unknown.bad-type",
        )
        assert path.as_posix().endswith("docs/build-kit-registry-v2/game-pack")


class TestResolveScaffoldContextMetadataMissing:
    def test_returns_v1_when_metadata_missing_app_type(self):
        result = resolve_scaffold_context(
            metadata={},
            template_kind="landing-page",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "true"},
            repo_root=REPO_ROOT,
        )
        assert result.source == "v1"
        assert result.fallback_reason == "registry_v2_metadata_missing"
        assert "Builder Kit: landing-page" in result.context


class TestResolveScaffoldContextV2Success:
    def test_returns_v2_playbook_context(self):
        result = resolve_scaffold_context(
            metadata={"registry_v2_app_type": "game.idle-incremental"},
            template_kind="generic",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
            repo_root=REPO_ROOT,
        )
        assert result.source == "v2"
        assert result.header == V2_HEADER
        assert result.fallback_reason is None
        assert result.registry_v2_app_type == "game.idle-incremental"
        assert result.registry_v2_pack_id == "pack.game"
        assert "Build Kit Registry v2 — BuildRecipe" in result.context
        assert "game.idle-incremental" in result.context
        assert "stack.dom-game-minimal" in result.context
        assert "validator.no-negative-currency" in result.context
        assert "Builder Kit:" not in result.context
        assert len(result.context) <= 12_000

    def test_returns_v2_playbook_context_for_turn_based_tactics_lite(self):
        result = resolve_scaffold_context(
            metadata={"registry_v2_app_type": "game.turn-based-tactics-lite"},
            template_kind="generic",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
            repo_root=REPO_ROOT,
        )
        assert result.source == "v2"
        assert result.registry_v2_app_type == "game.turn-based-tactics-lite"
        assert "game.turn-based-tactics-lite" in result.context
        for mechanic_id in (
            "mechanic.tactics-grid-board-state",
            "mechanic.tactics-unit-roster",
            "mechanic.tactics-selection-state",
            "mechanic.tactics-movement-range",
            "mechanic.tactics-attack-resolution",
            "mechanic.tactics-turn-loop",
            "mechanic.tactics-enemy-response",
            "mechanic.tactics-battle-result-state",
        ):
            assert mechanic_id in result.context
        assert "Builder Kit:" not in result.context

    def test_returns_v2_playbook_context_for_city_builder_lite(self):
        result = resolve_scaffold_context(
            metadata={"registry_v2_app_type": "game.city-builder-lite"},
            template_kind="generic",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
            repo_root=REPO_ROOT,
        )
        assert result.source == "v2"
        assert result.registry_v2_app_type == "game.city-builder-lite"
        assert "game.city-builder-lite" in result.context
        for mechanic_id in (
            "mechanic.city-grid-state",
            "mechanic.city-building-catalog",
            "mechanic.city-placement-rules",
            "mechanic.city-resource-pools",
            "mechanic.city-production-tick",
            "mechanic.city-population-happiness",
            "mechanic.city-upgrade-choice",
            "mechanic.city-goal-result-state",
        ):
            assert mechanic_id in result.context
        assert "Builder Kit:" not in result.context

    def test_returns_v2_playbook_context_for_landing_page_core(self):
        result = resolve_scaffold_context(
            metadata={"registry_v2_app_type": "site.landing-page-core"},
            template_kind="landing-page",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
            repo_root=REPO_ROOT,
        )
        assert result.source == "v2"
        assert result.header == V2_HEADER
        assert result.fallback_reason is None
        assert result.registry_v2_app_type == "site.landing-page-core"
        assert result.registry_v2_pack_id == "pack.site"
        assert "site.landing-page-core" in result.context
        assert "stack.dom-marketing-minimal" in result.context
        for section_id in (
            "section.landing-hero",
            "section.value-proposition",
            "section.feature-value-grid",
            "section.social-proof",
            "section.cta-band",
            "section.faq-block",
            "section.final-conversion",
        ):
            assert section_id in result.context
        assert "Builder Kit:" not in result.context

    def test_returns_v2_playbook_context_for_dashboard_ui_core(self):
        result = resolve_scaffold_context(
            metadata={"registry_v2_app_type": "site.dashboard-ui-core"},
            template_kind="generic",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
            repo_root=REPO_ROOT,
        )
        assert result.source == "v2"
        assert result.header == V2_HEADER
        assert result.fallback_reason is None
        assert result.registry_v2_app_type == "site.dashboard-ui-core"
        assert result.registry_v2_pack_id == "pack.site"
        assert "site.dashboard-ui-core" in result.context
        assert "stack.dom-dashboard-minimal" in result.context
        for section_id in (
            "section.dashboard-shell",
            "section.dashboard-kpi-row",
            "section.dashboard-chart-region",
            "section.dashboard-table-region",
            "section.dashboard-filter-bar",
            "section.dashboard-empty-loading-error-states",
            "section.dashboard-responsive-structure",
        ):
            assert section_id in result.context
        assert "Builder Kit:" not in result.context

    def test_returns_v2_playbook_context_for_saas_dashboard_core(self):
        result = resolve_scaffold_context(
            metadata={"registry_v2_app_type": "app.saas-dashboard-core"},
            template_kind="generic",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "1"},
            repo_root=REPO_ROOT,
        )
        assert result.source == "v2"
        assert result.header == V2_HEADER
        assert result.fallback_reason is None
        assert result.registry_v2_app_type == "app.saas-dashboard-core"
        assert result.registry_v2_pack_id == "pack.site"
        assert "app.saas-dashboard-core" in result.context
        assert "stack.dom-saas-dashboard-minimal" in result.context
        assert "section.saas-app-shell" in result.context
        assert "section.saas-usage-summary" in result.context
        assert "section.saas-resource-list" in result.context
        assert "validator.no-auth-backend-claims" in result.context
        assert "Builder Kit:" not in result.context


class TestResolveScaffoldContextUnknownAppType:
    def test_falls_back_to_v1_on_unknown_app_type(self):
        result = resolve_scaffold_context(
            metadata={"registry_v2_app_type": "game.does-not-exist"},
            template_kind="todo",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "yes"},
            repo_root=REPO_ROOT,
        )
        assert result.source == "v1"
        assert result.fallback_reason is not None
        assert result.fallback_reason.startswith("registry_v2_error:")
        assert result.registry_v2_app_type == "game.does-not-exist"
        assert result.fallback_template_kind in {"todo", "generic"}
        assert "Builder Kit:" in result.context


class TestResolveScaffoldContextBadPackRoot:
    def test_falls_back_to_v1_on_bad_pack_root(self, tmp_path: Path):
        result = resolve_scaffold_context(
            metadata={
                "registry_v2_app_type": "game.idle-incremental",
                "registry_v2_pack_root": str(tmp_path / "missing-pack"),
            },
            template_kind="generic",
            env={"HAM_BUILD_REGISTRY_V2_ENABLED": "on"},
            repo_root=REPO_ROOT,
        )
        assert result.source == "v1"
        assert result.fallback_reason is not None
        assert result.fallback_reason.startswith("registry_v2_error:")
        assert "Builder Kit: generic" in result.context


class TestResolveScaffoldContextNoV1Fallback:
    def test_returns_none_when_no_kit_resolves(self):
        with (
            patch("src.ham.builder_kits.get_kit", return_value=None),
            patch("src.ham.builder_kits.get_kit_for_template_kind", return_value=None),
        ):
            result = resolve_scaffold_context(
                metadata={},
                template_kind="nonexistent-kind",
                env={"HAM_BUILD_REGISTRY_V2_ENABLED": "false"},
                repo_root=REPO_ROOT,
            )
        assert result.source == "none"
        assert result.header == ""
        assert result.context == ""
        assert result.fallback_reason == "no_fallback_kit_resolved"


class TestNoRuntimeWiring:
    def test_builder_llm_scaffold_lazy_imports_scaffold_context(self):
        path = REPO_ROOT / "src/ham/builder_llm_scaffold.py"
        source = path.read_text(encoding="utf-8")
        assert "resolve_scaffold_context" in source
        assert "from src.ham.build_registry.scaffold_context import" in source
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("from src.ham.build_registry") or stripped.startswith(
                "import src.ham.build_registry"
            ):
                assert stripped.startswith("from src.ham.build_registry.scaffold_context import")

    def test_builder_chat_scaffold_lazy_imports_registry_intent(self):
        path = REPO_ROOT / "src/ham/builder_chat_scaffold.py"
        source = path.read_text(encoding="utf-8")
        assert "enrich_plan_metadata_with_registry_v2" in source
        assert "from src.ham.build_registry.intent import" in source
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("from src.ham.build_registry") or stripped.startswith(
                "import src.ham.build_registry"
            ):
                assert stripped.startswith("from src.ham.build_registry.intent import")
