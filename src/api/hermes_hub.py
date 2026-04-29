"""Read-only Hermes-forward control plane snapshot for the dashboard hub.

Aggregates gateway truth from the model catalog builder and Hermes skills host probe.
For allowlisted read-only Hermes CLI inventory, see ``GET /api/hermes-runtime/inventory``.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.models_catalog import build_catalog_payload
from src.ham.hermes_skills_install import capability_extension_fields
from src.ham.hermes_skills_probe import probe_capabilities

router = APIRouter(tags=["hermes-hub"], dependencies=[Depends(get_ham_clerk_actor)])


def _skills_capabilities_snapshot() -> dict[str, Any]:
    """Same shape as GET /api/hermes-skills/capabilities (single source for hub + tests)."""
    caps = dict(probe_capabilities())
    ext = capability_extension_fields()
    caps["shared_runtime_install_supported"] = ext["shared_runtime_install_supported"]
    caps["skills_apply_writes_enabled"] = ext["skills_apply_writes_enabled"]
    caps["warnings"] = list(caps.get("warnings") or []) + list(
        ext.get("install_readiness_warnings") or [],
    )
    caps["kind"] = "hermes_skills_capabilities"
    return caps


def _dashboard_chat_summary(
    *,
    gateway_mode: str,
    openrouter_ready: bool,
    http_ready: bool,
) -> dict[str, Any]:
    gm = gateway_mode
    if gm == "mock":
        return {
            "active_upstream": "mock",
            "short_label": "Mock gateway",
            "summary": "Dashboard chat uses the built-in mock assistant (no external LLM).",
        }
    if gm == "openrouter":
        return {
            "active_upstream": "openrouter",
            "short_label": "OpenRouter",
            "summary": (
                "Dashboard chat uses OpenRouter (LiteLLM); upstream is ready for chat."
                if openrouter_ready
                else "Dashboard chat targets OpenRouter, but readiness failed (see /api/models OpenRouter rows for disabled_reason)."
            ),
        }
    if gm == "http":
        return {
            "active_upstream": "hermes_http",
            "short_label": "HTTP (Hermes-compatible)",
            "summary": (
                "Dashboard chat streams to HERMES_GATEWAY_BASE_URL (OpenAI-compatible SSE), "
                "typically the Hermes Agent API. Topology is separate from Hermes runtime skills "
                "install (co-location / remote_only)."
                if http_ready
                else "HERMES_GATEWAY_MODE=http but HERMES_GATEWAY_BASE_URL is missing or empty on the API host."
            ),
        }
    return {
        "active_upstream": gm,
        "short_label": gm,
        "summary": f"Gateway mode is {gm!r} (see HERMES_GATEWAY_MODE).",
    }


def build_hermes_hub_payload() -> dict[str, Any]:
    """Sync Hermes hub snapshot (shared by ``GET /api/hermes-hub`` and gateway broker)."""
    catalog = build_catalog_payload()
    gw = str(catalog["gateway_mode"])
    or_ready = bool(catalog["openrouter_chat_ready"])
    http_ready = bool(catalog.get("http_chat_ready", False))
    dash_ready = bool(catalog.get("dashboard_chat_ready", False))
    caps = _skills_capabilities_snapshot()
    return {
        "kind": "ham_hermes_control_plane_snapshot",
        "gateway_mode": gw,
        "openrouter_chat_ready": or_ready,
        "http_chat_ready": http_ready,
        "dashboard_chat_ready": dash_ready,
        "dashboard_chat": _dashboard_chat_summary(
            gateway_mode=gw,
            openrouter_ready=or_ready,
            http_ready=http_ready,
        ),
        "skills_capabilities": caps,
        "scope_notes": {
            "in_ham_today": [
                "Hermes runtime skills: vendored catalog, host capabilities probe, and (when co-located) shared install preview/apply under /api/hermes-skills/*",
                "Dashboard chat may use OpenRouter (HERMES_GATEWAY_MODE=openrouter) or HTTP/SSE to a Hermes-compatible endpoint (HERMES_GATEWAY_MODE=http); see docs/HERMES_GATEWAY_CONTRACT.md",
                "HAM workspace profiles (/workspace/profiles) — not Hermes CLI profiles",
            ],
            "not_in_ham_yet": [
                "No generic Hermes agent, session, or workflow inventory APIs in this repository",
                "Full Hermes runtime explorer / job browser is out of scope for this hub",
            ],
        },
    }


@router.get("/api/hermes-hub")
async def get_hermes_hub_snapshot() -> dict[str, Any]:
    """HAM-native snapshot: Hermes-related dashboard chat gateway + runtime skills probe only."""
    return build_hermes_hub_payload()
