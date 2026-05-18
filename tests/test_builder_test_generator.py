"""Tests for src/ham/builder_test_generator.py — Phase 1 #5 (Tier 1 #19).

Covers: golden-file stability, structure assertions, determinism.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ham.builder_plan import Plan, Step
from src.ham.builder_test_generator import generate

_FIXTURES = Path(__file__).parent / "fixtures" / "builder_test_generator"
_PREVIEW_URL = "http://localhost:3000"


def _single_step_plan() -> Plan:
    return Plan(
        plan_id="pln_golden_single",
        workspace_id="ws_g",
        project_id="proj_g",
        user_message="Test",
        planner_confidence="high",
        steps=[Step(step_id="stp_1", title="Add button", description="Create a Submit button")],
    )


def _multi_step_plan() -> Plan:
    return Plan(
        plan_id="pln_golden_multi",
        workspace_id="ws_g",
        project_id="proj_g",
        user_message="Test",
        planner_confidence="high",
        steps=[
            Step(step_id="stp_1", title="Create heading", description="Add page heading"),
            Step(step_id="stp_2", title="Add form", description="Create input form"),
            Step(step_id="stp_3", title="Add link", description="Insert navigation link"),
        ],
    )


def _destructive_plan() -> Plan:
    return Plan(
        plan_id="pln_golden_destr",
        workspace_id="ws_g",
        project_id="proj_g",
        user_message="Test",
        planner_confidence="high",
        destructive=True,
        steps=[
            Step(
                step_id="stp_1",
                title="Delete table",
                description="Remove the data table",
                requires_approval=True,
            )
        ],
    )


class TestGoldenFiles:
    def test_single_step_matches_golden(self):
        expected = (_FIXTURES / "single_step.js").read_text(encoding="utf-8")
        actual = generate(_single_step_plan(), _PREVIEW_URL)
        assert actual == expected

    def test_multi_step_matches_golden(self):
        expected = (_FIXTURES / "multi_step.js").read_text(encoding="utf-8")
        actual = generate(_multi_step_plan(), _PREVIEW_URL)
        assert actual == expected

    def test_destructive_step_matches_golden(self):
        expected = (_FIXTURES / "destructive_step.js").read_text(encoding="utf-8")
        actual = generate(_destructive_plan(), _PREVIEW_URL)
        assert actual == expected


class TestOutputStructure:
    def test_output_contains_playwright_imports(self):
        src = generate(_single_step_plan(), _PREVIEW_URL)
        assert "require('@playwright/test')" in src

    def test_output_contains_plan_id(self):
        src = generate(_single_step_plan(), _PREVIEW_URL)
        assert "pln_golden_single" in src

    def test_output_contains_preview_url(self):
        src = generate(_single_step_plan(), _PREVIEW_URL)
        assert _PREVIEW_URL in src

    def test_output_contains_step_title(self):
        src = generate(_single_step_plan(), _PREVIEW_URL)
        assert "Add button" in src

    def test_multi_step_has_all_steps(self):
        src = generate(_multi_step_plan(), _PREVIEW_URL)
        assert "Step 1:" in src
        assert "Step 2:" in src
        assert "Step 3:" in src

    def test_output_has_body_not_empty_assertion(self):
        src = generate(_single_step_plan(), _PREVIEW_URL)
        assert "not.toBeEmpty" in src

    def test_output_includes_button_role_assertion_when_button_in_title(self):
        src = generate(_single_step_plan(), _PREVIEW_URL)
        assert "getByRole('button')" in src

    def test_output_has_goto_call(self):
        src = generate(_single_step_plan(), _PREVIEW_URL)
        assert f"page.goto('{_PREVIEW_URL}'" in src


class TestDeterminism:
    def test_same_inputs_produce_identical_output(self):
        plan = _single_step_plan()
        assert generate(plan, _PREVIEW_URL) == generate(plan, _PREVIEW_URL)

    def test_different_url_produces_different_output(self):
        plan = _single_step_plan()
        src1 = generate(plan, "http://localhost:3000")
        src2 = generate(plan, "http://localhost:9999")
        assert src1 != src2
        assert "localhost:9999" in src2
