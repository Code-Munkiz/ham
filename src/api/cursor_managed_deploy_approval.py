"""Managed Cloud Agent **deploy hook** approval: policy + record (operator-first; default non-blocking)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor
from src.ham.managed_deploy_approval_policy import (
    deploy_hook_allowed_in_policy_mode,
    managed_deploy_approval_mode,
)
from src.persistence.control_plane_run import utc_now_iso
from src.persistence.managed_deploy_approval import (
    ApprovalActor,
    ManagedDeployApproval,
    ManagedDeployApprovalStore,
    new_approval_id,
)
from src.persistence.managed_mission import ManagedMissionStore

_store = ManagedDeployApprovalStore()
_mission_store = ManagedMissionStore()

router = APIRouter(
    prefix="/api/cursor/managed",
    tags=["cursor-managed-deploy-approval"],
)


def _public_approval(a: ManagedDeployApproval) -> dict[str, Any]:
    d: dict[str, Any] = a.model_dump(mode="json", exclude_none=False)
    d["kind"] = "managed_deploy_approval"
    return d


@router.get("/deploy-approval")
async def get_managed_deploy_approval(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    agent_id: str = Query(..., min_length=1, max_length=512, description="Cursor Cloud Agent id"),
) -> dict[str, Any]:
    policy = managed_deploy_approval_mode()
    aid = agent_id.strip()
    latest = _store.latest_for_cursor_agent_id(aid)
    mission: str | None = None
    m = _mission_store.find_by_cursor_agent_id(aid)
    if m is not None:
        mission = m.mission_registry_id
    allowed = deploy_hook_allowed_in_policy_mode(policy, latest)
    return {
        "kind": "managed_deploy_approval_status",
        "policy": policy,
        "mission_registry_id": mission,
        "latest_approval": _public_approval(latest) if latest else None,
        "deploy_hook_would_allow": bool(allowed),
    }


class PostManagedDeployApprovalBody(BaseModel):
    """Record an operator decision (all modes are non-blocking except **hard** on the deploy route)."""

    agent_id: str = Field(min_length=1, max_length=512)
    state: Literal["approved", "denied"] = Field(description="Most recent decision wins for **hard** policy.")
    mission_registry_id: str | None = Field(default=None, description="Optional; resolved from mission store when omitted.")
    note: str | None = None
    override: bool = False
    override_justification: str | None = None
    source: Literal["operator_ui", "api", "script"] = "operator_ui"
    inputs_summary: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _override_just(self) -> PostManagedDeployApprovalBody:
        if self.override and not (self.override_justification or "").strip():
            raise ValueError("override_justification is required when override is true")
        return self


def _actor_payload(actor: HamActor | None) -> ApprovalActor | None:
    if actor is None:
        return None
    return ApprovalActor(
        kind="clerk",
        user_id=actor.user_id,
        email=actor.email,
    )


@router.post("/deploy-approval")
async def post_managed_deploy_approval(
    body: PostManagedDeployApprovalBody,
    actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    now = utc_now_iso()
    aid = body.agent_id.strip()
    mid = (body.mission_registry_id or "").strip() or None
    if not mid:
        m = _mission_store.find_by_cursor_agent_id(aid)
        if m is not None:
            mid = m.mission_registry_id

    row = ManagedDeployApproval(
        approval_id=new_approval_id(),
        mission_registry_id=mid,
        cursor_agent_id=aid,
        state=body.state,
        decision_at=now,
        actor=_actor_payload(actor),
        source=body.source,
        note=body.note,
        override=body.override,
        override_justification=body.override_justification,
        inputs_summary=body.inputs_summary,
    )
    _store.save(row)
    return {
        "kind": "managed_deploy_approval_result",
        "approval": _public_approval(row),
    }
