"""Tests for src/ham/builder_kits.py — composable Builder Kit contract.

These tests pin the data contract for kit metadata, the
``get_kit_for_template_kind`` selection behavior (including the
``generic`` fallback), and the wire-through of kit context into the
LLM scaffold message stream. No live LLM / gateway / agent calls.
"""

from __future__ import annotations

import json

import pytest

import src.ham.builder_kits as builder_kits
from src.ham.builder_kits import (
    BuilderKit,
    BuilderKitConfigError,
    BuilderResource,
    BuilderResourceConfigError,
    _load_kits_from_disk,
    _load_resources_from_disk,
    get_kit,
    get_kit_for_template_kind,
    get_resource,
    iter_kits,
    iter_resources,
    list_kit_ids,
    list_resource_ids,
    list_resources_for_kit,
    render_kit_context,
    resources_allowed_for_generation,
    validate_kit_resource_ids,
)
from src.ham.builder_llm_scaffold import generate_scaffold
from src.ham.builder_plan import Plan, Step
from src.ham.builder_template_kinds import (
    legacy_deterministic_kinds,
    select_scaffold_path,
)


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

_EXPECTED_KIT_IDS: frozenset[str] = frozenset(
    {"calculator", "tetris", "todo", "dashboard", "landing-page", "generic"}
)


def _make_plan(template_kind: str) -> Plan:
    return Plan(
        plan_id="pln_kits_test",
        workspace_id="ws_test",
        project_id="proj_test",
        user_message="Build something",
        steps=[Step(title="Scaffold", description="Create initial files")],
        planner_confidence="high",
        metadata={"template_kind": template_kind},
    )


# ---------------------------------------------------------------------------
# 1. Kit loading
# ---------------------------------------------------------------------------


class TestKitLoading:
    def test_loads_at_least_the_expected_kits(self):
        kits = _load_kits_from_disk()
        assert _EXPECTED_KIT_IDS.issubset(kits.keys())

    def test_list_kit_ids_is_exact_expected_set(self):
        assert set(list_kit_ids()) == _EXPECTED_KIT_IDS

    def test_list_kit_ids_is_sorted_tuple(self):
        ids = list_kit_ids()
        assert isinstance(ids, tuple)
        assert list(ids) == sorted(ids)

    def test_every_kit_has_required_fields(self):
        for kit in iter_kits():
            assert isinstance(kit, BuilderKit)
            assert isinstance(kit.kit_id, str) and kit.kit_id
            assert isinstance(kit.app_archetype, str) and kit.app_archetype
            assert isinstance(kit.supported_template_kinds, tuple)
            assert isinstance(kit.stack_recipe, tuple) and kit.stack_recipe
            assert isinstance(kit.expected_files, tuple)
            assert isinstance(kit.expected_routes, tuple)
            assert isinstance(kit.design_recipe, tuple)
            assert isinstance(kit.allowed_capabilities, tuple)
            assert isinstance(kit.validation_checklist, tuple)
            assert kit.validation_checklist, kit.kit_id
            assert isinstance(kit.safety_constraints, tuple)
            assert isinstance(kit.examples, tuple)
            assert isinstance(kit.legacy_parity_only, bool)
            assert kit.migration_note is None or isinstance(kit.migration_note, str)


# ---------------------------------------------------------------------------
# 2. Parity / legacy kit mapping
# ---------------------------------------------------------------------------


class TestParityKitMapping:
    def test_calculator_kit_resolves_by_kind(self):
        kit = get_kit_for_template_kind("calculator")
        assert kit is not None
        assert kit.kit_id == "calculator"

    def test_tetris_kit_resolves_by_kind(self):
        kit = get_kit_for_template_kind("tetris")
        assert kit is not None
        assert kit.kit_id == "tetris"

    def test_legacy_kits_marked_parity_only(self):
        for kit_id in ("calculator", "tetris"):
            kit = get_kit_for_template_kind(kit_id)
            assert kit is not None
            assert kit.legacy_parity_only is True, kit_id

    def test_non_legacy_kits_not_marked_parity_only(self):
        legacy = {"calculator", "tetris"}
        for kit in iter_kits():
            if kit.kit_id in legacy:
                continue
            assert kit.legacy_parity_only is False, kit.kit_id


# ---------------------------------------------------------------------------
# 3. Non-legacy kinds route to LLM and have kits
# ---------------------------------------------------------------------------


