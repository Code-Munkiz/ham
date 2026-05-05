#!/usr/bin/env python3
"""Export the HAM FastAPI OpenAPI schema to ``docs/api/openapi.json``.

This script is **import-only**: it instantiates the FastAPI ``app`` from
``src.api.server`` and calls ``app.openapi()``. It does **not** start a
server, listen on a port, or make any outbound network call.

Safe-to-run defaults
--------------------
The same mock-mode environment variables that ``scripts/run_local_api.py``
relies on are pre-set here so the script runs without production secrets,
without a live Hermes/OpenRouter gateway, and without Clerk JWT issuer
configuration. ``.env`` is *not* loaded; we set explicit, reviewable
defaults instead so an operator's secrets cannot leak into the schema.

Usage
-----
    # Regenerate the committed schema:
    python scripts/export_openapi.py

    # Verify the committed schema is up-to-date (CI / pre-merge guard):
    python scripts/export_openapi.py --check
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "docs" / "api" / "openapi.json"

SAFE_ENV_DEFAULTS = {
    "HERMES_GATEWAY_MODE": "mock",
    "HAM_CHAT_SESSION_STORE": "memory",
    "HAM_CLERK_REQUIRE_AUTH": "false",
    "HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS": "false",
    "HAM_DISABLE_FIRESTORE": "1",
    "HAM_WORKSPACE_STORE": "memory",
    "HAM_WORKSPACE_TOOLS_DISABLE_NETWORK": "1",
}


def _apply_safe_env() -> None:
    for key, value in SAFE_ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)


def _import_fastapi_app():
    repo_root_str = str(REPO_ROOT)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    os.environ.setdefault("PYTHONPATH", repo_root_str)
    # ``src.api.server`` exposes a wrapped ASGI ``app`` (PNA middleware) plus the
    # underlying ``fastapi_app`` used for OpenAPI introspection. We need the
    # latter so ``app.openapi()`` resolves on the FastAPI instance.
    from src.api.server import fastapi_app

    return fastapi_app


def _render_schema() -> str:
    fastapi_app = _import_fastapi_app()
    schema = fastapi_app.openapi()
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def _read_existing(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Do not write the file. Exit 0 if the on-disk schema matches "
            "the freshly rendered schema, exit 1 otherwise."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help=f"Output path for the schema (default: {OUTPUT_PATH.relative_to(REPO_ROOT)}).",
    )
    args = parser.parse_args()

    _apply_safe_env()
    rendered = _render_schema()

    if args.check:
        existing = _read_existing(args.output)
        if existing == rendered:
            print(f"OK: {args.output.relative_to(REPO_ROOT)} is up-to-date.")
            return 0
        print(
            f"DRIFT: {args.output.relative_to(REPO_ROOT)} is stale. "
            f"Run `python scripts/export_openapi.py` and commit the result.",
            file=sys.stderr,
        )
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {args.output.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
