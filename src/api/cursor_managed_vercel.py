"""Server-side Vercel deployment list + match to a managed Cloud Agent mission (read-only, no webhooks)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.post_deploy_validation import run_post_deploy_probe
from src.ham.vercel_deploy_status import build_deploy_status_payload, compute_matched_deployment_view
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


@router.get("/vercel/post-deploy-validation")
async def get_vercel_post_deploy_validation(
    agent_id: str = Query(..., min_length=1, max_length=512, description="Cursor Cloud Agent id"),
    force: bool = Query(False, description="When true, run the probe even if deploy match confidence is not high"),
) -> dict[str, Any]:
    """
    Server-side HTTP probe of the deployment URL derived from the matched Vercel deployment only.
    """
    force_bool = bool(force)
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
        if exc.status_code == 401:
            raise HTTPException(status_code=401, detail=str(exc) or "Cursor API rejected this API key.") from exc
        raise HTTPException(status_code=502, detail=str(exc) or "Cursor agent error") from exc
    if not isinstance(agent, dict):
        return {
            "deploy_ref": None,
            "post_deploy_validation": {
                "state": "not_attempted",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "url_probed": None,
                "http_status": None,
                "match_confidence": None,
                "reason_code": "no_agent",
                "message": "No agent payload from Cursor.",
            },
        }

    if not vercel_api_configured():
        return {
            "deploy_ref": None,
            "post_deploy_validation": {
                "state": "not_attempted",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "url_probed": None,
                "http_status": None,
                "match_confidence": None,
                "reason_code": "vercel_not_configured",
                "message": "Vercel API token and project id are not both configured; cannot match a deployment to probe.",
            },
        }

    try:
        deployments_json = list_recent_deployments(limit=30)
    except RuntimeError as exc:
        return {
            "deploy_ref": None,
            "post_deploy_validation": {
                "state": "not_attempted",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "url_probed": None,
                "http_status": None,
                "match_confidence": None,
                "reason_code": "vercel_list_error",
                "message": f"Could not list deployments: {exc}",
            },
        }

    if deployments_json is None:
        return {
            "deploy_ref": None,
            "post_deploy_validation": {
                "state": "not_attempted",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "url_probed": None,
                "http_status": None,
                "match_confidence": None,
                "reason_code": "vercel_not_configured",
                "message": "Vercel is not configured for deployment matching.",
            },
        }

    view = compute_matched_deployment_view(agent=agent, deployments_list_json=deployments_json)
    if not view:
        return {
            "deploy_ref": None,
            "post_deploy_validation": {
                "state": "not_attempted",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "url_probed": None,
                "http_status": None,
                "match_confidence": None,
                "reason_code": "no_matched_deployment",
                "message": "No Vercel deployment could be matched to this mission; nothing to validate.",
            },
        }

    dep = view.get("dep")
    if not isinstance(dep, dict):
        return {
            "deploy_ref": None,
            "post_deploy_validation": {
                "state": "not_attempted",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "url_probed": None,
                "http_status": None,
                "match_confidence": None,
                "reason_code": "internal",
                "message": "Invalid deployment object.",
            },
        }

    match_conf = view.get("match_confidence")
    mc = match_conf if match_conf in ("high", "medium", "low") else None
    vurl = view.get("url")
    durl = vurl if isinstance(vurl, str) else None

    deploy_ref = {
        "state": str(view.get("state") or ""),
        "match_confidence": mc,
        "match_reason": view.get("match_reason"),
        "deployment": {
            "url": durl,
            "vercel_state": view.get("vercel_state"),
        },
    }
    out = run_post_deploy_probe(
        dep=dep,
        match_confidence=mc,
        force_attempt=force_bool,
    )
    return {"deploy_ref": deploy_ref, "post_deploy_validation": out}
