"""
``/api/workspaces`` router (Phase 1b).

Routes:

- ``GET    /api/workspaces``                                   — list (filter by org_id, include_archived)
- ``POST   /api/workspaces``                                   — create
- ``GET    /api/workspaces/{workspace_id}``                    — get one
- ``PATCH  /api/workspaces/{workspace_id}``                    — update name / description
- ``DELETE /api/workspaces/{workspace_id}``                    — soft archive (confirmation phrase)
- ``GET    /api/workspaces/{workspace_id}/members``            — list members
- ``POST/PATCH/DELETE /api/workspaces/{workspace_id}/members*`` — scaffolded; 501 unless
  ``HAM_WORKSPACE_MEMBER_WRITES=true`` (Phase 1d). Permission gate runs **before** the
  501 so non-admins still see ``403``.

All workspace-scoped routes use ``require_workspace`` + ``require_perm``.
List/create/me-style routes use the actor-only ``require_actor`` dep.

No secret material is ever written to or read from any document touched by
this router; the workspace mirror collections (``users``, ``orgs``,
``memberships``, ``workspaces``, ``workspaces/{wid}/members``) are
metadata-only.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from src.api.dependencies.auth import require_actor
from src.api.dependencies.workspace import (
    get_workspace_store,
    require_perm,
)
from src.ham.clerk_auth import HamActor
from src.ham.operator_audit import append_operator_action_audit
from src.ham.workspace_models import (
    DESCRIPTION_MAX_LEN,
    NAME_MAX_LEN,
    NAME_MIN_LEN,
    SLUG_MAX_LEN,
    WorkspaceContext,
    WorkspaceMember,
    WorkspaceRecord,
    is_valid_slug,
)
from src.ham.workspace_perms import (
    PERM_MEMBER_READ,
    PERM_MEMBER_WRITE,
    PERM_WORKSPACE_ADMIN,
    PERM_WORKSPACE_READ,
    PERM_WORKSPACE_WRITE,
    map_org_role_to_workspace_role,
    perms_for_role,
)
from src.ham.workspace_serializers import (
    derive_unique_slug,
    member_response,
    pick_default_workspace_id,
    slugify_name,
    validate_workspace_name,
    workspace_response,
    workspace_summary,
)
from src.persistence.workspace_store import (
    WorkspaceSlugConflict,
    WorkspaceStore,
    new_workspace_id,
)

router = APIRouter(tags=["workspaces"])
_LOG = logging.getLogger(__name__)

MEMBER_WRITES_ENV = "HAM_WORKSPACE_MEMBER_WRITES"
ARCHIVE_PHRASE_TEMPLATE = "ARCHIVE WORKSPACE {slug}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _member_writes_enabled() -> bool:
    raw = (os.environ.get(MEMBER_WRITES_ENV) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _http_error(status_code: int, code: str, message: str, **extra: Any) -> HTTPException:
    detail: dict[str, Any] = {"error": {"code": code, "message": message}}
    if extra:
        detail["error"].update(extra)
    return HTTPException(status_code=status_code, detail=detail)


def _audit(action: str, ctx_or_actor: WorkspaceContext | HamActor, **fields: Any) -> str:
    base: dict[str, Any]
    if isinstance(ctx_or_actor, WorkspaceContext):
        base = ctx_or_actor.attribution()
    else:
        base = {
            "user_id": ctx_or_actor.user_id,
            "email": ctx_or_actor.email,
            "org_id": ctx_or_actor.org_id,
            "org_role": ctx_or_actor.org_role,
            "role": None,
            "perms": sorted(ctx_or_actor.permissions),
            "workspace_id": fields.get("workspace_id"),
        }
    payload = {"action": action, **base, **fields}
    return append_operator_action_audit(payload)


def _role_for_listing(
    rec: WorkspaceRecord,
    actor: HamActor,
    store: WorkspaceStore,
) -> str:
    member = store.get_member(rec.workspace_id, actor.user_id)
    if member is not None:
        return member.role
    if rec.org_id is None:
        return "owner" if actor.user_id == rec.owner_user_id else "viewer"
    return map_org_role_to_workspace_role(actor.org_role)


def _summaries_for_actor(
    actor: HamActor,
    store: WorkspaceStore,
    *,
    org_id: str | None,
    include_archived: bool,
) -> list[dict[str, Any]]:
    records = store.list_workspaces_for_user(
        actor.user_id,
        org_id=org_id,
        include_archived=include_archived,
    )
    out: list[dict[str, Any]] = []
    for rec in records:
        role = _role_for_listing(rec, actor, store)
        out.append(workspace_summary(rec, role=role))  # type: ignore[arg-type]
    return out


# ---------------------------------------------------------------------------
# Pydantic request bodies
# ---------------------------------------------------------------------------


class CreateWorkspaceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=NAME_MIN_LEN, max_length=NAME_MAX_LEN)
    slug: str | None = Field(default=None, max_length=SLUG_MAX_LEN)
    description: str = Field(default="", max_length=DESCRIPTION_MAX_LEN)
    org_id: str | None = Field(default=None, max_length=128)


class PatchWorkspaceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=NAME_MIN_LEN, max_length=NAME_MAX_LEN)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LEN)


class ArchiveWorkspaceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_phrase: str = Field(min_length=1, max_length=512)


class MemberWriteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str | None = Field(default=None, max_length=128)
    role: str | None = Field(default=None, max_length=32)


# ---------------------------------------------------------------------------
# Routes — actor-only (no workspace_id path)
# ---------------------------------------------------------------------------


@router.get("/api/workspaces")
async def list_workspaces(
    actor: Annotated[HamActor, Depends(require_actor)],
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
    org_id: Annotated[str | None, Query(max_length=128)] = None,
    include_archived: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    summaries = _summaries_for_actor(
        actor,
        store,
        org_id=org_id,
        include_archived=include_archived,
    )
    default_id = pick_default_workspace_id(summaries)
    for s in summaries:
        s["is_default"] = s["workspace_id"] == default_id
    return {"workspaces": summaries, "default_workspace_id": default_id}


@router.post("/api/workspaces", status_code=201)
async def create_workspace(
    body: CreateWorkspaceBody,
    actor: Annotated[HamActor, Depends(require_actor)],
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
) -> dict[str, Any]:
    name = body.name.strip()
    err = validate_workspace_name(name)
    if err:
        raise _http_error(422, "HAM_WORKSPACE_INVALID", err)

    desired_slug = (body.slug or "").strip().lower() or slugify_name(name)
    if desired_slug and not is_valid_slug(desired_slug):
        raise _http_error(
            422,
            "HAM_WORKSPACE_INVALID",
            "slug must match ^[a-z0-9](-?[a-z0-9])*$",
        )
    if not desired_slug:
        raise _http_error(
            422,
            "HAM_WORKSPACE_INVALID",
            "Could not derive a slug from name; provide an explicit slug.",
        )

    target_org_id = body.org_id
    if target_org_id is not None:
        if actor.org_id != target_org_id:
            raise _http_error(
                403,
                "HAM_ORG_MISMATCH",
                "Actor's Clerk org_id does not match requested org_id.",
            )
        if (actor.org_role or "") != "org:admin":
            raise _http_error(
                403,
                "HAM_ORG_ADMIN_REQUIRED",
                "Creating a workspace under an organization requires the org:admin role.",
            )

    def _is_taken(slug: str) -> bool:
        for rec in store.list_workspaces_for_user(
            actor.user_id,
            org_id=target_org_id,
            include_archived=False,
        ):
            scope_match = (
                rec.org_id == target_org_id
                if target_org_id is not None
                else (rec.org_id is None and rec.owner_user_id == actor.user_id)
            )
            if scope_match and rec.slug == slug:
                return True
        return False

    chosen_slug = (
        desired_slug
        if not _is_taken(desired_slug)
        else derive_unique_slug(desired_slug, is_taken=_is_taken)
    )
    if chosen_slug is None:
        raise _http_error(
            409,
            "HAM_WORKSPACE_SLUG_CONFLICT",
            f"slug {desired_slug!r} is already taken in this scope.",
            slug=desired_slug,
        )

    now = _utc_now()
    rec = WorkspaceRecord(
        workspace_id=new_workspace_id(),
        org_id=target_org_id,
        owner_user_id=actor.user_id,
        name=name,
        slug=chosen_slug,
        description=body.description,
        status="active",
        created_by=actor.user_id,
        created_at=now,
        updated_at=now,
    )
    try:
        store.create_workspace(rec)
    except WorkspaceSlugConflict as exc:
        # Race against a parallel POST — surface as 409.
        raise _http_error(
            409,
            "HAM_WORKSPACE_SLUG_CONFLICT",
            str(exc),
            slug=chosen_slug,
        ) from exc
    store.upsert_member(
        WorkspaceMember(
            user_id=actor.user_id,
            workspace_id=rec.workspace_id,
            role="owner",
            added_by=actor.user_id,
            added_at=now,
        ),
    )
    audit_id = _audit(
        "workspace.create",
        actor,
        workspace_id=rec.workspace_id,
        slug=chosen_slug,
        org_id=target_org_id,
    )
    return {
        "workspace": workspace_summary(
            rec,
            role="owner",
            perms=perms_for_role("owner"),
            is_default=False,
        ),
        "context": {
            "role": "owner",
            "perms": sorted(perms_for_role("owner")),
            "org_role": actor.org_role,
        },
        "audit_id": audit_id,
    }


# ---------------------------------------------------------------------------
# Routes — workspace-scoped (require_workspace + require_perm)
# ---------------------------------------------------------------------------


@router.get("/api/workspaces/{workspace_id}")
async def get_workspace(
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
) -> dict[str, Any]:
    rec = store.get_workspace(ctx.workspace_id)
    # Resolver already returned 404 if record was missing or archived.
    assert rec is not None  # noqa: S101
    return workspace_response(rec, ctx)


@router.patch("/api/workspaces/{workspace_id}")
async def patch_workspace(
    body: PatchWorkspaceBody,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
) -> dict[str, Any]:
    if body.name is not None:
        err = validate_workspace_name(body.name)
        if err:
            raise _http_error(422, "HAM_WORKSPACE_INVALID", err)
    rec = store.update_workspace(
        ctx.workspace_id,
        name=body.name.strip() if body.name is not None else None,
        description=body.description if body.description is not None else None,
        updated_at=_utc_now(),
    )
    audit_id = _audit(
        "workspace.patch",
        ctx,
        workspace_id=ctx.workspace_id,
        fields={
            "name": body.name is not None,
            "description": body.description is not None,
        },
    )
    payload = workspace_response(rec, ctx)
    payload["audit_id"] = audit_id
    return payload


@router.delete("/api/workspaces/{workspace_id}")
async def archive_workspace(
    body: ArchiveWorkspaceBody,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_ADMIN))],
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
) -> dict[str, Any]:
    rec = store.get_workspace(ctx.workspace_id)
    assert rec is not None  # noqa: S101  # resolver guarantees presence
    expected_phrase = ARCHIVE_PHRASE_TEMPLATE.format(slug=rec.slug)
    if (body.confirmation_phrase or "").strip() != expected_phrase:
        raise _http_error(
            403,
            "HAM_PHRASE_INVALID",
            f"confirmation_phrase must equal {expected_phrase!r}.",
            expected_phrase_template=ARCHIVE_PHRASE_TEMPLATE,
        )
    archived = store.update_workspace(
        ctx.workspace_id,
        status="archived",
        updated_at=_utc_now(),
    )
    audit_id = _audit(
        "workspace.archive",
        ctx,
        workspace_id=ctx.workspace_id,
        slug=rec.slug,
    )
    payload = workspace_response(archived, ctx)
    payload["audit_id"] = audit_id
    return payload


@router.get("/api/workspaces/{workspace_id}/members")
async def list_workspace_members(
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_MEMBER_READ))],
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
) -> dict[str, Any]:
    members = store.list_members(ctx.workspace_id)
    fallback_in_use = (
        ctx.raw.get("membership_source") == "org_fallback" if isinstance(ctx.raw, dict) else False
    )

    def _email_for(uid: str) -> str | None:
        u = store.get_user(uid)
        return u.email if u else None

    role_priority = {"owner": 0, "admin": 1, "member": 2, "viewer": 3}
    members_sorted = sorted(
        members,
        key=lambda m: (
            role_priority.get(m.role, 9),
            -(m.added_at.timestamp() if m.added_at else 0),
        ),
    )
    return {
        "members": [member_response(m, email=_email_for(m.user_id)) for m in members_sorted],
        "fallback_org_role_in_use": bool(fallback_in_use),
    }


# ---------------------------------------------------------------------------
# Member writes — scaffolded behind HAM_WORKSPACE_MEMBER_WRITES (PR 1d)
# ---------------------------------------------------------------------------


def _maybe_501() -> None:
    """Raise 501 unless the env flag is on. Permission deps already ran."""
    if _member_writes_enabled():  # pragma: no cover — Phase 1d implementation
        raise _http_error(
            500,
            "HAM_NOT_IMPLEMENTED",
            "Member writes are gated by HAM_WORKSPACE_MEMBER_WRITES; "
            "implementation lands in PR 1d.",
        )
    raise _http_error(
        501,
        "HAM_NOT_IMPLEMENTED",
        "Member writes are gated by HAM_WORKSPACE_MEMBER_WRITES; lands in PR 1d.",
    )


@router.post("/api/workspaces/{workspace_id}/members", status_code=501)
async def create_workspace_member(
    body: MemberWriteBody,  # noqa: ARG001 — accepted for OpenAPI completeness
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_MEMBER_WRITE))],  # noqa: ARG001
) -> dict[str, Any]:
    _maybe_501()
    return {}  # pragma: no cover — unreachable


@router.patch("/api/workspaces/{workspace_id}/members/{user_id}", status_code=501)
async def patch_workspace_member(
    user_id: str,  # noqa: ARG001
    body: MemberWriteBody,  # noqa: ARG001
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_MEMBER_WRITE))],  # noqa: ARG001
) -> dict[str, Any]:
    _maybe_501()
    return {}  # pragma: no cover — unreachable


@router.delete("/api/workspaces/{workspace_id}/members/{user_id}", status_code=501)
async def delete_workspace_member(
    user_id: str,  # noqa: ARG001
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_MEMBER_WRITE))],  # noqa: ARG001
) -> dict[str, Any]:
    _maybe_501()
    return {}  # pragma: no cover — unreachable


__all__ = ["router"]
