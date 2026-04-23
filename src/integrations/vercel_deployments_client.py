"""
Server-side Vercel REST: list recent deployments for a project.

Read-only. Token from env. Do not import from the browser.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

_LOG = logging.getLogger(__name__)

VERCEL_API_BASE = (os.environ.get("HAM_VERCEL_API_BASE") or "https://api.vercel.com").rstrip("/")


def _vercel_token() -> str | None:
    return (os.environ.get("HAM_VERCEL_API_TOKEN") or os.environ.get("VERCEL_API_TOKEN") or "").strip() or None


def _vercel_project_id() -> str | None:
    return (os.environ.get("HAM_VERCEL_PROJECT_ID") or os.environ.get("VERCEL_PROJECT_ID") or "").strip() or None


def _vercel_team_id() -> str | None:
    return (os.environ.get("HAM_VERCEL_TEAM_ID") or os.environ.get("VERCEL_TEAM_ID") or "").strip() or None


def vercel_token_configured() -> bool:
    return bool(_vercel_token())


def vercel_api_configured() -> bool:
    """True when HAM can call Vercel with the global project id (legacy; prefer per-repo resolution + token)."""
    return bool(_vercel_token() and _vercel_project_id())


def list_recent_deployments(
    *,
    project_id: str,
    team_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any] | None:
    """
    GET /v6/deployments for the given Vercel project (and team if set).

    Returns parsed JSON (expects `deployments` key) or None if not configured.
    Returns None if token is missing. Raises on HTTP !2xx (caller maps to API error state).
    """
    token = _vercel_token()
    if not token or not (project_id or "").strip():
        return None
    pid = project_id.strip()
    team = (team_id or "").strip() or None
    if team is None:
        team = _vercel_team_id()

    params: dict[str, str] = {
        "projectId": pid,
        "limit": str(max(1, min(limit, 50))),
    }
    if team:
        params["teamId"] = team

    with httpx.Client(timeout=45.0) as client:
        resp = client.get(
            f"{VERCEL_API_BASE}/v6/deployments",
            headers={"Authorization": f"Bearer {token}"},
            params=params,  # type: ignore[arg-type]
        )
    if resp.status_code == 401:
        _LOG.warning("vercel.deployments_list.unauthorized")
        msg = f"Vercel API rejected token (HTTP {resp.status_code})"
        raise RuntimeError(msg)
    if resp.status_code == 404:
        _LOG.warning("vercel.deployments_list.not_found", extra={"body_preview": (resp.text or "")[:300]})
        raise RuntimeError(f"Vercel project or team not found (HTTP {resp.status_code})")
    if resp.status_code >= 400:
        _LOG.warning(
            "vercel.deployments_list.error",
            extra={"status": resp.status_code, "body_preview": (resp.text or "")[:500]},
        )
        raise RuntimeError(f"Vercel list deployments error: HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise RuntimeError("Vercel returned non-JSON for deployments list") from exc
