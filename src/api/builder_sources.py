from __future__ import annotations

import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.dependencies.workspace import require_perm
from src.ham.builder_zip_intake import ZipSafetyError, validate_zip_upload
from src.ham.clerk_auth import HamActor
from src.ham.workspace_models import WorkspaceContext
from src.ham.workspace_perms import PERM_WORKSPACE_READ, PERM_WORKSPACE_WRITE
from src.persistence.builder_source_store import (
    ProjectSource,
    SourceSnapshot,
    get_builder_source_store,
)
from src.persistence.builder_runtime_store import PreviewEndpoint, get_builder_runtime_store
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


class LocalPreviewRegisterRequest(BaseModel):
    preview_url: str
    source_snapshot_id: str | None = None
    display_name: str | None = None


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
    source_snapshot_id = body.source_snapshot_id
    if source_snapshot_id is not None:
        snapshot_rows = get_builder_source_store().list_source_snapshots(
            workspace_id=ctx.workspace_id,
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
