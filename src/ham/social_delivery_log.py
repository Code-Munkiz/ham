"""Redacted delivery log for Social live provider actions."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from src.ham.ham_x.redaction import redact

_LOG = logging.getLogger(__name__)

_SOCIAL_DELIVERY_LOG_BACKEND_ENV = "HAM_SOCIAL_DELIVERY_LOG_BACKEND"

MAX_LOG_SCAN_BYTES = 1_048_576


def default_delivery_log_path() -> Path:
    raw = (os.environ.get("HAM_SOCIAL_DELIVERY_LOG_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.cwd() / ".ham" / "social_delivery_log.jsonl"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def iter_records_in_window(
    *,
    start: datetime,
    end: datetime,
    path: Path | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield delivery log records whose ``executed_at`` falls within [start, end]."""
    target = path or default_delivery_log_path()
    if not target.is_file():
        return
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        raw_ts = record.get("executed_at", "")
        if not isinstance(raw_ts, str) or not raw_ts.strip():
            continue
        try:
            executed_at = datetime.fromisoformat(raw_ts.strip().replace("Z", "+00:00"))
            # Normalize both sides to UTC-aware for comparison
            if executed_at.tzinfo is None:
                executed_at = executed_at.replace(tzinfo=UTC)
            _start = start if start.tzinfo is not None else start.replace(tzinfo=UTC)
            _end = end if end.tzinfo is not None else end.replace(tzinfo=UTC)
            if _start <= executed_at <= _end:
                yield record
        except ValueError:
            continue


# ---------------------------------------------------------------------------
# Protocol + file-backend wrapper + factory
# ---------------------------------------------------------------------------


@runtime_checkable
class SocialDeliveryLogStoreProtocol(Protocol):
    """Backend-agnostic social delivery log store contract."""

    def append_record(
        self,
        record: dict[str, Any],
        path: Path | None = None,
    ) -> Path: ...

    def successful_delivery_exists(
        self,
        *,
        idempotency_key: str,
        provider_id: str,
        path: Path | None = None,
    ) -> bool: ...

    def iter_records_in_window(
        self,
        *,
        start: datetime,
        end: datetime,
        path: Path | None = None,
    ) -> Iterator[dict[str, Any]]: ...


class SocialDeliveryLogFileStore:
    """File-backed social delivery log store (wraps module-level functions)."""

    def append_record(
        self,
        record: dict[str, Any],
        path: Path | None = None,
    ) -> Path:
        return append_delivery_record(record, path)

    def successful_delivery_exists(
        self,
        *,
        idempotency_key: str,
        provider_id: str = "telegram",
        path: Path | None = None,
    ) -> bool:
        return successful_delivery_exists(
            idempotency_key=idempotency_key,
            provider_id=provider_id,
            path=path,
        )

    def iter_records_in_window(
        self,
        *,
        start: datetime,
        end: datetime,
        path: Path | None = None,
    ) -> Iterator[dict[str, Any]]:
        return iter_records_in_window(start=start, end=end, path=path)


def build_social_delivery_log_store() -> SocialDeliveryLogStoreProtocol:
    """Pick a social delivery log store backend based on env.

    Defaults to :class:`SocialDeliveryLogFileStore`. ``HAM_SOCIAL_DELIVERY_LOG_BACKEND
    =firestore`` selects the Firestore backend (lazy-imported).
    """
    backend = (os.environ.get(_SOCIAL_DELIVERY_LOG_BACKEND_ENV) or "").strip().lower()
    if backend == "firestore":
        from src.ham.social_delivery_log_firestore import (  # noqa: PLC0415
            FirestoreSocialDeliveryLogStore,
        )

        return FirestoreSocialDeliveryLogStore()
    if backend not in ("", "file"):
        _LOG.warning(
            "Unknown %s=%r; falling back to file backend.",
            _SOCIAL_DELIVERY_LOG_BACKEND_ENV,
            backend,
        )
    return SocialDeliveryLogFileStore()


_social_delivery_log_store_singleton: SocialDeliveryLogStoreProtocol | None = None


def get_social_delivery_log_store() -> SocialDeliveryLogStoreProtocol:
    """Lazy singleton accessor for the configured social delivery log store."""
    global _social_delivery_log_store_singleton
    if _social_delivery_log_store_singleton is None:
        _social_delivery_log_store_singleton = build_social_delivery_log_store()
    return _social_delivery_log_store_singleton


def set_social_delivery_log_store_for_tests(
    store: SocialDeliveryLogStoreProtocol | None,
) -> None:
    """Replace the global delivery log store (``None`` restores lazy default)."""
    global _social_delivery_log_store_singleton
    _social_delivery_log_store_singleton = store