class TestNonLegacyKindsHaveKits:
    @pytest.mark.parametrize("kind", ["todo", "dashboard", "landing-page"])
    def test_routes_to_llm_path(self, kind: str):
        assert select_scaffold_path(kind) == "llm"

    @pytest.mark.parametrize("kind", ["todo", "dashboard", "landing-page"])
    def test_kit_resolves_for_kind(self, kind: str):
        kit = get_kit_for_template_kind(kind)
        assert kit is not None
        assert (
            kit.kit_id == kind or kind in kit.supported_template_kinds
        ), f"kit {kit.kit_id!r} does not advertise support for {kind!r}"

    def test_whitespace_and_case_variants_resolve(self):
        kit = get_kit_for_template_kind("  Todo  ")
        assert kit is not None
        assert kit.kit_id == "todo"


# ---------------------------------------------------------------------------
# 4. Unknown kinds → generic fallback
# ---------------------------------------------------------------------------


class TestGenericFallback:
    def test_unknown_kind_falls_back_to_generic(self):
        kit = get_kit_for_template_kind("totally-unknown-kind")
        assert kit is not None
        assert kit.kit_id == "generic"

    def test_empty_string_falls_back_to_generic(self):
        kit = get_kit_for_template_kind("")
        assert kit is not None
        assert kit.kit_id == "generic"

    def test_generic_kit_is_safe(self):
        kit = get_kit_for_template_kind("totally-unknown-kind")
        assert kit is not None
        assert kit.legacy_parity_only is False
        assert kit.validation_checklist  # non-empty


# ---------------------------------------------------------------------------
# 5. No new kinds route to legacy_deterministic
# ---------------------------------------------------------------------------


class TestLegacyRoutingInvariant:
    def test_only_legacy_kits_claim_legacy_kinds(self):
        legacy = {"calculator", "tetris"}
        for kit in iter_kits():
            overlap = set(kit.supported_template_kinds) & legacy
            if kit.kit_id in legacy:
                assert overlap == {kit.kit_id}, kit.kit_id
            else:
                assert overlap == set(), (
                    f"non-legacy kit {kit.kit_id!r} claims legacy kinds "
                    f"{overlap!r}"
                )

    def test_legacy_deterministic_kinds_is_empty_after_retirement(self):
        assert legacy_deterministic_kinds() == frozenset()


# ---------------------------------------------------------------------------
# 6. LLM scaffold receives kit context (mocked, no live calls)
# ---------------------------------------------------------------------------


class TestScaffoldReceivesKitContext:
    def _run_capture(self, monkeypatch, template_kind: str) -> str:
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test",
        )
        captured: list[list[dict]] = []

        def _capture(messages, **kwargs):
            captured.append(list(messages))
            return _VALID_LLM_JSON

        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.complete_chat_messages_openrouter",
            _capture,
        )
        plan = _make_plan(template_kind)
        generate_scaffold(plan, project_id="proj_test", workspace_id="ws_test")
        assert captured, "complete_chat_messages_openrouter was not called"
        return captured[0][1]["content"]

    def test_todo_kit_context_in_user_message(self, monkeypatch):
        content = self._run_capture(monkeypatch, "todo")
        assert "Builder Kit: todo" in content
        assert "Stack:" in content

    def test_dashboard_kit_context_in_user_message(self, monkeypatch):
        content = self._run_capture(monkeypatch, "dashboard")
        assert "Builder Kit: dashboard" in content
        assert "stat card" in content

    def test_unknown_kind_falls_through_to_generic_kit(self, monkeypatch):
        content = self._run_capture(monkeypatch, "totally-unknown-kind")
        assert "Builder Kit: generic" in content


# ---------------------------------------------------------------------------
# 7. Migration markers
# ---------------------------------------------------------------------------


class TestMigrationMarkers:
    def test_template_kinds_migration_policy(self):
        from src.ham.builder_template_kinds import MIGRATION_POLICY

        assert isinstance(MIGRATION_POLICY, str)
        assert MIGRATION_POLICY.strip()
        text = MIGRATION_POLICY.lower()
        assert "legacy" in text
        assert "frozen" in text
        assert "parity" in text

    def test_template_kinds_migration_policy_is_past_tense(self):
        from src.ham.builder_template_kinds import MIGRATION_POLICY

        assert "retired" in MIGRATION_POLICY.lower()


# ---------------------------------------------------------------------------
# 8. render_kit_context shape
# ---------------------------------------------------------------------------


