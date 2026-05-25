"""Tests for src/ham/build_registry — unwired Game Pack registry loader/composer."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from src.ham.build_registry import (
    BuildRegistryConfigError,
    compose_build_recipe,
    load_registry_pack,
    render_playbook_context,
    validate_registry_pack,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
GAME_PACK_ROOT = REPO_ROOT / "docs/build-kit-registry-v2/game-pack"

EXPECTED_MECHANIC_ORDER = (
    "mechanic.score",
    "mechanic.economy",
    "mechanic.upgrades",
    "mechanic.save-load",
)

EXPECTED_TRIVIA_MECHANIC_ORDER = (
    "mechanic.question-set",
    "mechanic.score",
    "mechanic.timer",
    "mechanic.answer-validation",
    "mechanic.progression",
)


@pytest.fixture
def game_pack_root() -> Path:
    return GAME_PACK_ROOT


class TestHappyPath:
    def test_load_docs_game_pack(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        assert pack.pack_id == "pack.game"
        assert pack.schema_version == "0.1"
        assert len(pack.modules) == 33

    def test_validate_docs_game_pack(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)

    def test_compose_idle_incremental(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        recipe = compose_build_recipe(pack, "game.idle-incremental")
        assert recipe.app_type_id == "game.idle-incremental"
        assert recipe.stack_kit_id == "stack.dom-game-minimal"
        assert recipe.mechanic_ids == EXPECTED_MECHANIC_ORDER

    def test_render_starts_with_header(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        recipe = compose_build_recipe(pack, "game.idle-incremental")
        rendered = render_playbook_context(recipe)
        assert rendered.startswith("Build Kit Registry v2 — BuildRecipe\n")

    def test_render_includes_key_ids_and_safety(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.idle-incremental")
        rendered = render_playbook_context(recipe)
        assert "game.idle-incremental" in rendered
        assert "stack.dom-game-minimal" in rendered
        assert "validator.no-negative-currency" in rendered
        assert "no-network-egress-for-mvp" in rendered
        assert "Safety constraints:" in rendered

    def test_render_is_deterministic(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.idle-incremental")
        first = render_playbook_context(recipe)
        second = render_playbook_context(recipe)
        assert first == second

    def test_render_under_default_budget(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.idle-incremental")
        rendered = render_playbook_context(recipe)
        assert len(rendered) <= 12_000


class TestTriviaTimerRecipe:
    def test_compose_trivia_timer(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        recipe = compose_build_recipe(pack, "game.trivia-timer")
        assert recipe.app_type_id == "game.trivia-timer"
        assert recipe.stack_kit_id == "stack.dom-game-minimal"
        assert recipe.mechanic_ids == EXPECTED_TRIVIA_MECHANIC_ORDER

    def test_render_trivia_includes_key_ids(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.trivia-timer")
        rendered = render_playbook_context(recipe)
        assert "game.trivia-timer" in rendered
        assert "stack.dom-game-minimal" in rendered
        assert "validator.timer-cleanup" in rendered
        assert "validator.score-calculation" in rendered
        assert "validator.question-progression" in rendered
        assert "static-question-data-for-mvp" in rendered

    def test_render_trivia_under_default_budget(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        recipe = compose_build_recipe(pack, "game.trivia-timer")
        rendered = render_playbook_context(recipe)
        assert len(rendered) <= 12_000
        assert rendered.startswith("Build Kit Registry v2 — BuildRecipe\n")

    def test_idle_recipe_still_compose_after_trivia_added(self, game_pack_root: Path):
        pack = load_registry_pack(game_pack_root)
        validate_registry_pack(pack)
        recipe = compose_build_recipe(pack, "game.idle-incremental")
        assert recipe.mechanic_ids == EXPECTED_MECHANIC_ORDER


class TestBrokenFixtures:
    def test_broken_reference_raises(self, tmp_path: Path, game_pack_root: Path):
        shutil.copytree(game_pack_root, tmp_path / "pack")
        pack_root = tmp_path / "pack"
        economy_path = pack_root / "mechanics/economy.yaml"
        data = yaml.safe_load(economy_path.read_text(encoding="utf-8"))
        data["depends_on"] = ["mechanic.nonexistent"]
        economy_path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")

        pack = load_registry_pack(pack_root)
        with pytest.raises(BuildRegistryConfigError, match="mechanic.nonexistent"):
            validate_registry_pack(pack)

    def test_dependency_cycle_raises(self, tmp_path: Path, game_pack_root: Path):
        shutil.copytree(game_pack_root, tmp_path / "pack")
        pack_root = tmp_path / "pack"
        score_path = pack_root / "mechanics/score.yaml"
        data = yaml.safe_load(score_path.read_text(encoding="utf-8"))
        data["depends_on"] = ["mechanic.economy"]
        score_path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")

        pack = load_registry_pack(pack_root)
        with pytest.raises(BuildRegistryConfigError, match="cycle"):
            validate_registry_pack(pack)


class TestNoRuntimeWiring:
    def test_builder_llm_scaffold_lazy_imports_build_registry(self):
        import src.ham.builder_llm_scaffold as scaffold

        source = Path(scaffold.__file__).read_text(encoding="utf-8")
        assert "resolve_scaffold_context" in source
        assert "from src.ham.build_registry.scaffold_context import" in source
        module_lines = source.splitlines()
        for line in module_lines:
            stripped = line.strip()
            if stripped.startswith("from src.ham.build_registry") or stripped.startswith(
                "import src.ham.build_registry"
            ):
                assert stripped.startswith("from src.ham.build_registry.scaffold_context import")
                assert "resolve_scaffold_context" in stripped

    def test_builder_kits_does_not_import_build_registry(self):
        import src.ham.builder_kits as kits

        source = Path(kits.__file__).read_text(encoding="utf-8")
        assert "build_registry" not in source
