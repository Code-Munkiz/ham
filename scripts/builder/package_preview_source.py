#!/usr/bin/env python3
"""Zip a local directory into a deterministic preview source bundle (no uploads).

Writes ``preview-source.zip`` suitable for manual spike uploads to GCS.
Safe paths only: rejects symlinks and paths escaping the root.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def package_preview_zip(*, root: Path, output: Path) -> None:
    root_resolved = root.expanduser().resolve()
    if not root_resolved.is_dir():
        raise SystemExit(f"Source root is not a directory: {root_resolved}")

    output.parent.mkdir(parents=True, exist_ok=True)

    exclude_dirs = {".git", ".hg", "node_modules", ".venv", "__pycache__"}
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root_resolved.rglob("*")):
            if path.is_dir():
                continue
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(root_resolved)
            except ValueError:
                continue
            if rel.parts and rel.parts[0] in exclude_dirs:
                continue
            if any(p in exclude_dirs for p in rel.parts):
                continue
            try:
                if path.is_symlink():
                    raise ValueError("symlinks not allowed")
            except OSError:
                continue
            arcname = "/".join(rel.parts)
            zf.write(path, arcname=arcname)


def main() -> int:
    parser = argparse.ArgumentParser(description="Package preview source tree into a zip bundle.")
    parser.add_argument("--root", required=True, help="Absolute or relative path to project root")
    parser.add_argument("--output", default="preview-source.zip", help="Output zip path")
    args = parser.parse_args()

    package_preview_zip(root=Path(args.root), output=Path(args.output))
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
