"""Redacted delivery log for Social live provider actions."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.ham.ham_x.redaction import redact

MAX_LOG_SCAN_BYTES = 1_048_576


def default_delivery_log_path() -> Path:
    raw = (os.environ.get("HAM_SOCIAL_DELIVERY_LOG_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.cwd() / ".ham" / "social_delivery_log.jsonl"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k)[:128]: _safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe(v) for v in value[:25]]
    if isinstance(value, str):
        return str(redact(value))[:1000]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return str(redact(str(value)))[:1000]


def build_delivery_record(**fields: Any) -> dict[str, Any]:
    allowed = {
        "provider_id",
        "execution_kind",
        "action_type",
        "target_kind",
        "target_ref",
        "proposal_digest",
        "persona_digest",
        "idempotency_key",
        "provider_message_id",
        "status",
        "executed_at",
        "execution_allowed",
        "mutation_attempted",
    }
    record = {key: _safe(value) for key, value in fields.items() if key in allowed}
    record.setdefault("executed_at", utc_now_iso())
    return record


def append_delivery_record(record: dict[str, Any], path: Path | None = None) -> Path:
    target = path or default_delivery_log_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    safe_record = build_delivery_record(**record)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(safe_record, sort_keys=True) + "\n")
    return target


def successful_delivery_exists(
    *,
    idempotency_key: str,
    provider_id: str = "telegram",
    path: Path | None = None,
) -> bool:
    target = path or default_delivery_log_path()
    if not target.is_file():
        return False
    try:
        if target.stat().st_size > MAX_LOG_SCAN_BYTES:
            return False
    except OSError:
        return False
    try:
        rows = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False
    for line in rows:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(row, dict)
            and row.get("provider_id") == provider_id
            and row.get("idempotency_key") == idempotency_key
            and row.get("status") == "sent"
        ):
            return True
    return False
