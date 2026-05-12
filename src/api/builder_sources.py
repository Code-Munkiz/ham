from __future__ import annotations

import os
import re
import shlex
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.dependencies.workspace import require_perm
from src.ham.builder_zip_intake import ZipSafetyError, validate_zip_upload
from src.ham.clerk_auth import HamActor
from src.ham.harness_capabilities import HARNESS_CAPABILITIES
from src.ham.worker_adapters.claude_agent_adapter import check_claude_agent_readiness
from src.ham.worker_adapters.cursor_adapter import check_cursor_readiness
from src.ham.workspace_models import WorkspaceContext
from src.ham.workspace_perms import PERM_WORKSPACE_READ, PERM_WORKSPACE_WRITE
from src.persistence.builder_source_store import (
    ProjectSource,
    SourceSnapshot,
    get_builder_source_store,
)
from src.persistence.builder_runtime_store import PreviewEndpoint, get_builder_runtime_store
from src.persistence.builder_run_profile_store import LocalRunProfile, get_builder_run_profile_store
from src.persistence.builder_visual_edit_request_store import (
    VisualEditRequest,
    get_builder_visual_edit_request_store,
)
from src.persistence.builder_usage_event_store import get_builder_usage_event_store
from src.persistence.project_store import get_project_store
from src.registry.projects import ProjectRecord

router = APIRouter(tags=["builder-sources"])

_ZIP_ERROR_MESSAGES = {
    "ZIP_TOO_LARGE": "ZIP exceeds the maximum compressed size.",
    "ZIP_TOO_MANY_FILES": "ZIP has too many files.",
    "ZIP_UNCOMPRESSED_TOO_LARGE": "ZIP exceeds the maximum expanded size.",
    "ZIP_ENTRY_TOO_LARGE": "ZIP contains a file that exceeds size limits.",
    "ZIP_PATH_TRAVERSAL": "ZIP contains unsafe path traversal entries.",
    "ZIP_ABSOLUTE_PATH": "ZIP contains absolute path entries.",
    "ZIP_UNSAFE_SYMLINK": "ZIP contains unsafe symbolic link entries.",
    "ZIP_INVALID": "ZIP archive is invalid or unsafe.",
    "ZIP_EMPTY": "ZIP archive is empty.",
}


def _project_workspace_id(record: ProjectRecord) -> str | None:
    raw = record.metadata.get("workspace_id")
    if raw is None:
        raw = record.metadata.get("workspaceId")
    text = str(raw or "").strip()
    return text or None


def _project_in_workspace_or_404(*, project_id: str, workspace_id: str) -> ProjectRecord:
    record = get_project_store().get_project(project_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PROJECT_NOT_FOUND",
                    "message": f"Unknown project_id {project_id!r}.",
                }
            },
        )
    project_workspace_id = _project_workspace_id(record)
    if project_workspace_id != workspace_id:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PROJECT_NOT_FOUND",
                    "message": f"Unknown project_id {project_id!r}.",
                }
            },
        )
    return record


