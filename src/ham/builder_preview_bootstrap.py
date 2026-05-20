"""Vite preview bootstrap files shared by deterministic and LLM builder scaffolds."""

from __future__ import annotations

import json
import re


def safe_npm_package_name(project_name: str) -> str:
    """Match ``safe_pkg`` derivation in ``builder_chat_scaffold`` tetris path."""
    title = str(project_name or "").strip()
    return re.sub(r"[^a-z0-9-]", "-", title.lower())[:40].strip("-") or "ham-builder-app"


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
                    "dev": "vite build && vite preview",
                    "build": "vite build",
                    "preview": "vite preview",
                },
                "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
                "devDependencies": {
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


def ensure_preview_bootstrap_files(files: dict[str, str], *, project_name: str) -> dict[str, str]:
    """Add missing Vite bootstrap files without overwriting LLM output."""
    out = dict(files)
    title = str(project_name or "").strip()[:120] or "HAM Builder App"
    safe_pkg = safe_npm_package_name(title)
    bootstrap = build_vite_bootstrap_files(title=title, safe_pkg=safe_pkg)
    for key in ("package.json", "vite.config.ts", "index.html"):
        if key not in out:
            out[key] = bootstrap[key]
    return out
