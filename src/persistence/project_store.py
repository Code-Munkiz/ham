from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.registry.projects import ProjectRecord

_DEFAULT_STORE_PATH = Path.home() / ".ham" / "projects.json"


def _project_id(name: str, root: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"
    short_hash = hashlib.sha256(root.encode("utf-8")).hexdigest()[:6]
    return f"project.{slug}-{short_hash}"


class ProjectStore:
    """File-backed store for registered HAM projects (~/.ham/projects.json)."""

    def __init__(self, store_path: Path | None = None) -> None:
        self._path = Path(store_path) if store_path is not None else _DEFAULT_STORE_PATH

    def list_projects(self) -> list[ProjectRecord]:
        raw = self._load_raw()
        records: list[ProjectRecord] = []
        for item in raw.get("projects", []):
            try:
                records.append(ProjectRecord.model_validate(item))
            except ValidationError as exc:
                print(
                    f"Warning: skipping malformed project entry ({type(exc).__name__}: {exc})",
                    file=sys.stderr,
                )
        return records

    def get_project(self, project_id: str) -> ProjectRecord | None:
        for record in self.list_projects():
            if record.id == project_id:
                return record
        return None

    def register(self, record: ProjectRecord) -> ProjectRecord:
        """Add or replace a project by id. Returns the stored record."""
        projects = self.list_projects()
        projects = [p for p in projects if p.id != record.id]
        projects.append(record)
        self._save(projects)
        return record

    def remove(self, project_id: str) -> bool:
        """Remove project by id. Returns True if it existed."""
        projects = self.list_projects()
        remaining = [p for p in projects if p.id != project_id]
        if len(remaining) == len(projects):
            return False
        self._save(remaining)
        return True

    def make_record(
        self,
        name: str,
        root: str,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ProjectRecord:
        """Build a ProjectRecord with a stable derived id."""
        return ProjectRecord(
            id=_project_id(name, root),
            name=name,
            root=str(Path(root).resolve()),
            description=description,
            metadata=metadata or {},
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_raw(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(
                f"Warning: project store unreadable ({type(exc).__name__}: {exc})",
                file=sys.stderr,
            )
            return {}

    def _save(self, projects: list[ProjectRecord]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"projects": [p.model_dump() for p in projects]},
            sort_keys=True,
            ensure_ascii=True,
            indent=2,
        )
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self._path)


# Process-wide registry (tests may replace via :func:`set_project_store_for_tests`).
_store_singleton: ProjectStore | None = None


def get_project_store() -> ProjectStore:
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = ProjectStore()
    return _store_singleton


def set_project_store_for_tests(store: ProjectStore | None) -> None:
    """Replace the global :class:`ProjectStore` (``None`` restores lazy default)."""
    global _store_singleton
    _store_singleton = store
