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


# ---------------------------------------------------------------------------
# 7. Per-actor Connected Tools OpenRouter key (BYO resolver)
# ---------------------------------------------------------------------------


def _byo_actor(uid: str = "user_byo"):
    from src.ham.clerk_auth import HamActor

    return HamActor(
        user_id=uid,
        org_id=None,
        session_id=None,
        email=f"{uid}@example.com",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def test_actor_connected_tools_key_wins_over_env_fallback(monkeypatch) -> None:
    from unittest.mock import patch

    from src.llm_client import resolve_openrouter_api_key_for_actor

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-envfallbackkey000000000000")
    actor = _byo_actor()
    with patch(
        "src.persistence.connected_tool_credentials.resolve_connected_tool_secret_plaintext",
        return_value="sk-or-v1-connectedtoolskey000000000000",
    ) as resolve_mock:
        key = resolve_openrouter_api_key_for_actor(actor)
    resolve_mock.assert_called_once_with(actor, "openrouter")
    assert key == "sk-or-v1-connectedtoolskey000000000000"
    assert key != "sk-or-v1-envfallbackkey000000000000"


def test_spaceship_prompt_no_key_signals_model_access_required(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    from src.ham.builder_chat_scaffold import maybe_chat_scaffold_for_turn
    from src.persistence.builder_source_store import (
        BuilderSourceStore,
        set_builder_source_store_for_tests,
    )

    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        with patch(
            "src.llm_client.resolve_openrouter_api_key_for_actor",
            return_value="",
        ):
            summary = maybe_chat_scaffold_for_turn(
                workspace_id="ws_cut_test",
                project_id="proj_cut_test",
                session_id="sess_spaceship_no_key",
                last_user_plain="build me a game where i can shoot things in a spaceship",
                created_by="user_1",
            )
        assert summary is not None
        assert summary.get("model_access_required") is True
        assert summary.get("scaffolded") is False
        snaps = store.list_source_snapshots(
            workspace_id="ws_cut_test", project_id="proj_cut_test"
        )
        assert snaps == []
    finally:
        set_builder_source_store_for_tests(None)


def test_spaceship_prompt_with_actor_byo_key_scaffolds(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    from src.ham.builder_chat_scaffold import maybe_chat_scaffold_for_turn
    from src.ham.builder_llm_scaffold import ScaffoldResult
    from src.persistence.builder_source_store import (
        BuilderSourceStore,
        set_builder_source_store_for_tests,
    )

    fake_app = (
        'import React from "react";\n'
        "export default function App() {\n"
        "  return <main><h1>Spaceship Shooter</h1><canvas /></main>;\n"
        "}\n"
    )
    fake_result = ScaffoldResult(
        file_changes=[("src/App.tsx", fake_app), ("package.json", "{}")],
        assertions=["canvas renders"],
    )

    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    actor = _byo_actor()
    try:
        with patch(
            "src.persistence.connected_tool_credentials.resolve_connected_tool_secret_plaintext",
            return_value="sk-or-v1-connectedtoolskey000000000000",
        ), patch(
            "src.ham.builder_llm_scaffold.generate_scaffold",
            return_value=fake_result,
        ) as gen_mock:
            summary = maybe_chat_scaffold_for_turn(
                workspace_id="ws_cut_test",
                project_id="proj_cut_test",
                session_id="sess_spaceship_actor_byo",
                last_user_plain="build me a game where i can shoot things in a spaceship",
                created_by=actor.user_id,
                ham_actor=actor,
            )
        assert gen_mock.called
        assert gen_mock.call_args.kwargs.get("ham_actor") is actor
        assert summary is not None
        assert summary.get("scaffolded") is True
        snap_id = str(summary["source_snapshot_id"])
        snap = next(
            row
            for row in store.list_source_snapshots(
                workspace_id="ws_cut_test", project_id="proj_cut_test"
            )
            if row.id == snap_id
        )
        app_tsx = str((snap.manifest or {}).get("inline_files", {}).get("src/App.tsx") or "")
        assert "Scaffold created from your chat request." not in app_tsx
        assert "Spaceship Shooter" in app_tsx
    finally:
        set_builder_source_store_for_tests(None)