class TestRenderKitContextShape:
    def test_starts_with_kit_id_header(self):
        kit = get_kit_for_template_kind("todo")
        assert kit is not None
        rendered = render_kit_context(kit)
        assert rendered.startswith(f"Builder Kit: {kit.kit_id}")

    def test_contains_required_section_headers(self):
        kit = get_kit_for_template_kind("dashboard")
        assert kit is not None
        rendered = render_kit_context(kit)
        assert "Archetype:" in rendered
        assert "Stack:" in rendered
        assert "Validation checklist:" in rendered

    def test_render_is_deterministic(self):
        kit = get_kit_for_template_kind("landing-page")
        assert kit is not None
        assert render_kit_context(kit) == render_kit_context(kit)


# ---------------------------------------------------------------------------
# 9. No live runtime imports in builder_kits
# ---------------------------------------------------------------------------


def test_builder_kits_does_not_import_live_runtime_dependencies():
    forbidden = (
        "complete_chat_messages_openrouter",
        "stream_chat_turn",
        "complete_chat_turn",
        "execute_droid_workflow",
        "run_cursor_agent_launch",
        "generate_scaffold",
    )
    mod_attrs = set(vars(builder_kits).keys())
    for name in forbidden:
        assert name not in mod_attrs, (
            f"builder_kits must not import runtime API {name!r}"
        )


# ---------------------------------------------------------------------------
# 10. Kit JSON well-formedness
# ---------------------------------------------------------------------------


class TestKitJsonWellFormedness:
    def test_reload_is_idempotent(self):
        first = _load_kits_from_disk()
        second = _load_kits_from_disk()
        assert set(first.keys()) == set(second.keys())
        for kit_id in first:
            assert first[kit_id] == second[kit_id]

    def test_duplicate_kit_id_raises(self, tmp_path):
        payload = {
            "kit_id": "dup-kit",
            "app_archetype": "single-page-utility",
            "supported_template_kinds": ["dup-kit"],
            "stack_recipe": ["react", "typescript"],
            "expected_files": ["src/App.tsx"],
            "expected_routes": [],
            "design_recipe": ["single-card-centered"],
            "allowed_capabilities": ["local-state"],
            "validation_checklist": ["App renders without errors"],
            "safety_constraints": ["no-network-egress"],
            "examples": [],
            "legacy_parity_only": False,
            "migration_note": None,
        }
        (tmp_path / "first.json").write_text(json.dumps(payload), encoding="utf-8")
        (tmp_path / "second.json").write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(BuilderKitConfigError, match="duplicate kit_id"):
            _load_kits_from_disk(tmp_path)

    def test_missing_required_field_raises(self, tmp_path):
        payload = {
            "kit_id": "broken-kit",
            "app_archetype": "single-page-utility",
            # missing supported_template_kinds and others
        }
        (tmp_path / "broken.json").write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(BuilderKitConfigError, match="missing required field"):
            _load_kits_from_disk(tmp_path)


# ---------------------------------------------------------------------------
# 11. Resource catalog basics
# ---------------------------------------------------------------------------


_EXPECTED_RESOURCE_IDS: frozenset[str] = frozenset(
    {
        "shadcn-ui",
        "page-ui",
        "launch-ui-free",
        "lucide-icons",
        "framer-motion",
        "shadcn-charts",
        "recharts",
        "tanstack-table",
        "react-hook-form",
        "zod",
        "tanstack-query",
        "dummyjson",
        "jsonplaceholder",
        "playwright",
        "axe-core",
        "preline-ui",
    }
)

_ALLOWED_RESOURCE_TYPES: frozenset[str] = frozenset(
    {
        "component-library",
        "ui-blocks",
        "ui-library",
        "charting",
        "table",
        "form",
        "validation",
        "accessibility-validation",
        "data-fetching",
        "mock-api",
        "icons",
        "animation",
        "reference-only",
    }
)
_ALLOWED_LICENSE_STATUSES: frozenset[str] = frozenset(
    {"safe-direct", "safe-reference", "restricted", "unknown"}
)
_ALLOWED_FREE_STATUSES: frozenset[str] = frozenset(
    {"free", "freemium", "paid", "mixed"}
)
_ALLOWED_USAGE_POLICIES: frozenset[str] = frozenset(
    {"use_directly", "reference_only", "avoid"}
)


