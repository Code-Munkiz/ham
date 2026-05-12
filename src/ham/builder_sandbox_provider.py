from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from urllib.parse import urlsplit

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


@dataclass
class SandboxRuntimeConfig:
    enabled: bool
    provider: str
    dry_run: bool
    default_port: int
    ttl_seconds: int
    install_timeout_seconds: int
    start_timeout_seconds: int
    fake_mode: Literal["success", "failure"]
    api_key_present: bool


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


class SandboxRuntimeProvider(Protocol):
    def create_sandbox(self, *, state: SandboxRuntimeState, config: SandboxRuntimeConfig) -> SandboxRuntimeState: ...

    def upload_source(
        self,
        *,
        state: SandboxRuntimeState,
        source_ref: str,
        artifact_uri: str,
    ) -> SandboxRuntimeState: ...

    def run_command(self, *, state: SandboxRuntimeState, command: list[str], stage: str) -> SandboxRuntimeState: ...

    def start_preview_server(self, *, state: SandboxRuntimeState, port: int) -> SandboxRuntimeState: ...

    def get_preview_url(self, *, state: SandboxRuntimeState, port: int) -> str | None: ...

    def get_status(self, *, state: SandboxRuntimeState) -> SandboxRuntimeStatus: ...

    def get_logs_summary(self, *, state: SandboxRuntimeState) -> str | None: ...

    def stop_sandbox(self, *, state: SandboxRuntimeState) -> SandboxRuntimeState: ...

    def normalize_error(self, *, error: Exception) -> tuple[str, str]: ...


class FakeSandboxRuntimeProvider:
    def __init__(self, *, provider: str, fake_mode: Literal["success", "failure"]) -> None:
        self._provider = provider
        self._fake_mode = fake_mode

    def create_sandbox(self, *, state: SandboxRuntimeState, config: SandboxRuntimeConfig) -> SandboxRuntimeState:
        sandbox_id = f"sbox_{uuid.uuid4().hex[:16]}"
        expires = datetime.now(UTC) + timedelta(seconds=config.ttl_seconds)
        return SandboxRuntimeState(
            **{**state.__dict__, "sandbox_id": sandbox_id, "status": "creating", "updated_at": _utc_now_iso(), "expires_at": expires.replace(microsecond=0).isoformat().replace("+00:00", "Z")},
        )

    def upload_source(
        self,
        *,
        state: SandboxRuntimeState,
        source_ref: str,
        artifact_uri: str,
    ) -> SandboxRuntimeState:
        _ = source_ref, artifact_uri
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
                    "error_code": "SANDBOX_PREVIEW_START_FAILED",
                    "error_message": "Sandbox failed to start preview server.",
                    "preview_upstream_url": None,
                }
            )
        preview_url = f"https://ham-sandbox-{state.runtime_job_id[-8:]}.run.app/"
        return SandboxRuntimeState(
            **{
                **state.__dict__,
                "status": "ready",
                "updated_at": _utc_now_iso(),
                "preview_upstream_url": preview_url,
                "logs_summary": "Sandbox created. Source uploaded. Install and preview startup simulated.",
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
        return ("SANDBOX_PROVIDER_ERROR", "Sandbox provider operation failed safely.")


def load_sandbox_runtime_config() -> SandboxRuntimeConfig:
    provider = str(os.environ.get("HAM_BUILDER_SANDBOX_PROVIDER") or "").strip().lower() or "e2b"
    fake_mode_raw = str(os.environ.get("HAM_BUILDER_SANDBOX_FAKE_MODE") or "").strip().lower()
    fake_mode: Literal["success", "failure"] = "success" if fake_mode_raw == "success" else "failure"
    return SandboxRuntimeConfig(
        enabled=_bool_env("HAM_BUILDER_SANDBOX_ENABLED", default=False),
        provider=provider,
        dry_run=_bool_env("HAM_BUILDER_SANDBOX_DRY_RUN", default=True),
        default_port=_int_env("HAM_BUILDER_SANDBOX_DEFAULT_PORT", default=3000, min_value=1, max_value=65535),
        ttl_seconds=_int_env("HAM_BUILDER_SANDBOX_TTL_SECONDS", default=3600, min_value=60, max_value=86400),
        install_timeout_seconds=_int_env(
            "HAM_BUILDER_SANDBOX_INSTALL_TIMEOUT_SECONDS",
            default=240,
            min_value=30,
            max_value=3600,
        ),
        start_timeout_seconds=_int_env(
            "HAM_BUILDER_SANDBOX_START_TIMEOUT_SECONDS",
            default=180,
            min_value=30,
            max_value=3600,
        ),
        fake_mode=fake_mode,
        api_key_present=bool(str(os.environ.get("HAM_BUILDER_SANDBOX_API_KEY") or "").strip()),
    )


def sandbox_provider_is_supported(provider: str) -> bool:
    return provider in {"e2b", "daytona"}


def sandbox_preview_host(raw_url: str | None) -> str | None:
    text = str(raw_url or "").strip()
    if not text:
        return None
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    host = (parts.hostname or "").strip().lower()
    if parts.scheme != "https" or not host.endswith(".run.app"):
        return None
    return host
