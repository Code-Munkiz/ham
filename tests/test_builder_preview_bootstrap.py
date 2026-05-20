"""Tests for src/ham/builder_preview_bootstrap.py."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.ham.builder_llm_scaffold import ScaffoldResult
from src.ham.builder_preview_bootstrap import (
    ensure_preview_bootstrap_files,
    safe_npm_package_name,
)


def test_ensure_preview_bootstrap_adds_missing_files() -> None:
    files = {
        "src/App.tsx": "export default function App() { return null; }\n",
        "src/main.tsx": "import App from './App';\n",
        "index.html": "<html></html>\n",
    }
    out = ensure_preview_bootstrap_files(files, project_name="Asteroids Game")
    assert "package.json" in out
    assert "vite.config.ts" in out
    assert out["index.html"] == files["index.html"]


def test_ensure_preview_bootstrap_adds_index_html_when_missing() -> None:
    files = {
        "src/App.tsx": "export default function App() { return null; }\n",
        "src/main.tsx": "import App from './App';\n",
    }
    out = ensure_preview_bootstrap_files(files, project_name="Asteroids Game")
    assert "index.html" in out
    assert "/src/main.tsx" in out["index.html"]


def test_ensure_preview_bootstrap_does_not_overwrite_existing() -> None:
    custom_pkg = '{"name":"custom-app","scripts":{"dev":"echo custom"}}\n'
    custom_vite = "export default {};\n"
    files = {
        "package.json": custom_pkg,
        "vite.config.ts": custom_vite,
        "src/App.tsx": "export default function App() { return null; }\n",
    }
    out = ensure_preview_bootstrap_files(files, project_name="Custom")
    assert out["package.json"] == custom_pkg
    assert out["vite.config.ts"] == custom_vite


def test_injected_package_json_parses_and_runs_vite() -> None:
    out = ensure_preview_bootstrap_files(
        {"src/main.tsx": "export {};\n"},
        project_name="ham build me asteroids",
    )
    payload = json.loads(out["package.json"])
    dev_script = str(payload.get("scripts", {}).get("dev", ""))
    assert "vite" in dev_script


def test_safe_npm_package_name_matches_tetris_sanitizer() -> None:
    assert safe_npm_package_name("Asteroids Game!!!") == "asteroids-game"


def test_maybe_llm_scaffold_replace_injects_package_json(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.ham.builder_chat_scaffold import _maybe_llm_scaffold_replace

    llm_files = [
        ("src/App.tsx", "export default function App() { return null; }\n"),
        ("src/main.tsx", "import App from './App';\n"),
        ("index.html", "<html><body><div id=\"root\"></div></body></html>\n"),
    ]

    monkeypatch.setattr(
        "src.llm_client.resolve_openrouter_api_key_for_actor",
        lambda ham_actor=None: "sk-or-test-key",
    )
    monkeypatch.setattr(
        "src.ham.builder_llm_scaffold._get_scaffold_model",
        lambda **kwargs: "openrouter/test-model",
    )
    with patch(
        "src.ham.builder_llm_scaffold.generate_scaffold",
        return_value=ScaffoldResult(file_changes=llm_files, assertions=[]),
    ):
        result = _maybe_llm_scaffold_replace(
            user_message="ham build me a game like asteroids",
            workspace_id="ws_asteroids",
            project_id="proj_asteroids",
            files={},
            scaffold_meta={},
        )
    assert isinstance(result, tuple)
    files, meta = result
    assert "package.json" in files
    assert "vite.config.ts" in files
    assert meta.get("llm_scaffold_file_count", 0) >= 5
