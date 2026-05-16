"""Best-effort tenant cleanup when archiving a workspace (metadata + local JSON stores).

Does **not** call external GKE/Cloud Run preview teardown; summaries expose
``runtime_cleanup_requested`` so operators know asynchronous cleanup may be needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.persistence.builder_runtime_job_store import BuilderRuntimeJobStore, get_builder_runtime_job_store
from src.persistence.builder_runtime_store import BuilderRuntimeStore, get_builder_runtime_store
from src.persistence.builder_source_store import BuilderSourceStore, get_builder_source_store
from src.persistence.chat_session_store import build_chat_session_store
from src.persistence.project_store import get_project_store


@dataclass(frozen=True)
class WorkspacePurgeSummary:
    chats_deleted: int
    projects_deleted: int
    project_sources_deleted: int
    snapshots_deleted: int
    import_jobs_deleted: int
    runtime_sessions_removed: int
    preview_endpoints_removed: int
    cloud_runtime_jobs_removed: int
    runtime_cleanup_requested: bool

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "chats_deleted": self.chats_deleted,
            "projects_deleted": self.projects_deleted,
            "project_sources_deleted": self.project_sources_deleted,
            "snapshots_deleted": self.snapshots_deleted,
            "import_jobs_deleted": self.import_jobs_deleted,
            "runtime_sessions_removed": self.runtime_sessions_removed,
            "preview_endpoints_removed": self.preview_endpoints_removed,
            "cloud_runtime_jobs_removed": self.cloud_runtime_jobs_removed,
            "runtime_cleanup_requested": self.runtime_cleanup_requested,
        }


def purge_builder_sources_for_workspace(
    *,
    workspace_id: str,
    source_store: BuilderSourceStore | None = None,
) -> tuple[int, int, int]:
    """Returns (sources_removed, snapshots_removed, import_jobs_removed)."""
    store = source_store if source_store is not None else get_builder_source_store()
    if not isinstance(store, BuilderSourceStore):
        return 0, 0, 0
    raw = store._load_raw()  # noqa: SLF001 — single concrete JSON backend
    before_ps = list(raw.get("project_sources", []))
    before_ss = list(raw.get("source_snapshots", []))
    before_ij = list(raw.get("import_jobs", []))

    ps_kept = [r for r in before_ps if str((r or {}).get("workspace_id") or "") != workspace_id]
    ss_kept = [r for r in before_ss if str((r or {}).get("workspace_id") or "") != workspace_id]
    ij_kept = [r for r in before_ij if str((r or {}).get("workspace_id") or "") != workspace_id]

    removed_ps = len(before_ps) - len(ps_kept)
    removed_ss = len(before_ss) - len(ss_kept)
    removed_ij = len(before_ij) - len(ij_kept)

    if removed_ps or removed_ss or removed_ij:
        raw["project_sources"] = ps_kept
        raw["source_snapshots"] = ss_kept
        raw["import_jobs"] = ij_kept
        store._save_raw(raw)  # noqa: SLF001

    return removed_ps, removed_ss, removed_ij


def purge_runtime_metadata_for_workspace(
    *,
    workspace_id: str,
) -> tuple[int, int, int]:
    """Returns (sessions_removed, preview_endpoints_removed, cloud_jobs_removed)."""
    rt_store = get_builder_runtime_store()
    sess_rm = pe_rm = 0
    if isinstance(rt_store, BuilderRuntimeStore):
        rt_raw = rt_store._load_raw()  # noqa: SLF001
        before_sess = list(rt_raw.get("runtime_sessions", []))
        before_pe = list(rt_raw.get("preview_endpoints", []))
        sess_kept = [
            r for r in before_sess if str((r or {}).get("workspace_id") or "") != workspace_id
        ]
        pe_kept = [
            r for r in before_pe if str((r or {}).get("workspace_id") or "") != workspace_id
        ]
        sess_rm = len(before_sess) - len(sess_kept)
        pe_rm = len(before_pe) - len(pe_kept)
        if sess_rm or pe_rm:
            rt_raw["runtime_sessions"] = sess_kept
            rt_raw["preview_endpoints"] = pe_kept
            rt_store._save_raw(rt_raw)  # noqa: SLF001

    jobs_rm = 0
    job_store = get_builder_runtime_job_store()
    if isinstance(job_store, BuilderRuntimeJobStore):
        j_raw = job_store._load_raw()  # noqa: SLF001
        before_jobs = list(j_raw.get("cloud_runtime_jobs", []))
        jobs_kept = [
            r for r in before_jobs if str((r or {}).get("workspace_id") or "") != workspace_id
        ]
        jobs_rm = len(before_jobs) - len(jobs_kept)
        if jobs_rm:
            j_raw["cloud_runtime_jobs"] = jobs_kept
            job_store._save_raw(j_raw)  # noqa: SLF001

    return sess_rm, pe_rm, jobs_rm


def purge_builder_projects_for_workspace(*, workspace_id: str) -> int:
    """Remove project records carrying ``metadata.workspace_id`` for this tenant."""
    pstore = get_project_store()
    removed = 0
    for row in list(pstore.list_projects()):
        meta = row.metadata if isinstance(row.metadata, dict) else {}
        if str(meta.get("workspace_id") or "").strip() == workspace_id:
            if pstore.remove(row.id):
                removed += 1
    return removed


def delete_chat_sessions_for_workspace(workspace_id: str) -> int:
    """Delete all persisted chat threads tagged with ``workspace_id``."""
    chat = build_chat_session_store()
    deleted = getattr(chat, "delete_sessions_for_workspace", None)
    if callable(deleted):
        try:
            return int(deleted(workspace_id))  # type: ignore[no-any-return,misc]
        except (TypeError, ValueError):
            return 0
    return 0


def purge_workspace_associated_records(*, workspace_id: str) -> WorkspacePurgeSummary:
    chats_deleted = delete_chat_sessions_for_workspace(workspace_id)

    sources_n, snaps_n, jobs_imp_n = purge_builder_sources_for_workspace(workspace_id=workspace_id)
    sess_rm, pe_rm, cr_jobs_rm = purge_runtime_metadata_for_workspace(workspace_id=workspace_id)
    proj_rm = purge_builder_projects_for_workspace(workspace_id=workspace_id)

    runtime_cleanup_requested = bool(cr_jobs_rm or sess_rm)

    return WorkspacePurgeSummary(
        chats_deleted=chats_deleted,
        projects_deleted=proj_rm,
        project_sources_deleted=sources_n,
        snapshots_deleted=snaps_n,
        import_jobs_deleted=jobs_imp_n,
        runtime_sessions_removed=sess_rm,
        preview_endpoints_removed=pe_rm,
        cloud_runtime_jobs_removed=cr_jobs_rm,
        runtime_cleanup_requested=runtime_cleanup_requested,
    )
