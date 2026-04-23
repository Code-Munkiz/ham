"""
Read-only API for HAM `ControlPlaneRun` records (durable control-plane launch facts).

This is not mission orchestration, queues, or graphs — only what HAM already persisted.
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor
from src.persistence.control_plane_run import ControlPlaneRun, ControlPlaneRunStore

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)

_store = ControlPlaneRunStore()

router = APIRouter(prefix="/api/control-plane-runs", tags=["control-plane-runs"])


def _public_run(r: ControlPlaneRun) -> dict[str, Any]:
    """HAM-safe, bounded fields only — no digests, project_root, or created_by."""
    return {
        "ham_run_id": r.ham_run_id,
        "provider": r.provider,
        "action_kind": r.action_kind,
        "project_id": r.project_id,
        "status": r.status,
        "status_reason": r.status_reason,
        "external_id": r.external_id,
        "workflow_id": r.workflow_id,
        "summary": r.summary,
        "error_summary": r.error_summary,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
        "committed_at": r.committed_at,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
        "last_observed_at": r.last_observed_at,
        "last_provider_status": r.last_provider_status,
        "audit_ref": r.audit_ref.model_dump(mode="json", exclude_none=True) if r.audit_ref else None,
    }


def _get_project_or_404(project_id: str) -> None:
    from src.persistence.project_store import get_project_store

    st = get_project_store()
    if st.get_project(project_id.strip()) is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PROJECT_NOT_FOUND",
                    "message": f"Unknown project_id {project_id!r}.",
                }
            },
        )


@router.get("")
async def list_control_plane_runs(
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    project_id: str = Query(..., min_length=1, max_length=180, description="Registered HAM project id (required)"),
    provider: str | None = Query(
        default=None,
        max_length=64,
        description="Optional exact provider filter (e.g. cursor_cloud_agent, factory_droid).",
    ),
    limit: int = Query(50, ge=1, le=500, description="Max rows to return (newest first)"),
) -> dict[str, Any]:
    _get_project_or_404(project_id)
    prov = (provider or "").strip() or None
    runs = _store.list_for_project(project_id, provider=prov, limit=limit)
    return {
        "kind": "control_plane_run_list",
        "project_id": project_id.strip(),
        "limit": limit,
        "provider_filter": prov,
        "runs": [_public_run(r) for r in runs],
    }


@router.get("/{ham_run_id}")
async def get_control_plane_run(
    ham_run_id: str,
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    if not _UUID_RE.match(ham_run_id.strip()):
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "CONTROL_PLANE_RUN_NOT_FOUND",
                    "message": "No control-plane run with that id.",
                }
            },
        )
    r = _store.get(ham_run_id.strip())
    if r is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "CONTROL_PLANE_RUN_NOT_FOUND",
                    "message": f"No control-plane run {ham_run_id!r}.",
                }
            },
        )
    return {
        "kind": "control_plane_run",
        "run": _public_run(r),
    }