def _artifact_root() -> Path:
    raw = (os.environ.get("HAM_BUILDER_SOURCE_ARTIFACT_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".ham" / "builder-source-artifacts").resolve()


def _save_zip_artifact(*, workspace_id: str, project_id: str, payload: bytes) -> tuple[str, dict[str, Any]]:
    artifact_id = f"bzip_{uuid.uuid4().hex}"
    root = _artifact_root()
    target_dir = root / workspace_id / project_id
    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / f"{artifact_id}.zip"
    zip_path.write_bytes(payload)
    return (
        f"builder-artifact://{artifact_id}",
        {
            "artifact_id": artifact_id,
            "artifact_name": zip_path.name,
        },
    )


def _safe_zip_error_message(code: str) -> str:
    return _ZIP_ERROR_MESSAGES.get(code, "ZIP import failed.")


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sanitize_local_preview_url(raw_url: str | None) -> str | None:
    text = str(raw_url or "").strip()
    if not text:
        return None
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    if parts.username or parts.password:
        return None
    if parts.scheme != "http":
        return None
    host = (parts.hostname or "").strip().lower()
    if host not in {"localhost", "127.0.0.1", "::1"}:
        return None
    if parts.port is None:
        return None
    netloc_host = f"[{host}]" if ":" in host else host
    return urlunsplit((parts.scheme, f"{netloc_host}:{parts.port}", parts.path or "/", "", ""))


def _derive_preview_status(
    *,
    runtime_status: str | None,
    runtime_health: str | None,
    endpoint_status: str | None,
    safe_preview_url: str | None,
) -> tuple[str, str]:
    rs = str(runtime_status or "").strip().lower()
    rh = str(runtime_health or "").strip().lower()
    es = str(endpoint_status or "").strip().lower()
    if not rs:
        return ("not_connected", "Local preview runtime is not connected.")
    if rs in {"stopped", "expired"}:
        return ("not_connected", "Local preview runtime is not connected.")
    if rs == "failed":
        return ("error", "Local preview runtime is not available.")
    if rh == "unhealthy":
        return ("error", "Local preview runtime is unhealthy.")
    if rs == "starting":
        return ("building", "Local preview runtime is starting.")
    if rs == "waiting":
        return ("waiting", "Local preview runtime is waiting for work.")
    if rs == "not_connected":
        return ("not_connected", "Local preview runtime is not connected.")
    if rs == "running" and es == "ready" and safe_preview_url:
        return ("ready", "Preview is ready.")
    if rs == "running" and es in {"provisioning", ""}:
        return ("building", "Local preview endpoint is provisioning.")
    if rs == "running" and es in {"unavailable", "revoked"}:
        return ("error", "Local preview endpoint is unavailable.")
    if rs == "running" and es == "ready" and not safe_preview_url:
        return ("error", "Preview URL is unavailable due to safety policy.")
    return ("waiting", "Local preview status is waiting for endpoint readiness.")


def _build_preview_status_payload(*, workspace_id: str, project_id: str) -> dict[str, Any]:
    source_rows = get_builder_source_store().list_project_sources(
        workspace_id=workspace_id,
        project_id=project_id,
    )
    active_snapshot_id = next((row.active_snapshot_id for row in source_rows if row.active_snapshot_id), None)
    runtime_store = get_builder_runtime_store()
    runtime = runtime_store.get_active_runtime_session(
        workspace_id=workspace_id,
        project_id=project_id,
    )
    endpoint = None
    if runtime is not None:
        endpoint = runtime_store.get_active_preview_endpoint(
            workspace_id=workspace_id,
            project_id=project_id,
            runtime_session_id=runtime.id,
        )
    safe_preview_url = _sanitize_local_preview_url(endpoint.url if endpoint is not None else None)
    status, message = _derive_preview_status(
        runtime_status=runtime.status if runtime is not None else None,
        runtime_health=runtime.health if runtime is not None else None,
        endpoint_status=endpoint.status if endpoint is not None else None,
        safe_preview_url=safe_preview_url,
    )
    return {
        "project_id": project_id,
        "workspace_id": workspace_id,
        "mode": "local",
        "status": status,
        "health": runtime.health if runtime is not None else "unknown",
        "preview_url": safe_preview_url if status == "ready" else None,
        "message": message,
        "updated_at": runtime.updated_at if runtime is not None else _utc_now_iso(),
        "source_snapshot_id": runtime.snapshot_id if runtime and runtime.snapshot_id else active_snapshot_id,
        "runtime_session_id": runtime.id if runtime is not None else None,
        "preview_endpoint_id": endpoint.id if endpoint is not None else None,
        "logs_hint": None,
    }


def _validated_snapshot_id(*, workspace_id: str, project_id: str, source_snapshot_id: str | None) -> str | None:
    if source_snapshot_id is None:
        return None
    snapshot_rows = get_builder_source_store().list_source_snapshots(
        workspace_id=workspace_id,
        project_id=project_id,
    )
    known_snapshot_ids = {row.id for row in snapshot_rows}
    if source_snapshot_id not in known_snapshot_ids:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SOURCE_SNAPSHOT_NOT_FOUND",
                    "message": f"Unknown source_snapshot_id {source_snapshot_id!r} for this project.",
                }
            },
        )
    return source_snapshot_id


def _serialize_local_run_profile(profile: LocalRunProfile | None, *, workspace_id: str, project_id: str) -> dict[str, Any]:
    configured = bool(profile and profile.status in {"configured", "draft"})
    return {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "configured": configured,
        "status": profile.status if profile is not None else "not_configured",
        "profile": profile.model_dump(mode="json") if profile is not None else None,
    }


_CLOUD_RUNTIME_STATES = {"queued", "provisioning", "running", "failed", "expired", "unsupported"}


def _serialize_cloud_runtime(
    runtime: Any | None,
    *,
    workspace_id: str,
    project_id: str,
) -> dict[str, Any]:
    if runtime is None:
        return {
            "workspace_id": workspace_id,
            "project_id": project_id,
            "mode": "cloud",
            "status": "unsupported",
            "message": "Cloud runtime is not provisioned yet. Request tracking only is available.",
            "updated_at": _utc_now_iso(),
            "runtime_session_id": None,
            "source_snapshot_id": None,
            "metadata": {},
        }
    status = str(runtime.status or "").strip().lower()
    if status not in _CLOUD_RUNTIME_STATES:
        status = "unsupported"
    message = _safe_text(
        runtime.message,
        fallback="Cloud runtime request tracked. Provisioning/execution is coming soon.",
    )
    return {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "mode": "cloud",
        "status": status,
        "message": message,
        "updated_at": runtime.updated_at or _utc_now_iso(),
        "runtime_session_id": runtime.id,
        "source_snapshot_id": runtime.snapshot_id,
        "metadata": runtime.metadata or {},
    }


class LocalPreviewRegisterRequest(BaseModel):
    preview_url: str
    source_snapshot_id: str | None = None
    display_name: str | None = None


class LocalRunProfilePayload(BaseModel):
    source_snapshot_id: str | None = None
    display_name: str = "Local run profile"
    working_directory: str = "."
    install_command: str | None = None
    dev_command: str
    build_command: str | None = None
    test_command: str | None = None
    expected_preview_url: str | None = None
    status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VisualEditRequestPayload(BaseModel):
    source_snapshot_id: str | None = None
    runtime_session_id: str | None = None
    preview_endpoint_id: str | None = None
    route: str | None = None
    selector_hints: list[str] = Field(default_factory=list)
    bbox: dict[str, Any] | None = None
    instruction: str
    status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CloudRuntimeRequestPayload(BaseModel):
    source_snapshot_id: str | None = None
    status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BuilderActivityItem(BaseModel):
    id: str
    kind: str
    status: str
    title: str
    message: str
    timestamp: str
    source_id: str | None = None
    snapshot_id: str | None = None
    import_job_id: str | None = None
    runtime_session_id: str | None = None
    preview_endpoint_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


BuilderWorkerStatus = Literal["available", "needs_connection", "unavailable", "disabled", "unknown"]


