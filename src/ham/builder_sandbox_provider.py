from __future__ import annotations

from importlib import util
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from typing import Any, Literal, Protocol, runtime_checkable
from urllib.parse import urljoin, urlsplit

import httpx

from src.ham.builder_cloud_runtime_gcp import safe_proxy_upstream_from_provider

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
    fake_mode_explicit: bool
    api_key_present: bool


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


@runtime_checkable
class SandboxRuntimeProvider(Protocol):
    def create_sandbox(self, *, state: SandboxRuntimeState, config: SandboxRuntimeConfig) -> SandboxRuntimeState: ...

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
        fake_mode_explicit=bool(fake_mode_raw),
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
    if parts.scheme != "https" or not (host.endswith(".run.app") or host.endswith(".e2b.app")):
        return None
    return host


class E2BSandboxRuntimeProvider:
    """Live E2B provider adapter (gated by runtime worker config)."""

    def __init__(self, *, api_key: str, template_id: str | None = None) -> None:
        self._api_key = api_key
        self._template_id = (template_id or "").strip() or None
        self._sandbox_ref: Any | None = None
        self._sandbox_id: str | None = None
        self._preview_url: str | None = None
        self._last_logs_summary: str | None = None

    def _require_sdk(self) -> Any:
        if util.find_spec("e2b") is None:
            raise RuntimeError("E2B_SDK_UNAVAILABLE")
        module = __import__("e2b", fromlist=["Sandbox"])
        return getattr(module, "Sandbox")

    def _command(self, cmd: str, *, timeout: int) -> tuple[bool, str]:
        if self._sandbox_ref is None:
            raise RuntimeError("E2B_SANDBOX_NOT_INITIALIZED")
        try:
            result = self._sandbox_ref.commands.run(cmd, timeout=max(1, timeout), cwd="/workspace")
            stdout = str(getattr(result, "stdout", "") or "").strip()
            stderr = str(getattr(result, "stderr", "") or "").strip()
            exit_code = int(getattr(result, "exit_code", 0) or 0)
            if exit_code != 0:
                tail = (stderr or stdout or "command failed")[:240]
                return False, tail
            return True, (stdout or "ok")[:240]
        except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            msg = str(exc).strip()
            return False, (msg or "command failed")[:240]

    def create_sandbox(self, *, state: SandboxRuntimeState, config: SandboxRuntimeConfig) -> SandboxRuntimeState:
        Sandbox = self._require_sdk()
        template = self._template_id or str(os.environ.get("HAM_BUILDER_SANDBOX_E2B_TEMPLATE") or "").strip() or None
        previous = os.environ.get("E2B_API_KEY")
        os.environ["E2B_API_KEY"] = self._api_key
        try:
            kwargs: dict[str, Any] = {
                "timeout": int(config.ttl_seconds),
                "secure": False,
                "allow_internet_access": True,
            }
            if template:
                kwargs["template"] = template
            sandbox = Sandbox.create(**kwargs)
        finally:
            if previous is None:
                os.environ.pop("E2B_API_KEY", None)
            else:
                os.environ["E2B_API_KEY"] = previous
        sandbox_id = str(getattr(sandbox, "sandbox_id", "") or "").strip()
        if not sandbox_id:
            raise RuntimeError("E2B_SANDBOX_ID_MISSING")
        self._sandbox_ref = sandbox
        self._sandbox_id = sandbox_id
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
        _ = source_ref, artifact_uri
        if self._sandbox_ref is None:
            raise RuntimeError("E2B_SANDBOX_NOT_INITIALIZED")
        if not files:
            raise RuntimeError("SANDBOX_SOURCE_FILES_MISSING")
        written = 0
        for entry in files:
            norm = str(PurePosixPath("/workspace") / entry.path.lstrip("/"))
            self._sandbox_ref.files.write(norm, entry.data)
            written += 1
        self._last_logs_summary = f"Uploaded {written} files to sandbox workspace."
        return SandboxRuntimeState(**{**state.__dict__, "status": "uploading", "updated_at": _utc_now_iso()})

    def run_command(self, *, state: SandboxRuntimeState, command: list[str], stage: str) -> SandboxRuntimeState:
        if stage != "install":
            return SandboxRuntimeState(
                **{
                    **state.__dict__,
                    "status": "starting",
                    "updated_at": _utc_now_iso(),
                    "logs_summary": "Start command queued for sandbox preview bootstrap.",
                }
            )
        cmd = " ".join(command).strip()
        timeout_raw = (
            os.environ.get("HAM_BUILDER_SANDBOX_INSTALL_TIMEOUT_SECONDS")
            if stage == "install"
            else os.environ.get("HAM_BUILDER_SANDBOX_START_TIMEOUT_SECONDS")
        )
        timeout = int(str(timeout_raw or "120"))
        ok, summary = self._command(cmd, timeout=timeout)
        if not ok:
            code = "SANDBOX_INSTALL_FAILED" if stage == "install" else "SANDBOX_START_FAILED"
            return SandboxRuntimeState(
                **{
                    **state.__dict__,
                    "status": "failed",
                    "updated_at": _utc_now_iso(),
                    "error_code": code,
                    "error_message": summary,
                    "logs_summary": summary,
                }
            )
        next_status: SandboxRuntimeStatus = "installing" if stage == "install" else "starting"
        self._last_logs_summary = summary
        return SandboxRuntimeState(
            **{
                **state.__dict__,
                "status": next_status,
                "updated_at": _utc_now_iso(),
                "logs_summary": summary,
            }
        )

    def start_preview_server(self, *, state: SandboxRuntimeState, port: int) -> SandboxRuntimeState:
        if self._sandbox_ref is None or not self._sandbox_id:
            raise RuntimeError("E2B_SANDBOX_NOT_INITIALIZED")
        timeout_seconds = max(5, int(os.environ.get("HAM_BUILDER_SANDBOX_START_TIMEOUT_SECONDS") or "120"))
        start_commands = [
            f"npm run dev -- --host 0.0.0.0 --port {int(port)}",
            f"npm run preview -- --host 0.0.0.0 --port {int(port)}",
        ]
        start_error = "Sandbox failed to start preview server."
        started = False
        for cmd in start_commands:
            try:
                self._sandbox_ref.commands.run(
                    cmd,
                    background=True,
                    cwd="/workspace",
                    timeout=timeout_seconds,
                )
                started = True
                break
            except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                start_error = str(exc)[:240] or start_error
        if not started:
            return SandboxRuntimeState(
                **{
                    **state.__dict__,
                    "status": "failed",
                    "updated_at": _utc_now_iso(),
                    "error_code": "SANDBOX_PREVIEW_START_FAILED",
                    "error_message": start_error,
                    "preview_upstream_url": None,
                }
            )
        preview_url = f"https://{int(port)}-{self._sandbox_id}.e2b.app/"
        safe_preview_url = safe_proxy_upstream_from_provider(preview_url)
        if not safe_preview_url:
            return SandboxRuntimeState(
                **{
                    **state.__dict__,
                    "status": "failed",
                    "updated_at": _utc_now_iso(),
                    "error_code": "SANDBOX_PREVIEW_URL_UNSAFE",
                    "error_message": "Sandbox provider returned an unsafe preview upstream URL.",
                    "preview_upstream_url": None,
                }
            )
        deadline = time.time() + timeout_seconds
        healthy = False
        unsafe_redirect = False
        while time.time() < deadline:
            try:
                res = httpx.get(safe_preview_url, timeout=2.5, follow_redirects=False)
                if 200 <= res.status_code < 300:
                    healthy = True
                    break
                if 300 <= res.status_code < 400:
                    redirect_raw = str(res.headers.get("location") or "").strip()
                    if not redirect_raw:
                        continue
                    redirect_url = urljoin(safe_preview_url, redirect_raw)
                    safe_redirect = safe_proxy_upstream_from_provider(redirect_url)
                    if not safe_redirect:
                        unsafe_redirect = True
                        break
                    redirected = httpx.get(safe_redirect, timeout=2.5, follow_redirects=False)
                    if 200 <= redirected.status_code < 300:
                        safe_preview_url = safe_redirect
                        healthy = True
                        break
            except httpx.HTTPError:
                pass
            time.sleep(1.5)
        if unsafe_redirect:
            return SandboxRuntimeState(
                **{
                    **state.__dict__,
                    "status": "failed",
                    "updated_at": _utc_now_iso(),
                    "error_code": "SANDBOX_PREVIEW_UNSAFE_REDIRECT",
                    "error_message": "Sandbox preview returned an unsafe redirect target.",
                    "preview_upstream_url": None,
                }
            )
        if not healthy:
            return SandboxRuntimeState(
                **{
                    **state.__dict__,
                    "status": "failed",
                    "updated_at": _utc_now_iso(),
                    "error_code": "SANDBOX_PREVIEW_HEALTHCHECK_FAILED",
                    "error_message": "Sandbox preview did not become reachable before timeout.",
                    "preview_upstream_url": None,
                }
            )
        self._preview_url = safe_preview_url
        self._last_logs_summary = "Sandbox preview server started and health-validated."
        return SandboxRuntimeState(
            **{
                **state.__dict__,
                "status": "ready",
                "updated_at": _utc_now_iso(),
                "preview_upstream_url": safe_preview_url,
                "logs_summary": self._last_logs_summary,
            }
        )

    def get_preview_url(self, *, state: SandboxRuntimeState, port: int) -> str | None:
        _ = state, port
        return self._preview_url

    def get_status(self, *, state: SandboxRuntimeState) -> SandboxRuntimeStatus:
        return state.status

    def get_logs_summary(self, *, state: SandboxRuntimeState) -> str | None:
        return state.logs_summary or self._last_logs_summary

    def stop_sandbox(self, *, state: SandboxRuntimeState) -> SandboxRuntimeState:
        if self._sandbox_ref is not None:
            try:
                self._sandbox_ref.kill()
            except Exception:  # pragma: no cover - best effort cleanup  # pylint: disable=broad-exception-caught
                pass
        return SandboxRuntimeState(**{**state.__dict__, "status": "stopped", "updated_at": _utc_now_iso()})

    def normalize_error(self, *, error: Exception) -> tuple[str, str]:
        text = str(error or "").strip().lower()
        if "timeout" in text:
            return ("SANDBOX_OPERATION_TIMEOUT", "Sandbox operation timed out.")
        if "api" in text and "key" in text:
            return ("SANDBOX_PROVIDER_AUTH_FAILED", "Sandbox provider authentication failed.")
        if "unavailable" in text or "not found" in text:
            return ("SANDBOX_PROVIDER_UNAVAILABLE", "Sandbox provider is unavailable.")
        return ("SANDBOX_PROVIDER_ERROR", "Sandbox provider operation failed safely.")


_PROVIDER_FACTORY_OVERRIDE: list[Any | None] = [None]


def build_sandbox_runtime_provider(*, config: SandboxRuntimeConfig) -> SandboxRuntimeProvider:
    override_factory = _PROVIDER_FACTORY_OVERRIDE[0]
    if callable(override_factory):
        return override_factory(config)
    if config.dry_run or config.fake_mode_explicit:
        return FakeSandboxRuntimeProvider(provider=config.provider, fake_mode=config.fake_mode)
    if config.provider == "e2b":
        api_key = str(os.environ.get("HAM_BUILDER_SANDBOX_API_KEY") or "").strip()
        template = str(os.environ.get("HAM_BUILDER_SANDBOX_E2B_TEMPLATE") or "").strip() or None
        return E2BSandboxRuntimeProvider(api_key=api_key, template_id=template)
    return FakeSandboxRuntimeProvider(provider=config.provider, fake_mode=config.fake_mode)


def set_sandbox_runtime_provider_factory_for_tests(factory: Any | None) -> None:
    _PROVIDER_FACTORY_OVERRIDE[0] = factory