class TestResourceCatalog:
    def test_resources_catalog_loads(self):
        resources = _load_resources_from_disk()
        assert resources, "resource catalog must be non-empty"
        assert set(resources.keys()) == _EXPECTED_RESOURCE_IDS

    def test_every_resource_has_required_fields(self):
        for resource in iter_resources():
            assert isinstance(resource, BuilderResource)
            assert isinstance(resource.resource_id, str) and resource.resource_id
            assert isinstance(resource.name, str) and resource.name
            assert resource.type in _ALLOWED_RESOURCE_TYPES
            assert isinstance(resource.url, str) and resource.url
            assert isinstance(resource.license, str) and resource.license
            assert resource.license_status in _ALLOWED_LICENSE_STATUSES
            assert resource.free_status in _ALLOWED_FREE_STATUSES
            assert isinstance(resource.api_key_required, bool)
            assert isinstance(resource.offline_friendly, bool)
            assert isinstance(resource.agent_friendliness, int)
            assert 1 <= resource.agent_friendliness <= 5
            assert isinstance(resource.recommended_for, tuple)
            assert resource.recommended_for
            assert resource.usage_policy in _ALLOWED_USAGE_POLICIES
            assert isinstance(resource.notes, str)
            assert isinstance(resource.risks, str)

    def test_resource_urls_are_https(self):
        for resource in iter_resources():
            assert resource.url.startswith("https://"), resource.resource_id


# ---------------------------------------------------------------------------
# 12. Beta-kit <-> resource wiring
# ---------------------------------------------------------------------------


class TestBetaKitResourceWiring:
    def test_landing_page_kit_includes_required_resources(self):
        kit = get_kit("landing-page")
        assert kit is not None
        ids = set(kit.recommended_resources)
        assert {
            "shadcn-ui",
            "page-ui",
            "launch-ui-free",
            "lucide-icons",
            "framer-motion",
        }.issubset(ids)

    def test_dashboard_kit_includes_required_resources(self):
        kit = get_kit("dashboard")
        assert kit is not None
        ids = set(kit.recommended_resources)
        assert {
            "shadcn-ui",
            "shadcn-charts",
            "recharts",
            "tanstack-table",
            "lucide-icons",
        }.issubset(ids)
        mock_apis = {
            resource_id
            for resource_id in ids
            if (resource := get_resource(resource_id)) is not None
            and resource.type == "mock-api"
        }
        assert mock_apis, "dashboard must recommend at least one mock-api resource"

    def test_todo_kit_includes_required_resources(self):
        kit = get_kit("todo")
        assert kit is not None
        ids = set(kit.recommended_resources)
        assert {
            "shadcn-ui",
            "react-hook-form",
            "zod",
            "lucide-icons",
        }.issubset(ids)
        mock_apis = {
            resource_id
            for resource_id in ids
            if (resource := get_resource(resource_id)) is not None
            and resource.type == "mock-api"
        }
        assert mock_apis, "todo must recommend at least one mock-api resource"

    def test_every_recommended_resource_id_resolves(self):
        for kit in iter_kits():
            for resource_id in kit.recommended_resources:
                assert get_resource(resource_id) is not None, (
                    f"kit {kit.kit_id!r} recommends unknown resource "
                    f"{resource_id!r}"
                )

    @pytest.mark.parametrize("kit_id", ["landing-page", "dashboard", "todo"])
    def test_beta_kits_have_non_empty_recommended_resources(self, kit_id: str):
        kit = get_kit(kit_id)
        assert kit is not None
        assert kit.recommended_resources, kit_id


# ---------------------------------------------------------------------------
# 13. License / policy enforcement
# ---------------------------------------------------------------------------


