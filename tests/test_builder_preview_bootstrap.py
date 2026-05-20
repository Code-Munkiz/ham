"""Tests for src/ham/builder_preview_bootstrap.py."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.ham.builder_llm_scaffold import ScaffoldResult
from src.ham.builder_preview_bootstrap import (
    ensure_preview_bootstrap_files,
    normalize_preview_scripts,
    repair_package_json,
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
    custom_pkg = '{"name":"custom-app","scripts":{"dev":"echo custom","lint":"eslint ."}}\n'
    custom_vite = "export default {};\n"
    files = {
        "package.json": custom_pkg,
        "vite.config.ts": custom_vite,
        "src/App.tsx": "export default function App() { return null; }\n",
    }
    out = ensure_preview_bootstrap_files(files, project_name="Custom")
    parsed = json.loads(out["package.json"])
    assert parsed["scripts"]["dev"] == "vite build && vite preview"
    assert parsed["scripts"]["lint"] == "eslint ."
    assert parsed["name"] == "custom-app"
    assert out["vite.config.ts"] == custom_vite


def test_injected_package_json_parses_and_runs_vite() -> None:
    out = ensure_preview_bootstrap_files(
        {"src/main.tsx": "export {};\n"},
        project_name="ham build me asteroids",
    )
    payload = json.loads(out["package.json"])
    assert payload["scripts"]["dev"] == "vite build && vite preview"


def test_normalize_preview_scripts_replaces_vite_dev() -> None:
    raw = json.dumps({"name": "demo", "scripts": {"dev": "vite", "lint": "eslint ."}})
    out = normalize_preview_scripts({"package.json": raw + "\n"})
    parsed = json.loads(out["package.json"])
    assert parsed["scripts"]["dev"] == "vite build && vite preview"
    assert parsed["scripts"]["build"] == "vite build"
    assert parsed["scripts"]["preview"] == "vite preview"
    assert parsed["scripts"]["lint"] == "eslint ."
    assert parsed["name"] == "demo"


def test_normalize_preview_scripts_creates_scripts_when_missing() -> None:
    raw = json.dumps({"name": "demo"})
    out = normalize_preview_scripts({"package.json": raw + "\n"})
    parsed = json.loads(out["package.json"])
    assert parsed["scripts"]["dev"] == "vite build && vite preview"


def test_normalize_preview_scripts_is_idempotent_for_bootstrap() -> None:
    out = ensure_preview_bootstrap_files({"src/main.tsx": "export {};\n"}, project_name="demo")
    once = out["package.json"]
    twice = normalize_preview_scripts({"package.json": once})["package.json"]
    assert once == twice


def test_normalize_preview_scripts_absent_package_json_unchanged() -> None:
    files = {"src/App.tsx": "export default function App() { return null; }\n"}
    assert normalize_preview_scripts(files) == files


def test_safe_npm_package_name_matches_tetris_sanitizer() -> None:
    assert safe_npm_package_name("Asteroids Game!!!") == "asteroids-game"


def test_repair_package_json_fixes_python_repr() -> None:
    raw = "{'name': 'x', 'private': True, 'scripts': {'dev': 'vite'}}\n"
    out = repair_package_json({"package.json": raw})
    parsed = json.loads(out["package.json"])
    assert parsed["name"] == "x"
    assert parsed["private"] is True


def test_repair_package_json_leaves_valid_json_unchanged() -> None:
    raw = '{"name":"custom-app","scripts":{"dev":"vite"}}\n'
    out = repair_package_json({"package.json": raw, "src/App.tsx": "x\n"})
    assert out["package.json"] == raw


def test_repair_package_json_replaces_unparseable_garbage() -> None:
    out = repair_package_json({"package.json": "not valid json {{{"})
    parsed = json.loads(out["package.json"])
    assert parsed["name"] == "ham-builder-app"
    assert "scripts" in parsed


def test_repair_package_json_absent_is_unchanged() -> None:
    files = {"src/App.tsx": "export default function App() { return null; }\n"}
    assert repair_package_json(files) == files


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


def test_maybe_llm_scaffold_replace_serializes_object_package_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.ham.builder_chat_scaffold import _maybe_llm_scaffold_replace
    from src.ham.builder_llm_scaffold import _parse_scaffold_result

    payload = json.dumps(
        {
            "file_changes": [
                {
                    "path": "package.json",
                    "content": {
                        "name": "asteroids-game",
                        "private": True,
                        "scripts": {"dev": "vite"},
                    },
                },
                {"path": "src/App.tsx", "content": "export default function App() { return null; }\n"},
                {"path": "src/main.tsx", "content": "import App from './App';\n"},
            ],
            "assertions": [],
        }
    )
    parsed = _parse_scaffold_result(payload)

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
        return_value=parsed,
    ):
        result = _maybe_llm_scaffold_replace(
            user_message="ham build me a game like asteroids",
            workspace_id="ws_asteroids",
            project_id="proj_asteroids",
            files={},
            scaffold_meta={},
        )
    assert isinstance(result, tuple)
    files, _meta = result
    package = json.loads(files["package.json"])
    assert package["name"] == "asteroids-game"
    assert package["private"] is True
    assert package["scripts"]["dev"] == "vite build && vite preview"
