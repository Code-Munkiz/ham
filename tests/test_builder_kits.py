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
    _load_kits_from_disk,
    get_kit_for_template_kind,
    iter_kits,
    list_kit_ids,
    render_kit_context,
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

    def test_legacy_deterministic_kinds_still_frozen(self):
        assert legacy_deterministic_kinds() == frozenset({"calculator", "tetris"})


# ---------------------------------------------------------------------------
# 6. LLM scaffold receives kit context (mocked, no live calls)
# ---------------------------------------------------------------------------


class TestScaffoldReceivesKitContext:
    def _run_capture(self, monkeypatch, template_kind: str) -> str:
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.normalized_openrouter_api_key",
            lambda: "sk-or-test",
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

    def test_legacy_templates_retirement_gate(self):
        from src.ham.builder_legacy_templates import LEGACY_RETIREMENT_GATE

        assert isinstance(LEGACY_RETIREMENT_GATE, str)
        assert LEGACY_RETIREMENT_GATE.strip()
        assert "parity" in LEGACY_RETIREMENT_GATE.lower()


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
