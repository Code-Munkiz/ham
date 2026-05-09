"""Per-user per-workspace chat composer model preference (HAM catalog id only)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.api.dependencies.workspace import get_workspace_store, require_perm
from src.ham.workspace_perms import PERM_WORKSPACE_READ
from src.ham.chat_composer_preference import (
    PreferencePutOutcome,
    effective_chat_model_id_for_actor,
    resolve_preference_put,
)
from src.ham.clerk_auth import HamActor
from src.ham.workspace_models import WorkspaceContext
from src.persistence.chat_composer_preference_store import (
    build_chat_composer_preference_store,
    preference_scope_key,
)
from src.persistence.workspace_store import WorkspaceStore

router = APIRouter(tags=["workspace-chat-preference"])

_PREF_STORE = build_chat_composer_preference_store()
_SCHEMA_VERSION = 1


class ChatComposerPreferencePut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str | None = Field(default=None, max_length=256)


def _raw_from_store(actor: HamActor, workspace_id: str) -> str | None:
    key = preference_scope_key(user_id=actor.user_id, workspace_id=workspace_id)
    blob = _PREF_STORE.get_raw(key)
    if not blob:
        return None
    mid = blob.get("model_id")
    if mid is None:
        return None
    s = str(mid).strip()
    return s or None


def _put_store(actor: HamActor, workspace_id: str, model_id: str | None) -> None:
    key = preference_scope_key(user_id=actor.user_id, workspace_id=workspace_id)
    payload: dict[str, Any] = {"schema_version": _SCHEMA_VERSION}
    if model_id is None:
        payload["model_id"] = None
    else:
        payload["model_id"] = str(model_id).strip()
    _PREF_STORE.put_raw(key, payload)


def _http_from_outcome(o: PreferencePutOutcome) -> dict[str, Any]:
    if o.http_status is not None and o.error_code:
        raise HTTPException(
            status_code=o.http_status,
            detail={
                "error": {
                    "code": o.error_code,
                    "message": o.error_message or o.error_code,
                },
            },
        )
    body: dict[str, Any] = {
        "kind": "ham_chat_composer_preference",
        "model_id": o.persist_id,
        "cleared": o.cleared,
    }
    return body


@router.get("/api/workspaces/{workspace_id}/chat-composer-preference")
async def get_chat_composer_preference(
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
) -> dict[str, Any]:
    """Effective model_id for UI (None = Hermes default). Read-only — does not mutate storage."""
    _ = store
    actor = HamActor(
        user_id=ctx.actor_user_id,
        org_id=ctx.org_id,
        session_id=None,
        email=ctx.actor_email,
        permissions=frozenset(ctx.perms),
        org_role=ctx.org_role,
        raw_permission_claim=None,
    )
    raw = _raw_from_store(actor, ctx.workspace_id)
    effective = effective_chat_model_id_for_actor(ham_actor=actor, raw_model_id=raw)
    return {
        "kind": "ham_chat_composer_preference",
        "model_id": effective,
    }


@router.put("/api/workspaces/{workspace_id}/chat-composer-preference")
async def put_chat_composer_preference(
    body: ChatComposerPreferencePut,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
) -> dict[str, Any]:
    _ = store
    actor = HamActor(
        user_id=ctx.actor_user_id,
        org_id=ctx.org_id,
        session_id=None,
        email=ctx.actor_email,
        permissions=frozenset(ctx.perms),
        org_role=ctx.org_role,
        raw_permission_claim=None,
    )
    outcome = resolve_preference_put(ham_actor=actor, raw_model_id=body.model_id)
    resp = _http_from_outcome(outcome)
    _put_store(actor, ctx.workspace_id, outcome.persist_id)
    return resp
