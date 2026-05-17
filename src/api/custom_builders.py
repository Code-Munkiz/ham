"""Workspace-scoped Custom Builder profiles API (PR 2).

Routes:

- ``GET    /api/workspaces/{workspace_id}/custom-builders`` — list profiles.
- ``POST   /api/workspaces/{workspace_id}/custom-builders`` — create profile.
- ``GET    /api/workspaces/{workspace_id}/custom-builders/{builder_id}`` — read.
- ``PATCH  /api/workspaces/{workspace_id}/custom-builders/{builder_id}`` — partial update.
- ``DELETE /api/workspaces/{workspace_id}/custom-builders/{builder_id}`` — soft delete.
- ``POST   /api/workspaces/{workspace_id}/custom-builders/preview`` — validate draft, no persistence.
- ``POST   /api/workspaces/{workspace_id}/custom-builders/{builder_id}/test-plan`` — stub conductor preview.

Auth model:

- All routes require workspace membership via ``require_perm(...)``.
- Mutating routes (POST/PATCH/DELETE) additionally require
  ``PERM_WORKSPACE_ADMIN`` plus a valid ``HAM_CUSTOM_BUILDER_WRITE_TOKEN``.
- The token is read from the ``Authorization: Bearer`` header (or
  ``X-Ham-Operator-Authorization`` when Clerk session occupies
  ``Authorization``).
- The whole feature is gated behind ``HAM_CUSTOM_BUILDER_ENABLED``; mutating
  routes return 503 when the gate is off. Read routes ignore the gate so
  operators can still inspect previously stored data.

Response bodies never include secret values. ``model_ref`` starting with
``byok:`` is masked to ``"byok:••••"`` for non-operator viewers. Operator
viewers (``ctx.role`` in ``{"owner", "admin"}``) additionally receive a
``technical_details`` block with the unmasked ``model_ref`` and a one-line
permission summary derived from the preset.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.api.dependencies.workspace import require_perm
from src.ham.clerk_auth import resolve_ham_operator_authorization_header
from src.ham.coding_router.types import ModelSourcePreference, TaskKind
from src.ham.custom_builder import (
    CustomBuilderProfile,
    public_dict,
    validate_profile,
)
from src.ham.workspace_models import WorkspaceContext
from src.ham.workspace_perms import PERM_WORKSPACE_ADMIN, PERM_WORKSPACE_READ
from src.persistence.custom_builder_store import (
    build_custom_builder_store,
    get_profile,
    list_profiles_for_workspace,
    put_profile,
    soft_delete_profile,
)

_LOG = logging.getLogger(__name__)

router = APIRouter(tags=["custom-builders"])

_PermissionPresetLiteral = Literal[
    "safe_docs",
    "app_build",
    "bug_fix",
    "refactor",
    "game_build",
    "test_write",
    "readonly_analyst",
    "custom",
]
_ReviewModeLiteral = Literal["always", "on_mutation", "on_delete_only", "never"]
_DeletionPolicyLiteral = Literal["deny", "require_review", "allow_with_warning"]
_ExternalNetworkPolicyLiteral = Literal["deny", "ask", "allow"]


_PRESET_SUMMARY: dict[str, str] = {
    "safe_docs": "read all; edits limited to docs; no delete, shell, or network",
    "app_build": "read all; edit and create allowed; delete requires review; ask before shell or network",
    "bug_fix": "read all; edit and limited create allowed; delete requires review; no install or network",
    "refactor": "read all; edit and create allowed; delete requires review; no shell or network",
    "game_build": "read all; edit and create allowed; delete requires review; ask before shell; no network",
    "test_write": "read all; edits limited to tests; no delete or network",
    "readonly_analyst": "read all; no edit, delete, shell, or network",
    "custom": "user-tightened policy on top of app_build baseline",
}


# ---------------------------------------------------------------------------
# Feature gate + write-token gate
# ---------------------------------------------------------------------------


def _feature_enabled() -> bool:
    raw = (os.environ.get("HAM_CUSTOM_BUILDER_ENABLED") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _require_feature_enabled() -> None:
    if not _feature_enabled():
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "CUSTOM_BUILDER_FEATURE_DISABLED",
                    "message": "Custom builder feature is not enabled on this server.",
                }
            },
        )


def _require_custom_builder_write_token(authorization: str | None) -> None:
    expected = (os.environ.get("HAM_CUSTOM_BUILDER_WRITE_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "CUSTOM_BUILDER_WRITES_DISABLED",
                    "message": "Custom builder writes are disabled on this server.",
                }
            },
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "CUSTOM_BUILDER_AUTH_REQUIRED",
                    "message": "Bearer write token required.",
                }
            },
        )
    if authorization[7:].strip() != expected:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "CUSTOM_BUILDER_AUTH_INVALID",
                    "message": "Invalid custom builder write token.",
                }
            },
        )


def _resolve_write_token_or_raise(
    authorization: str | None,
    x_ham_operator_authorization: str | None,
) -> None:
    _require_feature_enabled()
    bearer = resolve_ham_operator_authorization_header(
        authorization=authorization,
        x_ham_operator_authorization=x_ham_operator_authorization,
    )
    _require_custom_builder_write_token(bearer)


# ---------------------------------------------------------------------------
# Store accessor (overridable in tests)
# ---------------------------------------------------------------------------


def _get_store() -> Any:
    """Return the configured store. Rebuilt each call so tests can isolate
    via ``HAM_CUSTOM_BUILDER_LOCAL_PATH`` without import-time caching."""
    return build_custom_builder_store()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateBuilderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    builder_id: str
    name: str
    description: str = ""
    intent_tags: list[str] = Field(default_factory=list)
    task_kinds: list[TaskKind] = Field(default_factory=list)
    model_source: ModelSourcePreference = "ham_default"
    model_ref: str | None = None
    permission_preset: _PermissionPresetLiteral = "app_build"
    allowed_paths: list[str] = Field(default_factory=list)
    denied_paths: list[str] = Field(default_factory=list)
    denied_operations: list[str] = Field(default_factory=list)
    review_mode: _ReviewModeLiteral = "on_mutation"
    deletion_policy: _DeletionPolicyLiteral = "require_review"
    external_network_policy: _ExternalNetworkPolicyLiteral = "deny"
    enabled: bool = True


class PatchBuilderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    intent_tags: list[str] | None = None
    task_kinds: list[TaskKind] | None = None
    model_source: ModelSourcePreference | None = None
    model_ref: str | None = None
    permission_preset: _PermissionPresetLiteral | None = None
    allowed_paths: list[str] | None = None
    denied_paths: list[str] | None = None
    denied_operations: list[str] | None = None
    review_mode: _ReviewModeLiteral | None = None
    deletion_policy: _DeletionPolicyLiteral | None = None
    external_network_policy: _ExternalNetworkPolicyLiteral | None = None
    enabled: bool | None = None


class PreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    builder_id: str | None = None
    name: str
    description: str = ""
    intent_tags: list[str] = Field(default_factory=list)
    task_kinds: list[TaskKind] = Field(default_factory=list)
    model_source: ModelSourcePreference = "ham_default"
    model_ref: str | None = None
    permission_preset: _PermissionPresetLiteral = "app_build"
    allowed_paths: list[str] = Field(default_factory=list)
    denied_paths: list[str] = Field(default_factory=list)
    denied_operations: list[str] = Field(default_factory=list)
    review_mode: _ReviewModeLiteral = "on_mutation"
    deletion_policy: _DeletionPolicyLiteral = "require_review"
    external_network_policy: _ExternalNetworkPolicyLiteral = "deny"
    enabled: bool = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _is_operator(ctx: WorkspaceContext) -> bool:
    return ctx.role in ("owner", "admin")


def _mask_model_ref(model_ref: str | None) -> str | None:
    if model_ref is None:
        return None
    if model_ref.startswith("byok:"):
        return "byok:••••"
    return model_ref


_USER_INVISIBLE_FIELDS: frozenset[str] = frozenset({"preferred_harness", "allowed_harnesses"})


def _profile_to_public_response(profile: CustomBuilderProfile, *, operator: bool) -> dict[str, Any]:
    raw = {k: v for k, v in public_dict(profile).items() if k not in _USER_INVISIBLE_FIELDS}
    raw["model_ref"] = _mask_model_ref(profile.model_ref)
    if operator:
        raw["technical_details"] = {
            "harness": "opencode_cli",
            "compiled_permission_summary": _PRESET_SUMMARY.get(
                profile.permission_preset, _PRESET_SUMMARY["app_build"]
            ),
            "model_ref": profile.model_ref,
        }
    return raw


def _validation_error_payload(message: str) -> dict[str, Any]:
    return {
        "error": {
            "code": "CUSTOM_BUILDER_VALIDATION",
            "message": message,
        }
    }


def _not_found_payload() -> dict[str, Any]:
    return {
        "error": {
            "code": "CUSTOM_BUILDER_NOT_FOUND",
            "message": "Builder not found in this workspace.",
        }
    }


def _conflict_payload() -> dict[str, Any]:
    return {
        "error": {
            "code": "CUSTOM_BUILDER_CONFLICT",
            "message": "Builder id already exists.",
        }
    }


def _build_profile_from_create(
    body: CreateBuilderBody,
    *,
    workspace_id: str,
    owner_user_id: str,
) -> CustomBuilderProfile:
    now = _now_iso()
    return CustomBuilderProfile(
        builder_id=body.builder_id,
        workspace_id=workspace_id,
        owner_user_id=owner_user_id,
        name=body.name,
        description=body.description,
        intent_tags=list(body.intent_tags),
        task_kinds=list(body.task_kinds),
        model_source=body.model_source,
        model_ref=body.model_ref,
        permission_preset=body.permission_preset,
        allowed_paths=list(body.allowed_paths),
        denied_paths=list(body.denied_paths),
        denied_operations=list(body.denied_operations),
        review_mode=body.review_mode,
        deletion_policy=body.deletion_policy,
        external_network_policy=body.external_network_policy,
        enabled=body.enabled,
        created_at=now,
        updated_at=now,
        updated_by=owner_user_id,
    )


def _merge_patch(
    existing: CustomBuilderProfile,
    patch: PatchBuilderBody,
    *,
    actor_user_id: str,
) -> CustomBuilderProfile:
    updates = patch.model_dump(exclude_none=True)
    updates["updated_at"] = _now_iso()
    updates["updated_by"] = actor_user_id
    return existing.model_copy(update=updates)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/api/workspaces/{workspace_id}/custom-builders")
async def list_custom_builders(
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    store = _get_store()
    profiles = list_profiles_for_workspace(store, ctx.workspace_id)
    operator = _is_operator(ctx)
    return {
        "workspace_id": ctx.workspace_id,
        "builders": [_profile_to_public_response(p, operator=operator) for p in profiles],
    }


@router.get("/api/workspaces/{workspace_id}/custom-builders/{builder_id}")
async def get_custom_builder(
    builder_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    store = _get_store()
    profile = get_profile(store, ctx.workspace_id, builder_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=_not_found_payload())
    return _profile_to_public_response(profile, operator=_is_operator(ctx))


@router.post("/api/workspaces/{workspace_id}/custom-builders")
async def create_custom_builder(
    body: CreateBuilderBody,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_ADMIN))],
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(
        default=None, alias="X-Ham-Operator-Authorization"
    ),
) -> dict[str, Any]:
    _resolve_write_token_or_raise(authorization, x_ham_operator_authorization)
    store = _get_store()
    existing = get_profile(store, ctx.workspace_id, body.builder_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail=_conflict_payload())
    try:
        profile = _build_profile_from_create(
            body,
            workspace_id=ctx.workspace_id,
            owner_user_id=ctx.actor_user_id or "unknown",
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_error_payload(str(exc))) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_validation_error_payload(str(exc))) from exc
    put_profile(store, profile)
    _LOG.info(
        "custom_builder created: workspace=%s builder=%s preset=%s",
        ctx.workspace_id,
        profile.builder_id,
        profile.permission_preset,
    )
    return _profile_to_public_response(profile, operator=_is_operator(ctx))


@router.patch("/api/workspaces/{workspace_id}/custom-builders/{builder_id}")
async def patch_custom_builder(
    builder_id: str,
    body: PatchBuilderBody,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_ADMIN))],
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(
        default=None, alias="X-Ham-Operator-Authorization"
    ),
) -> dict[str, Any]:
    _resolve_write_token_or_raise(authorization, x_ham_operator_authorization)
    store = _get_store()
    existing = get_profile(store, ctx.workspace_id, builder_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=_not_found_payload())
    try:
        merged = _merge_patch(existing, body, actor_user_id=ctx.actor_user_id or "unknown")
        validate_profile(merged)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_error_payload(str(exc))) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_validation_error_payload(str(exc))) from exc
    put_profile(store, merged)
    _LOG.info(
        "custom_builder patched: workspace=%s builder=%s",
        ctx.workspace_id,
        merged.builder_id,
    )
    return _profile_to_public_response(merged, operator=_is_operator(ctx))


@router.delete("/api/workspaces/{workspace_id}/custom-builders/{builder_id}")
async def delete_custom_builder(
    builder_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_ADMIN))],
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(
        default=None, alias="X-Ham-Operator-Authorization"
    ),
) -> dict[str, Any]:
    _resolve_write_token_or_raise(authorization, x_ham_operator_authorization)
    store = _get_store()
    updated = soft_delete_profile(
        store,
        ctx.workspace_id,
        builder_id,
        updated_by=ctx.actor_user_id or "unknown",
        updated_at=_now_iso(),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=_not_found_payload())
    _LOG.info(
        "custom_builder soft-deleted: workspace=%s builder=%s",
        ctx.workspace_id,
        builder_id,
    )
    return {
        "workspace_id": ctx.workspace_id,
        "builder_id": builder_id,
        "enabled": False,
        "soft_deleted": True,
    }


@router.post("/api/workspaces/{workspace_id}/custom-builders/preview")
async def preview_custom_builder(
    body: PreviewBody,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    builder_id = body.builder_id or "draft-builder"
    now = _now_iso()
    errors: list[str] = []
    try:
        CustomBuilderProfile(
            builder_id=builder_id,
            workspace_id=ctx.workspace_id,
            owner_user_id=ctx.actor_user_id or "unknown",
            name=body.name,
            description=body.description,
            intent_tags=list(body.intent_tags),
            task_kinds=list(body.task_kinds),
            model_source=body.model_source,
            model_ref=body.model_ref,
            permission_preset=body.permission_preset,
            allowed_paths=list(body.allowed_paths),
            denied_paths=list(body.denied_paths),
            denied_operations=list(body.denied_operations),
            review_mode=body.review_mode,
            deletion_policy=body.deletion_policy,
            external_network_policy=body.external_network_policy,
            enabled=body.enabled,
            created_at=now,
            updated_at=now,
            updated_by=ctx.actor_user_id or "unknown",
        )
    except ValidationError as exc:
        errors = [str(err.get("msg") or err) for err in exc.errors()]
    except ValueError as exc:
        errors = [str(exc)]
    valid = not errors
    return {
        "valid": valid,
        "summary": {
            "name": body.name,
            "permission_preset": body.permission_preset,
            "review_mode": body.review_mode,
            "model_source": body.model_source,
        },
        "errors": errors,
    }


@router.post("/api/workspaces/{workspace_id}/custom-builders/{builder_id}/test-plan")
async def test_plan_custom_builder(
    builder_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    store = _get_store()
    profile = get_profile(store, ctx.workspace_id, builder_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=_not_found_payload())
    return {
        "workspace_id": ctx.workspace_id,
        "builder_id": builder_id,
        "candidates": [
            {
                "builder_id": profile.builder_id,
                "builder_name": profile.name,
                "task_kind": "feature",
                "would_be_chosen": True,
            }
        ],
        "note": "Conductor integration lands in PR 4.",
    }


__all__ = ["router"]
