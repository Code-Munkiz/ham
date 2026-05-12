from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from src.ham.builder_cloud_runtime_gcp import (
    load_gcp_runtime_config,
    redact_provider_metadata,
    request_runtime as request_gcp_runtime,
)
from src.persistence.builder_runtime_job_store import CloudRuntimeJob
from src.persistence.builder_runtime_store import RuntimeSession, get_builder_runtime_store

CloudRuntimeProviderMode = Literal["disabled", "local_mock", "cloud_run_poc"]


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_cloud_runtime_provider_mode() -> CloudRuntimeProviderMode:
    raw = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER") or "").strip().lower()
    if raw in {"local_mock", "cloud_run_poc"}:
        return raw
    return "disabled"


def get_cloud_runtime_provider_capability_status() -> str:
    mode = get_cloud_runtime_provider_mode()
    if mode == "local_mock":
        return "available_mock"
    if mode == "cloud_run_poc":
        cfg = load_gcp_runtime_config()
        if not cfg.enabled:
            return "disabled"
        if not cfg.gcp_project_present or not cfg.gcp_region_present:
            return "unavailable"
        return "available_poc"
    return "disabled"


@dataclass
class CloudRuntimeExecutionResult:
    job: CloudRuntimeJob
    runtime_session: RuntimeSession | None
    usage_event: dict[str, Any] | None


def execute_cloud_runtime_job(job: CloudRuntimeJob) -> CloudRuntimeExecutionResult:
    mode = get_cloud_runtime_provider_mode()
    runtime_store = get_builder_runtime_store()
    job.provider = mode
    job.updated_at = _utc_now_iso()

    if mode == "disabled":
        job.status = "unsupported"
        job.phase = "failed"
        job.error_code = "CLOUD_RUNTIME_PROVIDER_DISABLED"
        job.error_message = "Cloud runtime provider is disabled."
        job.logs_summary = "No execution performed. Enable local_mock for control-plane verification."
        job.completed_at = job.updated_at
        return CloudRuntimeExecutionResult(job=job, runtime_session=None, usage_event=None)

    if mode == "cloud_run_poc":
        gcp_result = request_gcp_runtime(job)
        runtime = runtime_store.request_cloud_runtime_session(
            workspace_id=job.workspace_id,
            project_id=job.project_id,
            source_snapshot_id=job.source_snapshot_id,
            requested_by=job.requested_by,
            metadata=redact_provider_metadata(
                {
                    "provider_mode": "cloud_run_poc",
                    "cloud_runtime_job_id": job.id,
                    "runtime_plan_status": gcp_result.plan.status,
                    "dry_run": bool(gcp_result.plan.metadata.get("dry_run")),
                }
            ),
        )
        job.metadata = {
            **(job.metadata or {}),
            "runtime_plan": gcp_result.plan.model_dump(mode="json"),
        }
        if gcp_result.status == "planned":
            runtime.status = "queued"
            runtime.health = "unknown"
            runtime.message = "Cloud runtime provider is configured for plan-only POC. No cloud runtime has been provisioned yet."
            runtime.updated_at = _utc_now_iso()
            runtime = runtime_store.upsert_runtime_session(runtime)
            job.runtime_session_id = runtime.id
            job.status = "succeeded"
            job.phase = "completed"
            job.error_code = None
            job.error_message = None
            job.logs_summary = "cloud_run_poc dry-run plan created. No provisioning was executed."
            job.completed_at = _utc_now_iso()
            job.updated_at = job.completed_at
            usage_event = {
                "category": "worker_job",
                "quantity": 1,
                "unit": "count",
                "attribution": {
                    "provider": "builder_cloud_runtime",
                    "worker_provider": "cloud_run_poc",
                    "source_snapshot_id": job.source_snapshot_id,
                    "runtime_session_id": runtime.id,
                },
                "metadata": {
                    "event_name": "cloud_runtime_plan_created",
                    "job_id": job.id,
                    "provider_mode": "cloud_run_poc",
                    "dry_run": bool(gcp_result.plan.metadata.get("dry_run")),
                },
            }
            return CloudRuntimeExecutionResult(job=job, runtime_session=runtime, usage_event=usage_event)
        runtime.status = "unsupported"
        runtime.health = "unknown"
        runtime.message = gcp_result.error_message or "Cloud runtime provider request failed safely."
        runtime.updated_at = _utc_now_iso()
        runtime = runtime_store.upsert_runtime_session(runtime)
        job.runtime_session_id = runtime.id
        job.status = "unsupported"
        job.phase = "failed"
        job.error_code = gcp_result.error_code or "CLOUD_RUNTIME_PROVIDER_ERROR"
        job.error_message = gcp_result.error_message or "Cloud runtime provider request failed safely."
        job.logs_summary = "; ".join(gcp_result.warnings) or "No provisioning was executed."
        job.completed_at = _utc_now_iso()
        job.updated_at = job.completed_at
        return CloudRuntimeExecutionResult(job=job, runtime_session=runtime, usage_event=None)

    # local_mock: simulate lifecycle without executing user code.
    job.phase = "running_poc"
    job.status = "running"
    job.updated_at = _utc_now_iso()
    runtime = runtime_store.request_cloud_runtime_session(
        workspace_id=job.workspace_id,
        project_id=job.project_id,
        source_snapshot_id=job.source_snapshot_id,
        requested_by=job.requested_by,
        metadata={
            "provider_mode": "local_mock",
            "cloud_runtime_job_id": job.id,
        },
    )
    runtime.status = "running"
    runtime.health = "healthy"
    runtime.message = "Cloud runtime POC simulated. No real sandbox/build executed."
    runtime.updated_at = _utc_now_iso()
    runtime = runtime_store.upsert_runtime_session(runtime)
    job.runtime_session_id = runtime.id
    job.phase = "completed"
    job.status = "succeeded"
    job.error_code = None
    job.error_message = None
    job.logs_summary = "local_mock lifecycle simulated: received -> preparing -> running_poc -> completed"
    job.completed_at = _utc_now_iso()
    job.updated_at = job.completed_at
    usage_event = {
        "category": "worker_job",
        "quantity": 1,
        "unit": "count",
        "attribution": {
            "provider": "builder_cloud_runtime",
            "worker_provider": mode,
            "source_snapshot_id": job.source_snapshot_id,
            "runtime_session_id": runtime.id,
        },
        "metadata": {
            "event_name": "cloud_runtime_poc_completed",
            "job_id": job.id,
            "provider_mode": mode,
        },
    }
    return CloudRuntimeExecutionResult(job=job, runtime_session=runtime, usage_event=usage_event)
