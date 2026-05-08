"""
Read-only Factory Droid audit — thin REST seam for the Coding Agents UI.

This router intentionally exposes ONLY the ``readonly_repo_audit`` workflow.
``safe_edit_low`` (mutating, requires ``HAM_DROID_EXEC_TOKEN``) is **not**
reachable from this router. The structured chat-operator phases
``droid_preview`` / ``droid_launch`` remain the path for any other
workflow.

Endpoints:
- ``POST /api/droid/preview`` → preview an audit run for a project.
- ``POST /api/droid/launch``  → launch the previewed audit (digest-verified).

Both endpoints reuse the already-shipped functions in
``src/ham/droid_workflows/preview_launch.py``; this module is just a
thin Pydantic + Clerk seam so the frontend doesn't need to drive the
chat-operator JSON envelope.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor
from src.ham.droid_workflows.preview_launch import (
    build_droid_preview,
    execute_droid_workflow,
    verify_launch_against_preview,
)
from src.ham.droid_workflows.registry import REGISTRY_REVISION, get_workflow
from src.persistence.project_store import get_project_store

# The ONLY workflow this router exposes. Mutating workflows are deliberately
# excluded; they remain operator-JSON-only until a token-gated UX lands.
_AUDIT_WORKFLOW_ID = "readonly_repo_audit"

router = APIRouter(
    prefix="/api/droid",
    tags=["control-plane"],
    dependencies=[Depends(get_ham_clerk_actor)],
)


def _audit_workflow_or_500() -> Any:
    wf = get_workflow(_AUDIT_WORKFLOW_ID)
    if wf is None:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "DROID_AUDIT_WORKFLOW_MISSING",
                    "message": "The audit workflow is not registered on this API host.",
                }
            },
        )
    if wf.mutates:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "DROID_AUDIT_WORKFLOW_NOT_READONLY",
                    "message": "The audit workflow has been misconfigured as mutating.",
                }
            },
        )
    return wf


def _project_or_404(project_id: str) -> Any:
    store = get_project_store()
    rec = store.get_project(project_id.strip())
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PROJECT_NOT_FOUND",
                    "message": f"Unknown project_id {project_id!r}.",
                }
            },
        )
    return rec


def _created_by(actor: HamActor | None) -> dict[str, Any] | None:
    if actor is None:
        return None
    d: dict[str, Any] = {"user_id": actor.user_id}
    if actor.org_id:
        d["org_id"] = actor.org_id
    if actor.email:
        d["email"] = actor.email
    if actor.session_id:
        d["session_id"] = actor.session_id
    return d


class DroidAuditPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=180)
    user_prompt: str = Field(min_length=1, max_length=12_000)


class DroidAuditLaunchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=180)
    user_prompt: str = Field(min_length=1, max_length=12_000)
    proposal_digest: str = Field(min_length=64, max_length=64)
    base_revision: str = Field(min_length=1, max_length=64)
    confirmed: bool = False


@router.post("/preview")
async def preview_droid_audit(body: DroidAuditPreviewBody) -> dict[str, Any]:
    """Preview a read-only audit. No execution; returns a digest the launch step must echo."""
    _audit_workflow_or_500()
    rec = _project_or_404(body.project_id)
    prev = build_droid_preview(
        workflow_id=_AUDIT_WORKFLOW_ID,
        project_id=rec.id,
        project_root=Path(rec.root),
        user_prompt=body.user_prompt,
    )
    if not prev.ok:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "DROID_AUDIT_PREVIEW_BLOCKED",
                    "message": prev.blocking_reason or "Preview blocked.",
                }
            },
        )
    return {
        "kind": "droid_audit_preview",
        "project_id": rec.id,
        "project_name": rec.name,
        "user_prompt": prev.user_prompt,
        "summary_preview": prev.summary_preview,
        # Internals required for verify-on-launch — the frontend echoes them verbatim.
        "proposal_digest": prev.proposal_digest,
        "base_revision": prev.base_revision,
        # Honest, friendly product-truth flags:
        "is_readonly": True,
        "mutates": False,
    }


@router.post("/launch")
async def launch_droid_audit(
    body: DroidAuditLaunchBody,
    ham_actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    """Launch the previewed audit. Digest-verified; read-only; never accepts safe_edit_low."""
    if not body.confirmed:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "DROID_AUDIT_LAUNCH_REQUIRES_CONFIRMATION",
                    "message": "Approve the launch before sending.",
                }
            },
        )
    _audit_workflow_or_500()
    rec = _project_or_404(body.project_id)
    root = Path(rec.root)
    v_err = verify_launch_against_preview(
        workflow_id=_AUDIT_WORKFLOW_ID,
        project_id=rec.id,
        project_root=root,
        user_prompt=body.user_prompt,
        proposal_digest=body.proposal_digest,
        base_revision=body.base_revision,
    )
    if v_err:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "DROID_AUDIT_LAUNCH_PREVIEW_STALE",
                    "message": v_err,
                }
            },
        )

    launch = execute_droid_workflow(
        workflow_id=_AUDIT_WORKFLOW_ID,
        project_root=root,
        user_prompt=body.user_prompt,
        project_id=rec.id,
        proposal_digest=body.proposal_digest,
        created_by=_created_by(ham_actor),
    )
    return {
        "kind": "droid_audit_launch",
        "project_id": rec.id,
        "ok": launch.ok,
        "ham_run_id": launch.ham_run_id,
        "control_plane_status": launch.control_plane_status,
        "summary": launch.summary,
        "blocking_reason": launch.blocking_reason if not launch.ok else None,
        "is_readonly": True,
    }


__all__ = ["router", "REGISTRY_REVISION"]
