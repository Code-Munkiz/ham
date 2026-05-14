"""Post-exec managed workspace emitter: snapshots working tree → GCS + snapshot store."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from src.ham.managed_workspace.models import (
    ManifestFileEntry,
    ProjectSnapshot,
    SnapshotManifest,
)
from src.ham.managed_workspace.paths import managed_working_dir, posix_paths_under
from src.ham.managed_workspace.snapshot_object_storage import (
    snapshot_object_storage_from_env,
)
from src.ham.managed_workspace.snapshot_store import get_project_snapshot_store

if TYPE_CHECKING:
    from src.ham.droid_runner.build_lane_output import OutputResult, PostExecCommon


_LOG = logging.getLogger(__name__)


MANAGED_SNAPSHOT_STORAGE_REQUIRED = "MANAGED_SNAPSHOT_STORAGE_REQUIRED"
MANAGED_WORKSPACE_CWD_MISMATCH = "MANAGED_WORKSPACE_CWD_MISMATCH"
MANAGED_WORKSPACE_IDS_REQUIRED = "MANAGED_WORKSPACE_IDS_REQUIRED"


@dataclass(frozen=False)
class ManagedWorkspaceRuntime:
    """Process-wide seams for pytest (storage + snapshot store overrides)."""

    object_storage: object | None = None  # SnapshotObjectStorage
    snapshot_store_override: object | None = None


_managed_runtime = ManagedWorkspaceRuntime()


def managed_workspace_runtime() -> ManagedWorkspaceRuntime:
    return _managed_runtime


def reset_managed_workspace_runtime() -> None:
    global _managed_runtime
    _managed_runtime = ManagedWorkspaceRuntime()


def _utc_now_iso() -> str:
    from src.persistence.control_plane_run import utc_now_iso  # noqa: PLC0415

    return utc_now_iso()


def _preview_relative_url(project_id: str, snapshot_id: str) -> str:
    return f"/api/projects/{project_id}/snapshots/{snapshot_id}"


def _snap_prefix(workspace_id: str, project_id: str, snapshot_id: str) -> str:
    wi = workspace_id.strip()
    pi = project_id.strip()
    sid = snapshot_id.strip()
    return f"{wi}/{pi}/snapshots/{sid}"


def _head_object(workspace_id: str, project_id: str) -> str:
    wi = workspace_id.strip()
    pi = project_id.strip()
    return f"{wi}/{pi}/head.json"


def _file_object(prefix: str, rel_path: str) -> str:
    return f"{prefix.rstrip('/')}/files/{rel_path}"


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_manifest(storage: object, object_path: str) -> SnapshotManifest | None:
    raw = storage.read_object(object_path)  # type: ignore[union-attr]
    if raw is None:
        return None
    try:
        return SnapshotManifest.model_validate_json(raw.decode("utf-8"))
    except Exception:
        return None


def _read_parent_snapshot_ids(storage: object, *, workspace_id: str, project_id: str) -> str | None:
    raw_h = storage.read_object(_head_object(workspace_id, project_id))  # type: ignore[union-attr]
    if raw_h is None:
        return None
    try:
        data = json.loads(raw_h.decode("utf-8"))
    except Exception:
        return None
    sid = str(data.get("snapshot_id") or "").strip()
    return sid or None


def emit_managed_workspace_snapshot(common: PostExecCommon) -> OutputResult:
    from src.ham.droid_runner.build_lane_output import OutputResult  # noqa: PLC0415

    rt = managed_workspace_runtime()
    sto = rt.object_storage or snapshot_object_storage_from_env()
    if sto is None:
        return OutputResult(
            target="managed_workspace",
            build_outcome="failed",
            target_ref={"neutral_outcome": "failed"},
            error_summary=MANAGED_SNAPSHOT_STORAGE_REQUIRED,
        )

    wid = common.workspace_id.strip() if common.workspace_id else ""
    pid = common.project_id.strip() if common.project_id else ""

    if not wid or not pid:
        return OutputResult(
            target="managed_workspace",
            build_outcome="failed",
            target_ref={"neutral_outcome": "failed"},
            error_summary=MANAGED_WORKSPACE_IDS_REQUIRED,
        )

    try:
        expected = managed_working_dir(wid, pid).resolve(strict=False)
    except ValueError:
        expected = Path()

    resolved_root = common.project_root.expanduser().resolve(strict=False)

    if resolved_root.resolve() != expected.resolve():
        return OutputResult(
            target="managed_workspace",
            build_outcome="failed",
            target_ref={"neutral_outcome": "failed"},
            error_summary=(
                f"{MANAGED_WORKSPACE_CWD_MISMATCH} expected {expected} got {resolved_root}"
            ),
        )

    store = rt.snapshot_store_override or get_project_snapshot_store()

    parent_snapshot_id = _read_parent_snapshot_ids(sto, workspace_id=wid, project_id=pid)
    prev_manifest: SnapshotManifest | None = None
    if parent_snapshot_id:
        prev_manifest = _read_manifest(
            sto,
            f"{_snap_prefix(wid, pid, parent_snapshot_id)}/manifest.json",
        )

    current_files = posix_paths_under(resolved_root)
    hashes: dict[str, str] = {}
    entries: list[ManifestFileEntry] = []
    for rel, fp in sorted(current_files.items(), key=lambda x: x[0]):
        hashes[rel] = _sha_file(fp)
        entries.append(ManifestFileEntry(path=rel, sha256=hashes[rel]))

    prev_hashes: dict[str, str] = {}
    deleted_paths: list[str] = []
    if prev_manifest is not None:
        prev_hashes = {f.path: f.sha256 for f in prev_manifest.files}
        deleted_paths = sorted(set(prev_hashes) - set(hashes))

    changed_new_mod = sorted(
        [p for p, h in hashes.items() if prev_hashes.get(p) != h],
    )
    changed_paths_count = len(changed_new_mod) + len(deleted_paths)

    if changed_paths_count == 0 and parent_snapshot_id:
        snap_id_final = parent_snapshot_id
        return OutputResult(
            target="managed_workspace",
            build_outcome="nothing_to_change",
            target_ref={
                "neutral_outcome": "nothing_to_change",
                "snapshot_id": snap_id_final,
                "parent_snapshot_id": parent_snapshot_id,
                "preview_url": _preview_relative_url(pid, snap_id_final),
                "changed_paths_count": 0,
                "correlation_id": common.change_id,
            },
            error_summary=None,
        )

    snapshot_id_new = uuid.uuid4().hex
    snap_pref = _snap_prefix(wid, pid, snapshot_id_new)
    now = _utc_now_iso()
    manifest = SnapshotManifest(
        workspace_id=wid,
        project_id=pid,
        snapshot_id=snapshot_id_new,
        parent_snapshot_id=parent_snapshot_id,
        created_at=now,
        deleted_paths=deleted_paths,
        files=entries,
    )
    mb = manifest.model_dump_json().encode("utf-8")

    for rel in changed_new_mod:
        fp = current_files.get(rel)
        if fp is None:
            continue
        body = fp.read_bytes()
        sto.write_object(
            _file_object(snap_pref, rel),
            body,
            content_type="application/octet-stream",
        )  # type: ignore[union-attr]

    sto.write_object(f"{snap_pref}/manifest.json", mb, content_type="application/json")  # type: ignore[union-attr]
    sto.write_object(
        _head_object(wid, pid),
        json.dumps({"snapshot_id": snapshot_id_new, "updated_at": now}, separators=(",", ":")).encode(
            "utf-8",
        ),
        content_type="application/json",
    )  # type: ignore[union-attr]

    bn = sto.bucket_name()  # type: ignore[union-attr]
    bn_s = bn or ""
    manifest_object = f"{snap_pref}/manifest.json"
    gs_uri = f"gs://{bn_s}/{manifest_object}" if bn_s else None

    row = ProjectSnapshot(
        project_id=pid,
        workspace_id=wid,
        snapshot_id=snapshot_id_new,
        parent_snapshot_id=parent_snapshot_id,
        created_at=now,
        bucket=bn_s or None,
        object_prefix=f"{snap_pref}/",
        preview_url=_preview_relative_url(pid, snapshot_id_new),
        manifest_object=manifest_object,
        gcs_uri=gs_uri,
        changed_paths_count=changed_paths_count,
        neutral_outcome="succeeded",
    )
    store.put_snapshot(row)  # type: ignore[union-attr]

    return OutputResult(
        target="managed_workspace",
        build_outcome="succeeded",
        target_ref={
            "neutral_outcome": "succeeded",
            "snapshot_id": snapshot_id_new,
            "parent_snapshot_id": parent_snapshot_id,
            "preview_url": row.preview_url,
            "changed_paths_count": changed_paths_count,
            "correlation_id": common.change_id,
        },
        error_summary=None,
    )


def compute_deleted_paths_against_parent(common: PostExecCommon) -> tuple[str, ...]:
    """Compute, without writing anything, the sorted POSIX paths that would be
    recorded as deleted by emit_managed_workspace_snapshot(common).

    Returns () when there is no parent snapshot (first run for this project),
    when the working tree is missing or empty (no diff possible), or when the
    parent manifest cannot be read.

    Pure: performs no GCS writes, does not advance head.json, does not persist
    a ProjectSnapshot row. Safe to call before emit_managed_workspace_snapshot()
    as a dry-run probe.
    """
    rt = managed_workspace_runtime()
    sto = rt.object_storage or snapshot_object_storage_from_env()
    if sto is None:
        return ()

    wid = common.workspace_id.strip() if common.workspace_id else ""
    pid = common.project_id.strip() if common.project_id else ""
    if not wid or not pid:
        return ()

    try:
        expected = managed_working_dir(wid, pid).resolve(strict=False)
    except ValueError:
        return ()

    resolved_root = common.project_root.expanduser().resolve(strict=False)
    if resolved_root.resolve() != expected.resolve():
        return ()
    if not resolved_root.is_dir():
        return ()

    try:
        parent_snapshot_id = _read_parent_snapshot_ids(sto, workspace_id=wid, project_id=pid)
    except Exception as exc:
        _LOG.warning(
            "compute_deleted_paths_against_parent head read raised %s",
            type(exc).__name__,
        )
        return ()
    if not parent_snapshot_id:
        return ()

    try:
        prev_manifest = _read_manifest(
            sto,
            f"{_snap_prefix(wid, pid, parent_snapshot_id)}/manifest.json",
        )
    except Exception as exc:
        _LOG.warning(
            "compute_deleted_paths_against_parent manifest read raised %s",
            type(exc).__name__,
        )
        return ()
    if prev_manifest is None:
        return ()

    current_files = posix_paths_under(resolved_root)
    if not current_files:
        return ()

    prev_hashes = {f.path: f.sha256 for f in prev_manifest.files}
    deleted = sorted(set(prev_hashes) - set(current_files))
    return tuple(deleted)
