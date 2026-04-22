"""Append-only JSONL audit on the runner host (no secrets, no argv/prompt)."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def default_audit_file_path() -> Path:
    raw = (os.environ.get("HAM_DROID_RUNNER_AUDIT_FILE") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".ham" / "droid_runner_audit.jsonl"


def append_runner_audit_line(row: dict[str, Any]) -> str:
    """
    Append one JSON object as a line. Returns ``runner_request_id`` from the row
    (generates one if missing). Never raises to callers: I/O errors go to stderr.
    """
    rid = str(row.get("runner_request_id") or uuid.uuid4())
    out = {**row, "runner_request_id": rid}
    out.setdefault("logged_at", datetime.now(UTC).isoformat())
    path = default_audit_file_path()
    line = json.dumps(out, ensure_ascii=False) + "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.open("a", encoding="utf-8").write(line)
    except OSError as exc:
        print(
            f"Warning: droid runner audit write failed ({type(exc).__name__}: {exc})",
            file=sys.stderr,
        )
    return rid
