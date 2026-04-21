"""Persist Ham bridge run records under ``<project_root>/.ham/runs/`` (shared by CLI and API)."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.registry.backends import DEFAULT_BACKEND_ID, DEFAULT_BACKEND_REGISTRY
from src.registry.profiles import DEFAULT_PROFILE_REGISTRY


def _resolve_author() -> str:
    for var in ("HAM_AUTHOR", "USER", "USERNAME"):
        value = os.environ.get(var)
        if value and value.strip():
            return value.strip()
    return "unknown"


def persist_ham_run_record(
    project_root: Path,
    *,
    prompt: str,
    profile_id: str,
    bridge_result: object,
    review: dict[str, Any],
) -> Path | None:
    """Write run JSON next to ``main.py`` convention (timestamp-run_id.json)."""
    try:
        now = datetime.now(timezone.utc)
        created_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        created_at_for_filename = now.strftime("%Y%m%dT%H%M%SZ")

        if hasattr(bridge_result, "model_dump"):
            bridge_payload = bridge_result.model_dump()
        elif hasattr(bridge_result, "dict"):
            bridge_payload = bridge_result.dict()
        else:
            bridge_payload = bridge_result

        run_id = str(getattr(bridge_result, "run_id", "")) or str(bridge_payload.get("run_id", ""))
        profile_version = DEFAULT_PROFILE_REGISTRY.get(profile_id).version
        backend_version = DEFAULT_BACKEND_REGISTRY.get_record(DEFAULT_BACKEND_ID).version

        record = {
            "run_id": run_id,
            "created_at": created_at,
            "profile_id": profile_id,
            "profile_version": profile_version,
            "backend_id": DEFAULT_BACKEND_ID,
            "backend_version": backend_version,
            "prompt_summary": prompt[:200],
            "author": _resolve_author(),
            "bridge_result": bridge_payload,
            "hermes_review": review,
        }

        root = project_root.resolve()
        runs_dir = root / ".ham" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        final_path = runs_dir / f"{created_at_for_filename}-{run_id}.json"
        tmp_path = runs_dir / f"{created_at_for_filename}-{run_id}.json.tmp"
        payload = json.dumps(record, sort_keys=True, ensure_ascii=True, indent=2)
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, final_path)
        return final_path
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"Warning: run persistence failed ({type(exc).__name__}: {exc})", file=sys.stderr)
        return None


def stable_run_id_for_prompt(prompt: str) -> str:
    """Match ``main.py`` hash slice used inside ``run-{hash}`` ids."""
    h = hashlib.sha256(prompt.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"run-{h}"
