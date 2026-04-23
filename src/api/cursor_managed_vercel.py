"""Server-side Vercel deployment list + match to a managed Cloud Agent mission (read-only, no webhooks)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.vercel_deploy_status import build_deploy_status_payload
from src.integrations.cursor_cloud_client import CursorCloudApiError, cursor_api_get_agent
from src.integrations.vercel_deployments_client import list_recent_deployments, vercel_api_configured
from src.persistence.cursor_credentials import get_effective_cursor_api_key

_LOG = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/cursor/managed",
    tags=["cursor-managed"],
    dependencies=[Depends(get_ham_clerk_actor)],
)


@router.get("/vercel/deploy-status")
async def get_vercel_managed_deploy_status(
    agent_id: str = Query(..., min_length=1, max_length=512, description="Cursor Cloud Agent id"),
) -> dict[str, Any]:
    """
    Poll Vercel Deployments API and return normalized status + match confidence for this mission.
    Requires Cursor API key (agent fetch) and Vercel token + project id on the server.
    """
    key = get_effective_cursor_api_key()
    if not key:
        raise HTTPException(
            status_code=400,
            detail="No Cursor API key configured. Set it in Settings or CURSOR_API_KEY.",
        )
    aid = agent_id.strip()
    try:
        agent = cursor_api_get_agent(api_key=key, agent_id=aid)
    except CursorCloudApiError as exc:
        _LOG.warning("cursor.managed.vercel.deploy_status.cursor_error", extra={"status": exc.status_code})
        if exc.status_code == 401:
            raise HTTPException(status_code=401, detail=str(exc) or "Cursor API rejected this API key.") from exc
        raise HTTPException(
            status_code=502,
            detail=str(exc) or "Cursor agent error",
        ) from exc
    if not isinstance(agent, dict):
        return build_deploy_status_payload(agent=None, deployments_list_json=None, not_configured=False)

    if not vercel_api_configured():
        return build_deploy_status_payload(
            not_configured=True,
            agent=agent,
            deployments_list_json=None,
        )

    try:
        deployments_json = list_recent_deployments(limit=30)
    except RuntimeError as exc:
        return build_deploy_status_payload(
            agent=agent,
            deployments_list_json=None,
            api_error=str(exc),
        )

    if deployments_json is None:
        return build_deploy_status_payload(
            not_configured=True,
            agent=agent,
            deployments_list_json=None,
        )

    return build_deploy_status_payload(
        agent=agent,
        deployments_list_json=deployments_json,
    )
