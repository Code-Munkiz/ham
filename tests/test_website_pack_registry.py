"""Tests for Build Registry v2 Website Pack."""

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
    SAAS_DASHBOARD_CORE_APP_TYPE,
    select_registry_v2_app_type_for_prompt,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_PACK_ROOT = REPO_ROOT / "docs/build-kit-registry-v2/website-pack"
WEBSITE_PACK_MANIFEST = WEBSITE_PACK_ROOT / "registry-pack.yaml"
APP_TYPE_ID = "site.landing-page-core"
APP_TYPE_ID_DASHBOARD = "site.dashboard-ui-core"
APP_TYPE_ID_SAAS = "app.saas-dashboard-core"
APP_TYPE_ID_ADMIN = "app.admin-dashboard-core"

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

# app.saas-dashboard-core expected module IDs
EXPECTED_SAAS_SECTION_IDS = frozenset(
    {
        "section.saas-app-shell",
        "section.saas-workspace-context",
        "section.saas-usage-summary",
        "section.saas-plan-status",
        "section.saas-activity-feed",
        "section.saas-resource-list",
        "section.saas-upgrade-cta",
        "section.saas-empty-loading-error-states",
        "section.saas-responsive-structure",
    }
)

EXPECTED_SAAS_COMPONENT_IDS = frozenset(
    {
        "component.app-shell",
        "component.sidebar-nav",
        "component.topbar",
        "component.workspace-switcher",
        "component.usage-card",
        "component.plan-status-card",
        "component.activity-item",
        "component.resource-list",
        "component.upgrade-card",
        "component.settings-shortcut",
    }
)

EXPECTED_SAAS_VALIDATOR_IDS = frozenset(
    {
        "validator.app-shell-bounds",
        "validator.no-auth-backend-claims",
        "validator.no-billing-implementation",
        "validator.usage-data-meaningful",
        "validator.activity-feed-bounded",
        "validator.resource-list-readable",
        "validator.no-admin-crud-drift",
        "validator.responsive-a11y-basics",
        "validator.no-dead-nav-deception",
    }
)

EXPECTED_SAAS_RECOVERY_IDS = frozenset(
    {
        "recovery.auth-drift",
        "recovery.billing-drift",
        "recovery.admin-drift",
        "recovery.crud-sprawl",
        "recovery.dead-nav-shell",
        "recovery.meaningless-saas-metrics",
        "recovery.upgrade-cta-spam",
    }
)

# app.admin-dashboard-core expected module IDs
EXPECTED_ADMIN_SECTION_IDS = frozenset(
    {
        "section.admin-app-shell",
        "section.admin-overview-status",
        "section.admin-user-team-summary",
        "section.admin-role-permission-summary",
        "section.admin-review-queue",
        "section.admin-resource-table",
        "section.admin-audit-log",
        "section.admin-system-status",
        "section.admin-demo-action-boundaries",
        "section.admin-empty-loading-error-states",
        "section.admin-responsive-structure",
    }
)

EXPECTED_ADMIN_COMPONENT_IDS = frozenset(
    {
        "component.admin-shell",
        "component.admin-sidebar-nav",
        "component.admin-topbar",
        "component.status-card",
        "component.user-summary-card",
        "component.role-permission-pill",
        "component.review-queue-table",
        "component.audit-log-list",
        "component.system-status-panel",
        "component.resource-index-table",
        "component.demo-action-control",
        "component.danger-modal-mockup",
    }
)

EXPECTED_ADMIN_VALIDATOR_IDS = frozenset(
    {
        "validator.admin-shell-bounds",
        "validator.no-auth-backend-claims",
        "validator.no-rbac-implementation",
        "validator.no-crud-mutation",
        "validator.no-destructive-live-actions",
        "validator.audit-log-static-bounds",
        "validator.admin-table-semantics",
        "validator.disabled-action-accessibility",
        "validator.responsive-a11y-basics",
        "validator.no-security-theater",
    }
)

