"""OpenCode build router — Mission 1 disabled launch shim.

Sibling of :mod:`src.api.claude_agent_build`. Mission 1 only exposes a
single ``POST /api/opencode/build/launch`` route that always returns
HTTP 503 with ``detail.reason="opencode:not_implemented"``. The route
calls :func:`launch_opencode_coding` purely so the in-process facade is
exercised by the route layer; it never invokes the OpenCode CLI and
never persists a ``ControlPlaneRun`` row.

Live execution lands in Mission 2; see ``docs/OPENCODE_PROVIDER.md``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor
from src.ham.coding_router.opencode_provider import launch_opencode_coding

router = APIRouter(
    prefix="/api/opencode",
    tags=["opencode"],
    dependencies=[Depends(get_ham_clerk_actor)],
)


class OpenCodeBuildLaunchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = Field(default=None, max_length=180)
    user_prompt: str | None = Field(default=None, max_length=12_000)


@router.post("/build/launch")
async def launch_opencode_build(
    body: OpenCodeBuildLaunchBody | None = None,
    ham_actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    """Always returns HTTP 503 in Mission 1; no execution path.

    The route calls into the in-process facade so that the disabled-shim
    contract is exercised end-to-end. The facade never invokes the
    OpenCode CLI; this route raises HTTPException(503) regardless of the
    facade outcome.
    """
    body = body or OpenCodeBuildLaunchBody()
    result = launch_opencode_coding(
        project_id=body.project_id,
        user_prompt=body.user_prompt,
        actor=ham_actor,
    )
    raise HTTPException(
        status_code=503,
        detail={
            "error": {
                "code": "OPENCODE_NOT_IMPLEMENTED",
                "message": "OpenCode live execution is not yet implemented on this host.",
            },
            "status": result.status,
            "reason": result.reason,
            "summary": result.summary,
        },
    )


__all__ = ["router"]
