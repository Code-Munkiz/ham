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
    DASHBOARD_UI_CORE_APP_TYPE,
    LANDING_PAGE_CORE_APP_TYPE,
    select_registry_v2_app_type_for_prompt,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_PACK_ROOT = REPO_ROOT / "docs/build-kit-registry-v2/website-pack"
WEBSITE_PACK_MANIFEST = WEBSITE_PACK_ROOT / "registry-pack.yaml"
APP_TYPE_ID = "site.landing-page-core"
APP_TYPE_ID_DASHBOARD = "site.dashboard-ui-core"

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

EXPECTED_DASHBOARD_SECTION_IDS = frozenset(
    {
        "section.dashboard-shell",
        "section.dashboard-kpi-row",
        "section.dashboard-chart-region",
        "section.dashboard-table-region",
        "section.dashboard-filter-bar",
        "section.dashboard-empty-loading-error-states",
        "section.dashboard-responsive-structure",
    }
)

EXPECTED_DASHBOARD_COMPONENT_IDS = frozenset(
    {
        "component.kpi-card",
        "component.chart-card",
        "component.simple-data-table",
        "component.filter-bar",
        "component.status-badge",
    }
)

EXPECTED_DASHBOARD_VALIDATOR_IDS = frozenset(
    {
        "validator.dashboard-region-presence",
        "validator.kpi-count-bounds",
        "validator.chart-semantics",
        "validator.table-readability",
        "validator.filter-mapping",
        "validator.sample-data-relevance",
        "validator.dashboard-responsive-a11y",
        "validator.dashboard-anti-component-soup",
    }
)

EXPECTED_DASHBOARD_RECOVERY_IDS = frozenset(
    {
        "recovery.kpi-spam",
        "recovery.fake-chart-data",
        "recovery.dead-filters",
        "recovery.dense-table",
        "recovery.component-soup",
        "recovery.admin-drift",
    }
)

# Representative strong dashboard prompts that should route to site.dashboard-ui-core.
DASHBOARD_PROMPTS = (
    "Build a read-only dashboard overview for a developer tool team. Include 4 KPI cards, a line chart for build quality over time, a bar chart for issue categories, a simple recent builds table, a local filter bar, empty/loading/error state examples, meaningful sample data, responsive layout, and accessible headings/table structure. No backend, no auth, no CRUD, no live data.",
    "Build a read-only dashboard overview with KPI cards, simple charts, a table, "
    "filters, empty states, and responsive layout.",
    "Create a static dashboard UI for a SaaS metrics overview with KPIs, line chart, "
    "bar chart, recent activity table, and accessible headings.",
    "Build a local sample-data dashboard with status cards, trend charts, a simple "
    "table, and no backend.",
    "Create a dashboard overview page with bounded KPI cards, meaningful sample data, "
    "loading/empty/error states, and responsive stacking.",
    "Build a static dashboard with KPI cards, line chart, bar chart, and recent builds table without CRUD or live data.",
    "Build a local sample-data dashboard with filters, trend charts, and a simple table; no backend, no database, no auth.",
)

DASHBOARD_NEGATIVE_PROMPTS = (
    "Build me a dashboard",
    "build a dashboard with no CRUD",
    "build an app with no backend",
    "build a metrics page",
    "Build an admin dashboard with user management and CRUD",
    "Build an admin dashboard with CRUD forms and user management",
    "Build an analytics workbench with ad-hoc queries and pivots",
    "Build a SaaS app dashboard with auth, accounts, billing, and tenant state",
    "Create a backend API dashboard wired to a database",
    "Build a dashboard with auth, accounts, database, and API integration",
    "Build a dashboard connected to live backend data",
    "Build a CRM dashboard with leads and tickets",
    "Build a fintech trading dashboard with order book and candlestick charts",
    "Build a real-time operations dashboard with live monitoring and maps",
    "Build a payment and billing management dashboard",
    "Build a game HUD overlay with health bars and score",
)

NEAR_BUDGET_THRESHOLD = 11_400


@pytest.fixture(scope="module")
def website_pack():
    return load_registry_pack(WEBSITE_PACK_ROOT)


