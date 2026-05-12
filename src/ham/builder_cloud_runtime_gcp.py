from __future__ import annotations

import os
import re
from importlib import util
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from src.persistence.builder_runtime_job_store import CloudRuntimeJob

_SENSITIVE_KEY_RE = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|bearer|authorization|credential)",
    re.IGNORECASE,
)

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _bool_env(name: str, *, default: bool) -> bool:
    raw = str(os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    return default


def _safe_text(value: Any, *, limit: int = 180) -> str:
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    return text[:limit]


class CloudRuntimePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    project_id: str
    workspace_id: str
    source_snapshot_id: str | None = None
    runtime_kind: Literal["cloud_run_job", "cloud_run_service", "unsupported"] = "unsupported"
    image_ref: str | None = None
    artifact_uri: str | None = None
    region: str | None = None
    service_name: str | None = None
    job_name: str | None = None
    preview_strategy: Literal["none", "future_proxy"] = "none"
    status: Literal["planned", "unsupported", "invalid_config"] = "unsupported"
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class GcpCloudRuntimeConfig:
    enabled: bool
    dry_run: bool
    gcp_project_present: bool
    gcp_region_present: bool
    service_account_present: bool
    image_present: bool
    network_present: bool
    timeout_seconds: int
    max_seconds: int


@dataclass
class GcpCloudRuntimeResult:
    status: Literal["planned", "accepted", "unsupported", "invalid_config"]
    error_code: str | None
    error_message: str | None
    warnings: list[str]
    plan: CloudRuntimePlan
    provider_job_id: str | None = None
    provider_state: str | None = None


@runtime_checkable
class GcpCloudRuntimeClientProtocol(Protocol):
    def submit_cloud_run_job(
        self,
        *,
        workspace_id: str,
        project_id: str,
        request_id: str,
        region: str,
        image_ref: str,
        service_account_ref: str | None,
        timeout_seconds: int,
        metadata: dict[str, Any],
    ) -> dict[str, Any]: ...


class FakeGcpCloudRuntimeClient:
    def submit_cloud_run_job(
        self,
        *,
        workspace_id: str,
        project_id: str,
        request_id: str,
        region: str,
        image_ref: str,
        service_account_ref: str | None,
        timeout_seconds: int,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        _ = (
            workspace_id,
            project_id,
            region,
            image_ref,
            service_account_ref,
            timeout_seconds,
            metadata,
        )
        return {
            "provider_job_id": f"fake-crj-{request_id[-8:]}",
            "provider_state": "accepted",
        }


class RealGcpCloudRuntimeClient:
    def submit_cloud_run_job(
        self,
        *,
        workspace_id: str,
        project_id: str,
        request_id: str,
        region: str,
        image_ref: str,
        service_account_ref: str | None,
        timeout_seconds: int,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        _ = workspace_id
        _ = project_id
        _ = metadata
        spec = util.find_spec("google.cloud.run_v2")
        if spec is None:
            raise RuntimeError("CLOUD_RUNTIME_GCP_CLIENT_UNAVAILABLE")
        module = __import__("google.cloud.run_v2", fromlist=["JobsClient", "RunJobRequest"])
        jobs_client = module.JobsClient()
        run_request = module.RunJobRequest(
            name=f"projects/{project_id}/locations/{region}/jobs/{request_id}",
        )
        operation = jobs_client.run_job(request=run_request)
        _ = image_ref
        _ = service_account_ref
        _ = timeout_seconds
        operation_name = getattr(operation, "operation", None)
        provider_job_id = getattr(operation_name, "name", None) or f"gcp-operation-{request_id[-8:]}"
        return {
            "provider_job_id": _safe_text(provider_job_id, limit=120),
            "provider_state": "accepted",
        }


_CLIENT_OVERRIDE: list[GcpCloudRuntimeClientProtocol | None] = [None]


def load_gcp_runtime_config() -> GcpCloudRuntimeConfig:
    gcp_project = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT") or "").strip()
    gcp_region = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION") or "").strip()
    service_account = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_SERVICE_ACCOUNT") or "").strip()
    image_ref = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_IMAGE") or "").strip()
    network = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_NETWORK") or "").strip()
    timeout_raw = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_TIMEOUT_SECONDS") or "").strip()
    max_raw = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_MAX_SECONDS") or "").strip()
    timeout_seconds = int(timeout_raw) if timeout_raw.isdigit() else 120
    max_seconds = int(max_raw) if max_raw.isdigit() else 900
    timeout_seconds = max(30, min(timeout_seconds, 1800))
    max_seconds = max(timeout_seconds, min(max_seconds, 3600))
    return GcpCloudRuntimeConfig(
        enabled=_bool_env("HAM_BUILDER_CLOUD_RUNTIME_GCP_ENABLED", default=False),
        dry_run=_bool_env("HAM_BUILDER_CLOUD_RUNTIME_DRY_RUN", default=True),
        gcp_project_present=bool(gcp_project),
        gcp_region_present=bool(gcp_region),
        service_account_present=bool(service_account),
        image_present=bool(image_ref),
        network_present=bool(network),
        timeout_seconds=timeout_seconds,
        max_seconds=max_seconds,
    )


def validate_config(config: GcpCloudRuntimeConfig) -> tuple[Literal["planned", "unsupported", "invalid_config"], str | None, list[str]]:
    warnings: list[str] = []
    if not config.enabled:
        return "unsupported", "CLOUD_RUNTIME_PROVIDER_DISABLED", warnings
    if not config.gcp_project_present or not config.gcp_region_present:
        if not config.gcp_project_present:
            warnings.append("GCP project is not configured.")
        if not config.gcp_region_present:
            warnings.append("GCP region is not configured.")
        return "invalid_config", "CLOUD_RUNTIME_CONFIG_MISSING", warnings
    if config.dry_run:
        warnings.append("Cloud runtime provider is configured for plan-only POC.")
    if not config.image_present:
        warnings.append("Runtime image is not configured; provider defaults apply.")
    if config.network_present:
        warnings.append("Custom network is configured and may limit startup.")
    return "planned", None, warnings


def create_runtime_plan(*, job: CloudRuntimeJob, config: GcpCloudRuntimeConfig, status: Literal["planned", "unsupported", "invalid_config"], warnings: list[str]) -> CloudRuntimePlan:
    runtime_kind: Literal["cloud_run_job", "cloud_run_service", "unsupported"] = "unsupported"
    if status == "planned":
        runtime_kind = "cloud_run_job"
    return CloudRuntimePlan(
        provider="cloud_run_poc",
        project_id=job.project_id,
        workspace_id=job.workspace_id,
        source_snapshot_id=job.source_snapshot_id,
        runtime_kind=runtime_kind,
        image_ref="configured" if config.image_present else "provider-default",
        artifact_uri="builder-artifact://future",
        region="configured" if config.gcp_region_present else None,
        service_name=None,
        job_name=f"ham-builder-{job.workspace_id[:8]}-{job.project_id[:8]}-{job.id[-6:]}",
        preview_strategy="future_proxy",
        status=status,
        warnings=warnings,
        metadata=redact_provider_metadata(
            {
                "gcp_enabled": config.enabled,
                "dry_run": config.dry_run,
                "gcp_project_configured": config.gcp_project_present,
                "gcp_region_configured": config.gcp_region_present,
                "service_account_configured": config.service_account_present,
                "network_configured": config.network_present,
                "provider_mode": "cloud_run_poc",
                "max_seconds": config.max_seconds,
                "timeout_seconds": config.timeout_seconds,
            }
        ),
    )


def normalize_provider_error(error_code: str | None, error_message: str | None) -> tuple[str, str]:
    code = _safe_text(error_code or "CLOUD_RUNTIME_PROVIDER_ERROR", limit=64)
    message = _safe_text(error_message or "Cloud runtime provider request failed.", limit=240)
    return code, message


def redact_provider_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for idx, (key, value) in enumerate(raw.items()):
        if idx >= 20:
            break
        key_text = _safe_text(key, limit=64)
        if not key_text or _SENSITIVE_KEY_RE.search(key_text):
            continue
        if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
            safe[key_text] = value
        else:
            val_text = _safe_text(value, limit=180)
            if _SENSITIVE_KEY_RE.search(val_text):
                continue
            safe[key_text] = val_text
    return safe


def _build_client() -> GcpCloudRuntimeClientProtocol:
    if _CLIENT_OVERRIDE[0] is not None:
        return _CLIENT_OVERRIDE[0]
    return RealGcpCloudRuntimeClient()


def set_gcp_cloud_runtime_client_for_tests(client: GcpCloudRuntimeClientProtocol | None) -> None:
    _CLIENT_OVERRIDE[0] = client


def submit_gcp_cloud_runtime_poc(job: CloudRuntimeJob) -> GcpCloudRuntimeResult:
    config = load_gcp_runtime_config()
    status, error_code, warnings = validate_config(config)
    plan = create_runtime_plan(job=job, config=config, status=status, warnings=warnings)
    if status != "planned":
        msg = "Cloud runtime provider is disabled." if error_code == "CLOUD_RUNTIME_PROVIDER_DISABLED" else "Cloud runtime provider configuration is incomplete."
        code, message = normalize_provider_error(error_code, msg)
        return GcpCloudRuntimeResult(
            status=status,
            error_code=code,
            error_message=message,
            warnings=warnings,
            plan=plan,
        )
    if config.dry_run:
        return GcpCloudRuntimeResult(
            status="planned",
            error_code=None,
            error_message=None,
            warnings=warnings,
            plan=plan,
        )
    client = _build_client()
    project_value = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT") or "").strip()
    region_value = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION") or "").strip()
    image_value = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_IMAGE") or "").strip() or "gcr.io/ham/builder-poc:latest"
    service_account_ref = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_SERVICE_ACCOUNT") or "").strip() or None
    try:
        response = client.submit_cloud_run_job(
            workspace_id=job.workspace_id,
            project_id=project_value,
            request_id=job.id,
            region=region_value,
            image_ref=image_value,
            service_account_ref=service_account_ref,
            timeout_seconds=min(config.timeout_seconds, config.max_seconds),
            metadata=redact_provider_metadata(job.metadata or {}),
        )
    except Exception as exc:
        code, message = normalize_provider_error(
            "CLOUD_RUNTIME_PROVIDER_SUBMIT_FAILED",
            f"Cloud runtime provider submit failed: {exc}",
        )
        plan.status = "unsupported"
        return GcpCloudRuntimeResult(
            status="unsupported",
            error_code=code,
            error_message=message,
            warnings=warnings,
            plan=plan,
        )
    provider_job_id = _safe_text(response.get("provider_job_id") or "", limit=120) or None
    provider_state = _safe_text(response.get("provider_state") or "accepted", limit=40).lower()
    return GcpCloudRuntimeResult(
        status="accepted",
        error_code=None,
        error_message=None,
        warnings=warnings,
        plan=plan,
        provider_job_id=provider_job_id,
        provider_state=provider_state,
    )


def request_runtime(job: CloudRuntimeJob) -> GcpCloudRuntimeResult:
    return submit_gcp_cloud_runtime_poc(job)
