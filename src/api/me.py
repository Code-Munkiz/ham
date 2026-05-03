"""
``GET /api/me`` — caller identity + workspace summary (Phase 1b).

Behavior:

- Auth via :func:`require_actor`. In hosted mode this requires a Clerk JWT;
  in local-dev with the explicit bypass flag a synthetic actor is used.
- Best-effort idempotent mirror of ``users/{uid}``, ``orgs/{oid}``,
  ``memberships/{uid}__{oid}`` based on JWT claims. Mirror-write failures
  do **not** block the response (logged WARN).
- Returns workspace summaries the caller can access (org-fallback already
  handled by the Phase 1a store) plus a computed ``default_workspace_id``.
- ``auth_mode`` is ``"local_dev_bypass"`` when the synthetic actor is used,
  else ``"clerk"``.

Hard guarantees:

- No secret material returned (no token / api_key / access_token / refresh_token / secret keys).
- v1 endpoints not touched.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from src.api.dependencies.auth import require_actor
from src.api.dependencies.workspace import (
    LOCAL_DEV_USER_ID,
    get_workspace_store,
)
from src.ham.clerk_auth import HamActor
from src.ham.workspace_models import (
    MembershipRecord,
    OrgRecord,
    UserRecord,
    WorkspaceRecord,
)
from src.ham.workspace_perms import map_org_role_to_workspace_role
from src.ham.workspace_serializers import (
    pick_default_workspace_id,
    workspace_summary,
)
from src.persistence.workspace_store import WorkspaceStore

router = APIRouter(tags=["me"])
_LOG = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _is_local_dev_actor(actor: HamActor) -> bool:
    return actor.user_id == LOCAL_DEV_USER_ID and actor.raw_permission_claim == "local_dev_bypass"


def _mirror_user_org_membership(actor: HamActor, store: WorkspaceStore) -> None:
    """Best-effort idempotent mirror. Failure is logged and swallowed."""
    now = _utc_now()
    try:
        existing = store.get_user(actor.user_id)
        created_at = existing.created_at if existing else now
        store.upsert_user(
            UserRecord(
                user_id=actor.user_id,
                email=actor.email,
                display_name=existing.display_name if existing else None,
                photo_url=existing.photo_url if existing else None,
                primary_org_id=actor.org_id,
                created_at=created_at,
                last_seen_at=now,
            ),
        )
    except Exception:  # noqa: BLE001  # mirror is best-effort
        _LOG.warning("workspace mirror: upsert_user failed", exc_info=True)
    if actor.org_id:
        try:
            existing_org = store.get_org(actor.org_id)
            store.upsert_org(
                OrgRecord(
                    org_id=actor.org_id,
                    name=existing_org.name if existing_org else actor.org_id,
                    clerk_slug=existing_org.clerk_slug if existing_org else actor.org_id,
                    created_at=existing_org.created_at if existing_org else now,
                ),
            )
        except Exception:  # noqa: BLE001
            _LOG.warning("workspace mirror: upsert_org failed", exc_info=True)
        if actor.org_role:
            try:
                store.upsert_membership(
                    MembershipRecord(
                        user_id=actor.user_id,
                        org_id=actor.org_id,
                        org_role=actor.org_role,
                        joined_at=now,
                    ),
                )
            except Exception:  # noqa: BLE001
                _LOG.warning("workspace mirror: upsert_membership failed", exc_info=True)


def _user_dict(actor: HamActor, store: WorkspaceStore) -> dict[str, Any]:
    record = store.get_user(actor.user_id)
    return {
        "user_id": actor.user_id,
        "email": actor.email,
        "display_name": record.display_name if record else None,
        "photo_url": record.photo_url if record else None,
        "primary_org_id": actor.org_id,
    }


def _orgs_for_actor(actor: HamActor, store: WorkspaceStore) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for membership in store.list_memberships_for_user(actor.user_id):
        if membership.org_id in seen:
            continue
        seen.add(membership.org_id)
        org = store.get_org(membership.org_id)
        out.append(
            {
                "org_id": membership.org_id,
                "name": org.name if org else membership.org_id,
                "clerk_slug": org.clerk_slug if org else membership.org_id,
                "org_role": membership.org_role,
            },
        )
    if actor.org_id and actor.org_id not in seen:
        # Caller's current JWT mentions an org we haven't mirrored as a row yet
        # (mirror just failed or is brand-new). Surface it from the actor.
        org = store.get_org(actor.org_id)
        out.append(
            {
                "org_id": actor.org_id,
                "name": org.name if org else actor.org_id,
                "clerk_slug": org.clerk_slug if org else actor.org_id,
                "org_role": actor.org_role or "org:member",
            },
        )
    return out


def _role_for_workspace(
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


def _workspace_summaries(
    actor: HamActor,
    store: WorkspaceStore,
    *,
    org_id: str | None = None,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    records = store.list_workspaces_for_user(
        actor.user_id,
        org_id=org_id,
        include_archived=include_archived,
    )
    summaries: list[dict[str, Any]] = []
    for rec in records:
        role = _role_for_workspace(rec, actor, store)
        summaries.append(workspace_summary(rec, role=role))  # type: ignore[arg-type]
    return summaries


@router.get("/api/me")
async def get_me(
    actor: Annotated[HamActor, Depends(require_actor)],
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
) -> dict[str, Any]:
    """Caller identity + accessible workspace summaries."""
    _mirror_user_org_membership(actor, store)
    summaries = _workspace_summaries(actor, store)
    default_id = pick_default_workspace_id(summaries)
    for s in summaries:
        s["is_default"] = s["workspace_id"] == default_id
    return {
        "user": _user_dict(actor, store),
        "orgs": _orgs_for_actor(actor, store),
        "workspaces": summaries,
        "default_workspace_id": default_id,
        "auth_mode": "local_dev_bypass" if _is_local_dev_actor(actor) else "clerk",
    }


__all__ = ["router"]
