"""Append-only operator audit in HAM-controlled storage (not Clerk metadata)."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


def default_operator_audit_path() -> Path:
    raw = (os.environ.get("HAM_OPERATOR_AUDIT_FILE") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".ham" / "_audit" / "operator_actions.jsonl"


def append_operator_action_audit(row: dict[str, Any]) -> str:
    """Append one JSON line; returns ``audit_id``."""
    path = default_operator_audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    audit_id = str(uuid.uuid4())
    payload = {
        "audit_id": audit_id,
        "ts": time.time(),
        **row,
    }
    line = json.dumps(payload, default=str) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)
    return audit_id
