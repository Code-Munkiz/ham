"""Dashboard endpoints for Cursor API key identity and team key rotation (server-side only).

Chat operator **Cursor Cloud Agent** launch/status uses Bearer auth via
``src/integrations/cursor_cloud_client.py``; the REST routes here still proxy with the
existing httpx auth style for backward compatibility.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException

from src.api.clerk_gate import get_ham_clerk_actor
from pydantic import BaseModel, Field

from src.persistence.cursor_credentials import (
    clear_saved_cursor_api_key,
    credentials_path_for_display,
    get_effective_cursor_api_key,
    key_source,
    mask_api_key_preview,
    save_cursor_api_key,
)

router = APIRouter(
    prefix="/api/cursor",
    tags=["cursor"],
    dependencies=[Depends(get_ham_clerk_actor)],
)


class CursorApiKeyBody(BaseModel):
    api_key: str = Field(min_length=1, max_length=4096)


class CursorFollowupBody(BaseModel):
    """Maps to Cursor `POST /v0/agents/{id}/followup`."""

    prompt_text: str = Field(min_length=1, max_length=100_000)


class LaunchCloudAgentBody(BaseModel):
    """Maps to Cursor Cloud Agents `POST /v0/agents` (minimal fields)."""

    prompt_text: str = Field(min_length=1, max_length=100_000)
    repository: str = Field(
        min_length=1,
        description="GitHub repo URL, e.g. https://github.com/org/repo",
    )
    ref: str | None = Field(default=None, description="Branch, tag, or commit (optional)")
    model: str = Field(
        default="default",
        description='Model id from GET /api/cursor/models or "default"',
    )
    auto_create_pr: bool = False
    branch_name: str | None = None


def _require_cursor_key() -> str:
    key = get_effective_cursor_api_key()
    if not key:
        raise HTTPException(
            status_code=400,
            detail="No Cursor API key configured. Set it in Settings or CURSOR_API_KEY.",
        )
    return key


def _cursor_get(path: str, *, api_key: str) -> httpx.Response:
    with httpx.Client(timeout=60.0) as client:
        return client.get(
            f"https://api.cursor.com{path}",
            auth=(api_key.strip(), ""),
        )


def _cursor_post(path: str, *, api_key: str, json_body: dict[str, Any]) -> httpx.Response:
    with httpx.Client(timeout=120.0) as client:
        return client.post(
            f"https://api.cursor.com{path}",
            auth=(api_key.strip(), ""),
            json=json_body,
        )


def _fetch_cursor_me(api_key: str) -> dict[str, Any]:
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(
            "https://api.cursor.com/v0/me",
            auth=(api_key.strip(), ""),
        )
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Cursor rejected this API key (401).")
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Cursor API error: HTTP {resp.status_code}",
        )
    return resp.json()


def _wired_for_payload() -> dict[str, Any]:
    """Truthful capability flags for dashboard (avoid implying chat uses Cursor without a bridge)."""
    return {
        "models_list": True,
        "cloud_agents_launch": True,
        "missions_cloud_agent": True,
        "ci_hooks": True,
        "ci_hooks_note": (
            "CI/scripts call Ham POST /api/cursor/agents/launch (Ham proxies to api.cursor.com/v0/agents)."
        ),
        "dashboard_chat_uses_cursor": False,
        "dashboard_chat_note": (
            "Ham chat uses HERMES_GATEWAY_MODE (openrouter/mock/http). "
            "Composer via Cursor is not a public REST chat completion on api.cursor.com; "
            "use OpenRouter here or add a Node SDK sidecar later."
        ),
    }


@router.get("/credentials-status")
async def credentials_status() -> dict[str, Any]:
    """
    Who this key belongs to (from GET https://api.cursor.com/v0/me).
    Never returns the full secret.
    """
    key = get_effective_cursor_api_key()
    src = key_source()
    base = {
        "storage_path": credentials_path_for_display(),
        "storage_override_env": (os.environ.get("HAM_CURSOR_CREDENTIALS_FILE") or "").strip()
        or None,
        "wired_for": _wired_for_payload(),
    }
    if not key:
        return {
            **base,
            "configured": False,
            "source": "none",
            "masked_preview": None,
            "api_key_name": None,
            "user_email": None,
            "key_created_at": None,
            "error": None,
        }

    try:
        me = _fetch_cursor_me(key)
    except HTTPException as exc:
        return {
            **base,
            "configured": True,
            "source": src,
            "masked_preview": mask_api_key_preview(key),
            "api_key_name": None,
            "user_email": None,
            "key_created_at": None,
            "error": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        }
    except httpx.RequestError as exc:
        return {
            **base,
            "configured": True,
            "source": src,
            "masked_preview": mask_api_key_preview(key),
            "api_key_name": None,
            "user_email": None,
            "key_created_at": None,
            "error": f"Network error calling Cursor: {exc}",
        }

    return {
        **base,
        "configured": True,
        "source": src,
        "masked_preview": mask_api_key_preview(key),
        "api_key_name": me.get("apiKeyName"),
        "user_email": me.get("userEmail"),
        "key_created_at": me.get("createdAt"),
        "error": None,
    }


@router.post("/credentials", status_code=204)
async def set_credentials(body: CursorApiKeyBody) -> None:
    """Persist a new key for all HAM API users (shared internal deployments)."""
    key = body.api_key.strip()
    try:
        _fetch_cursor_me(key)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach Cursor to verify key: {exc}",
        ) from exc

    try:
        save_cursor_api_key(key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/credentials", status_code=204)
async def delete_credentials() -> None:
    """Remove UI-saved key; effective key falls back to CURSOR_API_KEY env if set."""
    clear_saved_cursor_api_key()


@router.get("/models")
async def cursor_models() -> dict[str, Any]:
    """Proxy to Cursor `GET /v0/models` using the effective team key (same as Cloud Agents API)."""
    key = _require_cursor_key()
    resp = _cursor_get("/v0/models", api_key=key)
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Cursor rejected this API key (401).")
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Cursor models error: HTTP {resp.status_code}",
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Cursor returned non-JSON") from exc


@router.post("/agents/launch")
async def cursor_launch_agent(body: LaunchCloudAgentBody) -> dict[str, Any]:
    """
    Launch a Cursor Cloud Agent (`POST https://api.cursor.com/v0/agents`) using the stored key.

    Use from CI/scripts: POST this Ham endpoint with JSON (Ham shape); Ham forwards to Cursor.
    """
    key = _require_cursor_key()
    payload: dict[str, Any] = {
        "prompt": {"text": body.prompt_text},
        "source": {"repository": body.repository.strip()},
        "model": body.model.strip() or "default",
    }
    if body.ref:
        payload["source"]["ref"] = body.ref.strip()
    target: dict[str, Any] = {}
    if body.auto_create_pr:
        target["autoCreatePr"] = True
    if body.branch_name:
        target["branchName"] = body.branch_name.strip()
    if target:
        payload["target"] = target

    resp = _cursor_post("/v0/agents", api_key=key, json_body=payload)
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Cursor rejected this API key (401).")
    if resp.status_code >= 400:
        detail = resp.text[:2000] if resp.text else f"HTTP {resp.status_code}"
        raise HTTPException(status_code=502, detail=f"Cursor launch error: {detail}")
    try:
        return resp.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Cursor returned non-JSON") from exc


def _cursor_proxy_error(resp: httpx.Response, prefix: str) -> HTTPException:
    detail = resp.text[:2000] if resp.text else f"HTTP {resp.status_code}"
    return HTTPException(status_code=502, detail=f"{prefix}: {detail}")


@router.get("/agents/{agent_id}")
async def cursor_get_agent(agent_id: str) -> dict[str, Any]:
    """Proxy `GET https://api.cursor.com/v0/agents/{id}` (status, summary, source, target)."""
    key = _require_cursor_key()
    aid = agent_id.strip()
    if not aid:
        raise HTTPException(status_code=422, detail="agent_id required")
    resp = _cursor_get(f"/v0/agents/{aid}", api_key=key)
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Cursor rejected this API key (401).")
    if resp.status_code >= 400:
        raise _cursor_proxy_error(resp, "Cursor agent error")
    try:
        return resp.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Cursor returned non-JSON") from exc


@router.get("/agents/{agent_id}/conversation")
async def cursor_get_agent_conversation(agent_id: str) -> dict[str, Any]:
    """Proxy `GET https://api.cursor.com/v0/agents/{id}/conversation`."""
    key = _require_cursor_key()
    aid = agent_id.strip()
    if not aid:
        raise HTTPException(status_code=422, detail="agent_id required")
    resp = _cursor_get(f"/v0/agents/{aid}/conversation", api_key=key)
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Cursor rejected this API key (401).")
    if resp.status_code >= 400:
        raise _cursor_proxy_error(resp, "Cursor conversation error")
    try:
        return resp.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Cursor returned non-JSON") from exc


@router.post("/agents/{agent_id}/followup")
async def cursor_post_agent_followup(agent_id: str, body: CursorFollowupBody) -> dict[str, Any]:
    """Proxy `POST https://api.cursor.com/v0/agents/{id}/followup`."""
    key = _require_cursor_key()
    aid = agent_id.strip()
    if not aid:
        raise HTTPException(status_code=422, detail="agent_id required")
    payload: dict[str, Any] = {"prompt": {"text": body.prompt_text.strip()}}
    resp = _cursor_post(f"/v0/agents/{aid}/followup", api_key=key, json_body=payload)
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Cursor rejected this API key (401).")
    if resp.status_code >= 400:
        raise _cursor_proxy_error(resp, "Cursor followup error")
    try:
        return resp.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Cursor returned non-JSON") from exc
