"""Tests for generated preview TypeScript validation."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.ham.builder_preview_bootstrap import ensure_preview_bootstrap_files
from src.ham.builder_preview_typecheck import (
    build_default_tailwind_config_js,
    ensure_tailwind_config_for_preview,
    run_preview_typecheck,
    sanitize_typecheck_output,
    try_repair_identifier_case_mismatch,
    user_safe_typecheck_failure_message,
    validate_preview_app_files,
)

_TEAM_MISMATCH_APP = (
    "export default function App() {\n"
    "  const TEAM = [{ id: 1, name: 'A' }];\n"
    "  return <div>{team.map((t) => t.id)}</div>;\n"
    "}\n"
)

_VALID_APP = "export default function App() { return <main>OK</main>; }\n"
_VALID_MAIN = (
    "import React from 'react';\n"
    "import ReactDOM from 'react-dom/client';\n"
    "import App from './App';\n"
    "ReactDOM.createRoot(document.getElementById('root')!).render(\n"
    "  <React.StrictMode>\n"
    "    <App />\n"
    "  </React.StrictMode>,\n"
    ");\n"
)


def _bootstrap_files(**extra: str) -> dict[str, str]:
    base = {
        "src/App.tsx": _VALID_APP,
        "src/main.tsx": _VALID_MAIN,
        "src/styles.css": "body { margin: 0; }\n",
        **extra,
    }
    return ensure_preview_bootstrap_files(base, project_name="Typecheck Test")


@pytest.mark.skipif(
    __import__("shutil").which("npx") is None,
    reason="npx required for preview typecheck tests",
)
def test_team_identifier_mismatch_fails_typecheck() -> None:
    files = _bootstrap_files(**{"src/App.tsx": _TEAM_MISMATCH_APP})
    ok, output = run_preview_typecheck(files)
    assert ok is False
    assert "team" in output.lower() or "TS2304" in output


@pytest.mark.skipif(
    __import__("shutil").which("npx") is None,
    reason="npx required for preview typecheck tests",
)
def test_validate_preview_app_repairs_team_identifier_mismatch() -> None:
    files = _bootstrap_files(**{"src/App.tsx": _TEAM_MISMATCH_APP})
    result = validate_preview_app_files(files)
    assert result.ok is True
    assert result.deterministic_repair_attempted is True
    assert "TEAM.map" in result.files["src/App.tsx"] or "TEAM" in result.files["src/App.tsx"]


@pytest.mark.skipif(
    __import__("shutil").which("npx") is None,
    reason="npx required for preview typecheck tests",
)
def test_valid_bundle_passes_typecheck() -> None:
    files = _bootstrap_files()
    result = validate_preview_app_files(files)
    assert result.ok is True


def test_ensure_tailwind_config_adds_content_paths() -> None:
    pkg = json.dumps(
        {
            "name": "demo",
            "private": True,
            "type": "module",
            "devDependencies": {"tailwindcss": "^3.4.0"},
        }
    )
    files = ensure_tailwind_config_for_preview(
        {
            "package.json": pkg + "\n",
            "postcss.config.js": "export default { plugins: { tailwindcss: {}, autoprefixer: {} } };\n",
        }
    )
    assert "tailwind.config.js" in files
    assert "./index.html" in files["tailwind.config.js"]
    assert "./src/**/*.{js,ts,jsx,tsx}" in files["tailwind.config.js"]


def test_ensure_tailwind_preserves_existing_postcss() -> None:
    postcss = "export default { plugins: { tailwindcss: {}, autoprefixer: {} } };\n"
    pkg = json.dumps({"name": "demo", "devDependencies": {"tailwindcss": "^3.4.0"}})
    files = ensure_tailwind_config_for_preview(
        {"package.json": pkg + "\n", "postcss.config.js": postcss}
    )
    assert files["postcss.config.js"] == postcss


def test_user_safe_typecheck_message_has_no_internals() -> None:
    msg = user_safe_typecheck_failure_message()
    haystack = msg.lower()
    for token in ("ts2304", "node_modules", "registry", "stack", "traceback"):
        assert token not in haystack


def test_sanitize_typecheck_output_strips_absolute_paths() -> None:
    raw = (
        "/home/user/proj/src/App.tsx(10,5): error TS2304: Cannot find name 'team'.\n"
        "    at Object.<anonymous> (/home/user/node_modules/foo.js:1:1)\n"
    )
    cleaned = sanitize_typecheck_output(raw)
    assert "/home/user" not in cleaned
    assert "node_modules" not in cleaned
    assert "src/App.tsx" in cleaned or "Cannot find name" in cleaned


def test_try_repair_identifier_case_mismatch_unit() -> None:
    files = {"src/App.tsx": _TEAM_MISMATCH_APP}
    output = "src/App.tsx(3,16): error TS2304: Cannot find name 'team'."
    repaired = try_repair_identifier_case_mismatch(files, output)
    assert repaired is not None
    assert "team.map" not in repaired["src/App.tsx"]
    assert "TEAM.map" in repaired["src/App.tsx"]


def test_build_default_tailwind_config_has_required_content() -> None:
    body = build_default_tailwind_config_js()
    assert '["./index.html", "./src/**/*.{js,ts,jsx,tsx}"]' in body
