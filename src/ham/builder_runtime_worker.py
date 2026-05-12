from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from src.ham.builder_cloud_runtime_gcp import (
    get_runtime_job_status as get_gcp_runtime_job_status,
    load_gcp_runtime_config,
    normalize_lifecycle_status,
    redact_provider_metadata,
    redact_runtime_logs,
    request_runtime as request_gcp_runtime,
    safe_proxy_host_from_upstream,
    safe_proxy_upstream_from_provider,
)
from src.persistence.builder_runtime_job_store import CloudRuntimeJob
from src.persistence.builder_source_store import get_builder_source_store
from src.persistence.builder_runtime_store import PreviewEndpoint, RuntimeSession, get_builder_runtime_store

CloudRuntimeProviderMode = Literal["disabled", "local_mock", "cloud_run_poc"]


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_cloud_runtime_provider_mode() -> CloudRuntimeProviderMode:
    raw = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER") or "").strip().lower()
    if raw in {"local_mock", "cloud_run_poc"}:
        return raw
    return "disabled"


def _is_experiments_enabled() -> bool:
    raw = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def get_cloud_runtime_experiment_status() -> tuple[str, str]:
    mode = get_cloud_runtime_provider_mode()
    experiments_enabled = _is_experiments_enabled()
    if not experiments_enabled and mode == "disabled":
        return (
            "experiment_not_enabled",
            "Cloud runtime experiments are not enabled in this environment.",
        )
    if mode == "disabled":
        return (
            "disabled",
            "Cloud runtime experiments are enabled, but no provider is selected.",
        )
    if mode == "local_mock":
        return (
            "provider_ready",
            "Cloud runtime local mock is ready for experimentation.",
        )
    cfg = load_gcp_runtime_config()
    if not experiments_enabled:
        return (
            "experiment_not_enabled",
            "Cloud runtime experiments are not enabled in this environment.",
        )
    if not cfg.enabled:
        return (
            "config_missing",
            "Cloud runtime provider needs configuration before it can run.",
        )
    if not cfg.gcp_project_present or not cfg.gcp_region_present:
        return (
            "config_missing",
            "Cloud runtime provider needs configuration before it can run.",
        )
    if cfg.dry_run:
        return (
            "dry_run_ready",
            "Cloud runtime dry-run mode is configured and ready.",
        )
    return (
        "provider_ready",
        "Cloud runtime provider is configured for experimentation.",
    )


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


@dataclass
class CloudRuntimeLifecycleStatus:
    phase: str
    message: str
    updated_at: str
    provider_status: str | None
    logs_summary: str | None


def _resolve_source_handoff(job: CloudRuntimeJob) -> dict[str, Any]:
    snapshot_id = str(job.source_snapshot_id or "").strip()
    if not snapshot_id:
        return {
            "handoff_status": "planned",
            "source_snapshot_id": None,
            "source_ref": None,
            "artifact_uri": None,
            "cleanup_after": None,
            "expires_at": None,
            "warnings": ["No source snapshot provided. Runtime handoff will use provider defaults."],
            "error_code": None,
            "error_message": None,
        }
    rows = get_builder_source_store().list_source_snapshots(
        workspace_id=job.workspace_id,
        project_id=job.project_id,
    )
    snapshot = next((row for row in rows if row.id == snapshot_id), None)
    if snapshot is None:
        return {
            "handoff_status": "failed",
            "source_snapshot_id": snapshot_id,
            "source_ref": None,
            "artifact_uri": None,
            "cleanup_after": None,
            "expires_at": None,
            "warnings": [],
            "error_code": "SOURCE_SNAPSHOT_NOT_FOUND",
            "error_message": "Source snapshot was not found for this project.",
        }
    artifact_uri = str(snapshot.artifact_uri or "").strip()
    if not artifact_uri.startswith("builder-artifact://"):
        return {
            "handoff_status": "failed",
            "source_snapshot_id": snapshot_id,
            "source_ref": None,
            "artifact_uri": None,
            "cleanup_after": None,
            "expires_at": None,
            "warnings": [],
            "error_code": "CLOUD_RUNTIME_SOURCE_HANDOFF_MISSING_ARTIFACT",
            "error_message": "Source snapshot has no safe artifact reference for handoff.",
        }
    expires_at = _utc_now_iso()
    source_ref = f"{snapshot.id}:{(snapshot.digest_sha256 or 'no-digest')[:16]}"
    return {
        "handoff_status": "planned",
        "source_snapshot_id": snapshot_id,
        "source_ref": source_ref,
        "artifact_uri": artifact_uri,
        "cleanup_after": "provider_default",
        "expires_at": expires_at,
        "warnings": [],
        "error_code": None,
        "error_message": None,
    }


