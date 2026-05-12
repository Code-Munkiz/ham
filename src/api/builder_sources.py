from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

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
