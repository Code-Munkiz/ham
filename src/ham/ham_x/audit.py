"""Append-only HAM-on-X audit log.

Phase 1A mirrors HAM's existing operator audit shape while keeping a
social-agent-specific event stream. Future consolidation can share append and
redaction primitives once the record semantics are stable.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Literal

from src.ham.ham_x.action_envelope import apply_platform_context, utc_now_iso
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.redaction import redact
from src.ham.ham_x.review_queue import _cap

AuditEventType = Literal[
    "search_attempt",
    "score_attempt",
    "draft_attempt",
    "safety_reject",
    "queued_for_review",
    "blocked_mutating_action",
    "dry_run_action",
]


def _path(config: HamXConfig | None) -> Path:
    cfg = config or load_ham_x_config()
    return cfg.audit_log_path


def append_audit_event(
    event_type: AuditEventType,
    payload: dict[str, Any] | None = None,
    *,
    config: HamXConfig | None = None,
) -> str:
    """Append one redacted JSONL audit event and return its audit id."""
    path = _path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    audit_id = str(uuid.uuid4())
    row = apply_platform_context(
        {
            "audit_id": audit_id,
            "event_type": event_type,
            "ts": utc_now_iso(),
            "payload": _cap(redact(payload or {})),
        },
        config,
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, ensure_ascii=True, default=str) + "\n")
    return audit_id
