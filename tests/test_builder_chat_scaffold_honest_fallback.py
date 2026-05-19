"""Regression tests for the "build me X" honest-fallback fix.

When the deterministic scaffold can't match a known template (calculator /
tetris) the chat-stream used to ship a generic placeholder + the success
copy "I've generated the project files". That was a lie when nothing
useful was produced.

These tests pin three guarantees:

1. Without an OpenRouter key, a non-template prompt produces a placeholder
   with ``placeholder_fallback=True`` AND the artifact verifier fails AND
   ``maybe_chat_scaffold_for_turn`` returns ``scaffolded=False`` so the
   chat-stream suppresses the success copy.
2. With an OpenRouter key + a successful LLM-scaffold response, the
   placeholder files are *replaced* with the real generated source and
   verification passes.
3. With an OpenRouter key but an LLM-scaffold failure, we still fall
   back to honest failure rather than rubber-stamping the placeholder.
4. Calculator and tetris paths are unchanged (no ``placeholder_fallback``).

The LLM call itself is patched so these tests don't need an OpenRouter
key or network access.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.ham.builder_artifact_verifier import verify_builder_scaffold_artifact
from src.ham.builder_chat_scaffold import (
    _build_react_scaffold_files,
    maybe_chat_scaffold_for_turn,
)
from src.ham.builder_llm_scaffold import (
    LLMScaffoldError,
    ScaffoldResult,
)
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    set_builder_source_store_for_tests,
)


SPACESHIP_PROMPT = "build me a game where i can shoot things in a spaceship"


def _cleanup() -> None:
    set_builder_source_store_for_tests(None)


# ---------------------------------------------------------------------------
# Sentinel: generic placeholder carries the placeholder_fallback flag
# ---------------------------------------------------------------------------


def test_generic_react_scaffold_sets_placeholder_fallback() -> None:
    """Spaceship-style prompt falls through to generic placeholder and the
    scaffold_meta carries placeholder_fallback=True so the verifier can reject it."""
    _, meta = _build_react_scaffold_files(SPACESHIP_PROMPT)
    assert meta.get("template") == "react_scaffold"
    assert meta.get("placeholder_fallback") is True


def test_calculator_scaffold_does_not_set_placeholder_fallback() -> None:
    _, meta = _build_react_scaffold_files("build me a clean calculator app")
    assert meta.get("template") == "calculator"
    assert not meta.get("placeholder_fallback")


def test_tetris_scaffold_does_not_set_placeholder_fallback() -> None:
    _, meta = _build_react_scaffold_files("build a tetris clone")
    assert meta.get("template") == "tetris"
    assert not meta.get("placeholder_fallback")


# ---------------------------------------------------------------------------
# Verifier honest-failure gate
# ---------------------------------------------------------------------------


def test_verifier_fails_on_placeholder_fallback() -> None:
    """Verifier must reject placeholder fallbacks so the chat-stream can suppress
    the 'I've generated the project files' success message."""
    files, meta = _build_react_scaffold_files(SPACESHIP_PROMPT)
    result = verify_builder_scaffold_artifact(
        SPACESHIP_PROMPT,
        meta,
        files,
        operation="build_or_create",
    )
    assert result["verified"] is False
    assert result["status"] == "failed"
    assert "OpenRouter API key" in result["reason"] or "calculator" in result["reason"]


def test_verifier_still_skips_for_non_calculator_non_placeholder_templates() -> None:
    """Tetris template doesn't have specific verifier checks; should skip (not fail)."""
    files, meta = _build_react_scaffold_files("build me a tetris game")
    result = verify_builder_scaffold_artifact(
        "build me a tetris game",
        meta,
        files,
        operation="build_or_create",
    )
    assert result["verified"] is True
    assert result["skipped"] is True


# ---------------------------------------------------------------------------
# End-to-end: maybe_chat_scaffold_for_turn returns scaffolded=False on
# honest-failure path (no OpenRouter key)
# ---------------------------------------------------------------------------


def test_spaceship_prompt_no_key_returns_not_scaffolded(tmp_path: Path, monkeypatch) -> None:
    """Without an OpenRouter key, the chat-scaffold path should NOT report
    scaffolded=True for an arbitrary 'build me X' prompt. The chat-stream
    uses scaffolded to gate the success message; reporting it falsely is
    the bug we're fixing."""
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)

    # Force no OpenRouter key visible to the LLM path.
    with patch(
        "src.llm_client.normalized_openrouter_api_key",
        return_value=None,
    ):
        out = maybe_chat_scaffold_for_turn(
            workspace_id="ws_a",
            project_id="pr_a",
            session_id="sess_spaceship_no_key",
            last_user_plain=SPACESHIP_PROMPT,
            created_by="user_1",
        )

    assert out is not None
    assert out.get("scaffolded") is False
    assert out.get("artifact_verification_failed") is True
    verification = out.get("artifact_verification") or {}
    assert verification.get("verified") is False
    _cleanup()


# ---------------------------------------------------------------------------
# End-to-end: LLM-scaffold replace path produces real source
# ---------------------------------------------------------------------------


