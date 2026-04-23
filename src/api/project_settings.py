"""Project-scoped allowlisted settings preview / apply / rollback (v1)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import resolve_ham_operator_authorization_header
from pydantic import BaseModel, ConfigDict, Field

from src.ham.settings_write import (
    ApplyResult,
    PreviewResult,
    RollbackResult,
    SettingsChanges,
    SettingsWriteConflictError,
    preview_project_settings,
    apply_project_settings,
    rollback_project_settings,
    settings_writes_enabled,
)

router = APIRouter(tags=["settings"])


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changes: SettingsChanges
    client_proposal_id: str | None = Field(default=None, max_length=128)


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changes: SettingsChanges
    base_revision: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backup_id: str = Field(min_length=1, max_length=180)


def _get_project_root(project_id: str) -> str:
    from src.persistence.project_store import get_project_store

    store = get_project_store()
    record = store.get_project(project_id)
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
    return record.root


def _require_settings_write_token(authorization: str | None) -> None:
    expected = (os.environ.get("HAM_SETTINGS_WRITE_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "SETTINGS_WRITES_DISABLED",
                    "message": "Set HAM_SETTINGS_WRITE_TOKEN to enable apply and rollback.",
                }
            },
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "SETTINGS_AUTH_REQUIRED",
                    "message": "Authorization: Bearer <HAM_SETTINGS_WRITE_TOKEN> required.",
                }
            },
        )
    got = authorization[7:].strip()
    if got != expected:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "SETTINGS_AUTH_INVALID",
                    "message": "Invalid settings write token.",
                }
            },
        )


def _preview_payload(
    result: PreviewResult,
    *,
    project_id: str,
    project_root: str,
    client_proposal_id: str | None,
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "project_root": project_root,
        "client_proposal_id": client_proposal_id,
        "effective_before": result.effective_before,
        "effective_after": result.effective_after,
        "diff": result.diff,
        "warnings": result.warnings,
        "write_target": result.write_target,
        "proposal_digest": result.proposal_digest,
        "base_revision": result.base_revision,
    }


@router.post("/api/projects/{project_id}/settings/preview")
async def post_settings_preview(project_id: str, body: PreviewRequest) -> dict[str, Any]:
    root = _get_project_root(project_id)
    try:
        result = preview_project_settings(Path(root), body.changes)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "SETTINGS_PREVIEW_INVALID",
                    "message": str(exc),
                }
            },
        ) from exc
    return _preview_payload(
        result,
        project_id=project_id,
        project_root=root,
        client_proposal_id=body.client_proposal_id,
    )


@router.post("/api/projects/{project_id}/settings/apply")
async def post_settings_apply(
    project_id: str,
    body: ApplyRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(None, alias="X-Ham-Operator-Authorization"),
) -> dict[str, Any]:
    ham_bearer = resolve_ham_operator_authorization_header(
        authorization=authorization,
        x_ham_operator_authorization=x_ham_operator_authorization,
    )
    _require_settings_write_token(ham_bearer)
    root = _get_project_root(project_id)
    try:
        result: ApplyResult = apply_project_settings(
            Path(root),
            body.changes,
            base_revision=body.base_revision,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "SETTINGS_APPLY_INVALID",
                    "message": str(exc),
                }
            },
        ) from exc
    except SettingsWriteConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "SETTINGS_CONFLICT",
                    "message": str(exc),
                }
            },
        ) from exc
    return {
        "project_id": project_id,
        "project_root": root,
        "backup_id": result.backup_id,
        "audit_id": result.audit_id,
        "effective_after": result.effective_after,
        "diff_applied": result.diff_applied,
        "new_revision": result.new_revision,
    }


@router.post("/api/projects/{project_id}/settings/rollback")
async def post_settings_rollback(
    project_id: str,
    body: RollbackRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(None, alias="X-Ham-Operator-Authorization"),
) -> dict[str, Any]:
    ham_bearer = resolve_ham_operator_authorization_header(
        authorization=authorization,
        x_ham_operator_authorization=x_ham_operator_authorization,
    )
    _require_settings_write_token(ham_bearer)
    root = _get_project_root(project_id)
    try:
        result: RollbackResult = rollback_project_settings(
            Path(root),
            body.backup_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SETTINGS_BACKUP_NOT_FOUND",
                    "message": str(exc),
                }
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "SETTINGS_ROLLBACK_INVALID",
                    "message": str(exc),
                }
            },
        ) from exc
    return {
        "project_id": project_id,
        "project_root": root,
        "pre_rollback_backup_id": result.backup_id,
        "audit_id": result.audit_id,
        "effective_after": result.effective_after,
        "new_revision": result.new_revision,
    }


@router.get("/api/settings/write-status")
async def get_settings_write_status() -> dict[str, Any]:
    """Whether apply/rollback are enabled (token set); does not reveal the token."""
    return {"writes_enabled": settings_writes_enabled()}
