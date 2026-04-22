"""
Thin HTTP client for Cursor Cloud Agents API (Bearer auth only).

Endpoints used in slice 1:
- POST https://api.cursor.com/v0/agents
- GET  https://api.cursor.com/v0/agents/{id}

Payload shapes match the existing Ham proxy in ``src/api/cursor_settings.py`` (no speculative fields).
"""

from __future__ import annotations

from typing import Any

import httpx

CURSOR_API_BASE = "https://api.cursor.com"


class CursorCloudApiError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, body_excerpt: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body_excerpt = body_excerpt


def _excerpt(text: str, limit: int = 2000) -> str:
    t = (text or "").strip()
    return t[:limit] if len(t) > limit else t


def cursor_api_launch_agent(
    *,
    api_key: str,
    prompt_text: str,
    repository: str,
    ref: str | None,
    model: str,
    auto_create_pr: bool,
    branch_name: str | None,
) -> dict[str, Any]:
    """POST /v0/agents. Returns parsed JSON on success."""
    payload: dict[str, Any] = {
        "prompt": {"text": prompt_text},
        "source": {"repository": repository.strip()},
        "model": (model or "default").strip() or "default",
    }
    if ref and str(ref).strip():
        payload["source"]["ref"] = str(ref).strip()
    target: dict[str, Any] = {}
    if auto_create_pr:
        target["autoCreatePr"] = True
    if branch_name and str(branch_name).strip():
        target["branchName"] = str(branch_name).strip()
    if target:
        payload["target"] = target

    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            f"{CURSOR_API_BASE}/v0/agents",
            headers={
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    if resp.status_code == 401:
        raise CursorCloudApiError(
            "Cursor rejected this API key (401).",
            status_code=401,
            body_excerpt=_excerpt(resp.text),
        )
    if resp.status_code >= 400:
        raise CursorCloudApiError(
            f"Cursor launch error: HTTP {resp.status_code}",
            status_code=resp.status_code,
            body_excerpt=_excerpt(resp.text),
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise CursorCloudApiError("Cursor returned non-JSON", status_code=resp.status_code) from exc


def cursor_api_get_agent(*, api_key: str, agent_id: str) -> dict[str, Any]:
    """GET /v0/agents/{id}. Returns parsed JSON on success."""
    aid = agent_id.strip()
    if not aid:
        raise CursorCloudApiError("agent_id required", status_code=None)

    with httpx.Client(timeout=60.0) as client:
        resp = client.get(
            f"{CURSOR_API_BASE}/v0/agents/{aid}",
            headers={
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
            },
        )
    if resp.status_code == 401:
        raise CursorCloudApiError(
            "Cursor rejected this API key (401).",
            status_code=401,
            body_excerpt=_excerpt(resp.text),
        )
    if resp.status_code >= 400:
        raise CursorCloudApiError(
            f"Cursor agent error: HTTP {resp.status_code}",
            status_code=resp.status_code,
            body_excerpt=_excerpt(resp.text),
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise CursorCloudApiError("Cursor returned non-JSON", status_code=resp.status_code) from exc
