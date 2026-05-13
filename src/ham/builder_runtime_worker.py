from __future__ import annotations

import os
import zipfile
from io import BytesIO
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
from src.ham.builder_sandbox_provider import (
    SandboxSourceFile,
    SandboxRuntimeState,
    build_sandbox_runtime_provider,
    classify_sandbox_provider_error,
    load_sandbox_runtime_config,
    sandbox_preview_host,
    sandbox_provider_is_supported,
)
from src.persistence.builder_runtime_job_store import CloudRuntimeJob
from src.persistence.builder_source_store import get_builder_source_store
from src.persistence.builder_runtime_store import PreviewEndpoint, RuntimeSession, get_builder_runtime_store

CloudRuntimeProviderMode = Literal["disabled", "local_mock", "cloud_run_poc", "sandbox_provider"]


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_cloud_runtime_provider_mode() -> CloudRuntimeProviderMode:
    raw = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER") or "").strip().lower()
    if raw in {"local_mock", "cloud_run_poc", "sandbox_provider"}:
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
    if mode == "sandbox_provider":
        cfg = load_sandbox_runtime_config()
        if not experiments_enabled:
            return (
                "experiment_not_enabled",
                "Cloud runtime experiments are not enabled in this environment.",
            )
        if not cfg.enabled:
            return (
                "config_missing",
                "Cloud sandbox provider is not enabled in this environment.",
            )
        if not sandbox_provider_is_supported(cfg.provider):
            return (
                "config_missing",
                "Cloud sandbox provider must be configured to e2b or daytona.",
            )
        if not cfg.dry_run and not cfg.api_key_present:
            return (
                "config_missing",
                "Cloud sandbox provider is missing required API key configuration.",
            )
        if cfg.dry_run:
            return (
                "dry_run_ready",
                "Cloud sandbox provider dry-run mode is configured and ready.",
            )
        return (
            "provider_ready",
            "Cloud sandbox provider is configured for live runtime experimentation.",
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
    if mode == "sandbox_provider":
        cfg = load_sandbox_runtime_config()
        if not cfg.enabled:
            return "disabled"
        if not sandbox_provider_is_supported(cfg.provider):
            return "unavailable"
        if not cfg.dry_run and not cfg.api_key_present:
            return "needs_connection"
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


def _sandbox_diag_payload(
    *,
    job: CloudRuntimeJob,
    lifecycle_stage: str,
    error_code: str | None,
    error_message: str | None,
    exception_class: str | None,
    retry_count: int,
    retryable: bool,
) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "snapshot_id": job.source_snapshot_id,
        "lifecycle_stage": lifecycle_stage,
        "exception_class": exception_class,
        "normalized_error_code": error_code,
        "normalized_error_message": error_message,
        "retry_count": retry_count,
        "retryable": retryable,
    }


def _set_sandbox_diag(
    *,
    job: CloudRuntimeJob,
    runtime: RuntimeSession,
    lifecycle_stage: str,
    error_code: str | None,
    error_message: str | None,
    exception_class: str | None,
    retry_count: int,
    retryable: bool,
) -> None:
    diagnostics = _sandbox_diag_payload(
        job=job,
        lifecycle_stage=lifecycle_stage,
        error_code=error_code,
        error_message=error_message,
        exception_class=exception_class,
        retry_count=retry_count,
        retryable=retryable,
    )
    job.metadata = {**(job.metadata or {}), "sandbox_diagnostics": diagnostics}
    runtime.metadata = {**(runtime.metadata or {}), "sandbox_diagnostics": diagnostics}


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