@pytest.fixture(scope="module")
def landing_recipe(website_pack):
    return compose_build_recipe(website_pack, APP_TYPE_ID)


@pytest.fixture(scope="module")
def dashboard_recipe(website_pack):
    return compose_build_recipe(website_pack, APP_TYPE_ID_DASHBOARD)


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


def test_render_context_requires_social_proof_when_requested(landing_recipe):
    rendered = render_playbook_context(landing_recipe)
    lowered = rendered.lower()
    assert "social proof" in lowered
    # Required-when-requested framing (app-type guidance + social-proof section + validator)
    assert "do not silently omit" in lowered
    assert "required as a distinct section" in lowered


def test_render_context_includes_primary_and_secondary_cta_guidance(landing_recipe):
    rendered = render_playbook_context(landing_recipe)
    lowered = rendered.lower()
    assert "secondary cta" in lowered
    assert "primary and secondary" in lowered or "primary AND secondary".lower() in lowered
    # Does not collapse requested dual CTAs into one button
    assert "collapse" in lowered


def test_render_context_discourages_dead_anchor_cta(landing_recipe):
    rendered = render_playbook_context(landing_recipe)
    assert 'href="#"' in rendered
    lowered = rendered.lower()
    assert "in-page anchor" in lowered or "anchor target" in lowered


def test_no_lorem_dead_cta_validator_mentions_fake_forms_and_dead_anchors():
    path = WEBSITE_PACK_ROOT / "validators/no-lorem-dead-cta.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    joined = " ".join(data["pass_conditions"] + data["fail_conditions"]).lower()
    assert 'href="#"' in joined or "dead anchor" in joined
    assert "fake form" in joined or "no live form" in joined or "no action pretending" in joined


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


def test_dashboard_ui_core_loads(website_pack):
    assert APP_TYPE_ID_DASHBOARD in website_pack.modules
    assert website_pack.modules[APP_TYPE_ID_DASHBOARD].kind == "app_type"


def test_module_index_covers_dashboard_ids(website_pack):
    index = dict(website_pack.manifest)["module_index"]
    assert APP_TYPE_ID_DASHBOARD in index["app_types"]
    assert "stack.dom-dashboard-minimal" in index["stack_kits"]
    assert EXPECTED_DASHBOARD_SECTION_IDS <= set(index["mechanics"])
    assert EXPECTED_DASHBOARD_COMPONENT_IDS <= set(index["component_contracts"])
    assert EXPECTED_DASHBOARD_VALIDATOR_IDS <= set(index["validators"])
    assert EXPECTED_DASHBOARD_RECOVERY_IDS <= set(index["recovery_playbooks"])
    assert "progress.dashboard-ui-core" in index["progress_labels"]
    assert "learning.dashboard-ui-core" in index["learning_hooks"]


def test_dashboard_ui_core_composes(dashboard_recipe):
    assert dashboard_recipe.app_type_id == APP_TYPE_ID_DASHBOARD
    assert dashboard_recipe.stack_kit_id == "stack.dom-dashboard-minimal"
    assert set(dashboard_recipe.mechanic_ids) == EXPECTED_DASHBOARD_SECTION_IDS
    assert set(dashboard_recipe.component_ids) == EXPECTED_DASHBOARD_COMPONENT_IDS
    assert set(dashboard_recipe.validator_ids) == EXPECTED_DASHBOARD_VALIDATOR_IDS
    assert set(dashboard_recipe.recovery_ids) == EXPECTED_DASHBOARD_RECOVERY_IDS
    assert dashboard_recipe.progress_label_id == "progress.dashboard-ui-core"
    assert dashboard_recipe.learning_hook_id == "learning.dashboard-ui-core"


def test_dashboard_render_under_budget(dashboard_recipe):
    rendered = render_playbook_context(dashboard_recipe)
    assert len(rendered) <= DEFAULT_RENDER_CHAR_BUDGET
    assert len(rendered) < NEAR_BUDGET_THRESHOLD
    assert APP_TYPE_ID_DASHBOARD in rendered
    assert "section.dashboard-kpi-row" in rendered
    assert "validator.kpi-count-bounds" in rendered
    lowered = rendered.lower()
    assert "inverted pyramid" in lowered
    assert "no-template-cloning" in rendered or "Non-template" in rendered


