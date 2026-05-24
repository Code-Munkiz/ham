#!/usr/bin/env python3
"""Read-only validator and renderer for Build Kit Registry v2 Game Pack pilot.

Phase 0 CLI — delegates to :mod:`src.ham.build_registry` (unwired package).

Example::

    python3 scripts/validate_game_pack_registry.py \\
      --pack-root docs/build-kit-registry-v2/game-pack \\
      --app-type game.idle-incremental \\
      --check \\
      --render-sample /dev/stdout
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ham.build_registry import (
    BuildRegistryConfigError,
    compose_build_recipe,
    load_registry_pack,
    render_playbook_context,
    validate_registry_pack,
)


def _write_render_sample(path: str, content: str) -> None:
    if path == "/dev/stdout":
        sys.stdout.write(content)
        return
    Path(path).write_text(content, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and render Build Kit Registry v2 Game Pack pilot YAML."
    )
    parser.add_argument(
        "--pack-root",
        type=Path,
        default=REPO_ROOT / "docs/build-kit-registry-v2/game-pack",
        help="Path to game-pack directory containing registry-pack.yaml",
    )
    parser.add_argument(
        "--app-type",
        default="game.idle-incremental",
        help="App type id to compose (default: game.idle-incremental)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate pack; exit 1 on failure",
    )
    parser.add_argument(
        "--render-sample",
        metavar="PATH",
        help="Write rendered playbook context to PATH (/dev/stdout supported)",
    )
    args = parser.parse_args(argv)

    try:
        pack = load_registry_pack(args.pack_root)
    except BuildRegistryConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1 if args.check else 0

    try:
        validate_registry_pack(pack)
    except BuildRegistryConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1 if args.check else 0

    if args.check:
        print(
            f"OK: pack {pack.pack_id} schema {pack.schema_version} "
            f"— {len(pack.modules)} modules validated"
        )

    try:
        recipe = compose_build_recipe(pack, args.app_type)
    except BuildRegistryConfigError as exc:
        print(f"ERROR: compose failed: {exc}", file=sys.stderr)
        return 1

    if args.check:
        print(f"Compose OK: app_type={recipe.app_type_id}")
        print(f"  mechanics: {' → '.join(recipe.mechanic_ids)}")
        print(f"  components: {' → '.join(recipe.component_ids)}")

    if args.render_sample:
        rendered = render_playbook_context(recipe)
        _write_render_sample(args.render_sample, rendered)
        if args.render_sample != "/dev/stdout":
            print(f"Rendered {len(rendered)} characters to {args.render_sample}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