class BuilderWorkerCapabilityEntry(BaseModel):
    worker_kind: str
    provider: str
    display_name: str
    status: BuilderWorkerStatus
    capabilities: list[str] = Field(default_factory=list)
    environment_fit: str
    required_setup: str
    settings_href: str | None = None
    last_checked_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _to_worker_status(raw: str | None) -> BuilderWorkerStatus:
    value = str(raw or "").strip().lower()
    if value in {"available", "needs_connection", "unavailable", "disabled", "unknown"}:
        return cast(BuilderWorkerStatus, value)
    return "unknown"


def _cursor_cloud_agent_entry() -> BuilderWorkerCapabilityEntry:
    now = _utc_now_iso()
    readiness = check_cursor_readiness()
    status: BuilderWorkerStatus = "needs_connection"
    if readiness.status == "ready":
        status = "available"
    elif readiness.status == "unavailable":
        status = "unavailable"
    row = HARNESS_CAPABILITIES.get("cursor_cloud_agent")
    metadata: dict[str, Any] = {
        "source": "cursor_readiness",
        "harness_provider": "cursor_cloud_agent",
        "readiness_status": readiness.status,
    }
    if row is not None:
        metadata["registry_status"] = row.registry_status
        metadata["supports_operator_launch"] = bool(row.supports_operator_launch)
    return BuilderWorkerCapabilityEntry(
        worker_kind="cursor_cloud_agent",
        provider="cursor_cloud_agent",
        display_name="Cursor Cloud Agent",
        status=status,
        capabilities=["plan", "edit_code", "run_tests", "open_pr"],
        environment_fit="Hosted/cloud coding runs against remote repositories.",
        required_setup="Add a Cursor API key in Connected Tools to enable cloud agent runs.",
        settings_href="/workspace/settings?section=integrations",
        last_checked_at=now,
        metadata=metadata,
    )


def _cursor_local_sdk_entry() -> BuilderWorkerCapabilityEntry:
    now = _utc_now_iso()
    profile = os.environ.get("HAM_CURSOR_SDK_BRIDGE_ENABLED", "").strip().lower()
    enabled = profile in {"1", "true", "yes", "on"}
    status: BuilderWorkerStatus = "disabled" if not enabled else "unknown"
    return BuilderWorkerCapabilityEntry(
        worker_kind="cursor_local_sdk",
        provider="cursor_sdk_bridge",
        display_name="Cursor Local SDK Bridge",
        status=status,
        capabilities=["status_stream", "event_projection"],
        environment_fit="Optional local/bridge telemetry path for Cursor-native status streams.",
        required_setup="Enable HAM_CURSOR_SDK_BRIDGE_ENABLED and configure provider credentials.",
        settings_href="/workspace/settings?section=integrations",
        last_checked_at=now,
        metadata={
            "source": "env_flag",
            "bridge_enabled": enabled,
        },
    )


def _claude_agent_entry(actor: HamActor | None) -> BuilderWorkerCapabilityEntry:
    now = _utc_now_iso()
    readiness = check_claude_agent_readiness(actor)
    status: BuilderWorkerStatus = "unknown"
    if readiness.status == "ready":
        status = "available"
    elif readiness.status == "needs_sign_in":
        status = "needs_connection"
    elif readiness.status == "unavailable":
        status = "unavailable"
    return BuilderWorkerCapabilityEntry(
        worker_kind="claude_agent",
        provider="claude_agent_sdk",
        display_name="Claude Agent",
        status=status,
        capabilities=["plan", "edit_code", "run_tests"],
        environment_fit="Server-side Claude Agent SDK with BYOK auth channels.",
        required_setup="Install claude-agent-sdk on host and connect Anthropic/Bedrock/Vertex auth.",
        settings_href="/workspace/settings?section=integrations",
        last_checked_at=now,
        metadata={
            "source": "claude_agent_readiness",
            "sdk_available": bool(readiness.sdk_available),
            "sdk_version": readiness.sdk_version,
            "readiness_status": readiness.status,
        },
    )


def _factory_droid_entry() -> BuilderWorkerCapabilityEntry:
    now = _utc_now_iso()
    token_present = bool((os.environ.get("HAM_DROID_EXEC_TOKEN") or "").strip())
    row = HARNESS_CAPABILITIES.get("factory_droid")
    return BuilderWorkerCapabilityEntry(
        worker_kind="factory_droid",
        provider="factory_droid",
        display_name="Factory Droid",
        status="available" if token_present else "unknown",
        capabilities=["edit_code", "run_tests"],
        environment_fit="Local bounded workflow execution on registered project roots.",
        required_setup="Configure HAM_DROID_EXEC_TOKEN and keep allowlisted droid workflows enabled.",
        settings_href="/workspace/settings?section=integrations",
        last_checked_at=now,
        metadata={
            "source": "env_and_registry",
            "token_configured": token_present,
            "registry_status": row.registry_status if row is not None else "unknown",
        },
    )


