"""Append-only review queue for HAM-on-X Phase 1A."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.ham.ham_x.action_envelope import SocialActionEnvelope, apply_platform_context
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.redaction import redact

MAX_RECORD_CHARS = 16_000
MAX_STRING_CHARS = 4_000


def _cap(value: Any) -> Any:
    if isinstance(value, str):
        return value[: MAX_STRING_CHARS - 3] + "..." if len(value) > MAX_STRING_CHARS else value
    if isinstance(value, list):
        return [_cap(item) for item in value[:100]]
    if isinstance(value, dict):
        return {str(k)[:256]: _cap(v) for k, v in list(value.items())[:100]}
    return value


def _path(config: HamXConfig | None) -> Path:
    cfg = config or load_ham_x_config()
    return cfg.review_queue_path


def append_review_record(
    record: SocialActionEnvelope | dict[str, Any],
    *,
    config: HamXConfig | None = None,
) -> Path:
    """Append one bounded, redacted JSONL review queue record."""
    path = _path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = record.redacted_dump() if isinstance(record, SocialActionEnvelope) else record
    raw = apply_platform_context(raw, config)
    payload = _cap(redact(raw))
    line = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
    if len(line) > MAX_RECORD_CHARS:
        payload = {
            "truncated": True,
            "record": _cap(payload),
        }
        line = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
        if len(line) > MAX_RECORD_CHARS:
            line = json.dumps(
                {"truncated": True, "reason": "record_exceeded_max_chars"},
                sort_keys=True,
                ensure_ascii=True,
            )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return path
