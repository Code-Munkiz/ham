"""Synthetic plan ``template_kind`` resolves to the prompt-selected Builder Kit."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.ham.builder_chat_scaffold import _maybe_llm_scaffold_replace
from src.ham.builder_kits import get_kit_for_template_kind
from src.ham.builder_llm_scaffold import ScaffoldResult
from src.ham.clerk_auth import HamActor


def _byo_actor(uid: str = "user_kit") -> HamActor:
    return HamActor(
        user_id=uid,
        org_id=None,
        session_id=None,
        email=f"{uid}@example.com",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _captured(user_message: str) -> dict:
    captured: dict = {}

    def _fake_generate_scaffold(plan, **_kw):
        captured["plan"] = plan
        return ScaffoldResult(file_changes=[("src/App.tsx", "export default function App(){return null;}")], assertions=[])

    with patch(
        "src.llm_client.resolve_openrouter_api_key_for_actor",
        return_value="sk-or-v1-test_kit_selection_000000000000",
    ), patch(
        "src.ham.builder_llm_scaffold._get_scaffold_model",
        return_value="openrouter/anthropic/claude-3.5-haiku",
    ), patch(
        "src.ham.builder_llm_scaffold.generate_scaffold",
        side_effect=_fake_generate_scaffold,
    ):
        _maybe_llm_scaffold_replace(
            user_message=user_message,
            workspace_id="ws_kit",
            project_id="proj_kit",
            files={"src/App.tsx": "// placeholder"},
            scaffold_meta={},
            ham_actor=_byo_actor(),
        )
    assert "plan" in captured, "generate_scaffold was not invoked"
    return captured["plan"].metadata or {}


def _captured_result_meta(user_message: str) -> dict:
    """Returns the ``new_meta`` dict produced by ``_maybe_llm_scaffold_replace``.

    Mirrors ``_captured`` but inspects the LLM replace helper's return value so
    we can lock kit-routing metadata (``template_kind`` / ``scaffold_path`` /
    ``kit_id``) that downstream consumers (chat ``done`` payload, FE workbench)
    rely on to verify the request really hit the LLM-scaffold path.
    """

    def _fake_generate_scaffold(_plan, **_kw):
        return ScaffoldResult(
            file_changes=[("src/App.tsx", "export default function App(){return null;}")],
            assertions=[],
        )

    with patch(
        "src.llm_client.resolve_openrouter_api_key_for_actor",
        return_value="sk-or-v1-test_kit_selection_000000000000",
    ), patch(
        "src.ham.builder_llm_scaffold._get_scaffold_model",
        return_value="openrouter/anthropic/claude-3.5-haiku",
    ), patch(
        "src.ham.builder_llm_scaffold.generate_scaffold",
        side_effect=_fake_generate_scaffold,
    ):
        result = _maybe_llm_scaffold_replace(
            user_message=user_message,
            workspace_id="ws_kit",
            project_id="proj_kit",
            files={"src/App.tsx": "// placeholder"},
            scaffold_meta={},
            ham_actor=_byo_actor(),
        )
    assert isinstance(result, tuple) and len(result) == 2, (
        f"_maybe_llm_scaffold_replace returned {result!r}; expected (files, meta) tuple"
    )
    return result[1]


@pytest.mark.parametrize(
    ("phrase", "expected_kit"),
    [
        ("build me a landing page for roofers", "landing-page"),
        ("build me an analytics dashboard", "dashboard"),
        ("build a task tracker", "todo"),
        ("build a calculator", "calculator"),
        ("build me a tetris clone", "tetris"),
        ("build me a CRM", "generic"),
    ],
)
def test_synthetic_plan_carries_selected_kit(phrase: str, expected_kit: str) -> None:
    metadata = _captured(phrase)
    assert metadata.get("template_kind") == expected_kit
    assert metadata.get("originated_from") == "builder_chat_scaffold"


def test_ham_scaffold_model_env_used_when_no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.ham.builder_llm_scaffold import _get_scaffold_model as real_get_scaffold_model

    seen: list[str] = []

    def _spy_get_scaffold_model(**kwargs):
        model = real_get_scaffold_model(**kwargs)
        seen.append(model)
        return model

    def _fake_generate_scaffold(_plan, **_kw):
        return ScaffoldResult(
            file_changes=[("src/App.tsx", "export default function App(){return null;}")],
            assertions=[],
        )

    monkeypatch.setenv("HAM_SCAFFOLD_MODEL", "qwen/qwen3-coder:free")
    monkeypatch.delenv("HAM_PLANNER_MODEL", raising=False)
    monkeypatch.setenv("DEFAULT_MODEL", "minimax/minimax-m2.5:free")

    with patch(
        "src.llm_client.resolve_openrouter_api_key_for_actor",
        return_value="sk-or-v1-test_kit_selection_000000000000",
    ), patch(
        "src.ham.builder_llm_scaffold._get_scaffold_model",
        side_effect=_spy_get_scaffold_model,
    ), patch(
        "src.ham.builder_llm_scaffold.generate_scaffold",
        side_effect=_fake_generate_scaffold,
    ):
        _maybe_llm_scaffold_replace(
            user_message="build me a landing page for roofers",
            workspace_id="ws_kit",
            project_id="proj_kit",
            files={"src/App.tsx": "// placeholder"},
            scaffold_meta={},
            ham_actor=_byo_actor(),
        )
    assert "openrouter/qwen/qwen3-coder:free" in seen


def test_landing_page_template_kind_resolves_to_landing_kit() -> None:
    metadata = _captured("build me a landing page for roofers")
    template_kind = metadata.get("template_kind")
    kit = get_kit_for_template_kind(template_kind)
    assert kit is not None
    assert kit.kit_id == "landing-page"


@pytest.mark.parametrize(
    ("phrase", "expected_kit"),
    [
        ("build me a landing page for roofers", "landing-page"),
        ("build me an analytics dashboard", "dashboard"),
    ],
)
def test_llm_scaffold_replace_result_carries_kit_routing(
    phrase: str, expected_kit: str
) -> None:
    """`_maybe_llm_scaffold_replace` must surface ``template_kind`` / ``scaffold_path``
    / ``kit_id`` on its returned ``new_meta`` so the chat ``done`` event can
    confirm kit routing (root cause #4 — kit metadata propagation)."""
    meta = _captured_result_meta(phrase)
    assert meta.get("template_kind") == expected_kit
    assert meta.get("scaffold_path") == "llm"
    assert meta.get("kit_id") == expected_kit
