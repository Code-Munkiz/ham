"""Create, persist, and execute builder cloud runtime jobs (shared by HTTP API and chat hooks)."""

from __future__ import annotations

from typing import Any

from src.ham.builder_runtime_worker import execute_cloud_runtime_job, get_cloud_runtime_provider_mode
from src.persistence.builder_runtime_job_store import CloudRuntimeJob, get_builder_runtime_job_store
from src.persistence.builder_runtime_store import RuntimeSession
from src.persistence.builder_usage_event_store import (
    UsageEvent,
    UsageEventAttribution,
    get_builder_usage_event_store,
)


def _sanitize_job_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for idx, (key, value) in enumerate(raw.items()):
        if idx >= 20:
            break
        key_text = str(key).strip()[:64]
        if not key_text:
            continue
        if isinstance(value, bool) or value is None:
            safe[key_text] = value
        elif isinstance(value, int):
            safe[key_text] = value
        elif isinstance(value, float):
            safe[key_text] = round(value, 6)
        else:
            safe[key_text] = str(value).strip()[:500]
    return safe


def run_persist_builder_cloud_runtime_job(
    *,
    workspace_id: str,
    project_id: str,
    source_snapshot_id: str | None,
    requested_by: str | None,
    metadata: dict[str, Any],
) -> tuple[CloudRuntimeJob, RuntimeSession | None]:
    provider_mode = get_cloud_runtime_provider_mode()
    job = CloudRuntimeJob(
        workspace_id=workspace_id,
        project_id=project_id,
        source_snapshot_id=source_snapshot_id,
        provider=provider_mode,
        requested_by=requested_by,
        status="queued",
        phase="received",
        metadata=_sanitize_job_metadata(metadata),
    )
    job_store = get_builder_runtime_job_store()
    job = job_store.upsert_cloud_runtime_job(job)
    get_builder_usage_event_store().append_usage_event(
        UsageEvent(
            workspace_id=workspace_id,
            project_id=project_id,
            category="worker_job",
            quantity=1,
            unit="count",
            attribution=UsageEventAttribution(
                provider="builder_cloud_runtime",
                worker_provider=provider_mode,
                source_snapshot_id=source_snapshot_id,
            ),
            metadata={"event_name": "cloud_runtime_job_requested", "job_id": job.id},
        )
    )
    if source_snapshot_id:
        get_builder_usage_event_store().append_usage_event(
            UsageEvent(
                workspace_id=workspace_id,
                project_id=project_id,
                category="worker_job",
                quantity=1,
                unit="count",
                attribution=UsageEventAttribution(
                    provider="builder_cloud_runtime",
                    worker_provider=provider_mode,
                    source_snapshot_id=source_snapshot_id,
                ),
                metadata={"event_name": "source_handoff_requested", "job_id": job.id},
            )
        )
    result = execute_cloud_runtime_job(job)
    saved_job = job_store.upsert_cloud_runtime_job(result.job)
    if result.usage_event is not None:
        get_builder_usage_event_store().append_usage_event(
            UsageEvent(
                workspace_id=workspace_id,
                project_id=project_id,
                category=result.usage_event["category"],
                quantity=result.usage_event["quantity"],
                unit=result.usage_event["unit"],
                attribution=UsageEventAttribution.from_raw(result.usage_event["attribution"]),
                metadata=result.usage_event["metadata"],
            )
        )
    return saved_job, result.runtime_session