def get_runtime_job_lifecycle_status(
    *,
    job: CloudRuntimeJob,
    runtime_session: RuntimeSession | None,
) -> CloudRuntimeLifecycleStatus:
    now = _utc_now_iso()
    provider_status: str | None = None
    logs_summary: str | None = redact_runtime_logs(job.logs_summary or "", max_chars=240)
    phase = "queued"
    message = "Cloud runtime job is queued."
    if job.provider == "disabled":
        phase = "failed"
        message = "Cloud runtime provider is disabled."
    elif job.provider == "local_mock":
        if job.status == "succeeded":
            phase = "ready"
            message = "Local mock cloud runtime completed."
        elif job.status in {"failed", "unsupported"}:
            phase = "failed"
            message = "Local mock cloud runtime failed."
        else:
            phase = "running"
            message = "Local mock cloud runtime is running."
    elif job.provider == "cloud_run_poc":
        provider_job_id = str((job.metadata or {}).get("provider_job_id") or "").strip() or None
        polled = get_gcp_runtime_job_status(provider_job_id=provider_job_id)
        provider_status = polled.get("provider_status")
        if polled.get("logs_summary"):
            logs_summary = redact_runtime_logs(str(polled.get("logs_summary") or ""), max_chars=240)
        provider_state = normalize_lifecycle_status(str(polled.get("provider_state") or ""))
        if provider_state in {"ready", "running", "provisioning"}:
            phase = provider_state
            message = "Cloud runtime lifecycle status refreshed."
        elif provider_state in {"failed", "expired"}:
            phase = provider_state
            message = "Cloud runtime lifecycle reported failure."
        elif provider_state == "provider_accepted":
            phase = "provider_accepted"
            message = "Cloud runtime provider accepted the request."
        elif str(polled.get("provider_state") or "") == "planned":
            phase = "preview_pending"
            message = "Cloud runtime is in dry-run or plan phase; no live preview URL yet."
        elif str(polled.get("provider_state") or "") == "invalid_config":
            phase = "failed"
            message = "Cloud runtime config is incomplete."
        if runtime_session is not None and runtime_session.preview_endpoint_id and phase == "running":
            phase = "preview_pending"
            message = "Cloud runtime preview endpoint exists but is not ready yet."
    if runtime_session is not None and runtime_session.status in {"expired", "failed", "unsupported"}:
        phase = "failed" if runtime_session.status != "expired" else "expired"
    return CloudRuntimeLifecycleStatus(
        phase=phase,
        message=message,
        updated_at=job.updated_at or now,
        provider_status=provider_status,
        logs_summary=logs_summary,
    )


