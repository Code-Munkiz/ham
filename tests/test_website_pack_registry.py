"""Tests for Build Registry v2 Website Pack (schema-only routing behind flag)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.ham.build_registry import (
    compose_build_recipe,
    load_registry_pack,
    render_playbook_context,
    validate_registry_pack,
)
from src.ham.build_registry.models import DEFAULT_RENDER_CHAR_BUDGET
from src.ham.build_registry.intent import (
    LANDING_PAGE_CORE_APP_TYPE,
    select_registry_v2_app_type_for_prompt,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_PACK_ROOT = REPO_ROOT / "docs/build-kit-registry-v2/website-pack"
WEBSITE_PACK_MANIFEST = WEBSITE_PACK_ROOT / "registry-pack.yaml"
APP_TYPE_ID = "site.landing-page-core"

EXPECTED_SECTION_ORDER = (
    "section.landing-hero",
    "section.value-proposition",
    "section.feature-value-grid",
    "section.social-proof",
    "section.cta-band",
    "section.faq-block",
    "section.final-conversion",
)

EXPECTED_COMPONENT_IDS = frozenset(
    {
        "component.hero-block",
        "component.feature-card-grid",
        "component.testimonial-strip",
        "component.cta-button-group",
        "component.faq-list",
    }
)

EXPECTED_VALIDATOR_IDS = frozenset(
    {
        "validator.landing-section-presence",
        "validator.cta-clarity",
        "validator.copy-specificity",
        "validator.semantic-heading-order",
        "validator.responsive-accessibility-basics",
        "validator.no-lorem-dead-cta",
        "validator.anti-slop-patterns",
    }
)

EXPECTED_RECOVERY_IDS = frozenset(
    {
        "recovery.generic-hero",
        "recovery.weak-cta",
        "recovery.section-repetition",
        "recovery.inaccessible-buttons",
        "recovery.mobile-layout-ignored",
        "recovery.vague-copy",
    }
)

NEAR_BUDGET_THRESHOLD = 11_400


@pytest.fixture(scope="module")
def website_pack():
    return load_registry_pack(WEBSITE_PACK_ROOT)


@pytest.fixture(scope="module")
def landing_recipe(website_pack):
    return compose_build_recipe(website_pack, APP_TYPE_ID)


def test_registry_yaml_parses():
    path = WEBSITE_PACK_ROOT / "registry-pack.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["id"] == "pack.site"


def test_website_pack_loads(website_pack):
    assert website_pack.pack_id == "pack.site"
    assert website_pack.schema_version == "0.1"
    assert APP_TYPE_ID in website_pack.modules


def test_module_index_covers_expected_ids(website_pack):
    index = dict(website_pack.manifest)["module_index"]
    assert APP_TYPE_ID in index["app_types"]
    assert "stack.dom-marketing-minimal" in index["stack_kits"]
    for section_id in EXPECTED_SECTION_ORDER:
        assert section_id in index["mechanics"]
    assert EXPECTED_COMPONENT_IDS <= set(index["component_contracts"])
    assert EXPECTED_VALIDATOR_IDS <= set(index["validators"])
    assert EXPECTED_RECOVERY_IDS <= set(index["recovery_playbooks"])
    assert "progress.landing-page-core" in index["progress_labels"]
    assert "learning.landing-page-core" in index["learning_hooks"]


def test_no_orphan_yaml_files(website_pack):
    yaml_files = {
        p
        for p in WEBSITE_PACK_ROOT.rglob("*.yaml")
        if p.name != "registry-pack.yaml"
    }
    indexed_paths = {mod.path for mod in website_pack.modules.values()}
    assert yaml_files == indexed_paths


def test_landing_page_core_composes(landing_recipe):
    assert landing_recipe.app_type_id == APP_TYPE_ID
    assert landing_recipe.stack_kit_id == "stack.dom-marketing-minimal"
    assert landing_recipe.mechanic_ids == EXPECTED_SECTION_ORDER
    assert set(landing_recipe.component_ids) == EXPECTED_COMPONENT_IDS
    assert set(landing_recipe.validator_ids) == EXPECTED_VALIDATOR_IDS
    assert set(landing_recipe.recovery_ids) == EXPECTED_RECOVERY_IDS
    assert landing_recipe.progress_label_id == "progress.landing-page-core"
    assert landing_recipe.learning_hook_id == "learning.landing-page-core"


def test_render_context_under_budget(landing_recipe):
    rendered = render_playbook_context(landing_recipe)
    assert len(rendered) <= DEFAULT_RENDER_CHAR_BUDGET
    assert len(rendered) < NEAR_BUDGET_THRESHOLD
    assert APP_TYPE_ID in rendered
    assert "section.landing-hero" in rendered
    assert "validator.cta-clarity" in rendered
    assert "no-template-cloning" in rendered or "Non-template" in rendered


def test_adaptive_policy_prompt_examples_exist():
    app_path = WEBSITE_PACK_ROOT / "app-types/site.landing-page-core.yaml"
    app = yaml.safe_load(app_path.read_text(encoding="utf-8"))
    examples = app["user_prompt_examples"]
    assert len(examples["positive"]) >= 4
    assert len(examples["negative"]) >= 8
    assert app["conflict_policy"]["user_explicit_overrides_soft_defaults"] is True
    assert app["hard_constraints"]


def test_site_landing_page_core_routes_when_flagged_intent_matches():
    positive = (
        "Build a landing page for a SaaS product with a hero, features, "
        "testimonials, CTA, FAQ, and responsive layout."
    )
    assert select_registry_v2_app_type_for_prompt(positive) == APP_TYPE_ID
    assert select_registry_v2_app_type_for_prompt(positive) == LANDING_PAGE_CORE_APP_TYPE
    assert select_registry_v2_app_type_for_prompt("build a landing page") is None


def test_module_count(website_pack):
    # 1 app + 1 stack + 7 sections + 5 components + 7 validators + 6 recovery
    # + 1 progress + 1 learning = 29
    assert len(website_pack.modules) == 29


def test_validate_registry_pack_passes(website_pack):
    validate_registry_pack(website_pack)


def test_reference_checker_passes():
    import importlib.util
    import sys

    script_path = REPO_ROOT / "scripts/check_build_registry_references.py"
    spec = importlib.util.spec_from_file_location(
        "check_build_registry_references_website",
        script_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    result = module.run_reference_checks(
        WEBSITE_PACK_MANIFEST,
        app_type=APP_TYPE_ID,
        check_orphans=True,
        check_render_budget=True,
    )
    assert result.errors == []
    assert result.summary_counts["error"] == 0
