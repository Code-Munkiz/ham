"""Narrow HAM-only deploy handoff: POST to a Vercel Deploy Hook URL (server env only). No Cursor forward."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.clerk_gate import get_ham_clerk_actor

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
async def deploy_hook_status() -> dict[str, Any]:
    """Whether a deploy hook URL is configured (never return the secret)."""
    return {"configured": _vercel_deploy_hook_url() is not None}


class TriggerDeployHookBody(BaseModel):
    """Optional audit key; the hook URL is not selected per request."""
    agent_id: str = Field(min_length=1, max_length=512)


@router.post("/deploy-hook")
async def trigger_vercel_deploy_hook(body: TriggerDeployHookBody) -> dict[str, Any]:
    """
    POST to the configured Vercel Deploy Hook. Does not poll deployment status; does not forward to Cursor.
    """
    url = _vercel_deploy_hook_url()
    if not url:
        raise HTTPException(
            status_code=503,
            detail="Deploy hook is not configured. Set HAM_VERCEL_DEPLOY_HOOK_URL (or VERCEL_DEPLOY_HOOK_URL) on the API host.",
        )
    _LOG.info(
        "cursor.managed.deploy_hook.request",
        extra={"agent_id": body.agent_id.strip(), "hook_configured": True},
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
        }
    if 200 <= resp.status_code < 300:
        return {
            "ok": True,
            "outcome": "hook_request_accepted",
            "message": "Deploy hook request was accepted (HTTP 2xx). Check Vercel for build and deployment output.",
            "status_code": resp.status_code,
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
    }