def execute_cloud_runtime_job(job: CloudRuntimeJob) -> CloudRuntimeExecutionResult:
    mode = get_cloud_runtime_provider_mode()
    runtime_store = get_builder_runtime_store()
    job.provider = mode
    job.updated_at = _utc_now_iso()
    experiment_status, _ = get_cloud_runtime_experiment_status()

    if mode == "disabled":
        job.status = "unsupported"
        job.phase = "failed"
        if experiment_status == "experiment_not_enabled":
            job.error_code = "CLOUD_RUNTIME_EXPERIMENT_NOT_ENABLED"
            job.error_message = "Cloud runtime experiments are not enabled."
        else:
            job.error_code = "CLOUD_RUNTIME_PROVIDER_DISABLED"
            job.error_message = "Cloud runtime provider is disabled."
        job.logs_summary = "No execution performed. Enable local_mock for control-plane verification."
        job.completed_at = job.updated_at
        return CloudRuntimeExecutionResult(job=job, runtime_session=None, usage_event=None)

    if mode == "cloud_run_poc":
        if experiment_status == "experiment_not_enabled":
            job.status = "unsupported"
            job.phase = "failed"
            job.error_code = "CLOUD_RUNTIME_EXPERIMENT_NOT_ENABLED"
            job.error_message = "Cloud runtime experiments are not enabled."
            job.logs_summary = "No execution performed. Enable experiment mode before cloud runtime requests."
            job.completed_at = _utc_now_iso()
            job.updated_at = job.completed_at
            return CloudRuntimeExecutionResult(job=job, runtime_session=None, usage_event=None)
        job.phase = "validating_source"
        job.status = "running"
        job.updated_at = _utc_now_iso()
        source_handoff = _resolve_source_handoff(job)
        job.metadata = {
            **(job.metadata or {}),
            "source_handoff": redact_provider_metadata(source_handoff),
            "source_handoff_status": str(source_handoff.get("handoff_status") or "planned"),
        }
        job.phase = "validating_config"
        if source_handoff.get("handoff_status") == "failed":
            job.status = "unsupported"
            job.phase = "failed"
            job.error_code = str(source_handoff.get("error_code") or "CLOUD_RUNTIME_SOURCE_HANDOFF_FAILED")
            job.error_message = str(
                source_handoff.get("error_message") or "Cloud runtime source handoff failed safely."
            )
            job.logs_summary = "Cloud runtime source handoff failed before provider submission."
            job.completed_at = _utc_now_iso()
            job.updated_at = job.completed_at
            return CloudRuntimeExecutionResult(job=job, runtime_session=None, usage_event=None)
        job.phase = "submitting_cloud_runtime"
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
                    "provider_job_id": gcp_result.provider_job_id,
                }
            ),
        )
        job.metadata = {**(job.metadata or {}), "runtime_plan": gcp_result.plan.model_dump(mode="json")}
        if gcp_result.status == "planned":
            runtime.status = "provisioning"
            runtime.health = "unknown"
            runtime.message = (
                "Cloud runtime dry-run completed. No live service was provisioned; preview URL is not available yet."
            )
            runtime.updated_at = _utc_now_iso()
            runtime = runtime_store.upsert_runtime_session(runtime)
            job.runtime_session_id = runtime.id
            job.status = "succeeded"
            job.phase = "completed"
            job.error_code = None
            job.error_message = None
            job.logs_summary = "cloud_run_poc dry-run plan created. No live Cloud Run provisioning was executed."
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
                    "source_handoff_status": str(source_handoff.get("handoff_status") or "planned"),
                },
            }
            return CloudRuntimeExecutionResult(job=job, runtime_session=runtime, usage_event=usage_event)
        if gcp_result.status == "accepted":
            runtime.status = "provisioning"
            runtime.health = "unknown"
            runtime.message = "Cloud runtime provider accepted the request. Preview will appear only after a real preview endpoint exists."
            runtime.updated_at = _utc_now_iso()
            runtime.metadata = {
                **(runtime.metadata or {}),
                "provider_job_id": gcp_result.provider_job_id,
                "provider_state": gcp_result.provider_state or "accepted",
            }
            runtime = runtime_store.upsert_runtime_session(runtime)
            preview_endpoint = runtime_store.get_active_preview_endpoint(
                workspace_id=job.workspace_id,
                project_id=job.project_id,
                runtime_session_id=runtime.id,
            )
            if preview_endpoint is None:
                preview_endpoint = PreviewEndpoint(
                    workspace_id=job.workspace_id,
                    project_id=job.project_id,
                    runtime_session_id=runtime.id,
                )
            preview_endpoint.access_mode = "proxy"
            preview_endpoint.status = "provisioning"
            preview_endpoint.last_checked_at = _utc_now_iso()
            preview_endpoint.metadata = {
                **(preview_endpoint.metadata or {}),
                "provider": "gcp_cloud_run_poc",
                "provider_job_id": gcp_result.provider_job_id,
                "trusted_proxy_host": safe_proxy_host_from_upstream(gcp_result.preview_upstream_url),
            }
            if (gcp_result.provider_state or "").lower() == "ready":
                safe_upstream = safe_proxy_upstream_from_provider(gcp_result.preview_upstream_url)
                if safe_upstream:
                    preview_endpoint.status = "ready"
                    preview_endpoint.url = safe_upstream
            preview_endpoint = runtime_store.upsert_preview_endpoint(preview_endpoint)
            runtime.preview_endpoint_id = preview_endpoint.id
            runtime = runtime_store.upsert_runtime_session(runtime)
            job.runtime_session_id = runtime.id
            job.status = "running"
            job.phase = "provider_accepted"
            job.error_code = None
            job.error_message = None
            job.logs_summary = "cloud_run_poc submit accepted by provider. Runtime provisioning is pending."
            job.completed_at = None
            job.updated_at = _utc_now_iso()
            job.metadata = {
                **job.metadata,
                "provider_job_id": gcp_result.provider_job_id,
                "provider_state": gcp_result.provider_state or "accepted",
            }
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
                    "event_name": "cloud_runtime_provider_request_accepted",
                    "job_id": job.id,
                    "provider_mode": "cloud_run_poc",
                    "source_handoff_status": str(source_handoff.get("handoff_status") or "planned"),
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
