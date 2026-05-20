"""Append-only review queue for HAM-on-X Phase 1A.

This intentionally mirrors existing HAM proposal-store patterns: bounded,
redacted records, parent directory creation, and append-only persistence. It
stays local to HAM-on-X for Phase 1A so the social action schema can settle;
future phases should consolidate shared proposal-store primitives where that
does not blur Browser Operator and social-agent semantics.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.ham.ham_x.action_envelope import SocialActionEnvelope, apply_platform_context
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.redaction import redact, redact_text

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


_SAFE_PROJECTION_KEYS = ("action_type", "channel", "created_at")
_MAX_TEXT_PREVIEW_CHARS = 240
_MAX_READ_LIMIT = 500


def _stable_record_id(line: str, payload: dict[str, Any]) -> str:
    raw_id = payload.get("record_id") or payload.get("action_id") or payload.get("idempotency_key")
    if isinstance(raw_id, str) and raw_id:
        return raw_id[:64]
    digest = hashlib.sha256(line.encode("utf-8")).hexdigest()
    return digest[:16]


def _safe_text_snippet(payload: dict[str, Any]) -> str:
    text = payload.get("text")
    if not isinstance(text, str):
        text = ""
    if not text:
        return ""
    from src.ham.hamgomoon_learning.redaction import redact_text as _hg_redact

    # Belt-and-suspenders: HAM-on-X redact_text catches long opaque tokens, the
    # HAMgomoon helper also scrubs short branded keys like xai-/xoxb-/bot tokens.
    redacted = _hg_redact(redact_text(text))
    return redacted[:_MAX_TEXT_PREVIEW_CHARS]


def _project_safe_record(line: str, payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "record_id": _stable_record_id(line, payload),
        "action_type": str(payload.get("action_type") or "") or None,
        "channel": str(payload.get("channel") or "") or None,
        "created_at": str(payload.get("created_at") or "") or None,
        "text": _safe_text_snippet(payload),
        "decision_state": str(payload.get("decision_state") or "") or None,
    }
    return out


def read_recent_review_records(
    *,
    limit: int = 100,
    path: Path | None = None,
    config: HamXConfig | None = None,
) -> list[dict[str, Any]]:
    """Return a bounded, safe-projection list of recent review queue rows."""
    target = path if path is not None else _path(config)
    clamped = max(1, min(int(limit), _MAX_READ_LIMIT))
    if not target.exists():
        return []
    try:
        raw = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    out: list[dict[str, Any]] = []
    for line in reversed(lines):
        if len(out) >= clamped:
            break
        try:
            payload = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue
        out.append(_project_safe_record(line, payload))
    return list(reversed(out))
