"""
Hermes gateway broker API — backend-mediated command center snapshot (Path B).

Read-only GET routes; no arbitrary shell or Hermes control from the browser.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.hermes_gateway.broker import default_broker
from src.ham.hermes_gateway.dto import GATEWAY_SNAPSHOT_SCHEMA_VERSION

router = APIRouter(tags=["hermes-gateway"], dependencies=[Depends(get_ham_clerk_actor)])


def _sse_interval_s() -> float:
    raw = (os.environ.get("HAM_HERMES_GATEWAY_SSE_INTERVAL_S") or "").strip()
    if not raw:
        return 20.0
    try:
        return max(5.0, min(120.0, float(raw)))
    except ValueError:
        return 20.0


@router.get("/api/hermes-gateway/snapshot")
async def get_hermes_gateway_snapshot(
    project_id: str | None = Query(
        default=None,
        max_length=180,
        description="Optional HAM project id for control-plane run summaries.",
    ),
    refresh: bool = Query(
        default=False,
        description="When true, bypass TTL cache for this request.",
    ),
) -> dict[str, Any]:
    return default_broker().build_snapshot(
        project_id=project_id,
        force_refresh=refresh,
    )


@router.get("/api/hermes-gateway/capabilities")
async def get_hermes_gateway_capabilities() -> dict[str, Any]:
    return {
        "kind": "ham_hermes_gateway_capabilities",
        "schema_version": GATEWAY_SNAPSHOT_SCHEMA_VERSION,
        "snapshot": {
            "method": "GET",
            "path": "/api/hermes-gateway/snapshot",
            "query": ["project_id (optional)", "refresh (optional bool)"],
        },
        "stream": {
            "method": "GET",
            "path": "/api/hermes-gateway/stream",
            "format": "text/event-stream",
            "note": "Lightweight ticks; full data via snapshot. Interval from HAM_HERMES_GATEWAY_SSE_INTERVAL_S (default 20s).",
        },
        "hermes_agent_v0_8_0_surfaces": {
            "verified_rest": [
                "GET /health",
                "GET /v1/models (stub list)",
                "POST /v1/chat/completions (+ SSE when streaming)",
                "GET /v1/runs/{id}/events (SSE)",
                "/api/jobs (CRUD + run/pause/resume)",
            ],
            "not_available_for_dashboard": [
                "JSON-RPC",
                "WebSocket menu/control",
                "REST slash-command or live TUI menu discovery",
            ],
            "cli_config_discovery": [
                "hermes tools --summary",
                "hermes plugins list",
                "hermes mcp list",
                "hermes skills list (via /api/hermes-skills/installed)",
            ],
        },
        "security": [
            "No secrets or raw env in snapshot responses.",
            "raw_redacted CLI captures omitted from snapshot; use dedicated allowlisted routes if needed.",
            "HTTP probes use server-side HERMES_GATEWAY_* only.",
        ],
    }


@router.get("/api/hermes-gateway/stream")
async def stream_hermes_gateway_ticks(
    project_id: str | None = Query(default=None, max_length=180),
) -> StreamingResponse:
    broker = default_broker()
    interval = _sse_interval_s()

    async def event_gen():
        while True:
            snap = broker.build_snapshot(project_id=project_id, force_refresh=False)
            tick = {
                "kind": "ham_hermes_gateway_stream_tick",
                "schema_version": snap.get("schema_version"),
                "captured_at": snap.get("captured_at"),
                "gateway_mode": (snap.get("hermes_hub") or {}).get("gateway_mode"),
                "degraded_capabilities": snap.get("degraded_capabilities"),
                "warnings_count": len(snap.get("warnings") or []),
                "freshness": snap.get("freshness"),
            }
            yield f"data: {json.dumps(tick, default=str)}\n\n"
            await asyncio.sleep(interval)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
