"""Phase 2 — Plan approval gate API (Contract 2).

GET  /api/plans/<plan_id>           — fetch Plan + approval record
POST /api/plans/<plan_id>/approve   — approval gate → CloudRuntimeJob + enqueue

Spec: docs/PHASE_0_CONTRACTS.md § Contract 2
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.builder_plan import Plan, PlanApprovalRecord
from src.ham.builder_plan_approval_service import ApprovePlanError, approve_plan
from src.ham.clerk_auth import HamActor
from src.persistence.builder_plan_store import get_builder_plan_store

router = APIRouter(tags=["builder-plans"])


class PlanDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: Plan
    approval: PlanApprovalRecord


class ApprovePlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    job_id: str
    approval_state: str


@router.get("/api/plans/{plan_id}")
def get_plan_detail(
    plan_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> PlanDetailResponse:
    store = get_builder_plan_store()
    plan = store.get_plan(plan_id=plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "plan_not_found"}})
    approval = store.get_approval_record(plan_id=plan_id)
    if approval is None:
        from datetime import UTC, datetime

        approval = PlanApprovalRecord(
            plan_id=plan_id,
            state="proposed",
            proposed_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
    return PlanDetailResponse(plan=plan, approval=approval)


@router.post("/api/plans/{plan_id}/approve", status_code=202)
def post_approve_plan(
    plan_id: str,
    actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> ApprovePlanResponse:
    requested_by = actor.user_id if actor is not None else "anonymous"
    try:
        result = approve_plan(plan_id=plan_id, requested_by=requested_by)
    except ApprovePlanError as exc:
        if exc.code == "not_found":
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "plan_not_found", "message": exc.message}},
            ) from exc
        if exc.code == "plan_stale":
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "plan_stale",
                        "message": exc.message,
                        "details": exc.details or {},
                    }
                },
            ) from exc
        if exc.code == "project_busy":
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "project_busy",
                        "message": exc.message,
                        "details": exc.details or {},
                    }
                },
            ) from exc
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details or {},
                }
            },
        ) from exc
    return ApprovePlanResponse(
        plan_id=result.plan_id,
        job_id=result.job_id,
        approval_state=result.approval_state,
    )