class TestResourcePolicyEnforcement:
    def test_validate_kit_resource_ids_passes_at_import(self):
        validate_kit_resource_ids()

    def test_no_kit_recommends_a_reference_only_or_avoid_resource(self):
        for kit in iter_kits():
            for resource_id in kit.recommended_resources:
                resource = get_resource(resource_id)
                assert resource is not None
                assert resource.usage_policy == "use_directly", (
                    f"kit {kit.kit_id!r} recommends {resource_id!r} with "
                    f"usage_policy={resource.usage_policy!r}"
                )

    def test_preline_is_restricted_and_reference_only(self):
        resource = get_resource("preline-ui")
        assert resource is not None
        assert resource.license_status == "restricted"
        assert resource.usage_policy == "reference_only"
        assert resource.recommended_for == ("none",)

    def test_no_kit_recommends_preline(self):
        for kit in iter_kits():
            assert "preline-ui" not in kit.recommended_resources, kit.kit_id

    def test_resources_allowed_for_generation_excludes_restricted(self):
        for kit_id in ("landing-page", "dashboard", "todo"):
            allowed = resources_allowed_for_generation(kit_id)
            for resource in allowed:
                assert resource.usage_policy == "use_directly"
                assert resource.license_status in {"safe-direct", "safe-reference"}
                assert resource.resource_id != "preline-ui"

    def test_validate_kit_resource_ids_raises_on_unknown_id(self, monkeypatch):
        original = dict(builder_kits._KITS)
        try:
            synthetic = BuilderKit(
                kit_id="synthetic-unknown",
                app_archetype="single-page-utility",
                supported_template_kinds=("synthetic-unknown",),
                stack_recipe=("vite-react",),
                expected_files=("src/App.tsx",),
                expected_routes=(),
                design_recipe=("single-card-centered",),
                allowed_capabilities=("local-state",),
                validation_checklist=("App renders without errors",),
                safety_constraints=("no-network-egress",),
                recommended_resources=("nonexistent-resource",),
            )
            builder_kits._KITS["synthetic-unknown"] = synthetic
            with pytest.raises(
                BuilderResourceConfigError, match="unknown resource"
            ):
                validate_kit_resource_ids()
        finally:
            builder_kits._KITS.clear()
            builder_kits._KITS.update(original)

    def test_validate_kit_resource_ids_raises_on_restricted_id(self, monkeypatch):
        original = dict(builder_kits._KITS)
        try:
            synthetic = BuilderKit(
                kit_id="synthetic-restricted",
                app_archetype="marketing-site",
                supported_template_kinds=("synthetic-restricted",),
                stack_recipe=("vite-react",),
                expected_files=("src/App.tsx",),
                expected_routes=(),
                design_recipe=("hero-above-fold",),
                allowed_capabilities=("local-state",),
                validation_checklist=("App renders without errors",),
                safety_constraints=("no-network-egress",),
                recommended_resources=("preline-ui",),
            )
            builder_kits._KITS["synthetic-restricted"] = synthetic
            with pytest.raises(
                BuilderResourceConfigError, match="usage_policy"
            ):
                validate_kit_resource_ids()
        finally:
            builder_kits._KITS.clear()
            builder_kits._KITS.update(original)


# ---------------------------------------------------------------------------
# 14. render_kit_context resource block
# ---------------------------------------------------------------------------


class TestRenderKitContextResources:
    def test_render_kit_context_includes_recommended_resources_when_present(self):
        kit = get_kit("landing-page")
        assert kit is not None
        rendered = render_kit_context(kit)
        assert "Recommended resources:" in rendered
        for resource_id in kit.recommended_resources:
            assert resource_id in rendered, resource_id

    def test_render_kit_context_omits_block_when_empty(self):
        kit = get_kit("generic")
        assert kit is not None
        assert kit.recommended_resources == ()
        rendered = render_kit_context(kit)
        assert "Recommended resources:" not in rendered


# ---------------------------------------------------------------------------
# 15. Schema preservation
# ---------------------------------------------------------------------------


class TestRecommendedResourcesDefault:
    @pytest.mark.parametrize("kit_id", ["calculator", "tetris", "generic"])
    def test_recommended_resources_field_defaults_to_empty_tuple(self, kit_id: str):
        kit = get_kit(kit_id)
        assert kit is not None
        assert kit.recommended_resources == ()


# ---------------------------------------------------------------------------
# 16. list_resources_for_kit / list_resource_ids basics
# ---------------------------------------------------------------------------


class TestResourceListing:
    def test_list_resource_ids_is_sorted_tuple(self):
        ids = list_resource_ids()
        assert isinstance(ids, tuple)
        assert list(ids) == sorted(ids)
        assert set(ids) == _EXPECTED_RESOURCE_IDS

    def test_list_resources_for_kit_landing_page(self):
        resources = list_resources_for_kit("landing-page")
        ids = {resource.resource_id for resource in resources}
        assert "page-ui" in ids
        assert "shadcn-ui" in ids
        # Preline is recommended_for=["none"], so it must NOT appear here.
        assert "preline-ui" not in ids

    def test_get_resource_is_whitespace_and_case_tolerant(self):
        assert get_resource("  Shadcn-UI  ") is not None
        assert get_resource("") is None
        assert get_resource("totally-unknown-resource") is None
