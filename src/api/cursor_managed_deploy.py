"""Narrow HAM-only deploy handoff: POST to a Vercel Deploy Hook URL (server env only). No Cursor forward."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.vercel_project_mapping import (
    resolve_vercel_hook_for_agent,
    vercel_hook_resolution_to_dict,
)
from src.integrations.cursor_cloud_client import CursorCloudApiError, cursor_api_get_agent
from src.persistence.cursor_credentials import get_effective_cursor_api_key

_LOG = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/cursor/managed",
    tags=["cursor-managed"],
    dependencies=[Depends(get_ham_clerk_actor)],
)


def _vercel_deploy_hook_url() -> str | None:
    u = (os.environ.get("HAM_VERCEL_DEPLOY_HOOK_URL") or os.environ.get("VERCEL_DEPLOY_HOOK_URL") or "").strip()
    return u or None


@router.get("/deploy-hook")
async def deploy_hook_status(
    agent_id: str | None = Query(None, max_length=512, description="When set, resolve hook for this agent's repo (managed)."),
) -> dict[str, Any]:
    """
    Whether a deploy hook is available. Without agent_id, reports global HAM_VERCEL_DEPLOY_HOOK_URL only (legacy).
    With agent_id, uses per-repo map + global fallback per HAM policy (never returns the secret).
    """
    if not (agent_id or "").strip():
        g = _vercel_deploy_hook_url() is not None
        return {"configured": g}

    key = get_effective_cursor_api_key()
    if not key:
        return {
            "configured": False,
            "vercel_mapping": {
                "repo_key": None,
                "mapping_tier": "unavailable",
                "hook_configured": False,
                "deploy_hook_env_name": None,
                "used_global_hook_fallback": False,
                "fail_closed": True,
                "message": "No Cursor API key configured; cannot load agent to resolve per-repo deploy hook.",
                "map_load_error": None,
            },
        }
    try:
        agent = cursor_api_get_agent(api_key=key, agent_id=agent_id.strip())
    except CursorCloudApiError as exc:
        raise HTTPException(
            status_code=401 if exc.status_code == 401 else 502,
            detail=str(exc) or "Cursor agent error",
        ) from exc
    hres = resolve_vercel_hook_for_agent(agent if isinstance(agent, dict) else None)
    vm = vercel_hook_resolution_to_dict(hres)
    return {"configured": hres.hook_configured, "vercel_mapping": vm}


class TriggerDeployHookBody(BaseModel):
    """Optional audit key; hook URL is resolved from per-repo map + global policy."""
    agent_id: str = Field(min_length=1, max_length=512)


@router.post("/deploy-hook")
async def trigger_vercel_deploy_hook(body: TriggerDeployHookBody) -> dict[str, Any]:
    """
    POST to the resolved Vercel Deploy Hook. Does not poll deployment status; does not forward to Cursor.
    """
    key = get_effective_cursor_api_key()
    if not key:
        raise HTTPException(
            status_code=400,
            detail="No Cursor API key configured. Set it in Settings or CURSOR_API_KEY.",
        )
    try:
        agent = cursor_api_get_agent(api_key=key, agent_id=body.agent_id.strip())
    except CursorCloudApiError as exc:
        if exc.status_code == 401:
            raise HTTPException(status_code=401, detail=str(exc) or "Cursor API rejected this API key.") from exc
        raise HTTPException(status_code=502, detail=str(exc) or "Cursor agent error") from exc
    if not isinstance(agent, dict):
        return {
            "ok": False,
            "outcome": "no_agent",
            "message": "No agent payload from Cursor; cannot resolve deploy hook.",
        }

    hres = resolve_vercel_hook_for_agent(agent)
    url = hres.hook_url
    if not url:
        _LOG.warning("cursor.managed.deploy_hook.unresolved", extra={"agent_id": body.agent_id.strip()})
        return {
            "ok": False,
            "outcome": "hook_unavailable",
            "message": hres.message,
            "vercel_mapping": vercel_hook_resolution_to_dict(hres),
        }
    _LOG.info(
        "cursor.managed.deploy_hook.request",
        extra={
            "agent_id": body.agent_id.strip(),
            "hook_resolved": True,
            "mapping_tier": hres.mapping_tier,
        },
    )
    try:
        with httpx.Client(timeout=45.0) as client:
            resp = client.post(url)
    except httpx.RequestError as exc:
        _LOG.warning("cursor.managed.deploy_hook.request_error", extra={"err": str(exc)})
        return {
            "ok": False,
            "outcome": "hook_request_failed",
            "message": f"Request to deploy hook failed: {exc}",
            "vercel_mapping": vercel_hook_resolution_to_dict(hres),
        }
    if 200 <= resp.status_code < 300:
        return {
            "ok": True,
            "outcome": "hook_request_accepted",
            "message": "Deploy hook request was accepted (HTTP 2xx). Check Vercel for build and deployment output.",
            "status_code": resp.status_code,
            "vercel_mapping": vercel_hook_resolution_to_dict(hres),
        }
    _LOG.warning(
        "cursor.managed.deploy_hook.bad_status",
        extra={"status_code": resp.status_code, "body_preview": (resp.text or "")[:500]},
    )
    return {
        "ok": False,
        "outcome": "hook_request_rejected",
        "message": f"Deploy hook returned HTTP {resp.status_code}. This does not confirm a successful build—check Vercel.",
        "status_code": resp.status_code,
        "vercel_mapping": vercel_hook_resolution_to_dict(hres),
    }
