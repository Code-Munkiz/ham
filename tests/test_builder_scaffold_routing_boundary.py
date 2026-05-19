"""Scaffold routing boundary tests.

The legacy_deterministic runtime path was retired; every kind (including
``calculator`` and ``tetris``) now routes through the LLM scaffold path.
These tests pin the contract between
``src/ham/builder_template_kinds.py`` and
``src/ham/builder_llm_scaffold.py``:

- :func:`select_scaffold_path` always returns ``"llm"``.
- ``legacy_deterministic_kinds()`` returns the empty set.
- ``builder_llm_scaffold.generate_scaffold`` keeps an invariant signature
  (``plan, project_id, workspace_id``) so callers can rely on the boundary.
- The LLM scaffold refuses to run without an OpenRouter API key — it
  surfaces a typed ``LLMScaffoldError`` rather than calling out to a live
  endpoint. These tests never make a network call.
"""

from __future__ import annotations

import inspect
from typing import get_type_hints

import pytest

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
    "calculator",
    "tetris",
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


def test_legacy_set_is_empty_after_retirement() -> None:
    """Legacy runtime path was retired; the registry exposes no kinds."""
    legacy = legacy_deterministic_kinds()
    assert legacy == frozenset()
    for kind in _LLM_DEFAULT_KINDS:
        assert kind not in legacy
        assert select_scaffold_path(kind) != "legacy_deterministic"


# ---------------------------------------------------------------------------
# LLM scaffold invariant signature
# ---------------------------------------------------------------------------


def test_generate_scaffold_signature_is_invariant() -> None:
    sig = inspect.signature(generate_scaffold)
    assert list(sig.parameters.keys())[:3] == ["plan", "project_id", "workspace_id"]
    ham_actor = sig.parameters.get("ham_actor")
    assert ham_actor is not None
    assert ham_actor.default is None
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
