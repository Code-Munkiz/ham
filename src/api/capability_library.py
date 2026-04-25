"""HAM Capability Library — saved catalog references (Phase 1; no install, no drafts)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import resolve_ham_operator_authorization_header
from src.ham.capability_library.aggregate import build_aggregate, library_payload
from src.ham.capability_library.store import (
    CapabilityLibraryWriteConflictError,
    remove_entry,
    reorder_entries,
    save_entry,
)
from src.persistence.project_store import get_project_store

router = APIRouter(tags=["capability-library"], dependencies=[Depends(get_ham_clerk_actor)])


def _get_project_root(project_id: str) -> str:
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


def _require_capability_library_write_token(authorization: str | None) -> None:
    expected = (os.environ.get("HAM_CAPABILITY_LIBRARY_WRITE_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "CAPABILITY_LIBRARY_WRITES_DISABLED",
                    "message": "Set HAM_CAPABILITY_LIBRARY_WRITE_TOKEN to enable library mutations.",
                }
            },
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "CAPABILITY_LIBRARY_AUTH_REQUIRED",
                    "message": "Authorization: Bearer <HAM_CAPABILITY_LIBRARY_WRITE_TOKEN> required.",
                }
            },
        )
    got = authorization[7:].strip()
    if got != expected:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "CAPABILITY_LIBRARY_AUTH_INVALID",
                    "message": "Invalid capability library write token.",
                }
            },
        )


class SaveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=8, max_length=300)
    notes: str = Field(default="", max_length=4000)
    base_revision: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")


class RemoveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=8, max_length=300)
    base_revision: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")


class ReorderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: list[str] = Field(min_length=1)
    base_revision: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")


@router.get("/api/capability-library/write-status")
async def capability_library_write_status() -> dict[str, Any]:
    tok = (os.environ.get("HAM_CAPABILITY_LIBRARY_WRITE_TOKEN") or "").strip()
    return {
        "kind": "ham_capability_library_write_status",
        "writes_enabled": bool(tok),
    }


@router.get("/api/capability-library/library")
async def get_capability_library(project_id: str) -> dict[str, Any]:
    root = _get_project_root(project_id)
    try:
        return library_payload(root)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "CAPABILITY_LIBRARY_INVALID", "message": str(exc)}},
        ) from exc


@router.get("/api/capability-library/aggregate")
async def get_capability_library_aggregate(project_id: str) -> dict[str, Any]:
    root = _get_project_root(project_id)
    try:
        return build_aggregate(root)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "CAPABILITY_LIBRARY_INVALID", "message": str(exc)}},
        ) from exc


@router.post("/api/capability-library/save")
async def post_capability_library_save(
    body: SaveBody,
    project_id: str,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(
        default=None, alias="X-Ham-Operator-Authorization"
    ),
) -> dict[str, Any]:
    ham_bearer = resolve_ham_operator_authorization_header(
        authorization=authorization,
        x_ham_operator_authorization=x_ham_operator_authorization,
    )
    _require_capability_library_write_token(ham_bearer)
    root = _get_project_root(project_id)
    try:
        result = save_entry(
            Path(root),
            ref=body.ref,
            notes=body.notes,
            expect_revision=body.base_revision,
        )
    except CapabilityLibraryWriteConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "CAPABILITY_LIBRARY_CONFLICT",
                    "message": str(exc),
                }
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "CAPABILITY_LIBRARY_VALIDATION", "message": str(exc)}},
        ) from exc
    return {
        "kind": "ham_capability_library_save",
        "project_id": project_id,
        "project_root": root,
        "new_revision": result.new_revision,
        "audit_id": result.audit_id,
    }


@router.post("/api/capability-library/remove")
async def post_capability_library_remove(
    body: RemoveBody,
    project_id: str,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(
        default=None, alias="X-Ham-Operator-Authorization"
    ),
) -> dict[str, Any]:
    ham_bearer = resolve_ham_operator_authorization_header(
        authorization=authorization,
        x_ham_operator_authorization=x_ham_operator_authorization,
    )
    _require_capability_library_write_token(ham_bearer)
    root = _get_project_root(project_id)
    try:
        new_rev, audit_id, _ = remove_entry(
            Path(root),
            ref=body.ref,
            expect_revision=body.base_revision,
        )
    except CapabilityLibraryWriteConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "CAPABILITY_LIBRARY_CONFLICT",
                    "message": str(exc),
                }
            },
        ) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "CAPABILITY_LIBRARY_NOT_FOUND", "message": str(exc)}},
        ) from exc
    return {
        "kind": "ham_capability_library_remove",
        "project_id": project_id,
        "project_root": root,
        "new_revision": new_rev,
        "audit_id": audit_id,
    }


@router.post("/api/capability-library/reorder")
async def post_capability_library_reorder(
    body: ReorderBody,
    project_id: str,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(
        default=None, alias="X-Ham-Operator-Authorization"
    ),
) -> dict[str, Any]:
    ham_bearer = resolve_ham_operator_authorization_header(
        authorization=authorization,
        x_ham_operator_authorization=x_ham_operator_authorization,
    )
    _require_capability_library_write_token(ham_bearer)
    root = _get_project_root(project_id)
    try:
        new_rev, audit_id, _ = reorder_entries(
            Path(root),
            order=body.order,
            expect_revision=body.base_revision,
        )
    except CapabilityLibraryWriteConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "CAPABILITY_LIBRARY_CONFLICT",
                    "message": str(exc),
                }
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "CAPABILITY_LIBRARY_VALIDATION", "message": str(exc)}},
        ) from exc
    return {
        "kind": "ham_capability_library_reorder",
        "project_id": project_id,
        "project_root": root,
        "new_revision": new_rev,
        "audit_id": audit_id,
    }
