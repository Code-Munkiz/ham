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
    build_gcp_gke_runtime_provider,
    classify_builder_runtime_error,
    gcp_gke_runtime_config_complete,
    load_gcp_gke_runtime_config,
    runtime_preview_host,
)
from src.ham.gcp_preview_runtime_client import (
    PreviewPodRef,
    build_gke_runtime_client,
)
from src.ham.gcp_preview_source_bundle import (
    build_source_bundle_uploader,
    package_source_files_to_zip,
)
from src.ham.gcp_preview_worker_manifest import build_gke_preview_pod_manifest
from src.persistence.builder_runtime_job_store import CloudRuntimeJob
from src.persistence.builder_source_store import get_builder_source_store
from src.persistence.builder_runtime_store import PreviewEndpoint, RuntimeSession, get_builder_runtime_store

CloudRuntimeProviderMode = Literal["disabled", "local_mock", "cloud_run_poc", "gcp_gke_sandbox"]


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_cloud_runtime_provider_mode() -> CloudRuntimeProviderMode:
    raw = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER") or "").strip().lower()
    if raw in {"local_mock", "cloud_run_poc", "gcp_gke_sandbox"}:
        return raw
    return "disabled"


def _is_experiments_enabled() -> bool:
    raw = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _is_true_env(name: str) -> bool:
    raw = str(os.environ.get(name) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _gcp_gke_live_gates_ready(cfg: Any) -> bool:
    return bool(
        cfg.enabled
        and not cfg.dry_run
        and _is_true_env("HAM_BUILDER_GCP_RUNTIME_LIVE_K8S_ENABLED")
        and _is_true_env("HAM_BUILDER_GCP_RUNTIME_LIVE_BUNDLE_UPLOAD")
        and cfg.project_id_present
        and cfg.region_present
        and cfg.cluster_present
        and cfg.namespace_prefix_present
        and cfg.bucket_present
        and cfg.runner_image_present
    )


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
    if mode == "gcp_gke_sandbox":
        cfg = load_gcp_gke_runtime_config()
        if not experiments_enabled:
            return (
                "experiment_not_enabled",
                "Cloud runtime experiments are not enabled in this environment.",
            )
        if not cfg.enabled:
            return (
                "config_missing",
                "GCP GKE runtime is not enabled in this environment.",
            )
        if not gcp_gke_runtime_config_complete(cfg):
            return (
                "config_missing",
                "GCP GKE runtime scaffold configuration is incomplete.",
            )
        if not cfg.dry_run and not cfg.fake_mode_explicit and not _gcp_gke_live_gates_ready(cfg):
            return (
                "config_missing",
                "GCP GKE runtime live gates are incomplete.",
            )
        if cfg.dry_run:
            return (
                "dry_run_ready",
                "GCP GKE runtime dry-run scaffold is configured and ready.",
            )
        if _gcp_gke_live_gates_ready(cfg):
            return (
                "provider_ready",
                "GCP GKE runtime live mode gates are configured.",
            )
        return (
            "provider_ready",
            "GCP GKE runtime fake mode is configured for controlled tests.",
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
    if mode == "gcp_gke_sandbox":
        cfg = load_gcp_gke_runtime_config()
        if not cfg.enabled:
            return "disabled"
        if not gcp_gke_runtime_config_complete(cfg):
            return "unavailable"
        if not cfg.dry_run and not cfg.fake_mode_explicit and not _gcp_gke_live_gates_ready(cfg):
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


def _runtime_diag_payload(
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


def _set_runtime_diag(
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
    diagnostics = _runtime_diag_payload(
        job=job,
        lifecycle_stage=lifecycle_stage,
        error_code=error_code,
        error_message=error_message,
        exception_class=exception_class,
        retry_count=retry_count,
        retryable=retryable,
    )
    job.metadata = {**(job.metadata or {}), "runtime_diagnostics": diagnostics}
    runtime.metadata = {**(runtime.metadata or {}), "runtime_diagnostics": diagnostics}


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
    elif job.provider == "gcp_gke_sandbox":
        if job.status in {"failed", "unsupported"}:
            phase = "failed"
            message = "GCP GKE sandbox runtime failed."
        elif runtime_session is not None and runtime_session.preview_endpoint_id:
            phase = "ready"
            message = "GCP GKE sandbox preview proxy is ready."
        elif job.status == "succeeded":
            phase = "preview_pending"
            message = "GCP GKE sandbox runtime completed dry-run planning. Preview was not started."
        else:
            phase = "running"
            message = "GCP GKE sandbox runtime is provisioning."
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

    if mode == "gcp_gke_sandbox":
        if experiment_status == "experiment_not_enabled":
            job.status = "unsupported"
            job.phase = "failed"
            job.error_code = "CLOUD_RUNTIME_EXPERIMENT_NOT_ENABLED"
            job.error_message = "Cloud runtime experiments are not enabled."
            job.logs_summary = (
                "No execution performed. Enable experiment mode before GCP GKE sandbox runtime requests."
            )
            job.completed_at = _utc_now_iso()
            job.updated_at = job.completed_at
            return CloudRuntimeExecutionResult(job=job, runtime_session=None, usage_event=None)
        cfg = load_gcp_gke_runtime_config()
        if not cfg.enabled or not gcp_gke_runtime_config_complete(cfg):
            job.status = "unsupported"
            job.phase = "failed"
            job.error_code = "GCP_GKE_RUNTIME_CONFIG_MISSING"
            job.error_message = "GCP GKE runtime scaffold is not configured."
            job.logs_summary = "No execution performed. Configure GCP GKE runtime scaffold env vars."
            job.completed_at = _utc_now_iso()
            job.updated_at = job.completed_at
            return CloudRuntimeExecutionResult(job=job, runtime_session=None, usage_event=None)
        live_mode_requested = _gcp_gke_live_gates_ready(cfg)
        if not cfg.dry_run and not cfg.fake_mode_explicit and not live_mode_requested:
            job.status = "unsupported"
            job.phase = "failed"
            job.error_code = "GCP_GKE_RUNTIME_CONFIG_MISSING"
            job.error_message = "GCP GKE runtime live gates are incomplete."
            job.logs_summary = (
                "No execution performed. Configure explicit GCP live gates or use dry-run/fake mode."
            )
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
            "provider_mode": "gcp_gke_sandbox",
            "workload_runtime": cfg.provider,
            "dry_run": cfg.dry_run,
        }
        if source_handoff.get("handoff_status") == "failed":
            job.status = "unsupported"
            job.phase = "failed"
            job.error_code = str(source_handoff.get("error_code") or "GCP_GKE_SOURCE_HANDOFF_FAILED")
            job.error_message = str(
                source_handoff.get("error_message") or "GCP GKE runtime source handoff failed safely."
            )
            job.logs_summary = "GCP GKE runtime source handoff failed before workload simulation."
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
                    "provider_mode": "gcp_gke_sandbox",
                    "workload_runtime": cfg.provider,
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
            runtime.message = "GCP GKE runtime dry-run completed. No workload preview was started."
            runtime.updated_at = _utc_now_iso()
            runtime = runtime_store.upsert_runtime_session(runtime)
            job.runtime_session_id = runtime.id
            job.status = "succeeded"
            job.phase = "completed"
            job.error_code = None
            job.error_message = None
            job.logs_summary = (
                "gcp_gke_sandbox dry-run plan created. No live Kubernetes workload was executed."
            )
            job.completed_at = _utc_now_iso()
            job.updated_at = job.completed_at
            usage_event = {
                "category": "worker_job",
                "quantity": 1,
                "unit": "count",
                "attribution": {
                    "provider": "builder_cloud_runtime",
                    "worker_provider": "gcp_gke_sandbox",
                    "source_snapshot_id": job.source_snapshot_id,
                    "runtime_session_id": runtime.id,
                },
                "metadata": {
                    "event_name": "gcp_gke_runtime_plan_created",
                    "job_id": job.id,
                    "workload_runtime": cfg.provider,
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
            runtime.message = "GCP GKE runtime source payload is unavailable."
            runtime.updated_at = _utc_now_iso()
            runtime = runtime_store.upsert_runtime_session(runtime)
            job.runtime_session_id = runtime.id
            job.status = "failed"
            job.phase = "failed"
            job.error_code = source_files_error
            job.error_message = "GCP GKE runtime source payload is unavailable."
            job.logs_summary = "GCP GKE runtime source materialization failed before workload simulation."
            job.completed_at = _utc_now_iso()
            job.updated_at = job.completed_at
            return CloudRuntimeExecutionResult(job=job, runtime_session=runtime, usage_event=None)
        bundle_package = None
        bundle_outcome = None
        upload_error_code: str | None = None
        upload_error_message: str | None = None
        try:
            bundle_package = package_source_files_to_zip(
                files=source_files,
                workspace_id=job.workspace_id,
                project_id=job.project_id,
                runtime_job_id=job.id,
            )
            uploader = build_source_bundle_uploader()
            bucket_name = str(os.environ.get("HAM_BUILDER_PREVIEW_SOURCE_BUCKET") or "").strip()
            if not bucket_name:
                raise ValueError("HAM_BUILDER_PREVIEW_SOURCE_BUCKET is missing")
            bundle_outcome = uploader.upload_bundle(
                bucket=bucket_name,
                object_name=bundle_package.object_name,
                payload=bundle_package.payload,
            )
            source_handoff = {
                **source_handoff,
                "artifact_uri": bundle_outcome.uri,
                "source_ref": f"bundle:{bundle_package.sha256[:16]}",
            }
            job.metadata = {
                **(job.metadata or {}),
                "source_bundle": redact_provider_metadata(
                    {
                        "uri": bundle_outcome.uri,
                        "uploaded": bundle_outcome.uploaded,
                        "sha256": bundle_package.sha256,
                        "byte_size": bundle_outcome.byte_size,
                        "file_count": bundle_package.file_count,
                        "object_name": bundle_package.object_name,
                    }
                ),
                "source_handoff": redact_provider_metadata(source_handoff),
            }
        except Exception as exc:  # pragma: no cover - defensive guard
            upload_error_code = "GCP_GKE_SOURCE_BUNDLE_UPLOAD_FAILED"
            upload_error_message = f"GCP GKE source bundle upload failed safely: {type(exc).__name__}."
        if upload_error_code:
            runtime.status = "failed"
            runtime.health = "unhealthy"
            runtime.message = upload_error_message or "GCP GKE source bundle upload failed safely."
            runtime.updated_at = _utc_now_iso()
            runtime = runtime_store.upsert_runtime_session(runtime)
            job.runtime_session_id = runtime.id
            job.status = "failed"
            job.phase = "failed"
            job.error_code = upload_error_code
            job.error_message = upload_error_message
            job.logs_summary = "GCP GKE runtime source bundle upload failed before workload simulation."
            job.completed_at = _utc_now_iso()
            job.updated_at = job.completed_at
            return CloudRuntimeExecutionResult(job=job, runtime_session=runtime, usage_event=None)
        gke_client = build_gke_runtime_client()
        gke_resource = None
        pod_status = None
        pod_logs_summary = None
        service_name: str | None = None
        try:
            lifecycle_stage = "render_manifest"
            manifest = build_gke_preview_pod_manifest(
                workspace_id=job.workspace_id,
                project_id=job.project_id,
                runtime_session_id=runtime.id,
                namespace=f"{str(os.environ.get('HAM_BUILDER_GKE_NAMESPACE_PREFIX') or 'ham-builder-preview').strip()}-spike",
                bundle_gs_uri=str(source_handoff.get("artifact_uri") or ""),
                runner_image=str(os.environ.get("HAM_BUILDER_PREVIEW_RUNNER_IMAGE") or ""),
                preview_port=cfg.default_port,
                ttl_seconds=cfg.ttl_seconds,
            )
            lifecycle_stage = "create_preview_pod"
            gke_resource = gke_client.create_preview_pod(manifest=manifest)
            lifecycle_stage = "wait_for_pod_ready"
            pod_status = gke_client.poll_pod_ready(
                pod_ref=gke_resource,
                timeout_seconds=cfg.start_timeout_seconds,
            )
            lifecycle_stage = "collect_logs"
            pod_logs_summary = gke_client.get_pod_logs_summary(pod_ref=gke_resource, max_chars=240)
            lifecycle_stage = "create_preview_service"
            service_name = gke_client.create_preview_service(pod_ref=gke_resource)
            if gke_resource is not None:
                gke_resource = PreviewPodRef(
                    namespace=gke_resource.namespace,
                    pod_name=gke_resource.pod_name,
                    service_name=service_name,
                    labels=gke_resource.labels,
                )
        except Exception as exc:  # pragma: no cover - defensive guard
            err_code, err_msg = gke_client.normalize_error(error=exc)
            runtime.status = "failed"
            runtime.health = "unhealthy"
            runtime.message = err_msg
            runtime.updated_at = _utc_now_iso()
            _set_runtime_diag(
                job=job,
                runtime=runtime,
                lifecycle_stage=lifecycle_stage,
                error_code=err_code,
                error_message=err_msg,
                exception_class=type(exc).__name__,
                retry_count=0,
                retryable=False,
            )
            runtime = runtime_store.upsert_runtime_session(runtime)
            job.runtime_session_id = runtime.id
            job.status = "failed"
            job.phase = "failed"
            job.error_code = err_code
            job.error_message = err_msg
            job.logs_summary = pod_logs_summary or "GCP GKE runtime client lifecycle failed."
            job.completed_at = _utc_now_iso()
            job.updated_at = job.completed_at
            return CloudRuntimeExecutionResult(job=job, runtime_session=runtime, usage_event=None)
        if pod_status is None or not pod_status.ready:
            runtime.status = "failed"
            runtime.health = "unhealthy"
            runtime.message = (pod_status.error_message if pod_status else "Preview pod did not become ready.")
            runtime.updated_at = _utc_now_iso()
            _set_runtime_diag(
                job=job,
                runtime=runtime,
                lifecycle_stage="wait_for_pod_ready",
                error_code=(pod_status.error_code if pod_status else "GCP_GKE_POD_NOT_READY"),
                error_message=(pod_status.error_message if pod_status else "Preview pod did not become ready."),
                exception_class=None,
                retry_count=0,
                retryable=False,
            )
            runtime = runtime_store.upsert_runtime_session(runtime)
            job.runtime_session_id = runtime.id
            job.status = "failed"
            job.phase = "failed"
            job.error_code = pod_status.error_code if pod_status else "GCP_GKE_POD_NOT_READY"
            job.error_message = pod_status.error_message if pod_status else "Preview pod did not become ready."
            job.logs_summary = pod_logs_summary or "GCP GKE runtime pod was not ready."
            job.completed_at = _utc_now_iso()
            job.updated_at = job.completed_at
            return CloudRuntimeExecutionResult(job=job, runtime_session=runtime, usage_event=None)
        job.metadata = {
            **(job.metadata or {}),
            "runtime_resource": redact_provider_metadata(
                {
                    "namespace": gke_resource.namespace if gke_resource else None,
                    "pod_name": gke_resource.pod_name if gke_resource else None,
                    "service_name": service_name,
                    "pod_phase": pod_status.phase if pod_status else None,
                    "cleanup_status": "pending",
                }
            ),
        }
        if live_mode_requested:
            upstream_url: str | None = None
            if pod_status and pod_status.pod_ip:
                upstream_url = f"http://{pod_status.pod_ip}:{cfg.default_port}/"
            elif gke_resource is not None and service_name:
                upstream_url = f"http://{service_name}.{gke_resource.namespace}.svc.cluster.local/"
            preview_endpoint: PreviewEndpoint | None = None
            if upstream_url:
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
                preview_endpoint.status = "ready"
                preview_endpoint.url = upstream_url
                preview_endpoint.last_checked_at = _utc_now_iso()
                preview_endpoint.metadata = {
                    **(preview_endpoint.metadata or {}),
                    "provider": "gcp_gke_sandbox",
                    "internal_upstream": True,
                    "workload_runtime": cfg.provider,
                    "trusted_proxy_host": None,
                }
                preview_endpoint = runtime_store.upsert_preview_endpoint(preview_endpoint)
                runtime.preview_endpoint_id = preview_endpoint.id
            runtime.status = "running"
            runtime.health = "healthy" if preview_endpoint is not None else "unknown"
            runtime.message = (
                "GCP GKE pod is running and preview proxy endpoint is ready."
                if preview_endpoint is not None
                else "GCP GKE pod is running. Preview proxy endpoint remains pending until a safe upstream link is available."
            )
            runtime.updated_at = _utc_now_iso()
            runtime.metadata = {
                **(runtime.metadata or {}),
                "workload_runtime": cfg.provider,
                "runtime_resource_ref": redact_provider_metadata(
                    {
                        "namespace": gke_resource.namespace if gke_resource else None,
                        "pod_name": gke_resource.pod_name if gke_resource else None,
                        "service_name": service_name,
                    }
                ),
                "health_check": {
                    "stage": "pod_ready",
                    "result": "pass" if (pod_status and pod_status.ready) else "unknown",
                },
            }
            _set_runtime_diag(
                job=job,
                runtime=runtime,
                lifecycle_stage="persist",
                error_code=None,
                error_message=None,
                exception_class=None,
                retry_count=0,
                retryable=False,
            )
            runtime = runtime_store.upsert_runtime_session(runtime)
            job.runtime_session_id = runtime.id
            job.status = "succeeded" if preview_endpoint is not None else "running"
            job.phase = "completed" if preview_endpoint is not None else "preview_pending"
            job.error_code = None
            job.error_message = None
            job.logs_summary = (
                pod_logs_summary
                or (
                    "GCP GKE runtime pod started and preview proxy endpoint linked."
                    if preview_endpoint is not None
                    else "GCP GKE runtime pod started; preview proxy not yet linked."
                )
            )
            job.completed_at = _utc_now_iso() if preview_endpoint is not None else None
            job.updated_at = job.completed_at or _utc_now_iso()
            usage_event = {
                "category": "worker_job",
                "quantity": 1,
                "unit": "count",
                "attribution": {
                    "provider": "builder_cloud_runtime",
                    "worker_provider": "gcp_gke_sandbox",
                    "source_snapshot_id": job.source_snapshot_id,
                    "runtime_session_id": runtime.id,
                },
                "metadata": {
                    "event_name": (
                        "gcp_gke_runtime_preview_proxy_ready"
                        if preview_endpoint is not None
                        else "gcp_gke_runtime_pod_ready_pending_proxy"
                    ),
                    "job_id": job.id,
                    "workload_runtime": cfg.provider,
                    "dry_run": False,
                },
            }
            return CloudRuntimeExecutionResult(job=job, runtime_session=runtime, usage_event=usage_event)
        provider = build_gcp_gke_runtime_provider(config=cfg)
        lifecycle_stage = "create_sandbox"
        exception_class: str | None = None
        retry_count = 0
        retryable = False
        try:
            lifecycle_stage = "create_sandbox"
            state = provider.create_sandbox(state=state, config=cfg)
        except Exception as exc:  # pragma: no cover - defensive adapter guard
            classified = classify_builder_runtime_error(error=exc, lifecycle_stage=lifecycle_stage)
            exception_class = classified.exception_class
            retryable = bool(classified.retryable)
            state = SandboxRuntimeState(
                **{
                    **state.__dict__,
                    "status": "failed",
                    "updated_at": _utc_now_iso(),
                    "error_code": classified.error_code,
                    "error_message": classified.error_message,
                }
            )
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
            runtime.message = state.error_message or "GCP GKE runtime workload simulation failed safely."
            runtime.updated_at = _utc_now_iso()
            runtime.metadata = {
                **(runtime.metadata or {}),
                "workload_runtime": cfg.provider,
                "workload_id": state.sandbox_id,
            }
            _set_runtime_diag(
                job=job,
                runtime=runtime,
                lifecycle_stage=lifecycle_stage,
                error_code=state.error_code or "GCP_GKE_RUNTIME_PROVIDER_ERROR",
                error_message=state.error_message or "GCP GKE runtime workload simulation failed safely.",
                exception_class=exception_class,
                retry_count=retry_count,
                retryable=retryable,
            )
            runtime = runtime_store.upsert_runtime_session(runtime)
            job.runtime_session_id = runtime.id
            job.status = "failed"
            job.phase = "failed"
            job.error_code = state.error_code or "GCP_GKE_RUNTIME_PROVIDER_ERROR"
            job.error_message = state.error_message or "GCP GKE runtime workload simulation failed safely."
            job.logs_summary = provider.get_logs_summary(state=state) or pod_logs_summary or "GCP GKE runtime simulation failed."
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
            runtime.message = "GCP GKE runtime returned an unsafe preview upstream URL."
            runtime.updated_at = _utc_now_iso()
            _set_runtime_diag(
                job=job,
                runtime=runtime,
                lifecycle_stage=lifecycle_stage,
                error_code="GCP_GKE_PREVIEW_URL_UNSAFE",
                error_message="GCP GKE runtime returned an unsafe preview upstream URL.",
                exception_class=exception_class,
                retry_count=retry_count,
                retryable=False,
            )
            runtime = runtime_store.upsert_runtime_session(runtime)
            job.runtime_session_id = runtime.id
            job.status = "failed"
            job.phase = "failed"
            job.error_code = "GCP_GKE_PREVIEW_URL_UNSAFE"
            job.error_message = "GCP GKE runtime returned an unsafe preview upstream URL."
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
            "provider": "gcp_gke_sandbox",
            "workload_runtime": cfg.provider,
            "workload_id": state.sandbox_id,
            "trusted_proxy_host": runtime_preview_host(safe_upstream),
        }
        preview_endpoint = runtime_store.upsert_preview_endpoint(preview_endpoint)
        runtime.preview_endpoint_id = preview_endpoint.id
        runtime.status = "running"
        runtime.health = "healthy"
        runtime.message = "GCP GKE sandbox preview is ready via authenticated HAM proxy."
        runtime.updated_at = _utc_now_iso()
        runtime.metadata = {
            **(runtime.metadata or {}),
            "workload_runtime": cfg.provider,
            "workload_id": state.sandbox_id,
        }
        _set_runtime_diag(
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
        job.logs_summary = provider.get_logs_summary(state=state) or pod_logs_summary
        job.completed_at = _utc_now_iso()
        job.updated_at = job.completed_at
        usage_event = {
            "category": "worker_job",
            "quantity": 1,
            "unit": "count",
            "attribution": {
                "provider": "builder_cloud_runtime",
                "worker_provider": "gcp_gke_sandbox",
                "source_snapshot_id": job.source_snapshot_id,
                "runtime_session_id": runtime.id,
            },
            "metadata": {
                "event_name": "gcp_gke_runtime_preview_ready",
                "job_id": job.id,
                "workload_runtime": cfg.provider,
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