def _local_runtime_entry(*, workspace_id: str, project_id: str) -> BuilderWorkerCapabilityEntry:
    now = _utc_now_iso()
    preview = _build_preview_status_payload(workspace_id=workspace_id, project_id=project_id)
    profile = get_builder_run_profile_store().get_active_local_run_profile(
        workspace_id=workspace_id,
        project_id=project_id,
    )
    preview_status = str(preview.get("status") or "").strip().lower()
    status: BuilderWorkerStatus = "needs_connection"
    if preview_status == "ready":
        status = "available"
    elif preview_status == "error":
        status = "unavailable"
    elif profile is not None and profile.status == "disabled":
        status = "disabled"
    elif profile is None and preview_status == "not_connected":
        status = "needs_connection"
    return BuilderWorkerCapabilityEntry(
        worker_kind="local_runtime",
        provider="builder_local_runtime",
        display_name="Local Runtime",
        status=_to_worker_status(status),
        capabilities=["local_preview_registration", "local_run_profile"],
        environment_fit="Operator-run local dev server + loopback preview URL registration.",
        required_setup="Save a local run profile and connect a safe localhost preview URL.",
        settings_href=None,
        last_checked_at=now,
        metadata={
            "source": "builder_preview_and_run_profile",
            "preview_status": preview_status or "unknown",
            "run_profile_status": profile.status if profile is not None else "not_configured",
            "runtime_session_id": preview.get("runtime_session_id"),
            "preview_endpoint_id": preview.get("preview_endpoint_id"),
        },
    )


def _hermes_planner_entry() -> BuilderWorkerCapabilityEntry:
    return BuilderWorkerCapabilityEntry(
        worker_kind="hermes_planner",
        provider="hermes_supervisor",
        display_name="Hermes Planner",
        status="available",
        capabilities=["plan", "critique", "route"],
        environment_fit="Built-in HAM supervisory planning and critique loops.",
        required_setup="No additional setup for read-only planner visibility.",
        settings_href="/workspace/settings?section=agents",
        last_checked_at=_utc_now_iso(),
        metadata={
            "source": "static_control_plane",
        },
    )


def _build_worker_capabilities(*, workspace_id: str, project_id: str, actor: HamActor | None) -> list[BuilderWorkerCapabilityEntry]:
    return [
        _cursor_cloud_agent_entry(),
        _cursor_local_sdk_entry(),
        _claude_agent_entry(actor),
        _factory_droid_entry(),
        _local_runtime_entry(workspace_id=workspace_id, project_id=project_id),
        _hermes_planner_entry(),
    ]


_SENSITIVE_VALUE_RE = re.compile(r"(token|secret|password|passwd|api[_-]?key|bearer|authorization)", re.IGNORECASE)


def _safe_text(value: str | None, *, fallback: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return fallback
    text = " ".join(raw.replace("\r", " ").replace("\n", " ").split())
    if _SENSITIVE_VALUE_RE.search(text):
        return fallback
    return text[:240]


def _safe_stats(stats: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for key in ("file_count", "dir_count", "compressed_bytes", "uncompressed_bytes"):
        value = stats.get(key)
        if isinstance(value, int):
            out[key] = max(0, value)
    return out


_COMMAND_META_RE = re.compile(r"(;|&&|\|\||\||>|<|`|\$\(|\r|\n)")
_DISALLOWED_COMMANDS = {"rm", "del", "format", "shutdown", "powershell", "pwsh"}
_WORKDIR_DRIVE_RE = re.compile(r"^[a-zA-Z]:")
_VISUAL_EDIT_ALLOWED_STATUS = {"draft", "queued", "processing", "resolved", "failed", "cancelled"}


def _normalize_working_directory(raw: str | None) -> str:
    text = str(raw or "").strip().replace("\\", "/")
    if not text:
        return "."
    if len(text) > 180:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_WORKDIR_INVALID", "message": "Working directory is too long."}},
        )
    if text.startswith("/") or text.startswith("\\") or text.startswith("//") or _WORKDIR_DRIVE_RE.match(text):
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_WORKDIR_INVALID", "message": "Working directory must be project-relative."}},
        )
    parts = [seg for seg in text.split("/") if seg not in {"", "."}]
    if any(seg == ".." for seg in parts):
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_WORKDIR_INVALID", "message": "Path traversal is not allowed in working_directory."}},
        )
    normalized = "/".join(parts)
    return normalized or "."


def _parse_command_argv(raw: str | None, *, field_name: str, required: bool = False) -> list[str] | None:
    text = str(raw or "").strip()
    if not text:
        if required:
            raise HTTPException(
                status_code=422,
                detail={"error": {"code": "LOCAL_RUN_COMMAND_INVALID", "message": f"{field_name} is required."}},
            )
        return None
    if len(text) > 240:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_COMMAND_INVALID", "message": f"{field_name} is too long."}},
        )
    if _COMMAND_META_RE.search(text):
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_COMMAND_INVALID", "message": f"{field_name} contains unsupported shell metacharacters."}},
        )
    try:
        argv = shlex.split(text, posix=True)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_COMMAND_INVALID", "message": f"{field_name} could not be parsed."}},
        ) from exc
    if not argv:
        if required:
            raise HTTPException(
                status_code=422,
                detail={"error": {"code": "LOCAL_RUN_COMMAND_INVALID", "message": f"{field_name} is required."}},
            )
        return None
    if len(argv) > 24 or any((not arg) or len(arg) > 120 for arg in argv):
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_COMMAND_INVALID", "message": f"{field_name} exceeds argument safety limits."}},
        )
    command_name = argv[0].split("/")[-1].split("\\")[-1].lower()
    if command_name in _DISALLOWED_COMMANDS:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_COMMAND_INVALID", "message": f"{field_name} command is not allowed for local run profile."}},
        )
    if command_name in {"curl", "wget"} and any("|" in arg for arg in argv[1:]):
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_COMMAND_INVALID", "message": f"{field_name} contains an unsafe download pattern."}},
        )
    return argv