EXPECTED_ADMIN_RECOVERY_IDS = frozenset(
    {
        "recovery.auth-backend-drift",
        "recovery.rbac-drift",
        "recovery.crud-sprawl",
        "recovery.destructive-action-drift",
        "recovery.audit-log-fakery",
        "recovery.security-theater",
        "recovery.dense-table-soup",
        "recovery.inaccessible-disabled-controls",
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


@pytest.fixture(scope="module")
def saas_recipe(website_pack):
    return compose_build_recipe(website_pack, APP_TYPE_ID_SAAS)


@pytest.fixture(scope="module")
def admin_recipe(website_pack):
    return compose_build_recipe(website_pack, APP_TYPE_ID_ADMIN)


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


def test_saas_dashboard_core_loads(website_pack):
    assert APP_TYPE_ID_SAAS in website_pack.modules
    assert website_pack.modules[APP_TYPE_ID_SAAS].kind == "app_type"


def test_module_index_covers_saas_ids(website_pack):
    index = dict(website_pack.manifest)["module_index"]
    assert APP_TYPE_ID_SAAS in index["app_types"]
    assert "stack.dom-saas-dashboard-minimal" in index["stack_kits"]
    assert EXPECTED_SAAS_SECTION_IDS <= set(index["mechanics"])
    assert EXPECTED_SAAS_COMPONENT_IDS <= set(index["component_contracts"])
    assert EXPECTED_SAAS_VALIDATOR_IDS <= set(index["validators"])
    assert EXPECTED_SAAS_RECOVERY_IDS <= set(index["recovery_playbooks"])
    assert "progress.app-saas-dashboard-core" in index["progress_labels"]
    assert "learning.app-saas-dashboard-core" in index["learning_hooks"]


def test_admin_dashboard_core_loads(website_pack):
    assert APP_TYPE_ID_ADMIN in website_pack.modules
    assert website_pack.modules[APP_TYPE_ID_ADMIN].kind == "app_type"


def test_module_index_covers_admin_ids(website_pack):
    index = dict(website_pack.manifest)["module_index"]
    assert APP_TYPE_ID_ADMIN in index["app_types"]
    assert "stack.dom-admin-dashboard-minimal" in index["stack_kits"]
    assert EXPECTED_ADMIN_SECTION_IDS <= set(index["mechanics"])
    assert EXPECTED_ADMIN_COMPONENT_IDS <= set(index["component_contracts"])
    assert EXPECTED_ADMIN_VALIDATOR_IDS <= set(index["validators"])
    assert EXPECTED_ADMIN_RECOVERY_IDS <= set(index["recovery_playbooks"])
    assert "progress.app-admin-dashboard-core" in index["progress_labels"]
    assert "learning.app-admin-dashboard-core" in index["learning_hooks"]


def test_dashboard_ui_core_composes(dashboard_recipe):
    assert dashboard_recipe.app_type_id == APP_TYPE_ID_DASHBOARD
    assert dashboard_recipe.stack_kit_id == "stack.dom-dashboard-minimal"
    assert set(dashboard_recipe.mechanic_ids) == EXPECTED_DASHBOARD_SECTION_IDS
    assert set(dashboard_recipe.component_ids) == EXPECTED_DASHBOARD_COMPONENT_IDS
    assert set(dashboard_recipe.validator_ids) == EXPECTED_DASHBOARD_VALIDATOR_IDS
    assert set(dashboard_recipe.recovery_ids) == EXPECTED_DASHBOARD_RECOVERY_IDS
    assert dashboard_recipe.progress_label_id == "progress.dashboard-ui-core"
    assert dashboard_recipe.learning_hook_id == "learning.dashboard-ui-core"


def test_saas_dashboard_core_composes(saas_recipe):
    assert saas_recipe.app_type_id == APP_TYPE_ID_SAAS
    assert saas_recipe.stack_kit_id == "stack.dom-saas-dashboard-minimal"
    assert set(saas_recipe.mechanic_ids) == EXPECTED_SAAS_SECTION_IDS
    assert set(saas_recipe.component_ids) == EXPECTED_SAAS_COMPONENT_IDS
    assert set(saas_recipe.validator_ids) == EXPECTED_SAAS_VALIDATOR_IDS
    assert set(saas_recipe.recovery_ids) == EXPECTED_SAAS_RECOVERY_IDS
    assert saas_recipe.progress_label_id == "progress.app-saas-dashboard-core"
    assert saas_recipe.learning_hook_id == "learning.app-saas-dashboard-core"


def test_admin_dashboard_core_composes(admin_recipe):
    assert admin_recipe.app_type_id == APP_TYPE_ID_ADMIN
    assert admin_recipe.stack_kit_id == "stack.dom-admin-dashboard-minimal"
    assert set(admin_recipe.mechanic_ids) == EXPECTED_ADMIN_SECTION_IDS
    assert set(admin_recipe.component_ids) == EXPECTED_ADMIN_COMPONENT_IDS
    assert set(admin_recipe.validator_ids) == EXPECTED_ADMIN_VALIDATOR_IDS
    assert set(admin_recipe.recovery_ids) == EXPECTED_ADMIN_RECOVERY_IDS
    assert admin_recipe.progress_label_id == "progress.app-admin-dashboard-core"
    assert admin_recipe.learning_hook_id == "learning.app-admin-dashboard-core"


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


def test_saas_render_under_budget(saas_recipe):
    rendered = render_playbook_context(saas_recipe)
    assert len(rendered) <= DEFAULT_RENDER_CHAR_BUDGET
    # SaaS lane is intentionally near budget and tracked by reference-checker warnings.
    assert len(rendered) >= NEAR_BUDGET_THRESHOLD


def test_saas_render_contains_key_sections_and_components(saas_recipe):
    rendered = render_playbook_context(saas_recipe)
    lowered = rendered.lower()
    assert APP_TYPE_ID_SAAS in rendered
    assert "section.saas-app-shell" in rendered
    assert "section.saas-workspace-context" in rendered
    assert "section.saas-usage-summary" in rendered
    assert "section.saas-plan-status" in rendered
    assert "section.saas-activity-feed" in rendered
    assert "section.saas-resource-list" in rendered
    assert "section.saas-upgrade-cta" in rendered
    assert "section.saas-empty-loading-error-states" in rendered
    assert "section.saas-responsive-structure" in rendered
    assert "component.workspace-switcher" in rendered
    assert "component.settings-shortcut" in rendered
    assert "semantic header/nav/main" in lowered or (
        "header" in lowered and "nav" in lowered and "main" in lowered
    )
    assert "local/static" in lowered or "static local sample data" in lowered


def test_saas_render_requires_visible_static_empty_loading_error_examples(saas_recipe):
    rendered = render_playbook_context(saas_recipe)
    lowered = rendered.lower()
    assert "empty" in lowered
    assert "loading" in lowered
    assert "error" in lowered
    assert "visible" in lowered
    assert "card" in lowered or "panel" in lowered or "region" in lowered
    assert "static/local" in lowered or "static local" in lowered or "static" in lowered
    assert "never imply live fetch" in lowered or "no live fetch" in lowered
    assert "backend retries" in lowered or "backend/api" in lowered


def test_saas_render_prefers_semantic_resource_table_or_semantic_list(saas_recipe):
    rendered = render_playbook_context(saas_recipe)
    lowered = rendered.lower()
    assert "resource" in lowered
    assert "semantic table" in lowered
    assert "table preferred" in lowered or "<table>/<thead>/<tbody>/<th>/<td>" in lowered
    assert "semantic list" in lowered
    assert "non-tabular" in lowered
    assert "div-soup" in lowered or "div-only pseudo-table" in lowered


def test_saas_render_forbids_live_fetch_interpretation_for_loading_error_states(saas_recipe):
    rendered = render_playbook_context(saas_recipe).lower()
    assert "states are static/local" in rendered
    assert "never imply live fetch" in rendered
    assert "or api wiring" in rendered or "backend/api" in rendered


def test_saas_render_contains_hard_exclusions(saas_recipe):
    rendered = render_playbook_context(saas_recipe).lower()
    assert "never imply real auth" in rendered
    assert "no backend/api/database" in rendered
    assert "no billing/auth/admin/crud behavior" in rendered
    assert "no login/signup/session/backend/api/database implementation claims" in rendered
    assert "no checkout, invoice, card form, or payment processing behavior appears" in rendered
    assert "avoid fake realtime claims" in rendered
    assert "avoid crud affordances that imply create/edit/delete workflows" in rendered
    assert "no fake links suggesting hidden pages or backend settings exist" in rendered
    assert "no checked-in saas template, clone baseline, or starter tree" in rendered


def test_admin_render_under_budget(admin_recipe):
    rendered = render_playbook_context(admin_recipe)
    assert len(rendered) <= DEFAULT_RENDER_CHAR_BUDGET
    assert len(rendered) < NEAR_BUDGET_THRESHOLD


def test_admin_render_contains_key_sections_and_components(admin_recipe):
    rendered = render_playbook_context(admin_recipe)
    lowered = rendered.lower()
    assert APP_TYPE_ID_ADMIN in rendered
    assert "section.admin-app-shell" in rendered
    assert "section.admin-overview-status" in rendered
    assert "section.admin-user-team-summary" in rendered
    assert "section.admin-role-permission-summary" in rendered
    assert "section.admin-review-queue" in rendered
    assert "section.admin-resource-table" in rendered
    assert "section.admin-audit-log" in rendered
    assert "section.admin-system-status" in rendered
    assert "section.admin-demo-action-boundaries" in rendered
    assert "section.admin-empty-loading-error-states" in rendered
    assert "section.admin-responsive-structure" in rendered
    assert "component.admin-shell" in rendered
    assert "component.review-queue-table" in rendered
    assert "component.resource-index-table" in rendered
    assert "component.demo-action-control" in rendered
    assert "semantic header/nav/main" in lowered or (
        "header" in lowered and "nav" in lowered and "main" in lowered
    )
    assert "local/static" in lowered or "static local sample data" in lowered


def test_admin_render_contains_hard_exclusions(admin_recipe):
    rendered = render_playbook_context(admin_recipe).lower()
    assert "no-user-accounts-for-mvp" in rendered
    assert "no-backend-api-for-mvp" in rendered
    assert "no-rbac-implementation-for-mvp" in rendered
    assert "no-crud-mutation-for-mvp" in rendered
    assert "no-destructive-actions-for-mvp" in rendered
    assert "no-live-monitoring-or-streaming-for-mvp" in rendered
    assert "no-billing-processing-for-mvp" in rendered
    assert "no-security-compliance-implementation-for-mvp" in rendered
    assert "no-cryptographic-security-tooling" in rendered
    assert "demo-mode" in rendered or "read-only" in rendered


def test_admin_render_includes_states_and_accessibility_controls(admin_recipe):
    rendered = render_playbook_context(admin_recipe).lower()
    assert "empty" in rendered
    assert "loading" in rendered
    assert "error" in rendered
    assert "disabled" in rendered or "read-only" in rendered
    assert "tooltip-only" in rendered or "reachable explanatory text" in rendered
    assert "semantic table" in rendered or "<table>" in rendered


def test_dashboard_adaptive_policy_prompt_examples_exist():
    app_path = WEBSITE_PACK_ROOT / "app-types/site.dashboard-ui-core.yaml"
    app = yaml.safe_load(app_path.read_text(encoding="utf-8"))
    examples = app["user_prompt_examples"]
    assert len(examples["positive"]) >= 4
    assert len(examples["negative"]) >= 8
    assert app["conflict_policy"]["user_explicit_overrides_soft_defaults"] is True
    assert app["hard_constraints"]


def test_saas_adaptive_policy_prompt_examples_exist():
    app_path = WEBSITE_PACK_ROOT / "app-types/app.saas-dashboard-core.yaml"
    app = yaml.safe_load(app_path.read_text(encoding="utf-8"))
    examples = app["user_prompt_examples"]
    assert len(examples["positive"]) >= 4
    assert len(examples["negative"]) >= 8
    assert app["conflict_policy"]["user_explicit_overrides_soft_defaults"] is True
    assert app["hard_constraints"]


def test_admin_adaptive_policy_prompt_examples_exist():
    app_path = WEBSITE_PACK_ROOT / "app-types/app.admin-dashboard-core.yaml"
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


def test_saas_dashboard_core_routes_for_strong_prompts():
    prompt = (
        "Build a static SaaS app home with sidebar, topbar, workspace context, usage cards, "
        "plan status, activity list, resource list, and one upgrade CTA. "
        "No backend, no auth, no billing, no CRUD, no live data."
    )
    routed = select_registry_v2_app_type_for_prompt(prompt)
    assert routed == APP_TYPE_ID_SAAS
    assert routed == SAAS_DASHBOARD_CORE_APP_TYPE


def test_admin_dashboard_core_not_routed_yet():
    prompt = (
        "Build a static admin dashboard with sidebar, role summary, review queue, "
        "audit log, and system status using local mock data only."
    )
    routed = select_registry_v2_app_type_for_prompt(prompt)
    assert routed is None


def test_saas_dashboard_intent_constant_exists():
    intent_path = REPO_ROOT / "src/ham/build_registry/intent.py"
    text = intent_path.read_text(encoding="utf-8")
    assert "SAAS_DASHBOARD_CORE_APP_TYPE" in text
    assert "app.saas-dashboard-core" in text


def test_admin_dashboard_intent_constant_absent():
    intent_path = REPO_ROOT / "src/ham/build_registry/intent.py"
    text = intent_path.read_text(encoding="utf-8")
    assert "ADMIN_DASHBOARD_CORE_APP_TYPE" not in text
    assert "app.admin-dashboard-core" not in text


def test_module_count(website_pack):
    # Landing: 1 app + 1 stack + 7 sections + 5 components + 7 validators
    #   + 6 recovery + 1 progress + 1 learning = 29
    # Dashboard: 1 app + 1 stack + 7 sections + 5 components + 8 validators
    #   + 6 recovery + 1 progress + 1 learning = 30
    # SaaS: 1 app + 1 stack + 9 sections + 10 components + 9 validators
    #   + 6 new recovery (+ shared recovery.admin-drift) + 1 progress + 1 learning = 38 new
    # Admin: 1 app + 1 stack + 11 sections + 12 components + 8 new validators (+ 2 reused)
    #   + 7 new recovery (+ shared recovery.crud-sprawl) + 1 progress + 1 learning = 42 new
    # Total = 139
    assert len(website_pack.modules) == 139


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


def test_reference_checker_passes_for_saas_app_type():
    import importlib.util
    import sys

    script_path = REPO_ROOT / "scripts/check_build_registry_references.py"
    spec = importlib.util.spec_from_file_location(
        "check_build_registry_references_website_saas",
        script_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    result = module.run_reference_checks(
        WEBSITE_PACK_MANIFEST,
        app_type=APP_TYPE_ID_SAAS,
        check_orphans=True,
        check_render_budget=True,
    )
    assert result.errors == []
    assert result.summary_counts["error"] == 0


def test_reference_checker_passes_for_admin_app_type():
    import importlib.util
    import sys

    script_path = REPO_ROOT / "scripts/check_build_registry_references.py"
    spec = importlib.util.spec_from_file_location(
        "check_build_registry_references_website_admin",
        script_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    result = module.run_reference_checks(
        WEBSITE_PACK_MANIFEST,
        app_type=APP_TYPE_ID_ADMIN,
        check_orphans=True,
        check_render_budget=True,
    )
    assert result.errors == []
    assert result.summary_counts["error"] == 0
