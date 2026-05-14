from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol, runtime_checkable

SandboxRuntimeStatus = Literal[
    "queued",
    "creating",
    "uploading",
    "installing",
    "starting",
    "ready",
    "failed",
    "stopped",
]


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bool_env(name: str, *, default: bool) -> bool:
    raw = str(os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _int_env(name: str, *, default: int, min_value: int, max_value: int) -> int:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(min_value, min(max_value, value))


def _str_present(name: str) -> bool:
    return bool(str(os.environ.get(name) or "").strip())


@dataclass
class GcpGkeRuntimeConfig:
    """GCP-native builder runtime scaffolding (dry-run / fake only until live GKE lands)."""

    provider: str
    enabled: bool
    dry_run: bool
    fake_mode: Literal["success", "failure"]
    fake_mode_explicit: bool
    default_port: int
    ttl_seconds: int
    install_timeout_seconds: int
    start_timeout_seconds: int
    project_id_present: bool
    region_present: bool
    cluster_present: bool
    namespace_prefix_present: bool
    bucket_present: bool
    runner_image_present: bool


@dataclass
class SandboxSourceFile:
    path: str
    data: bytes


@dataclass
class SandboxRuntimeState:
    provider: str
    sandbox_id: str | None
    workspace_id: str
    project_id: str
    snapshot_id: str | None
    runtime_job_id: str
    status: SandboxRuntimeStatus
    preview_upstream_url: str | None
    preview_proxy_url: str | None
    logs_summary: str | None
    error_code: str | None
    error_message: str | None
    started_at: str | None
    updated_at: str
    expires_at: str | None


@dataclass(frozen=True)
class SandboxErrorClassification:
    error_code: str
    error_message: str
    retryable: bool
    exception_class: str
    lifecycle_stage: str


@runtime_checkable
class SandboxRuntimeProvider(Protocol):
    def create_sandbox(self, *, state: SandboxRuntimeState, config: GcpGkeRuntimeConfig) -> SandboxRuntimeState: ...

    def upload_source(
        self,
        *,
        state: SandboxRuntimeState,
        source_ref: str,
        artifact_uri: str,
        files: list[SandboxSourceFile],
    ) -> SandboxRuntimeState: ...

    def run_command(self, *, state: SandboxRuntimeState, command: list[str], stage: str) -> SandboxRuntimeState: ...

    def start_preview_server(self, *, state: SandboxRuntimeState, port: int) -> SandboxRuntimeState: ...

    def get_preview_url(self, *, state: SandboxRuntimeState, port: int) -> str | None: ...

    def get_status(self, *, state: SandboxRuntimeState) -> SandboxRuntimeStatus: ...

    def get_logs_summary(self, *, state: SandboxRuntimeState) -> str | None: ...

    def stop_sandbox(self, *, state: SandboxRuntimeState) -> SandboxRuntimeState: ...

    def normalize_error(self, *, error: Exception) -> tuple[str, str]: ...


class FakeGcpGkeSandboxRuntimeProvider:
    """Test/explicit fake mode only — simulates workload lifecycle without Kubernetes."""

    def __init__(self, *, fake_mode: Literal["success", "failure"]) -> None:
        self._fake_mode = fake_mode

    def create_sandbox(self, *, state: SandboxRuntimeState, config: GcpGkeRuntimeConfig) -> SandboxRuntimeState:
        sandbox_id = f"gke_fake_{uuid.uuid4().hex[:16]}"
        expires = datetime.now(UTC) + timedelta(seconds=config.ttl_seconds)
        return SandboxRuntimeState(
            **{
                **state.__dict__,
                "sandbox_id": sandbox_id,
                "status": "creating",
                "updated_at": _utc_now_iso(),
                "expires_at": expires.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            }
        )

    def upload_source(
        self,
        *,
        state: SandboxRuntimeState,
        source_ref: str,
        artifact_uri: str,
        files: list[SandboxSourceFile],
    ) -> SandboxRuntimeState:
        _ = source_ref, artifact_uri, files
        return SandboxRuntimeState(**{**state.__dict__, "status": "uploading", "updated_at": _utc_now_iso()})

    def run_command(self, *, state: SandboxRuntimeState, command: list[str], stage: str) -> SandboxRuntimeState:
        _ = command
        next_status: SandboxRuntimeStatus = "installing" if stage == "install" else "starting"
        return SandboxRuntimeState(**{**state.__dict__, "status": next_status, "updated_at": _utc_now_iso()})

    def start_preview_server(self, *, state: SandboxRuntimeState, port: int) -> SandboxRuntimeState:
        _ = port
        if self._fake_mode == "failure":
            return SandboxRuntimeState(
                **{
                    **state.__dict__,
                    "status": "failed",
                    "updated_at": _utc_now_iso(),
                    "error_code": "GCP_GKE_PREVIEW_START_FAILED",
                    "error_message": "Sandbox failed to start preview server.",
                    "preview_upstream_url": None,
                }
            )
        preview_url = f"https://ham-gke-preview-{state.runtime_job_id[-8:]}.run.app/"
        return SandboxRuntimeState(
            **{
                **state.__dict__,
                "status": "ready",
                "updated_at": _utc_now_iso(),
                "preview_upstream_url": preview_url,
                "logs_summary": "Fake GCP GKE sandbox: upload/install/start simulated.",
            }
        )

    def get_preview_url(self, *, state: SandboxRuntimeState, port: int) -> str | None:
        _ = port
        return state.preview_upstream_url

    def get_status(self, *, state: SandboxRuntimeState) -> SandboxRuntimeStatus:
        return state.status

    def get_logs_summary(self, *, state: SandboxRuntimeState) -> str | None:
        return state.logs_summary

    def stop_sandbox(self, *, state: SandboxRuntimeState) -> SandboxRuntimeState:
        return SandboxRuntimeState(**{**state.__dict__, "status": "stopped", "updated_at": _utc_now_iso()})

    def normalize_error(self, *, error: Exception) -> tuple[str, str]:
        _ = error
        return ("GCP_GKE_RUNTIME_PROVIDER_ERROR", "GCP GKE runtime provider operation failed safely.")


def load_gcp_gke_runtime_config() -> GcpGkeRuntimeConfig:
    fake_mode_raw = str(os.environ.get("HAM_BUILDER_GCP_RUNTIME_FAKE_MODE") or "").strip().lower()
    fake_mode: Literal["success", "failure"] = "success" if fake_mode_raw == "success" else "failure"
    return GcpGkeRuntimeConfig(
        provider="gcp_gke_sandbox",
        enabled=_bool_env("HAM_BUILDER_GCP_RUNTIME_ENABLED", default=False),
        dry_run=_bool_env("HAM_BUILDER_GCP_RUNTIME_DRY_RUN", default=True),
        fake_mode=fake_mode,
        fake_mode_explicit=bool(fake_mode_raw),
        default_port=_int_env(
            "HAM_BUILDER_PREVIEW_DEFAULT_PORT",
            default=3000,
            min_value=1,
            max_value=65535,
        ),
        ttl_seconds=_int_env(
            "HAM_BUILDER_PREVIEW_TTL_SECONDS",
            default=3600,
            min_value=60,
            max_value=86400,
        ),
        install_timeout_seconds=_int_env(
            "HAM_BUILDER_GCP_RUNTIME_INSTALL_TIMEOUT_SECONDS",
            default=240,
            min_value=30,
            max_value=3600,
        ),
        start_timeout_seconds=_int_env(
            "HAM_BUILDER_GCP_RUNTIME_START_TIMEOUT_SECONDS",
            default=300,
            min_value=30,
            max_value=3600,
        ),
        project_id_present=_str_present("HAM_BUILDER_GCP_PROJECT_ID"),
        region_present=_str_present("HAM_BUILDER_GCP_REGION"),
        cluster_present=_str_present("HAM_BUILDER_GKE_CLUSTER"),
        namespace_prefix_present=_str_present("HAM_BUILDER_GKE_NAMESPACE_PREFIX"),
        bucket_present=_str_present("HAM_BUILDER_PREVIEW_SOURCE_BUCKET"),
        runner_image_present=_str_present("HAM_BUILDER_PREVIEW_RUNNER_IMAGE"),
    )


def gcp_gke_runtime_config_complete(cfg: GcpGkeRuntimeConfig) -> bool:
    return bool(
        cfg.enabled
        and cfg.project_id_present
        and cfg.region_present
        and cfg.cluster_present
        and cfg.namespace_prefix_present
        and cfg.bucket_present
        and cfg.runner_image_present
    )


def runtime_preview_host(raw_url: str | None) -> str | None:
    text = str(raw_url or "").strip()
    if not text:
        return None
    try:
        from urllib.parse import urlsplit

        parts = urlsplit(text)
    except ValueError:
        return None
    host = (parts.hostname or "").strip().lower()
    if parts.scheme != "https" or not host.endswith(".run.app"):
        return None
    return host


_PROVIDER_FACTORY_OVERRIDE: list[Any | None] = [None]


def build_gcp_gke_runtime_provider(*, config: GcpGkeRuntimeConfig) -> SandboxRuntimeProvider:
    override_factory = _PROVIDER_FACTORY_OVERRIDE[0]
    if callable(override_factory):
        return override_factory(config)
    return FakeGcpGkeSandboxRuntimeProvider(fake_mode=config.fake_mode)


def set_gcp_gke_runtime_provider_factory_for_tests(factory: Any | None) -> None:
    _PROVIDER_FACTORY_OVERRIDE[0] = factory


def classify_builder_runtime_error(*, error: Exception, lifecycle_stage: str) -> SandboxErrorClassification:
    text = str(error or "").strip().lower()
    exc_class = type(error).__name__
    if "timeout" in text:
        return SandboxErrorClassification(
            error_code="GCP_GKE_OPERATION_TIMEOUT",
            error_message="GCP GKE runtime operation timed out.",
            retryable=False,
            exception_class=exc_class,
            lifecycle_stage=lifecycle_stage,
        )
    if "template" in text and ("invalid" in text or "not found" in text):
        return SandboxErrorClassification(
            error_code="GCP_GKE_TEMPLATE_INVALID",
            error_message="GCP GKE runtime template or workload spec is invalid.",
            retryable=False,
            exception_class=exc_class,
            lifecycle_stage=lifecycle_stage,
        )
    if "config" in text and ("missing" in text or "invalid" in text):
        return SandboxErrorClassification(
            error_code="GCP_GKE_CONFIG_MISSING",
            error_message="GCP GKE runtime configuration is invalid or missing.",
            retryable=False,
            exception_class=exc_class,
            lifecycle_stage=lifecycle_stage,
        )
    if "unavailable" in text or "not found" in text:
        return SandboxErrorClassification(
            error_code="GCP_GKE_PROVIDER_UNAVAILABLE",
            error_message="GCP GKE runtime provider is unavailable.",
            retryable=False,
            exception_class=exc_class,
            lifecycle_stage=lifecycle_stage,
        )
    return SandboxErrorClassification(
        error_code="GCP_GKE_RUNTIME_PROVIDER_ERROR",
        error_message="GCP GKE runtime provider operation failed safely.",
        retryable=False,
        exception_class=exc_class,
        lifecycle_stage=lifecycle_stage,
    )


# Back-compat aliases for incremental refactors / external imports.
classify_sandbox_provider_error = classify_builder_runtime_error
build_sandbox_runtime_provider = build_gcp_gke_runtime_provider
load_sandbox_runtime_config = load_gcp_gke_runtime_config
sandbox_preview_host = runtime_preview_host
set_sandbox_runtime_provider_factory_for_tests = set_gcp_gke_runtime_provider_factory_for_tests
