"""Append-only exception queue for HAM-on-X Phase 1C."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.ham.ham_x.action_envelope import SocialActionEnvelope, apply_platform_context
from src.ham.ham_x.autonomy import AutonomyDecisionResult
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.redaction import redact
from src.ham.ham_x.review_queue import MAX_RECORD_CHARS, _cap


def _path(config: HamXConfig | None) -> Path:
    cfg = config or load_ham_x_config()
    return cfg.exception_queue_path


def append_exception_record(
    *,
    envelope: SocialActionEnvelope,
    decision: AutonomyDecisionResult,
    payload: dict[str, Any] | None = None,
    config: HamXConfig | None = None,
) -> Path:
    """Append one bounded, redacted exception queue record."""
    path = _path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = {
        "kind": "ham_x_exception",
        "action": envelope.redacted_dump(),
        "autonomy_decision": decision.model_dump(mode="json"),
        "payload": payload or {},
    }
    raw = apply_platform_context(raw, config)
    raw["action_id"] = envelope.action_id
    line = json.dumps(_cap(redact(raw)), sort_keys=True, ensure_ascii=True, default=str)
    if len(line) > MAX_RECORD_CHARS:
        line = json.dumps(
            {"truncated": True, "reason": "exception_record_exceeded_max_chars"},
            sort_keys=True,
            ensure_ascii=True,
        )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return path
