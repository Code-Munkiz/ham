from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError


class RunRecord(BaseModel):
    """Persisted run JSON matching main.py::_persist_run_record (not a registry record)."""

    model_config = ConfigDict(extra="allow")

    run_id: str
    created_at: str
    profile_id: str
    profile_version: str
    backend_id: str
    backend_version: str
    prompt_summary: str
    author: str | None = None
    bridge_result: dict[str, Any]
    hermes_review: dict[str, Any]


class RunStore:
    """Read-side access to run JSON files under <root>/.ham/runs/."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = Path.cwd().resolve() if root is None else Path(root).resolve()
        self._runs_dir = self._root / ".ham" / "runs"

    def list_runs(self, *, limit: int = 20, newest_first: bool = True) -> list[RunRecord]:
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")
        if not self._runs_dir.is_dir():
            return []
        try:
            paths = sorted(self._runs_dir.glob("*.json"))
        except OSError as exc:
            print(
                f"Warning: run store list failed ({type(exc).__name__}: {exc})",
                file=sys.stderr,
            )
            return []

        loaded: list[tuple[RunRecord, str]] = []
        for path in paths:
            if not path.is_file():
                continue
            rec = self._load_record(path)
            if rec is not None:
                loaded.append((rec, path.name))

        loaded.sort(key=lambda item: (item[0].created_at, item[1]))
        if newest_first:
            loaded.reverse()
        return [rec for rec, _ in loaded[:limit]]

    def get_run(self, run_id: str) -> RunRecord | None:
        if not self._runs_dir.is_dir():
            return None
        suffix = f"-{run_id}.json"
        try:
            matches = [
                p
                for p in self._runs_dir.iterdir()
                if p.is_file() and p.name.endswith(suffix)
            ]
        except OSError as exc:
            print(
                f"Warning: run store read failed ({type(exc).__name__}: {exc})",
                file=sys.stderr,
            )
            return None
        if not matches:
            return None
        if len(matches) == 1:
            return self._load_record(matches[0])
        chosen = max(matches, key=lambda p: p.name)
        print(
            f"Warning: duplicate run files for run_id {run_id!r}, using {chosen.name}",
            file=sys.stderr,
        )
        return self._load_record(chosen)

    def count(self) -> int:
        if not self._runs_dir.is_dir():
            return 0
        try:
            return sum(1 for p in self._runs_dir.glob("*.json") if p.is_file())
        except OSError as exc:
            print(
                f"Warning: run store count failed ({type(exc).__name__}: {exc})",
                file=sys.stderr,
            )
            return 0

    def _load_record(self, path: Path) -> RunRecord | None:
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(
                f"Warning: skip run file {path.name} ({type(exc).__name__}: {exc})",
                file=sys.stderr,
            )
            return None
        try:
            return RunRecord.model_validate(data)
        except ValidationError as exc:
            print(
                f"Warning: skip run file {path.name} ({type(exc).__name__}: {exc})",
                file=sys.stderr,
            )
            return None