def _materialize_snapshot_source_files(
    *,
    workspace_id: str,
    project_id: str,
    snapshot_id: str | None,
) -> tuple[list[SandboxSourceFile], str | None]:
    snapshot_value = str(snapshot_id or "").strip()
    if not snapshot_value:
        return [], "SANDBOX_SOURCE_SNAPSHOT_MISSING"
    rows = get_builder_source_store().list_source_snapshots(
        workspace_id=workspace_id,
        project_id=project_id,
    )
    snapshot = next((row for row in rows if row.id == snapshot_value), None)
    if snapshot is None:
        return [], "SOURCE_SNAPSHOT_NOT_FOUND"
    manifest = snapshot.manifest or {}
    inline_files = manifest.get("inline_files")
    if isinstance(inline_files, dict):
        files: list[SandboxSourceFile] = []
        for raw_path, raw_text in inline_files.items():
            if not isinstance(raw_path, str) or not isinstance(raw_text, str):
                continue
            rel = raw_path.replace("\\", "/").lstrip("/")
            if not rel or ".." in rel.split("/"):
                continue
            files.append(SandboxSourceFile(path=rel, data=raw_text.encode("utf-8")))
        return files, None if files else "SANDBOX_SOURCE_FILES_MISSING"
    artifact_uri = str(snapshot.artifact_uri or "").strip()
    if not artifact_uri.startswith("builder-artifact://"):
        return [], "CLOUD_RUNTIME_SOURCE_HANDOFF_MISSING_ARTIFACT"
    artifact_id = artifact_uri.replace("builder-artifact://", "", 1).strip()
    if not artifact_id:
        return [], "CLOUD_RUNTIME_SOURCE_HANDOFF_MISSING_ARTIFACT"
    from src.ham.builder_chat_scaffold import load_zip_bytes_for_snapshot

    payload = load_zip_bytes_for_snapshot(
        workspace_id=workspace_id,
        project_id=project_id,
        artifact_id=artifact_id,
    )
    if payload is None:
        return [], "CLOUD_RUNTIME_SOURCE_HANDOFF_MISSING_ARTIFACT"
    files = []
    try:
        with zipfile.ZipFile(BytesIO(payload)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                rel = info.filename.replace("\\", "/").lstrip("/")
                if not rel or ".." in rel.split("/"):
                    continue
                data = zf.read(info)
                files.append(SandboxSourceFile(path=rel, data=data))
    except (zipfile.BadZipFile, OSError, RuntimeError):
        return [], "SANDBOX_SOURCE_ARTIFACT_INVALID"
    return files, None if files else "SANDBOX_SOURCE_FILES_MISSING"


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
    elif job.provider == "sandbox_provider":
        if job.status in {"failed", "unsupported"}:
            phase = "failed"
            message = "Cloud sandbox runtime failed."
        elif runtime_session is not None and runtime_session.preview_endpoint_id:
            phase = "ready"
            message = "Cloud sandbox preview proxy is ready."
        elif job.status == "succeeded":
            phase = "preview_pending"
            message = "Cloud sandbox runtime completed dry-run planning. Preview was not started."
        else:
            phase = "running"
            message = "Cloud sandbox runtime is provisioning."
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

    if mode == "sandbox_provider":
        if experiment_status == "experiment_not_enabled":
            job.status = "unsupported"
            job.phase = "failed"
            job.error_code = "CLOUD_RUNTIME_EXPERIMENT_NOT_ENABLED"
            job.error_message = "Cloud runtime experiments are not enabled."
            job.logs_summary = "No execution performed. Enable experiment mode before sandbox runtime requests."
            job.completed_at = _utc_now_iso()
            job.updated_at = job.completed_at
            return CloudRuntimeExecutionResult(job=job, runtime_session=None, usage_event=None)
        cfg = load_sandbox_runtime_config()
        if not cfg.enabled or not sandbox_provider_is_supported(cfg.provider):
            job.status = "unsupported"
            job.phase = "failed"
            job.error_code = "SANDBOX_PROVIDER_CONFIG_MISSING"
            job.error_message = "Cloud sandbox provider is not configured."
            job.logs_summary = "No execution performed. Configure sandbox provider settings."
            job.completed_at = _utc_now_iso()
            job.updated_at = job.completed_at
            return CloudRuntimeExecutionResult(job=job, runtime_session=None, usage_event=None)
        if not cfg.dry_run and not cfg.api_key_present:
            job.status = "unsupported"
            job.phase = "failed"
            job.error_code = "SANDBOX_PROVIDER_API_KEY_MISSING"
            job.error_message = "Cloud sandbox provider API key is missing."
            job.logs_summary = "No execution performed. Add API key configuration before non-dry-run requests."
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
            "provider_mode": "sandbox_provider",
            "sandbox_provider": cfg.provider,
            "dry_run": cfg.dry_run,
        }
        if source_handoff.get("handoff_status") == "failed":
            job.status = "unsupported"
            job.phase = "failed"
            job.error_code = str(source_handoff.get("error_code") or "SANDBOX_SOURCE_HANDOFF_FAILED")
            job.error_message = str(source_handoff.get("error_message") or "Sandbox source handoff failed safely.")
            job.logs_summary = "Sandbox runtime source handoff failed before provider simulation."
            job.completed_at = _utc_now_iso()
            job.updated_at = job.completed_at
            return CloudRuntimeExecutionResult(job=job, runtime_session=None, usage_event=None)
        runtime = runtime_store.request_cloud_runtime_session(
            workspace_id=job.workspace_id,
            project_id=job.project_id,
            source_snapshot_id=job.source_snapshot_id,
            requested_by=job.requested_by,
            metadata=redact_provider_metadata(
                {
                    "provider_mode": "sandbox_provider",
                    "sandbox_provider": cfg.provider,
                    "cloud_runtime_job_id": job.id,
                    "dry_run": cfg.dry_run,
                }
            ),
        )
        state = SandboxRuntimeState(
            provider=cfg.provider,
            sandbox_id=None,
            workspace_id=job.workspace_id,
            project_id=job.project_id,
            snapshot_id=job.source_snapshot_id,
            runtime_job_id=job.id,
            status="queued",
            preview_upstream_url=None,
            preview_proxy_url=None,
            logs_summary=None,
            error_code=None,
            error_message=None,
            started_at=_utc_now_iso(),
            updated_at=_utc_now_iso(),
            expires_at=None,
        )
        if cfg.dry_run:
            runtime.status = "provisioning"
            runtime.health = "unknown"
            runtime.message = (
                "Cloud sandbox dry-run completed. No live sandbox preview was started."
            )
            runtime.updated_at = _utc_now_iso()
            runtime = runtime_store.upsert_runtime_session(runtime)
            job.runtime_session_id = runtime.id
            job.status = "succeeded"
            job.phase = "completed"
            job.error_code = None
            job.error_message = None
            job.logs_summary = (
                "sandbox_provider dry-run plan created. No live sandbox execution was performed."
            )
            job.completed_at = _utc_now_iso()
            job.updated_at = job.completed_at
            usage_event = {
                "category": "worker_job",
                "quantity": 1,
                "unit": "count",
                "attribution": {
                    "provider": "builder_cloud_runtime",
                    "worker_provider": "sandbox_provider",
                    "source_snapshot_id": job.source_snapshot_id,
                    "runtime_session_id": runtime.id,
                },
                "metadata": {
                    "event_name": "sandbox_runtime_plan_created",
                    "job_id": job.id,
                    "sandbox_provider": cfg.provider,
                    "dry_run": True,
                },
            }
            return CloudRuntimeExecutionResult(job=job, runtime_session=runtime, usage_event=usage_event)
        source_files, source_files_error = _materialize_snapshot_source_files(
            workspace_id=job.workspace_id,
            project_id=job.project_id,
            snapshot_id=job.source_snapshot_id,
        )
        if source_files_error:
            runtime.status = "failed"
            runtime.health = "unhealthy"
            runtime.message = "Cloud sandbox source payload is unavailable."
            runtime.updated_at = _utc_now_iso()
            runtime = runtime_store.upsert_runtime_session(runtime)
            job.runtime_session_id = runtime.id
            job.status = "failed"
            job.phase = "failed"
            job.error_code = source_files_error
            job.error_message = "Cloud sandbox source payload is unavailable."
            job.logs_summary = "Sandbox source materialization failed before provider call."
            job.completed_at = _utc_now_iso()
            job.updated_at = job.completed_at
            return CloudRuntimeExecutionResult(job=job, runtime_session=runtime, usage_event=None)
        provider = build_sandbox_runtime_provider(config=cfg)
        lifecycle_stage = "create_sandbox"
        exception_class: str | None = None
        retry_count = 0
        retryable = False
        while True:
            try:
                lifecycle_stage = "create_sandbox"
                state = provider.create_sandbox(state=state, config=cfg)
                break
            except Exception as exc:  # pragma: no cover - defensive adapter guard
                classified = classify_sandbox_provider_error(error=exc, lifecycle_stage=lifecycle_stage)
                exception_class = classified.exception_class
                retryable = bool(classified.retryable)
                if retryable and retry_count < 1:
                    retry_count += 1
                    continue
                state = SandboxRuntimeState(
                    **{
                        **state.__dict__,
                        "status": "failed",
                        "updated_at": _utc_now_iso(),
                        "error_code": classified.error_code,
                        "error_message": classified.error_message,
                    }
                )
                break
        if state.status != "failed":
            lifecycle_stage = "upload_source"
            state = provider.upload_source(
                state=state,
                source_ref=str(source_handoff.get("source_ref") or ""),
                artifact_uri=str(source_handoff.get("artifact_uri") or ""),
                files=source_files,
            )
        if state.status != "failed":
            lifecycle_stage = "install"
            state = provider.run_command(state=state, command=["npm", "install"], stage="install")
        if state.status != "failed":
            lifecycle_stage = "start"
            state = provider.run_command(
                state=state,
                command=["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", str(cfg.default_port)],
                stage="start",
            )
        if state.status != "failed":
            lifecycle_stage = "health"
            state = provider.start_preview_server(state=state, port=cfg.default_port)
        if state.status != "ready":
            runtime.status = "failed"
            runtime.health = "unhealthy"
            runtime.message = state.error_message or "Cloud sandbox provider request failed safely."
            runtime.updated_at = _utc_now_iso()
            runtime.metadata = {
                **(runtime.metadata or {}),
                "sandbox_provider": cfg.provider,
                "sandbox_id": state.sandbox_id,
            }
            _set_sandbox_diag(
                job=job,
                runtime=runtime,
                lifecycle_stage=lifecycle_stage,
                error_code=state.error_code or "SANDBOX_PROVIDER_ERROR",
                error_message=state.error_message or "Cloud sandbox provider request failed safely.",
                exception_class=exception_class,
                retry_count=retry_count,
                retryable=retryable,
            )
            runtime = runtime_store.upsert_runtime_session(runtime)
            job.runtime_session_id = runtime.id
            job.status = "failed"
            job.phase = "failed"
            job.error_code = state.error_code or "SANDBOX_PROVIDER_ERROR"
            job.error_message = state.error_message or "Cloud sandbox provider request failed safely."
            job.logs_summary = provider.get_logs_summary(state=state) or "Sandbox provider simulation failed."
            job.completed_at = _utc_now_iso()
            job.updated_at = job.completed_at
            return CloudRuntimeExecutionResult(job=job, runtime_session=runtime, usage_event=None)
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
        upstream_url = provider.get_preview_url(state=state, port=cfg.default_port)
        safe_upstream = safe_proxy_upstream_from_provider(upstream_url)
        if safe_upstream is None:
            lifecycle_stage = "persist"
            runtime.status = "failed"
            runtime.health = "unhealthy"
            runtime.message = "Sandbox provider returned an unsafe preview upstream URL."
            runtime.updated_at = _utc_now_iso()
            _set_sandbox_diag(
                job=job,
                runtime=runtime,
                lifecycle_stage=lifecycle_stage,
                error_code="SANDBOX_PREVIEW_URL_UNSAFE",
                error_message="Sandbox provider returned an unsafe preview upstream URL.",
                exception_class=exception_class,
                retry_count=retry_count,
                retryable=False,
            )
            runtime = runtime_store.upsert_runtime_session(runtime)
            job.runtime_session_id = runtime.id
            job.status = "failed"
            job.phase = "failed"
            job.error_code = "SANDBOX_PREVIEW_URL_UNSAFE"
            job.error_message = "Sandbox provider returned an unsafe preview upstream URL."
            job.logs_summary = provider.get_logs_summary(state=state)
            job.completed_at = _utc_now_iso()
            job.updated_at = job.completed_at
            return CloudRuntimeExecutionResult(job=job, runtime_session=runtime, usage_event=None)
        preview_endpoint.access_mode = "proxy"
        preview_endpoint.status = "ready"
        preview_endpoint.url = safe_upstream
        preview_endpoint.last_checked_at = _utc_now_iso()
        preview_endpoint.metadata = {
            **(preview_endpoint.metadata or {}),
            "provider": "sandbox_provider",
            "sandbox_provider": cfg.provider,
            "sandbox_id": state.sandbox_id,
            "trusted_proxy_host": sandbox_preview_host(safe_upstream),
        }
        preview_endpoint = runtime_store.upsert_preview_endpoint(preview_endpoint)
        runtime.preview_endpoint_id = preview_endpoint.id
        runtime.status = "running"
        runtime.health = "healthy"
        runtime.message = "Cloud sandbox preview is ready via authenticated cloud proxy."
        runtime.updated_at = _utc_now_iso()
        runtime.metadata = {
            **(runtime.metadata or {}),
            "sandbox_provider": cfg.provider,
            "sandbox_id": state.sandbox_id,
        }
        _set_sandbox_diag(
            job=job,
            runtime=runtime,
            lifecycle_stage="persist",
            error_code=None,
            error_message=None,
            exception_class=exception_class,
            retry_count=retry_count,
            retryable=False,
        )
        runtime = runtime_store.upsert_runtime_session(runtime)
        job.runtime_session_id = runtime.id
        job.status = "succeeded"
        job.phase = "completed"
        job.error_code = None
        job.error_message = None
        job.logs_summary = provider.get_logs_summary(state=state)
        job.completed_at = _utc_now_iso()
        job.updated_at = job.completed_at
        usage_event = {
            "category": "worker_job",
            "quantity": 1,
            "unit": "count",
            "attribution": {
                "provider": "builder_cloud_runtime",
                "worker_provider": "sandbox_provider",
                "source_snapshot_id": job.source_snapshot_id,
                "runtime_session_id": runtime.id,
            },
            "metadata": {
                "event_name": "sandbox_runtime_preview_ready",
                "job_id": job.id,
                "sandbox_provider": cfg.provider,
                "dry_run": False,
            },
        }
        return CloudRuntimeExecutionResult(job=job, runtime_session=runtime, usage_event=usage_event)

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
