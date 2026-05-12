"""Auto-enqueue cloud runtime jobs after chat scaffold (idempotent)."""

from __future__ import annotations

from typing import Any

from src.ham.builder_cloud_runtime_job_runner import run_persist_builder_cloud_runtime_job
from src.ham.builder_runtime_worker import (
    get_cloud_runtime_experiment_status,
    get_cloud_runtime_provider_mode,
)
from src.persistence.builder_runtime_job_store import get_builder_runtime_job_store

CHAT_SCAFFOLD_ENQUEUE_REASON = "chat_scaffold"


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