_FAKE_SPACESHIP_APP_TSX = """\
import React, { useEffect, useRef, useState } from "react";
export default function App() {
  const [score, setScore] = useState(0);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    // ship position + projectile + enemy game loop omitted for test brevity
  }, []);
  return (
    <main>
      <h1>Spaceship Shooter</h1>
      <p>Score: {score}</p>
      <canvas ref={canvasRef} width={640} height={480} />
    </main>
  );
}
"""

_FAKE_SCAFFOLD_RESULT = ScaffoldResult(
    file_changes=[
        ("src/App.tsx", _FAKE_SPACESHIP_APP_TSX),
        ("src/main.tsx", "import App from './App'; /* mount */"),
        ("package.json", '{"name":"spaceship","version":"0.0.1"}'),
    ],
    assertions=["The app renders a canvas", "Score is visible"],
)


def test_spaceship_prompt_with_llm_key_replaces_placeholder(
    tmp_path: Path, monkeypatch
) -> None:
    """With an OpenRouter key + successful LLM scaffold, the placeholder
    files are replaced with the LLM-generated source and verification passes."""
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)

    with patch(
        "src.llm_client.normalized_openrouter_api_key",
        return_value="sk-or-v1-faketestkey",
    ), patch(
        "src.ham.builder_llm_scaffold.generate_scaffold",
        return_value=_FAKE_SCAFFOLD_RESULT,
    ):
        out = maybe_chat_scaffold_for_turn(
            workspace_id="ws_a",
            project_id="pr_a",
            session_id="sess_spaceship_with_key",
            last_user_plain=SPACESHIP_PROMPT,
            created_by="user_1",
        )

    assert out is not None, "scaffold call returned None"
    assert out.get("scaffolded") is True
    snap_id = str(out["source_snapshot_id"])
    rows = store.list_source_snapshots(workspace_id="ws_a", project_id="pr_a")
    snap = next(row for row in rows if row.id == snap_id)
    manifest = snap.manifest or {}
    inline_files = manifest.get("inline_files")
    assert isinstance(inline_files, dict)
    app_tsx = str(inline_files.get("src/App.tsx") or "")
    # Real LLM source must replace the placeholder.
    assert "Scaffold created from your chat request." not in app_tsx
    assert "Spaceship Shooter" in app_tsx
    assert "canvas" in app_tsx
    _cleanup()


def test_spaceship_prompt_with_llm_failure_falls_back_to_honest_failure(
    tmp_path: Path, monkeypatch
) -> None:
    """If the LLM scaffold raises, we must NOT silently ship the placeholder.
    Verification fails, scaffolded=False, chat-stream stays honest."""
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)

    def _raise(*_args, **_kwargs):
        raise LLMScaffoldError("simulated upstream failure", error_code="STEP_MODEL_UNAVAILABLE")

    with patch(
        "src.llm_client.normalized_openrouter_api_key",
        return_value="sk-or-v1-faketestkey",
    ), patch(
        "src.ham.builder_llm_scaffold.generate_scaffold",
        side_effect=_raise,
    ):
        out = maybe_chat_scaffold_for_turn(
            workspace_id="ws_a",
            project_id="pr_a",
            session_id="sess_spaceship_llm_fail",
            last_user_plain=SPACESHIP_PROMPT,
            created_by="user_1",
        )

    assert out is not None
    assert out.get("scaffolded") is False
    assert out.get("artifact_verification_failed") is True
    _cleanup()


def test_spaceship_prompt_with_empty_llm_result_falls_back_to_honest_failure(
    tmp_path: Path, monkeypatch
) -> None:
    """An LLM that returns zero file_changes is treated the same as a failure."""
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)

    empty = ScaffoldResult(file_changes=[], assertions=[])
    with patch(
        "src.llm_client.normalized_openrouter_api_key",
        return_value="sk-or-v1-faketestkey",
    ), patch(
        "src.ham.builder_llm_scaffold.generate_scaffold",
        return_value=empty,
    ):
        out = maybe_chat_scaffold_for_turn(
            workspace_id="ws_a",
            project_id="pr_a",
            session_id="sess_spaceship_empty",
            last_user_plain=SPACESHIP_PROMPT,
            created_by="user_1",
        )

    assert out is not None
    assert out.get("scaffolded") is False
    _cleanup()


# ---------------------------------------------------------------------------
# Regression: known templates still scaffold successfully
# ---------------------------------------------------------------------------


def test_calculator_path_still_scaffolds_after_fallback_fix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)

    out = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_calc_after_fix",
        last_user_plain="build me a clean calculator app",
        created_by="user_1",
    )
    assert out is not None
    assert out.get("scaffolded") is True
    _cleanup()


def test_tetris_path_still_scaffolds_after_fallback_fix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)

    out = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_tetris_after_fix",
        last_user_plain="build me a tetris clone with a dark theme",
        created_by="user_1",
    )
    assert out is not None
    assert out.get("scaffolded") is True
    _cleanup()
