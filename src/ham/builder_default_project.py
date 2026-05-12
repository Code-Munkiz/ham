"""Ensure a workspace-scoped default HAM builder project record exists."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from src.persistence.project_store import get_project_store
from src.registry.projects import ProjectRecord

_METADATA_DEFAULT_FLAG = "ham_builder_default"
_WORKSPACE_META_KEY = "workspace_id"


def _safe_workspace_segment(workspace_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", workspace_id.strip()).strip("._-")
    return (cleaned[:120] if cleaned else "ws") or "ws"


def _virtual_root_for_workspace(workspace_id: str) -> Path:
    base = Path.home() / ".ham" / "builder-virtual" / _safe_workspace_segment(workspace_id)
    root = (base / "default").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _record_workspace_id(metadata: dict, workspace_id: str) -> dict[str, object]:
    m = dict(metadata or {})
    m[_WORKSPACE_META_KEY] = workspace_id
    m[_METADATA_DEFAULT_FLAG] = "1"
    m["ham_builder_kind"] = "default_workspace_builder"
    return m


def find_default_builder_project(workspace_id: str) -> ProjectRecord | None:
    """Return existing default builder project for workspace, if any."""
    ws = workspace_id.strip()
    if not ws:
        return None
    store = get_project_store()
    for row in store.list_projects():
        meta = row.metadata or {}
        flag = str(meta.get(_METADATA_DEFAULT_FLAG) or "").strip().lower()
        wid = str(meta.get(_WORKSPACE_META_KEY) or meta.get("workspaceId") or "").strip()
        if flag in {"1", "true", "yes"} and wid == ws:
            return row
    return None


def ensure_default_builder_project(workspace_id: str) -> ProjectRecord:
    """Idempotently create or return the workspace default builder project."""
    ws = workspace_id.strip()
    if not ws:
        raise ValueError("workspace_id is required")
    hit = find_default_builder_project(ws)
    if hit is not None:
        return hit
    root = _virtual_root_for_workspace(ws)
    digest = hashlib.sha256(ws.encode("utf-8")).hexdigest()[:16]
    name = f"Builder ({digest})"
    store = get_project_store()
    project_id = f"project.builder-{digest}"
    existing = store.get_project(project_id)
    if existing is not None:
        meta = _record_workspace_id(dict(existing.metadata or {}), ws)
        updated = existing.model_copy(update={"metadata": meta})
        store.register(updated)
        return updated
    record = ProjectRecord(
        id=project_id,
        name=name,
        root=str(root),
        description="HAM default builder project for workspace chat (virtual root).",
        metadata=_record_workspace_id({}, ws),
    )
    store.register(record)
    return record