def test_dashboard_render_requires_line_and_bar_chart(dashboard_recipe):
    rendered = render_playbook_context(dashboard_recipe)
    lowered = rendered.lower()
    # Both requested chart types must be represented in the guidance.
    assert "line chart" in lowered
    assert "bar chart" in lowered
    # Chart semantics: time/trend vs categorical comparison.
    assert "time/trend" in lowered or "trend" in lowered
    assert "categorical" in lowered


def test_dashboard_render_discourages_empty_canvas_placeholder(dashboard_recipe):
    rendered = render_playbook_context(dashboard_recipe)
    lowered = rendered.lower()
    assert "empty canvas" in lowered
    assert "placeholder" in lowered


def test_dashboard_render_includes_filter_mapping_guidance(dashboard_recipe):
    rendered = render_playbook_context(dashboard_recipe)
    lowered = rendered.lower()
    # Filters must name their target region and avoid dead controls.
    assert "kpi row" in lowered
    assert "dead control" in lowered or "no dead controls" in lowered or "dead controls" in lowered
    assert "disabled" in lowered


def test_dashboard_render_includes_empty_loading_error_guidance(dashboard_recipe):
    rendered = render_playbook_context(dashboard_recipe)
    lowered = rendered.lower()
    assert "empty" in lowered
    assert "loading" in lowered
    assert "error" in lowered
    # States are static examples, not live fetches.
    assert "static" in lowered
    assert "no live fetch" in lowered or "no live data" in lowered or "not imply live" in lowered


def test_dashboard_render_includes_semantic_landmark_guidance(dashboard_recipe):
    rendered = render_playbook_context(dashboard_recipe)
    lowered = rendered.lower()
    assert "header/nav/main" in lowered or ("header" in lowered and "nav" in lowered and "main" in lowered)
    assert "single h1" in lowered or "accessible name" in lowered
    assert "table" in lowered
    assert "div soup" in lowered


def test_dashboard_render_stays_under_near_budget(dashboard_recipe):
    rendered = render_playbook_context(dashboard_recipe)
    assert len(rendered) <= DEFAULT_RENDER_CHAR_BUDGET
    assert len(rendered) < NEAR_BUDGET_THRESHOLD


def test_dashboard_adaptive_policy_prompt_examples_exist():
    app_path = WEBSITE_PACK_ROOT / "app-types/site.dashboard-ui-core.yaml"
    app = yaml.safe_load(app_path.read_text(encoding="utf-8"))
    examples = app["user_prompt_examples"]
    assert len(examples["positive"]) >= 4
    assert len(examples["negative"]) >= 8
    assert app["conflict_policy"]["user_explicit_overrides_soft_defaults"] is True
    assert app["hard_constraints"]


def test_dashboard_ui_core_routes_for_strong_prompts():
    for prompt in DASHBOARD_PROMPTS:
        assert select_registry_v2_app_type_for_prompt(prompt) == APP_TYPE_ID_DASHBOARD
        assert select_registry_v2_app_type_for_prompt(prompt) == DASHBOARD_UI_CORE_APP_TYPE


def test_dashboard_ui_core_does_not_route_for_weak_or_excluded_prompts():
    for prompt in DASHBOARD_NEGATIVE_PROMPTS:
        assert select_registry_v2_app_type_for_prompt(prompt) != APP_TYPE_ID_DASHBOARD


def test_landing_page_dashboard_screenshot_prompt_does_not_route_to_dashboard():
    routed = select_registry_v2_app_type_for_prompt(
        "Build a landing page with a fake dashboard screenshot hero."
    )
    assert routed != APP_TYPE_ID_DASHBOARD
    assert routed in {None, LANDING_PAGE_CORE_APP_TYPE}


def test_module_count(website_pack):
    # Landing: 1 app + 1 stack + 7 sections + 5 components + 7 validators
    #   + 6 recovery + 1 progress + 1 learning = 29
    # Dashboard: 1 app + 1 stack + 7 sections + 5 components + 8 validators
    #   + 6 recovery + 1 progress + 1 learning = 30
    # Total = 59
    assert len(website_pack.modules) == 59


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
