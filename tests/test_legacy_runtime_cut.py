"""Structural cut tests for the legacy deterministic scaffold retirement.

Pins:
- ``src/ham/builder_legacy_templates.py`` is deleted (no production
  module imports it).
- No production module imports the retired legacy prompt detectors
  (``_is_calculator_prompt``, ``_is_tetris_prompt``,
  ``legacy_template_kind_for_prompt``).
- :func:`select_scaffold_path` never returns ``"legacy_deterministic"``
  for any kind (the registry is empty).
- Calculator / Tetris prompts that flow through
  :func:`maybe_chat_scaffold_for_turn` without an OpenRouter key surface
  a typed ``model_access_required`` signal instead of silently producing
  legacy deterministic content.

Retirement commit: refactor(builder): retire legacy deterministic scaffolds
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from src.ham.builder_template_kinds import (
    _REGISTRY,
    legacy_deterministic_kinds,
    select_scaffold_path,
)


_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src"


def _iter_src_py_files():
    for path in _SRC_ROOT.rglob("*.py"):
        yield path


def _iter_imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, None
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                yield module, alias.name


# ---------------------------------------------------------------------------
# 1. Legacy module is deleted
# ---------------------------------------------------------------------------


def test_legacy_templates_module_is_deleted() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("src.ham.builder_legacy_templates")


# ---------------------------------------------------------------------------
# 2. No production module imports the retired legacy templates module
# ---------------------------------------------------------------------------


def test_no_production_module_imports_builder_legacy_templates() -> None:
    offenders: list[str] = []
    for path in _iter_src_py_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - source must parse
            continue
        for module, _name in _iter_imports(tree):
            if module == "src.ham.builder_legacy_templates" or module.endswith(
                ".builder_legacy_templates"
            ):
                offenders.append(str(path.relative_to(_REPO_ROOT)))
                break
    assert offenders == [], (
        "production modules still import the retired legacy templates module: "
        f"{offenders!r}"
    )


# ---------------------------------------------------------------------------
# 3. No production module imports the retired legacy prompt detectors
# ---------------------------------------------------------------------------


_RETIRED_DETECTOR_NAMES: frozenset[str] = frozenset(
    {
        "_is_calculator_prompt",
        "_is_tetris_prompt",
        "legacy_template_kind_for_prompt",
    }
)


def test_no_production_module_imports_legacy_prompt_detectors() -> None:
    offenders: list[tuple[str, str]] = []
    for path in _iter_src_py_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - source must parse
            continue
        for _module, name in _iter_imports(tree):
            if name and name in _RETIRED_DETECTOR_NAMES:
                offenders.append((str(path.relative_to(_REPO_ROOT)), name))
    assert offenders == [], (
        "production modules still import retired legacy prompt detectors: "
        f"{offenders!r}"
    )


# ---------------------------------------------------------------------------
# 4. select_scaffold_path is always "llm" — never "legacy_deterministic"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [
        "calculator",
        "tetris",
        "todo",
        "dashboard",
        "landing-page",
        "blog",
        "kanban",
        "unknown",
        "",
        " ",
        "Calculator",
    ],
)
def test_select_scaffold_path_never_returns_legacy_deterministic(kind: str) -> None:
    assert select_scaffold_path(kind) == "llm"


# ---------------------------------------------------------------------------
# 5. Empty registry / legacy set
# ---------------------------------------------------------------------------


def test_registry_is_empty() -> None:
    assert _REGISTRY == {}
    assert legacy_deterministic_kinds() == frozenset()


# ---------------------------------------------------------------------------
# 6. Calculator / Tetris prompts without API key → model_access_required
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt",
    [
        "ham build me a calculator app",
        "build a tetris clone",
    ],
)
def test_legacy_prompts_without_api_key_signal_model_access_required(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    prompt: str,
) -> None:
    from src.ham.builder_chat_scaffold import maybe_chat_scaffold_for_turn
    from src.persistence.builder_source_store import (
        BuilderSourceStore,
        set_builder_source_store_for_tests,
    )

    for name in (
        "OPENROUTER_API_KEY",
        "HAM_OPENROUTER_API_KEY",
        "HAM_PLANNER_OPENROUTER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "src.llm_client.normalized_openrouter_api_key",
        lambda: "",
    )

    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        summary = maybe_chat_scaffold_for_turn(
            workspace_id="ws_cut_test",
            project_id="proj_cut_test",
            session_id=f"sess_cut_{prompt[:8]}",
            last_user_plain=prompt,
            created_by="u1",
        )
        assert summary is not None
        assert summary.get("model_access_required") is True
        assert summary.get("scaffolded") is False
        # No snapshot must have been persisted from legacy deterministic content.
        snaps = store.list_source_snapshots(
            workspace_id="ws_cut_test", project_id="proj_cut_test"
        )
        assert snaps == []
    finally:
        set_builder_source_store_for_tests(None)
