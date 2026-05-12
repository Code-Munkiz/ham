from __future__ import annotations

import os
import re
from importlib import util
from dataclasses import dataclass
from typing import Any, Literal

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


@dataclass
class GcpCloudRuntimeResult:
    status: Literal["planned", "unsupported", "invalid_config"]
    error_code: str | None
    error_message: str | None
    warnings: list[str]
    plan: CloudRuntimePlan


def load_gcp_runtime_config() -> GcpCloudRuntimeConfig:
    gcp_project = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT") or "").strip()
    gcp_region = str(os.environ.get("HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION") or "").strip()
    return GcpCloudRuntimeConfig(
        enabled=_bool_env("HAM_BUILDER_CLOUD_RUNTIME_GCP_ENABLED", default=False),
        dry_run=_bool_env("HAM_BUILDER_CLOUD_RUNTIME_DRY_RUN", default=True),
        gcp_project_present=bool(gcp_project),
        gcp_region_present=bool(gcp_region),
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
        image_ref="gcp-poc-builder-image:future",
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
                "provider_mode": "cloud_run_poc",
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


def request_runtime(job: CloudRuntimeJob) -> GcpCloudRuntimeResult:
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
    if util.find_spec("google.cloud.run_v2") is None:
        code, message = normalize_provider_error(
            "CLOUD_RUNTIME_GCP_CLIENT_UNAVAILABLE",
            "GCP Cloud Run client libraries are unavailable for non-dry-run mode.",
        )
        plan.status = "unsupported"
        return GcpCloudRuntimeResult(
            status="unsupported",
            error_code=code,
            error_message=message,
            warnings=warnings,
            plan=plan,
        )
    code, message = normalize_provider_error(
        "CLOUD_RUNTIME_NOT_IMPLEMENTED",
        "GCP provisioning is not implemented in this POC.",
    )
    plan.status = "unsupported"
    return GcpCloudRuntimeResult(
        status="unsupported",
        error_code=code,
        error_message=message,
        warnings=warnings,
        plan=plan,
    )
