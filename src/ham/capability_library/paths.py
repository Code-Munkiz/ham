"""Canonical paths for capability library v1 (under a project root)."""
from __future__ import annotations

from pathlib import Path

INDEX_REL = Path(".ham") / "capability-library" / "v1" / "index.json"
AUDIT_REL = Path(".ham") / "_audit" / "capability-library"
LOCK_NAME = "capability-library.lock"


def index_path(root: Path) -> Path:
    return (root / INDEX_REL).resolve()


def audit_dir(root: Path) -> Path:
    return (root / AUDIT_REL).resolve()


def lock_path(root: Path) -> Path:
    return (root / Path(".ham") / "capability-library" / "v1" / LOCK_NAME).resolve()
