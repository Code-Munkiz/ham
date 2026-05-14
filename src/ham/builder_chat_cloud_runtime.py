"""Auto-enqueue cloud runtime jobs after chat scaffold (idempotent)."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from src.ham.builder_cloud_runtime_job_runner import run_persist_builder_cloud_runtime_job
from src.ham.builder_runtime_worker import (
    get_cloud_runtime_experiment_status,
    get_cloud_runtime_provider_mode,
)
from src.persistence.builder_runtime_job_store import get_builder_runtime_job_store

CHAT_SCAFFOLD_ENQUEUE_REASON = "chat_scaffold"
_TERMINAL_JOB_STATUSES = {"failed", "unsupported", "cancelled", "succeeded"}
_ACTIVE_JOB_STATUSES = {"queued", "running"}


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso_utc(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _stale_job_seconds() -> int:
    raw = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_STALE_JOB_SECONDS") or "").strip()
    try:
        value = int(raw) if raw else 900
    except ValueError:
        value = 900
    return max(60, min(value, 86400))


def _job_is_stale(row: Any) -> bool:
    now = datetime.now(UTC)
    updated = _parse_iso_utc(getattr(row, "updated_at", None))
    created = _parse_iso_utc(getattr(row, "created_at", None))
    ts = updated or created
    if ts is None:
        return True
    age = (now - ts).total_seconds()
    return age >= _stale_job_seconds()


def _supersede_job(*, row: Any, reason: str) -> Any:
    row.status = "cancelled"
    row.phase = "failed"
    row.completed_at = _utc_now_iso()
    row.updated_at = row.completed_at
    row.error_code = "CLOUD_RUNTIME_JOB_SUPERSEDED"
    row.error_message = reason
    row.logs_summary = "Superseded stale cloud runtime job before a fresh retry."
    row.metadata = {**(row.metadata or {}), "superseded_at": row.completed_at, "supersede_reason": reason}
    return row


def _chat_scaffold_dedupe_key(
    *,
    workspace_id: str,
    project_id: str,
    source_snapshot_id: str,
    session_id: str,
) -> str:
    return (
        f"{workspace_id}|{project_id}|{source_snapshot_id}|{session_id}|{CHAT_SCAFFOLD_ENQUEUE_REASON}"
    )


def builder_chat_cloud_runtime_auto_enqueue_eligible() -> bool:
    mode = get_cloud_runtime_provider_mode()
    if mode == "disabled":
        return False
    if mode == "local_mock":
        return True
    status, _ = get_cloud_runtime_experiment_status()
    return status not in {"experiment_not_enabled", "disabled", "config_missing"}


def maybe_enqueue_chat_scaffold_cloud_runtime_job(
    *,
    workspace_id: str,
    project_id: str,
    source_snapshot_id: str,
    session_id: str,
    requested_by: str,
) -> dict[str, Any]:
    if not builder_chat_cloud_runtime_auto_enqueue_eligible():
        return {}
    dedupe_key = _chat_scaffold_dedupe_key(
        workspace_id=workspace_id,
        project_id=project_id,
        source_snapshot_id=source_snapshot_id,
        session_id=session_id,
    )
    store = get_builder_runtime_job_store()
    for row in store.list_cloud_runtime_jobs(workspace_id=workspace_id, project_id=project_id):
        meta = row.metadata or {}
        if str(meta.get("chat_scaffold_dedupe_key") or "") == dedupe_key:
            status = str(row.status or "").strip().lower()
            if status in _TERMINAL_JOB_STATUSES:
                continue
            if status in _ACTIVE_JOB_STATUSES and _job_is_stale(row):
                superseded = _supersede_job(
                    row=row,
                    reason="Superseded stale chat dedupe cloud runtime job before fresh retry.",
                )
                store.upsert_cloud_runtime_job(superseded)
                continue
            return {
                "cloud_runtime_job_id": row.id,
                "cloud_runtime_job_deduplicated": True,
            }
    meta = {
        "enqueue_reason": CHAT_SCAFFOLD_ENQUEUE_REASON,
        "chat_scaffold_dedupe_key": dedupe_key,
    }
    saved_job, _ = run_persist_builder_cloud_runtime_job(
        workspace_id=workspace_id,
        project_id=project_id,
        source_snapshot_id=source_snapshot_id,
        requested_by=requested_by or None,
        metadata=meta,
    )
    return {
        "cloud_runtime_job_id": saved_job.id,
        "cloud_runtime_job_deduplicated": False,
    }
