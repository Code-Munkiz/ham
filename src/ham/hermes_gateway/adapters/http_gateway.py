from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import httpx

_HEALTH_PATH = "/health"
_MODELS_PATH = "/v1/models"
_TIMEOUT_S = 6.0


def _base_url() -> str:
    return (os.environ.get("HERMES_GATEWAY_BASE_URL") or "").strip().rstrip("/")


def _auth_headers() -> dict[str, str]:
    key = (os.environ.get("HERMES_GATEWAY_API_KEY") or "").strip()
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}"}


def probe_hermes_http_gateway() -> dict[str, Any]:
    """
    Read-only probes: ``GET /health`` and optional ``GET /v1/models`` on HERMES_GATEWAY_BASE_URL.
    Never returns response bodies that could contain secrets; only structural hints.
    """
    base = _base_url()
    if not base:
        return {
            "status": "not_configured",
            "reachable": False,
            "health_http_status": None,
            "models_count_hint": None,
            "error": None,
            "bind_host_hint": None,
        }
    parsed = urlparse(base)
    host_hint = parsed.hostname or ""
    headers = _auth_headers()
    out: dict[str, Any] = {
        "status": "unknown",
        "reachable": False,
        "health_http_status": None,
        "models_count_hint": None,
        "error": None,
        "bind_host_hint": host_hint or None,
    }
    try:
        with httpx.Client(timeout=_TIMEOUT_S, follow_redirects=False) as client:
            r = client.get(f"{base}{_HEALTH_PATH}", headers=headers)
        out["health_http_status"] = r.status_code
        out["reachable"] = r.status_code < 500
        if r.status_code == 200:
            try:
                body = r.json()
                if isinstance(body, dict) and body.get("status") == "ok":
                    out["status"] = "healthy"
                else:
                    out["status"] = "degraded"
            except ValueError:
                out["status"] = "degraded"
        elif r.status_code in (401, 403):
            out["status"] = "auth_required"
            out["error"] = "Health check returned unauthorized; verify HERMES_GATEWAY_API_KEY on the API host."
        else:
            out["status"] = "degraded"
            out["error"] = f"HTTP {r.status_code} from /health"
    except httpx.RequestError as exc:
        out["status"] = "unreachable"
        out["error"] = str(exc)[:280]
        return out

    # Optional models stub count (no model ids forwarded — cosmetic upstream list).
    try:
        with httpx.Client(timeout=_TIMEOUT_S, follow_redirects=False) as client:
            m = client.get(f"{base}{_MODELS_PATH}", headers=headers)
        if m.status_code == 200:
            try:
                data = m.json()
                md = data.get("data") if isinstance(data, dict) else None
                if isinstance(md, list):
                    out["models_count_hint"] = len(md)
            except (ValueError, TypeError):
                pass
    except httpx.RequestError:
        pass

    return out