def _sanitize_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for idx, (key, value) in enumerate(raw.items()):
        if idx >= 20:
            break
        key_text = str(key).strip()[:64]
        if not key_text:
            continue
        if _SENSITIVE_VALUE_RE.search(key_text):
            continue
        if isinstance(value, bool) or value is None:
            safe[key_text] = value
        elif isinstance(value, int):
            safe[key_text] = value
        elif isinstance(value, float):
            safe[key_text] = round(value, 6)
        else:
            text = _safe_text(str(value), fallback="")
            if text:
                safe[key_text] = text
    return safe


def _sanitize_selector_hints(raw: list[str]) -> list[str]:
    safe: list[str] = []
    for value in raw:
        if len(safe) >= 20:
            break
        text = " ".join(str(value).replace("\r", " ").replace("\n", " ").split())
        if not text:
            continue
        if _SENSITIVE_VALUE_RE.search(text):
            continue
        safe.append(text[:120])
    return safe


def _sanitize_route(raw_route: str | None) -> str | None:
    text = str(raw_route or "").strip()
    if not text:
        return None
    text = text.replace("\r", "").replace("\n", "")
    if len(text) > 240:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "VISUAL_EDIT_ROUTE_INVALID", "message": "route is too long."}},
        )
    return text


def _sanitize_visual_edit_bbox(raw: dict[str, Any] | None) -> dict[str, float] | None:
    if raw is None:
        return None
    required = ("x", "y", "width", "height")
    out: dict[str, float] = {}
    for key in required:
        value = raw.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise HTTPException(
                status_code=422,
                detail={"error": {"code": "VISUAL_EDIT_BBOX_INVALID", "message": "bbox values must be numeric."}},
            )
        numeric = float(value)
        if numeric < 0 or numeric > 100000:
            raise HTTPException(
                status_code=422,
                detail={"error": {"code": "VISUAL_EDIT_BBOX_INVALID", "message": "bbox values are out of allowed bounds."}},
            )
        out[key] = round(numeric, 4)
    if not out:
        return None
    missing = [key for key in required if key not in out]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "VISUAL_EDIT_BBOX_INVALID", "message": "bbox requires x, y, width, and height."}},
        )
    return out


def _normalize_visual_edit_status(raw_status: str | None) -> str:
    text = str(raw_status or "draft").strip().lower()
    if text not in _VISUAL_EDIT_ALLOWED_STATUS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "VISUAL_EDIT_STATUS_INVALID",
                    "message": "status must be one of draft, queued, processing, resolved, failed, or cancelled.",
                }
            },
        )
    return text


def _sanitize_visual_edit_instruction(raw_instruction: str) -> str:
    text = " ".join(str(raw_instruction or "").replace("\r", " ").replace("\n", " ").split())
    if not text:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "VISUAL_EDIT_INSTRUCTION_INVALID", "message": "instruction is required."}},
        )
    if len(text) > 1200:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "VISUAL_EDIT_INSTRUCTION_INVALID", "message": "instruction exceeds max length."}},
        )
    return text

