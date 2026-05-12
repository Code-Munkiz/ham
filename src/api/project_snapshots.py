"""Read APIs for managed workspace snapshots."""

from __future__ import annotations

import difflib
import io
import json
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response, StreamingResponse

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.managed_workspace.models import SnapshotManifest
from src.ham.managed_workspace.paths import sanitize_rel_file_path
from src.ham.managed_workspace.snapshot_object_storage import snapshot_object_storage_from_env
from src.ham.managed_workspace.snapshot_store import get_project_snapshot_store
from src.ham.managed_workspace.workspace_adapter import managed_workspace_runtime
from src.persistence.project_store import get_project_store

router = APIRouter(
    prefix="/api/projects",
    tags=["project-snapshots"],
    dependencies=[Depends(get_ham_clerk_actor)],
)


def _storage_or_503() -> object:
    rt = managed_workspace_runtime().object_storage
    out = rt or snapshot_object_storage_from_env()
    if out is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "MANAGED_SNAPSHOT_STORAGE_NOT_CONFIGURED",
                    "message": "Managed snapshot reads require HAM_MANAGED_SNAPSHOT_GCS_BUCKET on this host.",
                }
            },
        )
    return out


def _project_or_404(project_id: str) -> object:
    rec = get_project_store().get_project(project_id.strip())
    if rec is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "PROJECT_NOT_FOUND"}})
    return rec


def _snapshot_or_404(project_id: str, snapshot_id: str) -> object:
    snap = get_project_snapshot_store().get_snapshot(project_id.strip(), snapshot_id.strip())
    if snap is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SNAPSHOT_NOT_FOUND"}})
    return snap


@router.get("/{project_id}/snapshots")
async def list_snapshots(project_id: str) -> dict[str, object]:
    _project_or_404(project_id)
    rows = get_project_snapshot_store().list_snapshots(project_id.strip())
    return {"kind": "ham_project_snapshots", "snapshots": [r.model_dump(mode="json") for r in rows]}


@router.get("/{project_id}/snapshots/{snapshot_id}/manifest")
async def snapshot_manifest(
    project_id: str,
    snapshot_id: str,
) -> JSONResponse:
    row = _snapshot_or_404(project_id, snapshot_id)
    stor = _storage_or_503()
    raw = stor.read_object(row.manifest_object)  # type: ignore[union-attr]
    if raw is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MANIFEST_UNAVAILABLE"}})
    try:
        man = SnapshotManifest.model_validate_json(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail={"error": {"code": "MANIFEST_DECODE_FAILED"}}) from None
    return JSONResponse(content=man.model_dump(mode="json"))


@router.get("/{project_id}/snapshots/{snapshot_id}/file")
async def snapshot_file(
    project_id: str,
    snapshot_id: str,
    path: str = Query(..., min_length=1, max_length=2048),
) -> Response:
    row = _snapshot_or_404(project_id, snapshot_id)
    rel = sanitize_rel_file_path(path)
    if rel is None:
        raise HTTPException(status_code=422, detail={"error": {"code": "INVALID_PATH"}})
    stor = _storage_or_503()
    object_path = f"{row.object_prefix.rstrip('/')}/files/{rel}"
    data = stor.read_object(object_path)  # type: ignore[union-attr]
    if data is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "FILE_NOT_FOUND"}})
    return Response(content=data, media_type="application/octet-stream")


def _manifest_bytes(stor: object, manifest_object: str) -> SnapshotManifest:
    raw = stor.read_object(manifest_object)  # type: ignore[union-attr]
    if raw is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MANIFEST_UNAVAILABLE"}})
    try:
        return SnapshotManifest.model_validate_json(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail={"error": {"code": "MANIFEST_DECODE_FAILED"}}) from None


def _file_bytes_safe(stor: object, *, row: object, rel: str) -> bytes | None:
    rf = sanitize_rel_file_path(rel)
    if rf is None:
        return None
    p = f"{row.object_prefix.rstrip('/')}/files/{rf}"
    return stor.read_object(p)  # type: ignore[union-attr]


@router.get("/{project_id}/snapshots/{snapshot_id}/diff")
async def snapshot_diff(
    project_id: str,
    snapshot_id: str,
    vs: str = Query(..., min_length=8, max_length=120),
) -> dict[str, object]:
    a = _snapshot_or_404(project_id, snapshot_id)
    b = _snapshot_or_404(project_id, vs)
    stor = _storage_or_503()
    ma = _manifest_bytes(stor, a.manifest_object)
    mb = _manifest_bytes(stor, b.manifest_object)
    sa = {e.path for e in ma.files}
    sb = {e.path for e in mb.files}
    added = sorted(sb - sa)
    removed = sorted(sa - sb)
    common_sorted = sorted(sa & sb)
    modified: list[str] = []
    ha = {f.path: f.sha256 for f in ma.files}
    hb = {f.path: f.sha256 for f in mb.files}
    for path in common_sorted:
        if ha.get(path) != hb.get(path):
            modified.append(path)

    snippets: dict[str, str] = {}
    cap = 12_000
    for path in sorted(set(modified[:20])):
        oa = _file_bytes_safe(stor, row=a, rel=path) or b""
        ob = _file_bytes_safe(stor, row=b, rel=path) or b""
        ta = oa.decode("utf-8", errors="replace").splitlines(True)
        tb = ob.decode("utf-8", errors="replace").splitlines(True)
        diff_txt = "".join(difflib.unified_diff(ta, tb, fromfile=f"{snapshot_id}:{path}", tofile=f"{vs}:{path}"))
        if diff_txt.strip():
            snippets[path] = diff_txt[:cap]

    return {
        "kind": "ham_snapshot_diff",
        "snapshot_id": snapshot_id,
        "vs": vs,
        "added_paths": added,
        "removed_paths": removed,
        "modified_paths": modified,
        "unified_snippets": snippets,
    }


@router.get("/{project_id}/export")
async def snapshot_export(
    project_id: str,
    snapshot: str = Query(..., min_length=8, max_length=120),
) -> StreamingResponse:
    row = _snapshot_or_404(project_id, snapshot)
    stor = _storage_or_503()
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as z:
        mf = stor.read_object(row.manifest_object)  # type: ignore[union-attr]
        if mf is None:
            raise HTTPException(status_code=404, detail={"error": {"code": "MANIFEST_UNAVAILABLE"}})
        z.writestr("manifest.json", mf)
        man = SnapshotManifest.model_validate_json(mf.decode("utf-8"))
        for entry in man.files:
            fb = stor.read_object(f"{row.object_prefix.rstrip('/')}/files/{entry.path}")  # type: ignore[union-attr]
            if fb is None:
                continue
            z.writestr(entry.path.replace("\\", "/"), fb)
        if man.deleted_paths:
            z.writestr(
                "_deleted_paths.json",
                json.dumps(man.deleted_paths, separators=(",", ":")).encode("utf-8"),
            )

    bio.seek(0)

    fname = f"ham-snapshot-{project_id}-{snapshot}.zip"
    return StreamingResponse(
        bio,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
