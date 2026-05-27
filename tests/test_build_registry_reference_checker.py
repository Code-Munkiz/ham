"""Tests for scripts/check_build_registry_references.py."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
GAME_PACK_ROOT = REPO_ROOT / "docs/build-kit-registry-v2/game-pack"
WEBSITE_PACK_ROOT = REPO_ROOT / "docs/build-kit-registry-v2/website-pack"
DEFAULT_PACK = GAME_PACK_ROOT / "registry-pack.yaml"
WEBSITE_PACK = WEBSITE_PACK_ROOT / "registry-pack.yaml"


def _load_checker_module():
    script_path = REPO_ROOT / "scripts/check_build_registry_references.py"
    spec = importlib.util.spec_from_file_location(
        "check_build_registry_references",
        script_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker_module()


@pytest.fixture
def game_pack_root() -> Path:
    return GAME_PACK_ROOT


@pytest.fixture
def pack_copy(tmp_path: Path, game_pack_root: Path) -> Path:
    copied = tmp_path / "pack"
    shutil.copytree(game_pack_root, copied)
    return copied


class TestCurrentRegistry:
    def test_real_registry_has_no_hard_errors(self):
        result = checker.run_reference_checks(
            DEFAULT_PACK,
            check_orphans=True,
            check_render_budget=True,
        )
        assert result.errors == []
        assert result.summary_counts["error"] == 0

    def test_website_pack_has_no_hard_errors(self):
        result = checker.run_reference_checks(
            WEBSITE_PACK,
            app_type="site.landing-page-core",
            check_orphans=True,
            check_render_budget=True,
        )
        assert result.errors == []
        assert result.summary_counts["error"] == 0

    def test_cli_main_real_registry_exits_zero(self):
        exit_code = checker.main(
            [
                "--pack",
                str(DEFAULT_PACK),
                "--check-orphans",
                "--check-render-budget",
            ]
        )
        assert exit_code == 0

    def test_cli_main_website_pack_exits_zero(self):
        exit_code = checker.main(
            [
                "--pack",
                str(WEBSITE_PACK),
                "--app-type",
                "site.landing-page-core",
                "--check-orphans",
                "--check-render-budget",
            ]
        )
        assert exit_code == 0


class TestMissingReferencedFile:
    def test_missing_indexed_module_file_detected(self, pack_copy: Path):
        manifest_path = pack_copy / "registry-pack.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["module_index"]["mechanics"].append("mechanic.missing-test-module")
        manifest_path.write_text(yaml.dump(manifest, sort_keys=False), encoding="utf-8")

        result = checker.run_reference_checks(manifest_path)
        codes = {issue.code for issue in result.errors}
        assert "missing_referenced_file" in codes


class TestDuplicateIds:
    def test_duplicate_module_ids_detected(self, pack_copy: Path):
        score_path = pack_copy / "mechanics/score.yaml"
        score_data = yaml.safe_load(score_path.read_text(encoding="utf-8"))
        duplicate_path = pack_copy / "mechanics/duplicate-score.yaml"
        duplicate_path.write_text(yaml.dump(score_data, sort_keys=False), encoding="utf-8")

        result = checker.run_reference_checks(pack_copy / "registry-pack.yaml")
        codes = {issue.code for issue in result.errors}
        assert "duplicate_module_id" in codes


class TestInvalidAppliesTo:
    def test_invalid_applies_to_app_type_detected(self, pack_copy: Path):
        score_path = pack_copy / "mechanics/score.yaml"
        data = yaml.safe_load(score_path.read_text(encoding="utf-8"))
        data["applies_to"] = ["game.nonexistent-app-type"]
        score_path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")

        result = checker.run_reference_checks(pack_copy / "registry-pack.yaml")
        codes = {issue.code for issue in result.errors}
        assert "invalid_applies_to" in codes


class TestMissingComposedModule:
    def test_missing_composed_module_reference_detected(self, pack_copy: Path):
        app_path = pack_copy / "app-types/game.idle-incremental.yaml"
        data = yaml.safe_load(app_path.read_text(encoding="utf-8"))
        data["composed_modules"]["mechanics"].append("mechanic.nonexistent-compose-target")
        app_path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")

        result = checker.run_reference_checks(pack_copy / "registry-pack.yaml")
        codes = {issue.code for issue in result.errors}
        assert "registry_validation_error" in codes


class TestOrphans:
    def test_orphan_module_warning_with_flag(self, pack_copy: Path):
        orphan_path = pack_copy / "mechanics/orphan-test-module.yaml"
        orphan_path.write_text(
            yaml.dump(
                {
                    "id": "mechanic.orphan-test-module",
                    "kind": "mechanic",
                    "schema_version": "0.1",
                    "status": "proposed",
                    "description": "orphan fixture",
                    "non_template_statement": "fixture only",
                    "applies_to": ["game.idle-incremental"],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        result = checker.run_reference_checks(
            pack_copy / "registry-pack.yaml",
            check_orphans=True,
        )
        codes = {issue.code for issue in result.warnings}
        assert "orphan_module" in codes


class TestExitBehavior:
    def test_warn_only_exits_zero_despite_errors(self, pack_copy: Path):
        manifest_path = pack_copy / "registry-pack.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["module_index"]["mechanics"].append("mechanic.missing-test-module")
        manifest_path.write_text(yaml.dump(manifest, sort_keys=False), encoding="utf-8")

        result = checker.run_reference_checks(manifest_path)
        assert result.errors
        assert (
            checker.compute_exit_code(result, warn_only=True) == 0
        )

    def test_strict_exits_nonzero_on_warnings(self):
        result = checker.CheckResult(
            issues=[
                checker.CheckIssue(
                    code="render_near_budget",
                    severity="warning",
                    message="near budget",
                )
            ]
        )
        assert checker.compute_exit_code(result, strict=True) == 1
        assert checker.compute_exit_code(result, strict=False) == 0


class TestJsonOutput:
    def test_json_output_shape(self):
        result = checker.CheckResult(
            pack_path=str(DEFAULT_PACK),
            pack_root=str(GAME_PACK_ROOT),
            issues=[
                checker.CheckIssue(
                    code="example",
                    severity="info",
                    message="example issue",
                    path=str(DEFAULT_PACK),
                    suggestion="none",
                )
            ],
        )
        payload = json.loads(checker.format_json_report(result))
        assert payload["summary_counts"] == {"error": 0, "warning": 0, "info": 1}
        assert payload["issues"][0]["code"] == "example"
        assert payload["pack_path"] == str(DEFAULT_PACK)


class TestRenderBudget:
    def test_render_budget_check_runs_for_real_registry(self):
        result = checker.run_reference_checks(
            DEFAULT_PACK,
            check_render_budget=True,
            app_type="game.deck-builder-lite",
        )
        assert not any(issue.code == "render_over_budget" for issue in result.errors)

    def test_render_over_budget_detected(self, pack_copy: Path, monkeypatch):
        from src.ham.build_registry import compose_build_recipe, load_registry_pack

        pack = load_registry_pack(pack_copy)

        def _bloated_render(*_args, **_kwargs):
            return "x" * (checker.DEFAULT_RENDER_CHAR_BUDGET + 1)

        monkeypatch.setattr(checker, "render_playbook_context", _bloated_render)
        result = checker.CheckResult(pack_path=str(pack_copy / "registry-pack.yaml"))
        checker._check_render_budgets(
            result,
            pack,
            app_type="game.idle-incremental",
        )
        codes = {issue.code for issue in result.errors}
        assert "render_over_budget" in codes