def _build_activity_items(*, workspace_id: str, project_id: str) -> list[BuilderActivityItem]:
    source_store = get_builder_source_store()
    runtime_store = get_builder_runtime_store()
    items: list[BuilderActivityItem] = []

    for job in source_store.list_import_jobs(workspace_id=workspace_id, project_id=project_id):
        title = "Source import queued"
        if job.status == "running":
            title = "Validating source archive"
        elif job.status == "succeeded":
            title = "Source snapshot created"
        elif job.status == "failed":
            title = "Source import failed"
        message = _safe_text(job.error_message, fallback="Source import failed.") if job.status == "failed" else title
        items.append(
            BuilderActivityItem(
                id=f"act_{job.id}",
                kind="source_import",
                status=job.status if job.status in {"queued", "running", "succeeded", "failed"} else "info",
                title=title,
                message=message,
                timestamp=job.updated_at or job.created_at,
                source_id=job.project_source_id,
                snapshot_id=job.source_snapshot_id,
                import_job_id=job.id,
                metadata=_safe_stats(job.stats),
            )
        )

    for snapshot in source_store.list_source_snapshots(workspace_id=workspace_id, project_id=project_id):
        snapshot_status = "succeeded" if snapshot.status == "materialized" else "error"
        snapshot_title = "Source snapshot materialized" if snapshot.status == "materialized" else "Source snapshot invalid"
        items.append(
            BuilderActivityItem(
                id=f"act_{snapshot.id}",
                kind="source_snapshot",
                status=snapshot_status,
                title=snapshot_title,
                message=snapshot_title,
                timestamp=snapshot.created_at,
                source_id=snapshot.project_source_id,
                snapshot_id=snapshot.id,
                metadata={"size_bytes": max(0, int(snapshot.size_bytes))},
            )
        )

    for runtime in runtime_store.list_runtime_sessions(workspace_id=workspace_id, project_id=project_id):
        runtime_status = runtime.status.lower().strip()
        if runtime_status in {"running", "starting", "waiting"}:
            title = "Local preview connected"
            status = "ready" if runtime_status == "running" else "running"
            kind = "runtime_status"
        elif runtime_status in {"stopped", "expired"}:
            title = "Local preview disconnected"
            status = "stopped"
            kind = "preview_disconnected"
        else:
            title = "Local preview runtime error"
            status = "error"
            kind = "preview_error"
        items.append(
            BuilderActivityItem(
                id=f"act_{runtime.id}",
                kind=kind,
                status=status,
                title=title,
                message=_safe_text(runtime.message, fallback=title),
                timestamp=runtime.updated_at,
                snapshot_id=runtime.snapshot_id,
                runtime_session_id=runtime.id,
                metadata={"health": runtime.health, "mode": runtime.mode},
            )
        )

    for endpoint in runtime_store.list_preview_endpoints(workspace_id=workspace_id, project_id=project_id):
        endpoint_status = endpoint.status.lower().strip()
        if endpoint_status == "ready":
            kind = "preview_connected"
            status = "ready"
            title = "Local preview connected"
        elif endpoint_status in {"revoked", "unavailable"}:
            kind = "preview_disconnected" if endpoint_status == "revoked" else "preview_error"
            status = "stopped" if endpoint_status == "revoked" else "error"
            title = (
                "Local preview disconnected"
                if endpoint_status == "revoked"
                else "Preview endpoint unavailable"
            )
        else:
            kind = "runtime_status"
            status = "running"
            title = "Local preview endpoint provisioning"
        safe_url = _sanitize_local_preview_url(endpoint.url)
        items.append(
            BuilderActivityItem(
                id=f"act_{endpoint.id}",
                kind=kind,
                status=status,
                title=title,
                message=title,
                timestamp=endpoint.last_checked_at or _utc_now_iso(),
                runtime_session_id=endpoint.runtime_session_id,
                preview_endpoint_id=endpoint.id,
                metadata={
                    "access_mode": endpoint.access_mode,
                    "status": endpoint.status,
                    "preview_url": safe_url if safe_url else None,
                },
            )
        )

    run_profile_store = get_builder_run_profile_store()
    for profile in run_profile_store.list_local_run_profiles(workspace_id=workspace_id, project_id=project_id):
        if profile.status == "configured":
            title = "Local run profile configured"
            status = "ready"
        elif profile.status == "disabled":
            title = "Local run profile cleared"
            status = "stopped"
        else:
            title = "Local run profile draft"
            status = "info"
        items.append(
            BuilderActivityItem(
                id=f"act_{profile.id}",
                kind="runtime_status",
                status=status,
                title=title,
                message=title,
                timestamp=profile.updated_at,
                snapshot_id=profile.source_snapshot_id,
                metadata={
                    "working_directory": profile.working_directory,
                    "expected_preview_url": profile.expected_preview_url,
                },
            )
        )

    items.sort(key=lambda row: (row.timestamp, row.id), reverse=True)
    return items


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/sources")
async def list_project_sources(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    rows = get_builder_source_store().list_project_sources(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    return {
        "project_id": project_id,
        "workspace_id": ctx.workspace_id,
        "sources": [r.model_dump(mode="json") for r in rows],
    }


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/source-snapshots")
async def list_source_snapshots(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    rows = get_builder_source_store().list_source_snapshots(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    return {
        "project_id": project_id,
        "workspace_id": ctx.workspace_id,
        "source_snapshots": [r.model_dump(mode="json") for r in rows],
    }


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/import-jobs")
async def list_import_jobs(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    rows = get_builder_source_store().list_import_jobs(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    return {
        "project_id": project_id,
        "workspace_id": ctx.workspace_id,
        "import_jobs": [r.model_dump(mode="json") for r in rows],
    }


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/preview-status")
async def get_builder_preview_status(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    return _build_preview_status_payload(workspace_id=ctx.workspace_id, project_id=project_id)


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/activity")
async def get_builder_activity(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    items = _build_activity_items(workspace_id=ctx.workspace_id, project_id=project_id)
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": project_id,
        "items": [row.model_dump(mode="json") for row in items],
    }


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/usage-events")
async def list_builder_usage_events(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    rows = get_builder_usage_event_store().list_usage_events(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": project_id,
        "usage_events": [row.model_dump(mode="json") for row in rows],
    }


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/visual-edit-requests")
async def list_builder_visual_edit_requests(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    rows = get_builder_visual_edit_request_store().list_visual_edit_requests(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": project_id,
        "visual_edit_requests": [row.model_dump(mode="json") for row in rows],
    }


@router.post("/api/workspaces/{workspace_id}/projects/{project_id}/builder/visual-edit-requests")
async def create_builder_visual_edit_request(
    project_id: str,
    body: VisualEditRequestPayload,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
    actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    source_snapshot_id = _validated_snapshot_id(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        source_snapshot_id=body.source_snapshot_id,
    )
    request = VisualEditRequest(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        source_snapshot_id=source_snapshot_id,
        runtime_session_id=str(body.runtime_session_id or "").strip() or None,
        preview_endpoint_id=str(body.preview_endpoint_id or "").strip() or None,
        route=_sanitize_route(body.route),
        selector_hints=_sanitize_selector_hints(body.selector_hints),
        bbox=_sanitize_visual_edit_bbox(body.bbox),
        instruction=_sanitize_visual_edit_instruction(body.instruction),
        status=_normalize_visual_edit_status(body.status),
        created_by=actor.user_id if actor is not None else None,
        metadata=_sanitize_metadata(body.metadata),
    )
    saved = get_builder_visual_edit_request_store().upsert_visual_edit_request(request)
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": project_id,
        "visual_edit_request": saved.model_dump(mode="json"),
    }


@router.delete("/api/workspaces/{workspace_id}/projects/{project_id}/builder/visual-edit-requests/{request_id}")
async def cancel_builder_visual_edit_request(
    project_id: str,
    request_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    cancelled = get_builder_visual_edit_request_store().cancel_visual_edit_request(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        request_id=request_id,
    )
    if cancelled is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "VISUAL_EDIT_REQUEST_NOT_FOUND",
                    "message": f"Unknown visual edit request {request_id!r}.",
                }
            },
        )
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": project_id,
        "visual_edit_request": cancelled.model_dump(mode="json"),
    }


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/worker-capabilities")
async def get_builder_worker_capabilities(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
    actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    entries = _build_worker_capabilities(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        actor=actor,
    )
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": project_id,
        "workers": [entry.model_dump(mode="json") for entry in entries],
    }


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/local-run-profile")
async def get_builder_local_run_profile(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    profile = get_builder_run_profile_store().get_active_local_run_profile(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    return _serialize_local_run_profile(profile, workspace_id=ctx.workspace_id, project_id=project_id)


@router.put("/api/workspaces/{workspace_id}/projects/{project_id}/builder/local-run-profile")
async def put_builder_local_run_profile(
    project_id: str,
    body: LocalRunProfilePayload,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
    actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    profile_store = get_builder_run_profile_store()
    existing = profile_store.get_active_local_run_profile(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    source_snapshot_id = _validated_snapshot_id(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        source_snapshot_id=body.source_snapshot_id,
    )
    expected_preview_url = _sanitize_local_preview_url(body.expected_preview_url)
    if body.expected_preview_url and expected_preview_url is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "LOCAL_RUN_PREVIEW_URL_INVALID",
                    "message": "expected_preview_url must be a safe local loopback http URL with explicit port.",
                }
            },
        )
    status = str(body.status or "configured").strip().lower()
    if status not in {"draft", "configured", "disabled"}:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_PROFILE_STATUS_INVALID", "message": "status must be draft, configured, or disabled."}},
        )
    install_argv = _parse_command_argv(body.install_command, field_name="install_command")
    dev_argv = _parse_command_argv(body.dev_command, field_name="dev_command", required=True) or []
    build_argv = _parse_command_argv(body.build_command, field_name="build_command")
    test_argv = _parse_command_argv(body.test_command, field_name="test_command")
    if existing is None:
        profile = LocalRunProfile(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            dev_command_argv=dev_argv,
            created_by=actor.user_id if actor is not None else None,
        )
    else:
        profile = existing
    profile.source_snapshot_id = source_snapshot_id
    profile.display_name = _safe_text(body.display_name, fallback="Local run profile")
    profile.working_directory = _normalize_working_directory(body.working_directory)
    profile.install_command_argv = install_argv
    profile.dev_command_argv = dev_argv
    profile.build_command_argv = build_argv
    profile.test_command_argv = test_argv
    profile.expected_preview_url = expected_preview_url
    profile.execution_mode = "local_only"
    profile.status = status
    profile.metadata = _sanitize_metadata(body.metadata)
    saved = profile_store.upsert_local_run_profile(profile)
    return _serialize_local_run_profile(saved, workspace_id=ctx.workspace_id, project_id=project_id)


@router.delete("/api/workspaces/{workspace_id}/projects/{project_id}/builder/local-run-profile")
async def delete_builder_local_run_profile(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    cleared = get_builder_run_profile_store().clear_active_local_run_profile(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    return _serialize_local_run_profile(cleared, workspace_id=ctx.workspace_id, project_id=project_id)


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/cloud-runtime")
async def get_builder_cloud_runtime(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    runtime = get_builder_runtime_store().get_latest_runtime_session(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        mode="cloud",
    )
    return _serialize_cloud_runtime(runtime, workspace_id=ctx.workspace_id, project_id=project_id)


@router.post("/api/workspaces/{workspace_id}/projects/{project_id}/builder/cloud-runtime/request")
async def request_builder_cloud_runtime(
    project_id: str,
    body: CloudRuntimeRequestPayload,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
    actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    source_snapshot_id = _validated_snapshot_id(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        source_snapshot_id=body.source_snapshot_id,
    )
    requested_status = str(body.status or "").strip().lower()
    if requested_status and requested_status not in _CLOUD_RUNTIME_STATES:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "CLOUD_RUNTIME_STATUS_INVALID",
                    "message": "status must be queued, provisioning, running, failed, expired, or unsupported.",
                }
            },
        )
    runtime = get_builder_runtime_store().request_cloud_runtime_session(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        source_snapshot_id=source_snapshot_id,
        requested_by=actor.user_id if actor is not None else None,
        metadata=_sanitize_metadata(body.metadata),
    )
    if requested_status and requested_status != "queued":
        runtime.status = requested_status
        runtime.updated_at = _utc_now_iso()
        runtime = get_builder_runtime_store().upsert_runtime_session(runtime)
    return {
        "runtime": runtime.model_dump(mode="json"),
        "cloud_runtime": _serialize_cloud_runtime(
            runtime,
            workspace_id=ctx.workspace_id,
            project_id=project_id,
        ),
    }


@router.delete("/api/workspaces/{workspace_id}/projects/{project_id}/builder/cloud-runtime")
async def delete_builder_cloud_runtime(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    runtime = get_builder_runtime_store().clear_cloud_runtime(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    return {
        "cloud_runtime": _serialize_cloud_runtime(
            runtime,
            workspace_id=ctx.workspace_id,
            project_id=project_id,
        )
    }


@router.post("/api/workspaces/{workspace_id}/projects/{project_id}/builder/local-preview")
async def register_local_preview(
    project_id: str,
    body: LocalPreviewRegisterRequest,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    safe_preview_url = _sanitize_local_preview_url(body.preview_url)
    if safe_preview_url is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "LOCAL_PREVIEW_URL_INVALID",
                    "message": "Preview URL must be a safe local loopback http URL without credentials.",
                }
            },
        )
    source_snapshot_id = _validated_snapshot_id(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        source_snapshot_id=body.source_snapshot_id,
    )
    runtime_store = get_builder_runtime_store()
    runtime = runtime_store.upsert_local_runtime_session(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        source_snapshot_id=source_snapshot_id,
        message=(body.display_name or "").strip() or "Local preview connected.",
    )
    endpoint = runtime_store.get_active_preview_endpoint(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        runtime_session_id=runtime.id,
    )
    if endpoint is None:
        endpoint = PreviewEndpoint(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            runtime_session_id=runtime.id,
        )
    endpoint.url = safe_preview_url
    endpoint.access_mode = "local_url"
    endpoint.status = "ready"
    endpoint.last_checked_at = _utc_now_iso()
    endpoint = runtime_store.upsert_preview_endpoint(endpoint)
    runtime.preview_endpoint_id = endpoint.id
    runtime.updated_at = _utc_now_iso()
    runtime = runtime_store.upsert_runtime_session(runtime)
    return {
        "runtime_session": runtime.model_dump(mode="json"),
        "preview_endpoint": endpoint.model_dump(mode="json"),
        "preview_status": _build_preview_status_payload(workspace_id=ctx.workspace_id, project_id=project_id),
    }


@router.delete("/api/workspaces/{workspace_id}/projects/{project_id}/builder/local-preview")
async def clear_local_preview(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    get_builder_runtime_store().clear_local_preview(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    status_payload = _build_preview_status_payload(workspace_id=ctx.workspace_id, project_id=project_id)
    if status_payload["status"] == "error":
        status_payload["status"] = "not_connected"
        status_payload["preview_url"] = None
        status_payload["message"] = "Local preview runtime is not connected."
    return {"preview_status": status_payload}


@router.post("/api/workspaces/{workspace_id}/projects/{project_id}/builder/import-jobs/zip")
async def create_zip_import_job(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
    actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    payload = await file.read()
    store = get_builder_source_store()
    created_by = actor.user_id if actor is not None else ""
    job = store.create_import_job(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        created_by=created_by,
        phase="received",
        status="queued",
    )
    try:
        job = store.mark_import_job_running(import_job_id=job.id, phase="validating")
        zip_info = validate_zip_upload(payload)
        artifact_uri, artifact_meta = _save_zip_artifact(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            payload=payload,
        )
        existing_sources = store.list_project_sources(workspace_id=ctx.workspace_id, project_id=project_id)
        source = next((row for row in existing_sources if row.kind == "zip_upload"), None)
        if source is None:
            source = ProjectSource(
                workspace_id=ctx.workspace_id,
                project_id=project_id,
                kind="zip_upload",
                status="ready",
                display_name=file.filename or "uploaded.zip",
                origin_ref="zip_upload",
                created_by=created_by,
                metadata={"latest_import_job_id": job.id},
            )
        else:
            source.status = "ready"
            source.display_name = file.filename or source.display_name
            source.origin_ref = "zip_upload"
            source.metadata = {**source.metadata, "latest_import_job_id": job.id}
        source = store.upsert_project_source(source)
        snapshot = SourceSnapshot(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            project_source_id=source.id,
            digest_sha256=zip_info.digest_sha256,
            size_bytes=zip_info.uncompressed_bytes,
            artifact_uri=artifact_uri,
            manifest={
                "compressed_bytes": zip_info.compressed_bytes,
                "uncompressed_bytes": zip_info.uncompressed_bytes,
                "file_count": zip_info.file_count,
                "dir_count": zip_info.dir_count,
                "entries": [
                    {
                        "path": e.path,
                        "size_bytes": e.size_bytes,
                        "compressed_bytes": e.compressed_bytes,
                        "is_dir": e.is_dir,
                    }
                    for e in zip_info.entries
                ],
                "truncated_entries": max(0, zip_info.file_count + zip_info.dir_count - len(zip_info.entries)),
            },
            created_by=created_by,
            metadata=artifact_meta,
        )
        snapshot = store.upsert_source_snapshot(snapshot)
        source.active_snapshot_id = snapshot.id
        source = store.upsert_project_source(source)
        job = store.mark_import_job_succeeded(
            import_job_id=job.id,
            phase="materialized",
            source_snapshot_id=snapshot.id,
            stats={
                "file_count": zip_info.file_count,
                "dir_count": zip_info.dir_count,
                "compressed_bytes": zip_info.compressed_bytes,
                "uncompressed_bytes": zip_info.uncompressed_bytes,
            },
        )
        return {
            "project_id": project_id,
            "workspace_id": ctx.workspace_id,
            "import_job": job.model_dump(mode="json"),
            "project_source": source.model_dump(mode="json"),
            "source_snapshot": snapshot.model_dump(mode="json"),
        }
    except ZipSafetyError as exc:
        job = store.mark_import_job_failed(
            import_job_id=job.id,
            phase="failed",
            error_code=exc.code,
            error_message=_safe_zip_error_message(exc.code),
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": job.error_code,
                    "message": job.error_message,
                },
                "import_job": job.model_dump(mode="json"),
            },
        ) from exc
    except (OSError, ValueError) as exc:
        job = store.mark_import_job_failed(
            import_job_id=job.id,
            phase="failed",
            error_code="ZIP_INVALID",
            error_message=_safe_zip_error_message("ZIP_INVALID"),
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "ZIP_INVALID",
                    "message": _safe_zip_error_message("ZIP_INVALID"),
                },
                "import_job": job.model_dump(mode="json"),
            },
        ) from exc
