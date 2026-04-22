"""Hermes runtime skills — catalog, host probe (Phase 1), shared install preview/apply (Phase 2a).

Distinct from Cursor operator skills: ``GET /api/cursor-skills`` indexes ``.cursor/skills``.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import resolve_ham_operator_authorization_header
from pydantic import BaseModel, ConfigDict, Field

from src.ham.hermes_skills_catalog import (
    catalog_note,
    catalog_schema_version,
    catalog_upstream_meta,
    get_catalog_entry_detail,
    list_catalog_entries,
)
from src.ham.hermes_skills_install import (
    HermesSkillInstallError,
    assert_shared_target,
    apply_shared_install,
    capability_extension_fields,
    preview_shared_install,
    skills_apply_writes_enabled,
)
from src.ham.hermes_skills_probe import list_hermes_targets, probe_capabilities

router = APIRouter(tags=["hermes-skills"], dependencies=[Depends(get_ham_clerk_actor)])


def _not_found(catalog_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": "HERMES_SKILL_CATALOG_UNKNOWN",
                "message": f"No Hermes catalog entry for id {catalog_id!r}.",
            }
        },
    )


@router.get("/api/hermes-skills/catalog")
async def get_hermes_skills_catalog() -> dict[str, Any]:
    """Curated Hermes-runtime skill entries (read-only)."""
    entries = list_catalog_entries()
    payload: dict[str, Any] = {
        "kind": "hermes_runtime_skills_catalog",
        "schema_version": catalog_schema_version(),
        "count": len(entries),
        "entries": entries,
    }
    up = catalog_upstream_meta()
    if up:
        payload["upstream"] = up
    note = catalog_note()
    if note:
        payload["catalog_note"] = note
    return payload


@router.get("/api/hermes-skills/catalog/{catalog_id}")
async def get_hermes_skill_catalog_entry(catalog_id: str) -> dict[str, Any]:
    """Single catalog entry with inspection metadata (read-only)."""
    detail = get_catalog_entry_detail(catalog_id)
    if detail is None:
        raise _not_found(catalog_id)
    return {"kind": "hermes_runtime_skill_detail", "entry": detail}


@router.get("/api/hermes-skills/capabilities")
async def get_hermes_skills_capabilities() -> dict[str, Any]:
    """Whether this API host can observe / manage local Hermes runtime skills (Phase 2a: shared install)."""
    caps = dict(probe_capabilities())
    ext = capability_extension_fields()
    caps["shared_runtime_install_supported"] = ext["shared_runtime_install_supported"]
    caps["skills_apply_writes_enabled"] = ext["skills_apply_writes_enabled"]
    caps["warnings"] = list(caps.get("warnings") or []) + list(ext.get("install_readiness_warnings") or [])
    return {"kind": "hermes_skills_capabilities", **caps}


class InstallPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_id: str = Field(min_length=1, max_length=512)
    target: dict[str, Any]
    client_proposal_id: str | None = Field(default=None, max_length=128)


class InstallApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_id: str = Field(min_length=1, max_length=512)
    target: dict[str, Any]
    proposal_digest: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    base_revision: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    client_proposal_id: str | None = Field(default=None, max_length=128)


def _install_error(exc: HermesSkillInstallError) -> HTTPException:
    code = exc.code
    status = 400
    if code == "SKILL_NOT_IN_CATALOG":
        status = 404
    elif code == "APPLY_CONFLICT":
        status = 409
    return HTTPException(
        status_code=status,
        detail={"error": {"code": code, "message": exc.message}},
    )


def _require_skills_write_token(authorization: str | None) -> None:
    expected = (os.environ.get("HAM_SKILLS_WRITE_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "TOKEN_REQUIRED",
                    "message": "HAM_SKILLS_WRITE_TOKEN is not set; apply is disabled on this server.",
                }
            },
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "TOKEN_REQUIRED",
                    "message": "Authorization: Bearer <HAM_SKILLS_WRITE_TOKEN> required.",
                }
            },
        )
    got = authorization[7:].strip()
    if got != expected:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "INVALID_TOKEN",
                    "message": "Invalid Hermes skills write token.",
                }
            },
        )


@router.get("/api/hermes-skills/install/write-status")
async def get_hermes_skills_install_write_status() -> dict[str, Any]:
    """Whether apply is enabled (server has HAM_SKILLS_WRITE_TOKEN); does not reveal the secret."""
    return {"writes_enabled": skills_apply_writes_enabled()}


@router.post("/api/hermes-skills/install/preview")
async def post_hermes_skills_install_preview(body: InstallPreviewRequest) -> dict[str, Any]:
    """Dry-run shared install: no filesystem mutations."""
    try:
        assert_shared_target(body.target)
        result = preview_shared_install(
            body.catalog_id,
            client_proposal_id=body.client_proposal_id,
        )
    except HermesSkillInstallError as exc:
        raise _install_error(exc) from exc
    return {
        "kind": "hermes_skills_install_preview",
        "catalog_id": result.catalog_id,
        "target": result.target,
        "client_proposal_id": body.client_proposal_id,
        "paths_touched": result.paths_touched,
        "config_path": result.config_path,
        "config_diff": result.config_diff,
        "config_snippet_after": result.config_snippet_after,
        "warnings": result.warnings,
        "proposal_digest": result.proposal_digest,
        "base_revision": result.base_revision,
        "bundle_dest": result.bundle_dest,
        "entry": result.entry_summary,
    }


@router.post("/api/hermes-skills/install/apply")
async def post_hermes_skills_install_apply(
    body: InstallApplyRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(None, alias="X-Ham-Operator-Authorization"),
) -> dict[str, Any]:
    """Apply shared install: token, lock, backup, bundle materialize, atomic config write, audit."""
    ham_bearer = resolve_ham_operator_authorization_header(
        authorization=authorization,
        x_ham_operator_authorization=x_ham_operator_authorization,
    )
    _require_skills_write_token(ham_bearer)
    try:
        assert_shared_target(body.target)
        result = apply_shared_install(
            body.catalog_id,
            proposal_digest=body.proposal_digest,
            base_revision=body.base_revision,
        )
    except HermesSkillInstallError as exc:
        raise _install_error(exc) from exc
    return {
        "kind": "hermes_skills_install_apply",
        "audit_id": result.audit_id,
        "backup_id": result.backup_id,
        "catalog_id": result.catalog_id,
        "target": result.target,
        "installed_paths": result.installed_paths,
        "new_revision": result.new_revision,
        "warnings": result.warnings,
        "client_proposal_id": body.client_proposal_id,
    }


@router.get("/api/hermes-skills/targets")
async def get_hermes_skills_targets() -> dict[str, Any]:
    """Read-only install targets (shared + Hermes profiles); no Ham IntentProfile or Cursor subagents."""
    payload = list_hermes_targets()
    # Avoid duplicating full capabilities twice in normal responses; targets list is primary.
    return {
        "kind": "hermes_skills_targets",
        "targets": payload["targets"],
        "capabilities_summary": {
            "mode": payload["capabilities"].get("mode"),
            "hermes_home_detected": payload["capabilities"].get("hermes_home_detected"),
            "profile_listing_supported": payload["capabilities"].get("profile_listing_supported"),
        },
        "warnings": list(payload["capabilities"].get("warnings") or []),
    }
