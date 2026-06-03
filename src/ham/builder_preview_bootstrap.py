"""Vite preview bootstrap files shared by deterministic and LLM builder scaffolds."""

from __future__ import annotations

import ast
import json
import re

from src.ham.builder_preview_typecheck import (
    ensure_preview_tsconfig,
    ensure_tailwind_config_for_preview,
)


def safe_npm_package_name(project_name: str) -> str:
    """Match ``safe_pkg`` derivation in ``builder_chat_scaffold`` tetris path."""
    title = str(project_name or "").strip()
    return re.sub(r"[^a-z0-9-]", "-", title.lower())[:40].strip("-") or "ham-builder-app"


_PREVIEW_DEV_SCRIPT = "vite build && vite preview"
_PREVIEW_BUILD_SCRIPT = "vite build"
_PREVIEW_PREVIEW_SCRIPT = "vite preview"

_DEFAULT_APP_TSX = (
    "export default function App() {\n"
    "  return (\n"
    "    <main style={{ fontFamily: 'system-ui, sans-serif', padding: '2rem' }}>\n"
    "      HAM preview is ready.\n"
    "    </main>\n"
    "  );\n"
    "}\n"
)
_DEFAULT_MAIN_TSX = (
    "import React from 'react';\n"
    "import ReactDOM from 'react-dom/client';\n"
    "import App from './App';\n"
    "ReactDOM.createRoot(document.getElementById('root')!).render(\n"
    "  <React.StrictMode>\n"
    "    <App />\n"
    "  </React.StrictMode>,\n"
    ");\n"
)
_DEFAULT_STYLES_CSS = "body { margin: 0; }\n"


def build_vite_bootstrap_files(*, title: str, safe_pkg: str) -> dict[str, str]:
    """Return package.json, index.html, and vite.config.ts for cloud preview."""
    return {
        "package.json": json.dumps(
            {
                "name": safe_pkg,
                "private": True,
                "version": "0.0.1",
                "type": "module",
                "scripts": {
                    "dev": _PREVIEW_DEV_SCRIPT,
                    "build": _PREVIEW_BUILD_SCRIPT,
                    "preview": _PREVIEW_PREVIEW_SCRIPT,
                },
                "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
                "devDependencies": {
                    "@types/react": "^18.3.12",
                    "@types/react-dom": "^18.3.1",
                    "@vitejs/plugin-react": "^4.3.4",
                    "typescript": "^5.6.3",
                    "vite": "^5.4.11",
                },
            },
            indent=2,
        )
        + "\n",
        "index.html": (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "  <head>\n"
            '    <meta charset="UTF-8" />\n'
            f"    <title>{title}</title>\n"
            '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
            "  </head>\n"
            "  <body>\n"
            '    <div id="root"></div>\n'
            '    <script type="module" src="/src/main.tsx"></script>\n'
            "  </body>\n"
            "</html>\n"
        ),
        "vite.config.ts": (
            "import { defineConfig } from \"vite\";\n"
            "import react from \"@vitejs/plugin-react\";\n"
            "\n"
            "export default defineConfig({\n"
            "  plugins: [react()],\n"
            "  server: {\n"
            "    hmr: false,\n"
            "  },\n"
            "});\n"
        ),
    }


def repair_package_json(files: dict[str, str]) -> dict[str, str]:
    """Repair package.json when it is present but not valid JSON for npm."""
    if "package.json" not in files:
        return files
    out = dict(files)
    raw = out["package.json"]
    try:
        json.loads(raw)
    except json.JSONDecodeError:
        try:
            obj = ast.literal_eval(raw.strip())
        except (SyntaxError, ValueError):
            obj = None
        if isinstance(obj, dict):
            out["package.json"] = json.dumps(obj, indent=2) + "\n"
        else:
            safe_pkg = safe_npm_package_name("HAM Builder App")
            bootstrap = build_vite_bootstrap_files(title="HAM Builder App", safe_pkg=safe_pkg)
            out["package.json"] = bootstrap["package.json"]
    return out


def _package_json_type_is_module(package_json_content: str) -> bool:
    try:
        obj = json.loads(package_json_content)
    except json.JSONDecodeError:
        return False
    if not isinstance(obj, dict):
        return False
    return obj.get("type") == "module"


def _is_commonjs_config_content(content: str) -> bool:
    text = content.strip()
    if not text:
        return False
    if "export default" in text or "export {" in text:
        return False
    if re.search(r"^\s*import\s", text, re.MULTILINE):
        return False
    return "module.exports" in text or "require(" in text


def normalize_esm_config_extensions(files: dict[str, str]) -> dict[str, str]:
    """Rename CommonJS tailwind/postcss configs to .cjs when package.json uses type:module."""
    if "package.json" not in files:
        return files
    if not _package_json_type_is_module(files["package.json"]):
        return files
    out = dict(files)
    for js_name, cjs_name in (
        ("tailwind.config.js", "tailwind.config.cjs"),
        ("postcss.config.js", "postcss.config.cjs"),
    ):
        content = out.get(js_name)
        if content is None or not _is_commonjs_config_content(content):
            continue
        out[cjs_name] = content
        del out[js_name]
    return out


def normalize_preview_scripts(files: dict[str, str]) -> dict[str, str]:
    """Normalize package.json scripts for cloud preview (build + preview, not dev HMR)."""
    if "package.json" not in files:
        return files
    out = dict(files)
    obj = json.loads(out["package.json"])
    if not isinstance(obj, dict):
        return files
    scripts = obj.get("scripts")
    if not isinstance(scripts, dict):
        scripts = {}
    scripts["dev"] = _PREVIEW_DEV_SCRIPT
    scripts["build"] = _PREVIEW_BUILD_SCRIPT
    scripts["preview"] = _PREVIEW_PREVIEW_SCRIPT
    obj["scripts"] = scripts
    out["package.json"] = json.dumps(obj, indent=2) + "\n"
    return out


def ensure_preview_bootstrap_files(files: dict[str, str], *, project_name: str) -> dict[str, str]:
    """Add missing Vite bootstrap files without overwriting LLM output."""
    out = dict(files)
    title = str(project_name or "").strip()[:120] or "HAM Builder App"
    safe_pkg = safe_npm_package_name(title)
    bootstrap = build_vite_bootstrap_files(title=title, safe_pkg=safe_pkg)
    for key in ("package.json", "vite.config.ts", "index.html"):
        if key not in out:
            out[key] = bootstrap[key]
    for key, content in (
        ("src/main.tsx", _DEFAULT_MAIN_TSX),
        ("src/App.tsx", _DEFAULT_APP_TSX),
        ("src/styles.css", _DEFAULT_STYLES_CSS),
    ):
        if key not in out:
            out[key] = content
    out = repair_package_json(out)
    out = normalize_preview_scripts(out)
    out = normalize_esm_config_extensions(out)
    out = ensure_preview_tsconfig(out)
    out = ensure_tailwind_config_for_preview(out)
    return out
