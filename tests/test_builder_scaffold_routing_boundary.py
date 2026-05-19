"""Strangler-pattern routing boundary tests (ADR-0011).

These tests pin the contract between
``src/ham/builder_template_kinds.py`` (the registry) and
``src/ham/builder_llm_scaffold.py`` (the canonical LLM scaffold path):

- The LLM scaffold path is the default for everything except the frozen
  legacy set ``{calculator, tetris}``.
- ``builder_llm_scaffold.generate_scaffold`` keeps an invariant signature
  (``plan, project_id, workspace_id``) so callers can rely on the boundary.
- The LLM scaffold refuses to run without an OpenRouter API key — it
  surfaces a typed ``LLMScaffoldError`` rather than calling out to a live
  endpoint. These tests never make a network call.
- The chat-side scaffold module (``builder_chat_scaffold``) does not
  silently grow new template kinds beyond ``{calculator, tetris}``.
"""

from __future__ import annotations

import inspect
import re
from typing import get_type_hints

import pytest

from src.ham import builder_chat_scaffold
from src.ham.builder_error_codes import STEP_MODEL_UNAVAILABLE
from src.ham.builder_llm_scaffold import (
    LLMScaffoldError,
    ScaffoldResult,
    generate_scaffold,
)
from src.ham.builder_plan import Plan, Step
from src.ham.builder_template_kinds import (
    legacy_deterministic_kinds,
    select_scaffold_path,
)


_LLM_DEFAULT_KINDS: tuple[str, ...] = (
    "todo",
    "dashboard",
    "landing-page",
    "blog",
    "chat-assistant",
    "kanban",
    "analytics-portal",
    "chess",
    "snake",
    "shop",
    "form-builder",
)


# ---------------------------------------------------------------------------
# Registry / LLM-default boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", _LLM_DEFAULT_KINDS)
def test_non_legacy_kinds_route_to_llm(kind: str) -> None:
    assert select_scaffold_path(kind) == "llm"


def test_legacy_set_is_a_subset_of_supported_paths_only() -> None:
    # The legacy set is exactly the registry's legacy entries; nothing
    # else may be routed to the legacy deterministic path.
    legacy = legacy_deterministic_kinds()
    assert legacy == frozenset({"calculator", "tetris"})
    for kind in _LLM_DEFAULT_KINDS:
        assert kind not in legacy


# ---------------------------------------------------------------------------
# LLM scaffold invariant signature
# ---------------------------------------------------------------------------


def test_generate_scaffold_signature_is_invariant() -> None:
    sig = inspect.signature(generate_scaffold)
    assert list(sig.parameters.keys()) == ["plan", "project_id", "workspace_id"]
    hints = get_type_hints(generate_scaffold)
    assert hints["plan"] is Plan
    assert hints["return"] is ScaffoldResult


# ---------------------------------------------------------------------------
# LLM scaffold safety: never calls a live endpoint without explicit key
# ---------------------------------------------------------------------------


def test_generate_scaffold_without_api_key_raises_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No OpenRouter key → typed LLMScaffoldError; no network access attempted."""
    # Wipe any keys the test process may have inherited so the gate fires.
    for name in (
        "OPENROUTER_API_KEY",
        "HAM_OPENROUTER_API_KEY",
        "HAM_PLANNER_OPENROUTER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    plan = Plan(
        plan_id="pln_routing_boundary_test",
        workspace_id="ws_test",
        project_id="proj_test",
        user_message="Build a todo app",
        steps=[Step(title="Scaffold todo app", description="Create initial files")],
        planner_confidence="high",
        metadata={"template_kind": "todo"},
    )

    with pytest.raises(LLMScaffoldError) as excinfo:
        generate_scaffold(plan, project_id="proj_test", workspace_id="ws_test")
    assert excinfo.value.error_code == STEP_MODEL_UNAVAILABLE


# ---------------------------------------------------------------------------
# Chat-side scaffold does not silently grow new legacy template kinds
# ---------------------------------------------------------------------------


def test_builder_chat_scaffold_only_carries_known_legacy_detectors() -> None:
    """If a new ``_is_<kind>_prompt`` detector lands without an ADR / registry
    entry, this assertion fails and forces a deliberate review.

    The registry is the single source of truth for legacy kinds; adding a
    new module-private detector in ``builder_chat_scaffold`` without
    updating the registry would silently bypass it.
    """
    detector_names = {
        name
        for name in dir(builder_chat_scaffold)
        if re.fullmatch(r"_is_[a-z_]+_prompt", name)
    }
    assert detector_names == {
        "_is_calculator_prompt",
        "_is_tetris_prompt",
    }, (
        "builder_chat_scaffold gained or lost a legacy template detector. "
        "If you intend to add a new legacy kind, also update "
        "src/ham/builder_template_kinds._REGISTRY and the lock test in "
        "tests/test_builder_template_kinds.py."
    )
